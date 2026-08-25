#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Drives a Wetty instance the way a browser does and runs a command over it.

Wetty is a web page, a Socket.IO connection and an SSH client stitched
together. Asking it for its landing page proves only that Express is running:
the stock image serves that same page with no configuration at all, with no
SSH target and no way to reach one. The only thing that proves the whole chain
is to speak to it the way the browser does - open the WebSocket, let Wetty
spawn its SSH client, authenticate against the real SSH daemon behind it, run a
command and read the output back.

Only the Python standard library is used, so that the Molecule scenario does
not have to install a WebSocket library into the test container.

Usage:
    wetty-terminal-probe.py --url http://host:3000/wetty --password secret \
        --command 'id -un' --expect mashtest [--user someone]

Exits 0 when the expected text came back out of the terminal, 1 otherwise, and
prints a transcript of what the terminal produced to stderr either way.
"""

import argparse
import base64
import json
import os
import re
import secrets
import socket
import sys
import time
import urllib.parse

# Engine.IO packet types (the first character of a WebSocket text frame).
ENGINEIO_OPEN = "0"
ENGINEIO_PING = "2"
ENGINEIO_PONG = "3"
ENGINEIO_MESSAGE = "4"

# Socket.IO packet types (the character after ENGINEIO_MESSAGE).
SOCKETIO_CONNECT = "0"
SOCKETIO_CONNECT_ERROR = "4"
SOCKETIO_EVENT = "2"

# Terminal output arrives with colour codes and cursor movement in it, which
# would otherwise defeat a plain substring search for the expected text.
ANSI_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][B0]|[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ProbeError(Exception):
    """Anything that stops the probe from reaching a verdict."""


class WebSocketClient:
    """The client half of RFC 6455, in as much detail as Socket.IO needs.

    Text frames only, no extensions, no continuation frames on the way out.
    Incoming continuation and binary frames are handled because Socket.IO is
    free to use them, even though Wetty in practice does not.
    """

    def __init__(self, host, port, path, timeout):
        self.deadline = time.monotonic() + timeout
        self.buffer = b""
        self.socket = socket.create_connection((host, port), timeout=timeout)
        self.socket.settimeout(timeout)
        self._handshake(host, port, path)

    def _handshake(self, host, port, path):
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.socket.sendall(request.encode())

        while b"\r\n\r\n" not in self.buffer:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise ProbeError("connection closed during the WebSocket handshake")
            self.buffer += chunk

        head, _, rest = self.buffer.partition(b"\r\n\r\n")
        self.buffer = rest
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if "101" not in status:
            raise ProbeError(f"the server refused to upgrade to a WebSocket: {status}")

    def send(self, payload):
        data = payload.encode()
        header = bytearray([0x81])  # FIN + text frame
        mask = secrets.token_bytes(4)
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += length.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += length.to_bytes(8, "big")
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.socket.sendall(bytes(header) + masked)

    def _recv_exactly(self, count):
        while len(self.buffer) < count:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeError("timed out waiting for the terminal")
            self.socket.settimeout(remaining)
            chunk = self.socket.recv(65536)
            if not chunk:
                raise ProbeError("the server closed the WebSocket")
            self.buffer += chunk
        taken, self.buffer = self.buffer[:count], self.buffer[count:]
        return taken

    def receive(self):
        """Returns the next text message, reassembling fragments as needed."""
        message = b""
        while True:
            first, second = self._recv_exactly(2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(self._recv_exactly(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exactly(8), "big")
            payload = self._recv_exactly(length) if length else b""

            if opcode == 0x8:
                raise ProbeError("the server closed the WebSocket")
            if opcode == 0x9:  # ping; a pong is required to stay connected
                self.socket.sendall(bytes([0x8A, 0x80]) + secrets.token_bytes(4))
                continue
            if opcode == 0xA:  # pong
                continue

            message += payload
            if final:
                return message.decode(errors="replace")

    def close(self):
        try:
            self.socket.close()
        except OSError:
            pass


class WettyTerminal:
    """A Socket.IO connection to Wetty, exposing it as a terminal."""

    def __init__(self, url, timeout):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "http":
            raise ProbeError(f"only http:// URLs are supported, got {url!r}")
        base = parsed.path.rstrip("/")
        self.transcript = ""
        self.client = WebSocketClient(
            parsed.hostname,
            parsed.port or 80,
            f"{base}/socket.io/?EIO=4&transport=websocket",
            timeout,
        )
        self._connect()

    def _connect(self):
        opening = self.client.receive()
        if not opening.startswith(ENGINEIO_OPEN):
            raise ProbeError(f"expected an Engine.IO open packet, got {opening[:120]!r}")

        self.client.send(ENGINEIO_MESSAGE + SOCKETIO_CONNECT)
        while True:
            packet = self.client.receive()
            if packet.startswith(ENGINEIO_PING):
                self.client.send(ENGINEIO_PONG)
                continue
            if packet.startswith(ENGINEIO_MESSAGE + SOCKETIO_CONNECT_ERROR):
                raise ProbeError(f"Wetty refused the Socket.IO connection: {packet}")
            if packet.startswith(ENGINEIO_MESSAGE + SOCKETIO_CONNECT):
                return
            raise ProbeError(f"unexpected packet while connecting: {packet[:120]!r}")

    def type(self, text):
        """Sends keystrokes, as the browser does when a key is pressed."""
        self.client.send(ENGINEIO_MESSAGE + SOCKETIO_EVENT + json.dumps(["input", text]))

    def wait_for(self, pattern, description):
        """Reads terminal output until it matches, or gives up.

        Returns the transcript accumulated so far. Data arrives split across
        frames at arbitrary points, so the search runs against everything seen
        rather than against the newest frame.
        """
        expression = re.compile(pattern)
        while True:
            if expression.search(self.transcript):
                return self.transcript

            packet = self.client.receive()
            if packet.startswith(ENGINEIO_PING):
                self.client.send(ENGINEIO_PONG)
                continue
            if not packet.startswith(ENGINEIO_MESSAGE + SOCKETIO_EVENT):
                continue

            try:
                event = json.loads(packet[2:])
            except ValueError:
                continue
            if not isinstance(event, list) or not event:
                continue

            name = event[0]
            if name == "data" and len(event) > 1:
                self.transcript += ANSI_ESCAPES.sub("", str(event[1]))
            elif name == "logout":
                if expression.search(self.transcript):
                    return self.transcript
                raise ProbeError(
                    f"the terminal ended before {description}; "
                    f"transcript: {self.transcript!r}"
                )

    def close(self):
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="where Wetty serves its page")
    parser.add_argument("--password", required=True, help="the SSH password to log in with")
    parser.add_argument("--user", default="", help="typed at Wetty's own login prompt, when it asks")
    parser.add_argument("--command", required=True, help="the command to run in the terminal")
    parser.add_argument("--expect", required=True, help="text the command's output must contain")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds to allow in total")
    arguments = parser.parse_args()

    terminal = None
    try:
        terminal = WettyTerminal(arguments.url, arguments.timeout)

        # Wetty asks for the username itself when SSHUSER was not configured;
        # with SSHUSER set it goes straight to the SSH daemon's password
        # prompt. Both are the same terminal, so which one appeared is only
        # visible in what it printed.
        terminal.wait_for(
            r"(?i)enter your username|password:", "Wetty asked for credentials"
        )
        if not re.search(r"(?i)password:", terminal.transcript):
            if not arguments.user:
                raise ProbeError(
                    "Wetty asked for a username but --user was not given; "
                    f"transcript: {terminal.transcript!r}"
                )
            terminal.type(arguments.user + "\r")

        terminal.wait_for(r"(?i)password:", "the SSH daemon asked for a password")
        terminal.type(arguments.password + "\r")

        # The terminal echoes back what is typed into it, so the command line
        # itself appears in the transcript alongside the command's output. The
        # markers are typed in two halves joined by an empty shell string:
        # the echo therefore carries them split, and only the output the shell
        # produced carries either of them whole. Everything between them is
        # what the command printed, and nothing else can be.
        run = "WETTYRUN" + secrets.token_hex(4).upper()
        end = "WETTYEND" + secrets.token_hex(4).upper()
        terminal.type(
            f'echo {run[:8]}""{run[8:]}; {arguments.command}; '
            f'echo {end[:8]}""{end[8:]}:$?\r'
        )
        transcript = terminal.wait_for(
            re.escape(end) + r":\d+", "the command finished"
        )

        sys.stderr.write(f"--- terminal transcript ---\n{transcript}\n---\n")

        outcome = re.search(
            re.escape(run) + r"(.*?)" + re.escape(end) + r":(\d+)",
            transcript,
            re.DOTALL,
        )
        if outcome is None:
            raise ProbeError(
                "the command's output was not delimited as expected; "
                f"transcript: {transcript!r}"
            )
        output, exit_code = outcome.group(1), outcome.group(2)

        if exit_code != "0":
            raise ProbeError(
                f"the command exited with status {exit_code}; output: {output!r}"
            )
        if arguments.expect not in output:
            raise ProbeError(
                f"the command ran but {arguments.expect!r} was not in its "
                f"output; output: {output!r}"
            )
    except (ProbeError, OSError) as error:
        sys.stderr.write(f"FAILED: {error}\n")
        return 1
    finally:
        if terminal is not None:
            terminal.close()

    sys.stdout.write(
        f"OK: ran {arguments.command!r} over Wetty and read back {arguments.expect!r}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
