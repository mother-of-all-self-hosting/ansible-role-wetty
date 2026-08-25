<!--
SPDX-FileCopyrightText: 2018-2025 Slavi Pantaleev
SPDX-FileCopyrightText: 2019-2022 Aaron Raimist
SPDX-FileCopyrightText: 2019-2023 MDAD project contributors
SPDX-FileCopyrightText: 2023 QEDeD
SPDX-FileCopyrightText: 2024 Fabio Bonelli
SPDX-FileCopyrightText: 2024 Nikita Chernyi
SPDX-FileCopyrightText: 2024-2026 Suguru Hirahara
SPDX-FileCopyrightText: 2026 spatterlight

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Molecule Testing

This role supports [Molecule](https://docs.ansible.com/projects/molecule/), an Ansible testing framework designed for developing and testing Ansible collections, playbooks, and roles.

## Prerequisites

To utilize Molecule you need to prepare several requirements:

- **x86** computer running one of these operating systems that make use of [systemd](https://systemd.io/):
  - **Archlinux**
  - **CentOS**, **Rocky Linux**, **AlmaLinux**, or possibly other RHEL alternatives (although your mileage may vary)
  - **Debian** (10/Buster or newer)
  - **Ubuntu** (18.04 or newer, although [20.04 may be problematic](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/ansible.md#supported-ansible-versions) if you run the Ansible playbook on it)
- `root` access on the computer which Molecule runs against
- [Ansible](http://ansible.com/) program
- [Python](https://www.python.org/)
  - Most distributions install Python by default, but some don't (e.g. Ubuntu 18.04) and require manual installation (something like `apt-get install python3`)
- [Docker](https://www.docker.com)
  - Access to Docker UNIX socket (`/var/run/docker.sock`) is required by default

## Installation

To set up the environment for using Molecule, run the command below on the terminal:

```bash
python3 -m venv ./molecule/venv
source ./molecule/venv/bin/activate
pip3 install -r ./molecule/requirements.txt
```

## Scenarios

Currently there is one testing scenario available.

### `default`

Tests a standard Wetty installation against a real SSH daemon — a container of its own on Wetty's container network, with a real account and a real password, listening on a port that is *not* the one Wetty would fall back to by itself.

Wetty is three things stitched together: a web page, a Socket.IO connection and an SSH client. Only the first of those answers an HTTP request, and it answers just as cheerfully with no configuration at all — so the scenario begins by establishing what that is worth. It starts a second, completely unconfigured Wetty from the same image and shows that it:

- serves its own landing page with a `200`, which is why "Wetty answered" proves nothing on its own
- `404`s on the path prefix the role configures, which is why asking for that path *does* prove something
- cannot be logged in to through the same end-to-end probe used below, which is what makes reaching a shell on the role's instance meaningful

Only then does it look at the instance the role installed, and check that:

- it serves the configured path prefix **and** `404`s at `/` — the exact inverse of the stock image, so a `BASE` that never reached the container fails here
- it renders a page title that only `wetty_environment_variables_additional_variables` could have supplied
- the running container is the version `wetty_version` pins, cross-checked against the image reference, the OCI version label and the `package.json` inside the running process
- a command typed into Wetty's terminal runs on the SSH daemon and its output comes back

That last one is the point of the scenario. [`files/wetty-terminal-probe.py`](default/files/wetty-terminal-probe.py) speaks the browser's half of the protocol using nothing but the Python standard library: it opens the Socket.IO WebSocket, answers Wetty's own username prompt, answers the SSH daemon's password prompt, runs a command and reads the output back. It passes only if the web layer, the WebSocket and the SSH leg all work — and only if both `SSHHOST` and `SSHPORT` arrived, because nothing is listening on the port Wetty defaults to.

Finally, because `Restart=always` makes a crash-looping container look like a healthy unit, the scenario ends by asserting that `wetty.service` has not restarted at all.

## Running

By default it is configured to run the scenarios on Ubuntu 26.04.

```bash
molecule test --scenario-name default
```

You can utilize other distributions by setting one to the `MOLECULE_DISTRO` environment variable:

```bash
# Ubuntu 24.04
MOLECULE_DISTRO=ubuntu2404 molecule test --scenario-name default

# Debian 13
MOLECULE_DISTRO=debian13 molecule test --scenario-name default

# Debian 12
MOLECULE_DISTRO=debian12 molecule test --scenario-name default
```
