<!--
SPDX-FileCopyrightText: 2020 Aaron Raimist
SPDX-FileCopyrightText: 2020 Chris van Dijk
SPDX-FileCopyrightText: 2020 Dominik Zajac
SPDX-FileCopyrightText: 2020 Mickaël Cornière
SPDX-FileCopyrightText: 2020-2024 MDAD project contributors
SPDX-FileCopyrightText: 2020-2026 Slavi Pantaleev
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

>[!WARNING]
> Do not set this to `localhost`, `127.0.0.1` or `0.0.0.0`. Those values do not mean "the server this is running on" — Wetty runs in a container, so they mean the container itself. Worse, Wetty treats them as a special case: when it is running as `root` and its SSH host is one of those three names, it skips SSH entirely and offers a login prompt for the container it lives in. The result is a terminal that nobody can log in to, presented without any error.
>
> Use the hostname or the container-network name of the machine you actually want to reach.

### Configuring SSH port for Wetty (optional)

By default Wetty is configured to connect to the port 22 of the SSH server. If you wish to have the instance connect to another port, add the following configuration to your `vars.yml` file and adjust the port as you see fit.

```yaml
wetty_environment_variables_ssh_port: 222
```

### Configuring HTTP Basic authentication

Wetty is, by construction, a web page that opens a shell. Since there does not exist an authentication system on the web interface, this role is configured to enable the HTTP Basic authentication on Traefik by default, considering the nature of the service. See [this page](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/basicauth/) on the Traefik's documentation for details.

You can use `htpasswd` to generate the user and password pair, which needs to be set to `mailcatcher_container_labels_traefik_middleware_basic_auth_users`.

If another authentication service is used or authentication is not required at all, you can disable it by adding the following configuration to your `vars.yml` file:

```yaml
wetty_container_labels_traefik_middleware_basic_auth_enabled: false
```

>[!WARNING]
> Make sure to take a look at the [security considerations](#security-considerations) below before disabling the HTTP Basic authentication.

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

## Security considerations

There are several properties of Wetty itself which are worth knowing about. None of them are configurable through this role, because Wetty does not expose settings for them.

- **There is no rate limiting.** Wetty does not throttle or lock out failed attempts, so the page is a password-guessing oracle against your SSH daemon that works over HTTPS.
- **`fail2ban` and similar tools will not help much.** Every attempt reaches `sshd` from Wetty's container address, not from the visitor's, so a ban either does nothing useful or takes Wetty itself offline for everybody.
- **The SSH host key is not verified.** Wetty connects with `StrictHostKeyChecking=no` and `UserKnownHostsFile=/dev/null`, so it trusts whatever host key it is offered, every time. On a link that leaves your own machine or network, that connection can be intercepted without the terminal noticing.
- **A `remote-user` request header selects the SSH username.** Wetty trusts that header if it is present, so make sure nothing in front of it lets a visitor set it — reverse proxies normally set such headers, they do not usually strip them on the way in.
- **Credentials can travel in the URL.** Wetty serves an `ssh/<username>` route under its path prefix and accepts a `pass` query parameter as the SSH password, so `https://example.com/wetty/ssh/root?pass=…` is a complete login in a single link, with nothing typed. That is convenient, and it is also a password written into browser history, into `Referer` headers, and into every access log along the way. Prefer typing credentials into the terminal.
- **Prometheus metrics are served without authentication**, at `metrics` under the configured path prefix (`https://example.com/wetty/metrics` for the configuration above, or `https://example.com/metrics` when `wetty_path_prefix` is `/`).

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu wetty` (or how you/your playbook named the service, e.g. `mash-wetty`).
