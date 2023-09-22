# SPDX-FileCopyrightText: 2023 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Functions for cache DB for seafile mirror"""

import json
import logging
from pathlib import Path


def db_read(cachefile) -> dict:
    """Get the cache database file as a dict"""
    dbpath = Path(cachefile)

    # If DB file exists, return JSON as dict
    if dbpath.is_file():
        with open(cachefile, "r", encoding="UTF-8") as dbread:
            logging.debug("Reading cache file '%s' from disk", cachefile)
            cachedb = json.load(dbread)
    else:
        logging.debug("Cache file '%s' does not exist on disk", cachefile)
        cachedb = {}

    # Add/Update key containing the local cache file so we can easily access it
    cachedb["_cachefile"] = cachefile

    return cachedb


def db_write(dbdict):
    """Update/create the cache database file with a dict"""
    with open(dbdict["_cachefile"], "w", encoding="UTF-8") as dbwrite:
        logging.debug("Writing cache file '%s' to disk", dbdict["_cachefile"])
        json.dump(dbdict, dbwrite, indent=2)
        # Append newline to file
        dbwrite.write("\n")


def db_update(dbdict, libid, **kwargs):
    """Update the cached key/values for a specific library, and write the cache file"""
    # Create dict entry for library if it doesn't exist yet
    if libid not in dbdict:
        dbdict[libid] = {}
    for key, value in kwargs.items():
        logging.debug("Updating '%s' of library '%s' in in-memory cache dictionary", key, libid)
        dbdict[libid][key] = value

    db_write(dbdict)


def db_get_library_key(dbdict, libid, key):
    """Get value of requested key from the cache dictionary"""
    if libid in dbdict and key in dbdict[libid]:
        return dbdict[libid][key]

    return None
