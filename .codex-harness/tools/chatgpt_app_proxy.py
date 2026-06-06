#!/usr/bin/env python3
"""Proxy helper for ChatGPT App connector development.

Use this when the local network cannot reach ChatGPT or tunnel endpoints
directly. It configures process-level proxy variables for the user's local
Hiddify mixed port at 127.0.0.1:12334. It does not store credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 12334
DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"


def build_proxy_env(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, str]:
    http_proxy = f"http://{host}:{port}"
    socks_proxy = f"socks5://{host}:{port}"
    return {
        "HTTP_PROXY": http_proxy,
        "HTTPS_PROXY": http_proxy,
        "ALL_PROXY": socks_proxy,
        "NO_PROXY": DEFAULT_NO_PROXY,
        "http_proxy": http_proxy,
        "https_proxy": http_proxy,
        "all_proxy": socks_proxy,
        "no_proxy": DEFAULT_NO_PROXY,
    }


def write_env_file(path: str | Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    env = build_proxy_env(host, port)
    lines = [f"{key}={value}" for key, value in sorted(env.items())]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def probe_port(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 2.0) -> dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "error": str(exc),
            "hint": "Start Hiddify and make sure the mixed port is 12334.",
        }
    finally:
        sock.close()
    return {
        "ok": True,
        "host": host,
        "port": port,
    }


def run_with_proxy(command: list[str], host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    if not command:
        raise ValueError("command must not be empty")
    env = os.environ.copy()
    env.update(build_proxy_env(host, port))
    completed = subprocess.run(command, env=env, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure Hiddify 12334 proxy environment for ChatGPT App connector work.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("print-env", help="Print proxy environment as JSON")

    write_env = subparsers.add_parser("write-env", help="Write a .env-style proxy file")
    write_env.add_argument("path", type=Path)

    subparsers.add_parser("probe", help="Check whether the local mixed proxy port is reachable")

    wrap = subparsers.add_parser("run", help="Run a command with proxy environment variables")
    wrap.add_argument("argv", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.command == "print-env":
        print(json.dumps(build_proxy_env(args.host, args.port), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "write-env":
        path = write_env_file(args.path, args.host, args.port)
        print(str(path))
        return 0
    if args.command == "probe":
        result = probe_port(args.host, args.port)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "run":
        if args.argv and args.argv[0] == "--":
            args.argv = args.argv[1:]
        return run_with_proxy(args.argv, args.host, args.port)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
