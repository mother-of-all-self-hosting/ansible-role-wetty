<!--
SPDX-FileCopyrightText: 2020 Aaron Raimist
SPDX-FileCopyrightText: 2020 Chris van Dijk
SPDX-FileCopyrightText: 2020 Dominik Zajac
SPDX-FileCopyrightText: 2020 Mickaël Cornière
SPDX-FileCopyrightText: 2020-2024 MDAD project contributors
SPDX-FileCopyrightText: 2020-2025 Slavi Pantaleev
SPDX-FileCopyrightText: 2022 François Darveau
SPDX-FileCopyrightText: 2022 Julian Foad
SPDX-FileCopyrightText: 2022 Warren Bailey
SPDX-FileCopyrightText: 2023 Antonis Christofides
SPDX-FileCopyrightText: 2023 Felix Stupp
SPDX-FileCopyrightText: 2023 Pierre 'McFly' Marty
SPDX-FileCopyrightText: 2023-2025 MASH project contributors
SPDX-FileCopyrightText: 2024 Sergio Durigan Junior
SPDX-FileCopyrightText: 2024-2026 Suguru Hirahara

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Setting up Wetty

This is an [Ansible](https://www.ansible.com/) role which installs [Wetty](https://github.com/butlerx/wetty) to run as a [Docker](https://www.docker.com/) container wrapped in a systemd service.

Wetty is an SSH terminal over HTTP/HTTPS, useful for when on a strict network which disallows outbound SSH traffic, or when only a browser can be used (like a managed chromebook).

See the project's [documentation](https://butlerx.github.io/wetty) to learn what Wetty does and why it might be useful to you.

## Adjusting the playbook configuration

To enable Wetty with this role, add the following configuration to your `vars.yml` file.

**Note**: the path should be something like `inventory/host_vars/mash.example.com/vars.yml` if you use the [MASH Ansible playbook](https://github.com/mother-of-all-self-hosting/mash-playbook).

```yaml
########################################################################
#                                                                      #
# wetty                                                                #
#                                                                      #
########################################################################

wetty_enabled: true

########################################################################
#                                                                      #
# /wetty                                                               #
#                                                                      #
########################################################################
```

### Set the hostname

To enable Wetty you need to set the hostname as well. To do so, add the following configuration to your `vars.yml` file. Make sure to replace `example.com` with your own value.

```yaml
wetty_hostname: "example.com"
```

After adjusting the hostname, make sure to adjust your DNS records to point the domain to your server.

### Set the SSH server's hostname

It is also necessary to set a hostname of the SSH server which the Wetty instance should connect to by adding the following configuration to your `vars.yml` file:

```yaml
wetty_environment_variables_ssh_host: YOUR_SSH_SERVER_HOSTNAME_HERE
```

### Configuring SSH port for Wetty (optional)

By default Wetty is configured to connect to the port 22 of the SSH server. If you wish to have the instance connect to another port, add the following configuration to your `vars.yml` file and adjust the port as you see fit.

```yaml
wetty_environment_variables_ssh_port: 222
```

### Extending the configuration

There are some additional things you may wish to configure about the service.

Take a look at:

- [`defaults/main.yml`](../defaults/main.yml) for some variables that you can customize via your `vars.yml` file. You can override settings (even those that don't have dedicated playbook variables) using the `wetty_environment_variables_additional_variables` variable

## Installing

After configuring the playbook, run the installation command of your playbook as below:

```sh
ansible-playbook -i inventory/hosts setup.yml --tags=setup-all,start
```

If you use the MASH playbook, the shortcut commands with the [`just` program](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/just.md) are also available: `just install-all` or `just setup-all`

## Usage

After running the command for installation, Wetty becomes available at the specified hostname like `https://example.com`.

To get started, open the URL with a web browser, and log in to the server with the username and password.

>[!NOTE]
> Wetty only supports password authentication, so if the SSH daemon at `wetty_environment_variables_ssh_host` only allows pubkey authentication you will not be able to connect.

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu wetty` (or how you/your playbook named the service, e.g. `mash-wetty`).
