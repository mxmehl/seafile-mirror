# SPDX-FileCopyrightText: 2023 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Functions specific to Seafile for seafile mirror"""

import datetime
import logging
import subprocess
import sys
from time import sleep

from ._cachedb import db_get_library_key, db_update

# Constants
# Seafile CLI command
CMD = "seaf-cli"


def sf_runcmd(auth: list, *arguments: str) -> str:
    """Run a seaf-cli command and return the output (stdout)"""
    # Build command list
    # base command (seaf-cli)
    cmdargs = [CMD]

    # Arguments
    for arg in arguments:
        cmdargs.append(arg)

    # Optional authentication as list
    # "-s", server, "-u", user, "-p", password
    if auth:
        cmdargs.extend(["-s", auth[0], "-u", auth[1], "-p", auth[2]])

    # run command
    ret = subprocess.run(cmdargs, capture_output=True, check=False)

    # check for errors
    if ret.returncode != 0:
        logging.error("The command '%s' returned an error: %s", ret.args, ret.stderr)
        return ""

    return ret.stdout.decode("UTF-8")


def sf_parse(output: str, fromcommand: str) -> list:
    """Parse the output of `list` and `status`, return a list of dicts"""
    libs = []
    # Read line by line, skip first line
    for lib in output.splitlines()[1:]:
        # If list, split is by " ", and structure is name,id,dir
        if fromcommand == "list":
            lib_info = [x.strip() for x in lib.split(" ")]
            lib_dict = {"name": lib_info[0], "id": lib_info[1], "dir": lib_info[2]}
            libs.append(lib_dict)
        # If status, split is by "\t", and structure is name,status,progress
        elif fromcommand == "status":
            lib_tmp = [x.strip() for x in lib.split("\t")]
            lib_dict = {"name": lib_tmp[0], "status": lib_tmp[1]}
            # Add progress if it exists
            try:
                lib_dict["progress"] = lib_tmp[2]
            except IndexError:
                lib_dict["progress"] = ""

            libs.append(lib_dict)

    return libs


def sf_getstatus(libname: str) -> dict:
    """Return the current status of a library (name, status, progress)"""
    # Get output of `status` and parse it
    libsstatus_cmd = sf_runcmd([], "status")
    libsstatus = sf_parse(libsstatus_cmd, "status")

    # In the list of statuses, get the one for the requested library. None if no match
    status = next((item for item in libsstatus if item["name"] == libname), None)

    # Handle if the library does not appear in `status`. Usually directly after starting to sync it
    if not status:
        logging.debug("Status for %s cannot be retrieved", libname)
        # Construct a status dict
        status = {"name": libname, "status": None, "progress": None}

    return status


def sf_desync_all(cache):
    """Desync all libraries that are in `list` and `status`"""
    # Firstly, go through libslist
    libslist = sf_runcmd(None, "list")
    libslist = sf_parse(libslist, "list")

    # If libraries found in `list`, desync them
    if libslist:
        logging.warning(
            "There are still %s local synced libraries. Desyncing them...",
            len(libslist),
        )

        for lib in libslist:
            # Check if the cache status of the lib is still `started`. If so,
            # update the lastsync date
            if db_get_library_key(cache, lib["id"], "status") == "started":
                logging.debug(
                    "Library %s is synced but the cache file hasn't been updated "
                    "with the last sync date. Setting it to 'now'",
                    lib["name"],
                )
                sf_bump_cache_status(cache, lib["id"], status="synced")

            # Desync library
            logging.debug("Desyncing library %s stored in %s", lib["name"], lib["dir"])
            sf_runcmd(None, "desync", "-d", lib["dir"])

    # Secondly, go through libstatus
    # We cannot desync libraries that are in `status` but not `list`, so error out
    libsstatus = sf_runcmd(None, "status")
    libsstatus = sf_parse(libsstatus, "status")

    # If libraries found in `status`, return informative errors and abort
    if libsstatus:
        logging.error(
            "There are still %s local libraries currently downloading but not listed yet:",
            len(libsstatus),
        )

        for lib in libsstatus:
            logging.error(
                "- %s with the current status '%s' and progress '%s'",
                lib["name"],
                lib["status"],
                lib["progress"],
            )

        logging.critical(
            "Exiting application because we cannot resync at least one library, see errors above."
        )
        sys.exit(1)


