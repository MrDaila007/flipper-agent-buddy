"""Inspect/select the native agent target through the running Buddy daemon."""

import argparse
import json
import socket

from . import config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=config.SOCKET_PATH, help="Buddy IPC socket")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sessions")
    select = commands.add_parser("select")
    select.add_argument("session_id")
    commands.add_parser("status")
    commands.add_parser("interrupt")
    commands.add_parser("attention")
    args = parser.parse_args()
    request = {"action": "agent_" + args.command}
    if args.command == "attention":
        request = {"action": "attention_status"}
    if args.command == "select":
        request["session_id"] = args.session_id
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(args.socket)
            client.sendall(json.dumps(request).encode())
            client.shutdown(socket.SHUT_WR)
            stream = client.makefile("rb")
            with stream:
                response = json.loads(stream.readline(1024 * 1024))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Buddy IPC unavailable: {exc}\n")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    if response.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
