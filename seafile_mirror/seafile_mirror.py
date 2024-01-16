#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2023 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Handle clean read-only (re-)syncs of Seafile libraries to mirror them"""

import argparse
import logging
import shutil
from pathlib import Path
from time import sleep

import yaml

from . import __version__
from ._cachedb import db_read
from ._helpers import convert_bytes, findstring, get_lock
from ._seafile import (
    sf_bump_cache_status,
    sf_desync_all,
    sf_lastsync_old_enough,
    sf_runcmd,
    sf_waitforsynced,
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("-c", "--configdir", required=True, help="The config directory")
parser.add_argument(
    "-d",
    "--dry",
    action="store_true",
    default=False,
    help="Do not modify anything. Useful for being informed about which "
    "libraries are due to be synced",
)
parser.add_argument(
    "-f",
    "--force",
    action="store_true",
    default=False,
    help="Force re-sync of libraries even if they are newer than the configured limit",
)
parser.add_argument(
    "-v",
    "--verbose",
    action="store_true",
    default=False,
    help="Print and log DEBUG messages",
)
parser.add_argument("--version", action="version", version="%(prog)s " + __version__)


def main():  # pylint: disable=too-many-locals, too-many-statements
    """Main function"""
    args = parser.parse_args()
    # Set files depending on configdir
    configdir = args.configdir.rstrip("/") + "/"
    configfile = configdir + "seafile_mirror.conf.yaml"
    cachefile = configdir + ".seafile_mirror.db.json"
    logfile = configdir + "seafile_mirror.log"

    # Logging
    log = logging.getLogger()
    logging.basicConfig(
        encoding="utf-8",
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        # Log to file and stdout
        handlers=[
            logging.FileHandler(logfile),
            logging.StreamHandler(),
        ],
    )
    # Set loglevel based on --verbose flag
    if args.verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    # Get lock for this process
    get_lock("seafile_backup")

    # Read configfile
    with open(configfile, "r", encoding="UTF-8") as yamlfile:
        config = yaml.safe_load(yamlfile)

    # Populate cache dictionary
    cache = db_read(cachefile)

    # Check if there are still libraries in `list` or `status`. Desync them if
    # possible. Do not run in dry-run
    if not args.dry:
        sf_desync_all(cache)

    # Create list of libraries we handle(d) for final output
    libsdone = {"libs": [], "bytes": 0, "time": 0}

    # Go through users in config
    for access in config:
        # Setting variables for this server/user/pass combination
        server = access["server"]
        user = access["user"]
        password = access["password"]
        resyncinterval = access["resync_interval_days"]
        authlist = [server, user, password]

        logging.info(
            "Checking all libraries for user %s on server %s for "
            "whether they are due for a re-sync",
            user,
            server,
        )

        # Get remotely available libraries
        remotelibs = sf_runcmd(authlist, "list-remote")

        for lib in access["libs"]:
            # Setting variables for this library
            libdir = Path(lib["dir"])
            libname = lib["name"]
            libid = lib["id"]
            # Set resync interval if there is a lib-specific setting. Otherwise default
            libresyncinterval = (
                lib["resync_interval_days"] if "resync_interval_days" in lib else resyncinterval
            )

            # Check if last sync of library is older than resync_interval_days
            if sf_lastsync_old_enough(cache, libid, args.force, libresyncinterval):
                logging.info("Starting to re-sync library %s (%s) to %s", libname, libid, libdir)
            else:
                logging.info(
                    "Local mirror of library %s (%s) at %s is still recent enough. Skipping it.",
                    libname,
                    libid,
                    libdir,
                )
                continue

            # Check if desired library exists remotely
            if findstring(remotelibs, libid):
                logging.debug("The library %s exists remotely. Continuing...", libname)
            else:
                # If the library does not exist remotely, we don't continue
                # Otherwise, we would delete data which cannot be retrieved again!
                logging.warning(
                    "The library %s does not exist remotely. Aborting resyncing this library.",
                    libname,
                )
                # Start next iteration of loop (next library)
                continue

            if args.dry:
                logging.info(
                    "Running in dry run mode. Aborting resync of library %s which would happen now",
                    libname,
                )
                continue

            # Delete libdir if it exists
            if libdir.exists() and libdir.is_dir():
                logging.debug("Deleting library directory %s", libdir)
                shutil.rmtree(libdir)
            else:
                logging.debug("Library directory did not exist before: %s", libdir)

            # Re-create directory
            logging.debug("Creating library directory %s", libdir)
            Path(libdir).mkdir(parents=True, exist_ok=True)

            # Trigger sync of library
            logging.debug("Starting to sync library %s to %s", libname, libdir)
            sf_runcmd(authlist, "sync", "-l", libid, "-d", libdir)
            sf_bump_cache_status(cache, libid, status="started")

            # Sleep a second to populate `status`
            sleep(1)

            # Check regularly how the syncing progress is and wait for it to finish
            syncduration = sf_waitforsynced(libname)

            # Library is synchronised, now we desync it again
            logging.debug(
                "Desyncing library %s stored at %s after it has been synced",
                libname,
                libdir,
            )
            sf_runcmd(None, "desync", "-d", libdir)

            # Get size of directory (libdir) in bytes
            # Note: this is not fully equivalent with what `du` would show. It's
            # caused by the fact that `du` considers filesystem block sizes
            libdirsize = sum(f.stat().st_size for f in libdir.glob("**/*") if f.is_file())

            # Update libsdone and cache
            libsdone["libs"].append(libname)
            libsdone["bytes"] += libdirsize
            libsdone["time"] += syncduration
            sf_bump_cache_status(cache, libid, status="synced", duration=syncduration)

            logging.info(
                "Library %s (%s) has been re-synced to %s. Duration: %s minutes. Size: %s",
                libname,
                libid,
                libdir,
                round(syncduration),
                convert_bytes(libdirsize),
            )

    logging.info(
        "Fully re-synced the following libraries: %s. Total duration: %s minutes. Total size: %s",
        ", ".join(libsdone["libs"]),
        round(libsdone["time"]),
        convert_bytes(libsdone["bytes"]),
    )


if __name__ == "__main__":
    main()
