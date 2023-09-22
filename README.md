<!--
SPDX-FileCopyrightText: 2023 Max Mehl <https://mehl.mx>

SPDX-License-Identifier: Apache-2.0
-->

# Seafile Mirror

[![REUSE status](https://api.reuse.software/badge/src.mehl.mx/mxmehl/seafile-mirror)](https://api.reuse.software/info/src.mehl.mx/mxmehl/seafile-mirror)
[![The latest version of reuse can be found on PyPI.](https://img.shields.io/pypi/v/seafile-mirror.svg)](https://pypi.org/project/seafile-mirror/)
[![Information on what versions of Python the tool supports can be found on PyPI.](https://img.shields.io/pypi/pyversions/seafile-mirror.svg)](https://pypi.org/project/seafile-mirror/)

A Python tool to handle clean read-only (re-)syncs of
[Seafile](https://www.seafile.com) libraries with the intention to mirror them.

## Overview

If you have Seafile libraries, you may want to back them up in a safe place
automatically.

One option is to snapshot/backup the whole server on which the library is
stored. However, in some situations, this may not be feasible or even not
possible.

This is why this repository offers a different way: you can define one or
multiple Seafile libraries that shall be downloaded to a local directory. These
libraries can belong to the same or a different user, and even on different
Seafile servers!

## Features

* Download/sync defined libraries in customisable intervals
* De-sync libaries immediately after they have been downloaded to avoid sync
  errors
* Allow to force-re-sync a library even if its re-sync interval hasn't reached
  yet
* Extensive informative and error logging
* Created with automation in mind so you can run it in cronjobs or systemd
  triggers
* Deal with the numerous caveats of `seaf-cli` and Seafile in general


## Install

The tool depends on the following applications:
* `Python 3`
* [`seafile-cli`](https://help.seafile.com/syncing_client/linux-cli/), available
  e.g. in [Debian](https://packages.debian.org/bullseye/seafile-cli)

You can install the latest release via `pip3 install seafile-mirror`.

The tool is executable by `seafile-mirror`. The `--help` flag informs you about
the required and available commands.

There is also an [Ansible
role](https://src.mehl.mx/mxmehl/seafile-mirror-ansible) that takes care of
installing the tool via `pipx`, setting up a systemd service, and running it
daily.

To keep the Seafile daemon that is required for `seafile-cli` running in the
background, check out this [exemplary systemd
service](examples/seaf-daemon.service).

## Configuration

Configuration is done in a YAML file called `seafile_mirror.conf.yaml`. You can
find an example [here](examples/seafile_mirror.conf.yaml).

If that configuration file resides in the same location your current working
directory, you should provide `--configdir ./`.

## Logging and caching

The tool creates `seafile_mirror.log` in addition to the log to the standard
output in the configuration directory. With `-v` you can print DEBUG messages
that will help you in case of problems.

It also caches the current status of synced libraries and their latest full
download in the file `.seafile_mirror.db.json`. Do not delete this file unless
you don't mind that the tool will re-sync all libraries in the next run.

## Contribute and Development

Contributions are welcome! The development is easiest with `poetry`: `poetry
install` and `poetry run seafile-mirror` will get you started.

## License

Apache-2.0, Copyright Max Mehl
