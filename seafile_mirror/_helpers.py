# SPDX-FileCopyrightText: 2023 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Misc helper functions for seafile mirror."""

import logging
import socket
import sys


def get_lock(process_name: str) -> None:
    """Get the lock for this program to avoid double-execution."""
    # Without holding a reference to our socket somewhere it gets garbage
    # collected when the function exits
    get_lock._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)  # ty: ignore[unresolved-attribute]  # noqa: SLF001

    try:
        # The null byte (\0) means the socket is created
        # in the abstract namespace instead of being created
        # on the file system itself.
        # Works only in Linux
        get_lock._lock_socket.bind("\0" + process_name)  # ty: ignore[unresolved-attribute]  # noqa: SLF001
    except OSError:
        logging.critical("This script is already executed in another instance. Abort.")
        sys.exit(1)


def findstring(text: str, string: str) -> bool:
    """Check if a certain string exists in an output."""
    return text.find(string) >= 0


def countlines(string: str) -> int:
    """Count number of lines in a variable."""
    return len(string.splitlines())


def convert_bytes(size: float) -> str:
    """Convert bytes to KB, MB etc depending on size."""
    power = 1024
    level = 0
    labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size > power:
        size /= power
        level += 1
    return f"{round(size, 2)} {labels[level]}"