def sf_waitforsynced(libname) -> float:
    """Regularly check status of the library that started to sync"""
    libsynced = False
    syncwaitmins: float = 0
    nostatus, nostatus_limit = 0, 10
    while libsynced is not True:
        libstatus = sf_getstatus(libname)
        # If we have some status information, act upon it
        # If not, we already informed about being unable to retrieve it and also wait

        if libstatus["status"]:
            # Reset status fails
            nostatus = 0
            # If synchronised, inform and end loop
            if libstatus["status"] == "synchronized":
                logging.debug(
                    "Library %s has been fully synchronised after %s minutes",
                    libname,
                    round(syncwaitmins),
                )
                libsynced = True

            # If not synchronised yet, report on status
            else:
                logging.debug(
                    "Library %s is not fully synchronised yet. "
                    "Current status: %s with progress: %s",
                    libname,
                    libstatus["status"],
                    libstatus["progress"],
                )

        # Status is None, which is fine a few times. But if it happens too often
        # (`nostatus_limit`), we'll restart seaf-cli as it's probably hung up
        else:
            # Increment number of failed status retrievals
            nostatus += 1
            if nostatus >= nostatus_limit:
                logging.warning(
                    "Library %s didn't appear in status %s times. Restarting seaf-cli daemon...",
                    libname,
                    nostatus_limit,
                )
                sf_runcmd([], "stop")
                sf_runcmd([], "start")

        # If library not synced yet or no status available, wait
        if not libsynced:
            # Decide how long to wait for next `status` check depending on how
            # often we tried before
            if syncwaitmins < 1:
                # wait 15 seconds for 1 minute in total
                sleep(15)
                syncwaitmins += 0.25
            elif syncwaitmins < 10:
                # wait 60 seconds for 10 minutes in total
                sleep(60)
                syncwaitmins += 1
            else:
                # wait 120 seconds
                sleep(120)
                syncwaitmins += 2

    return syncwaitmins


def sf_bump_cache_status(dbdict, libid, status, duration=0) -> None:
    """Update the sync state of a library in the cache database"""
    logging.debug("Updating cache for library '%s' to status '%s'", libid, status)
    # Library has been successfully synced
    if status == "synced":
        lastsync = datetime.datetime.now() - datetime.timedelta(minutes=duration + 2)
        db_update(
            dbdict,
            libid,
            status=status,
            lastsync=lastsync.isoformat(),
        )
    # Library sync has just been started
    if status == "started":
        db_update(dbdict, libid, status=status)


def sf_lastsync_old_enough(dbdict, libid, force, resyncinterval) -> bool:
    """Find out if lastsync time of library is older than resyncinterval"""
    # Get lastsync key from cache for this library
    lastsync = db_get_library_key(dbdict, libid, "lastsync")
    # Check if there actually has been an entry for the last sync
    if lastsync:
        # Convert to datetime object
        lastsync = datetime.datetime.fromisoformat(lastsync)
        # Test if time difference (hours) is smaller than resyncinterval
        if datetime.datetime.now() - lastsync < datetime.timedelta(days=resyncinterval):
            logging.debug(
                "Last sync of library '%s' is newer than limit (%s days)",
                libid,
                resyncinterval,
            )

            if force:
                logging.info(
                    "Last sync of library '%s' is newer than limit (%s days), "
                    "but sync is enforced.",
                    libid,
                    resyncinterval,
                )
                return True

            return False

        # time difference is larger than resyncinterval
        logging.debug(
            "Last sync of library '%s' is older than limit (%s days)",
            libid,
            resyncinterval,
        )
        return True

    # The library has never been synced before (lastsync = None)
    logging.debug(
        "Library '%s' seems to not have been synced before",
        libid,
    )
    return True
