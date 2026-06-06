#!/usr/bin/env python3
"""No-API ChatGPT App connector for Codex-supervised artifact handoff.

The HTTP endpoint implements a small JSON-RPC surface compatible with the MCP
tool-call shape needed for local development and tunnel exposure. It never calls
OpenAI APIs and never runs local commands on behalf of ChatGPT.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from chatgpt_app_no_api_common import (
    AssistError,
    create_assist_run,
    create_workspace_bundle,
    get_supervisor_receipt,
    list_registered_workspaces,
    list_candidate_artifacts,
    list_workspace_files,
    read_workspace_file,
    request_revision,
    storage_root,
    submit_candidate_artifact,
)


JSON = dict[str, Any]
ToolHandler = Callable[[JSON, Path | None], JSON]


TOOLS: dict[str, ToolHandler] = {
    "list_registered_workspaces": list_registered_workspaces,
    "create_assist_run": create_assist_run,
    "list_workspace_files": list_workspace_files,
    "read_workspace_file": read_workspace_file,
    "create_workspace_bundle": create_workspace_bundle,
    "submit_candidate_artifact": submit_candidate_artifact,
    "list_candidate_artifacts": list_candidate_artifacts,
    "get_supervisor_receipt": get_supervisor_receipt,
    "request_revision": request_revision,
}


TOOL_SCHEMAS: dict[str, JSON] = {
    "create_assist_run": {
        "description": "Create a no-API ChatGPT Web assist run for Codex supervisor review. Does not call model APIs.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["goal", "redaction_confirmed"],
            "properties": {
                "goal": {"type": "string"},
                "task_id": {"type": "string"},
                "run_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "scope": {"type": "array", "items": {"type": "string"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "expected_artifacts": {"type": "array", "items": {"type": "string"}},
                "verification_commands": {"type": "array", "items": {"type": "string"}},
                "redaction_confirmed": {"type": "boolean"},
                "redaction_confirmed_by": {"type": "string"},
            },
        },
    },
    "list_registered_workspaces": {
        "description": "List local workspaces that the human operator has pre-registered for ChatGPT assist. Does not scan arbitrary local paths.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "include_roots": {"type": "boolean"},
            },
        },
    },
    "list_workspace_files": {
        "description": "List safe, text-only files from a registered workspace or assist run. Applies path, size, extension, and secret filters.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "workspace_id": {"type": "string"},
                "run_id": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "read_workspace_file": {
        "description": "Read one safe text file from a registered workspace or assist run. Cannot read secrets, ignored directories, binaries, or arbitrary absolute paths.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {
                "workspace_id": {"type": "string"},
                "run_id": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    "create_workspace_bundle": {
        "description": "Create a local source-files.zip and manifest from safe files in a registered workspace for human-reviewed upload to ChatGPT Project.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id"],
            "properties": {
                "run_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    "submit_candidate_artifact": {
        "description": "Submit a candidate artifact for local Codex supervisor verification. Does not apply patches to the real repository.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id", "artifact_type", "filename", "content"],
            "properties": {
                "run_id": {"type": "string"},
                "artifact_type": {
                    "type": "string",
                    "enum": [
                        "patch",
                        "markdown_report",
                        "text_report",
                        "json",
                        "execution_plan",
                        "review_notes",
                        "code_bundle_manifest",
                    ],
                },
                "filename": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
        },
    },
    "list_candidate_artifacts": {
        "description": "List candidate artifacts already submitted for a run.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id"],
            "properties": {"run_id": {"type": "string"}},
        },
    },
    "get_supervisor_receipt": {
        "description": "Read the local Codex supervisor receipt for a run. If absent, returns not_ready.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id"],
            "properties": {"run_id": {"type": "string"}},
        },
    },
    "request_revision": {
        "description": "Record a revision request after local Codex supervisor review finds issues.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["run_id", "message"],
            "properties": {
                "run_id": {"type": "string"},
                "message": {"type": "string"},
                "blocking": {"type": "boolean"},
            },
        },
    },
}


def json_response(request_id: Any, result: Any = None, error: JSON | None = None) -> JSON:
    response: JSON = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response


def tool_result(payload: JSON) -> JSON:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": payload,
    }


class MCPRequestHandler(BaseHTTPRequestHandler):
    server_version = "ChatGPTNoAPIAssist/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path.rstrip("/") in {"", "/health"}:
            self._send_json({"ok": True, "service": "chatgpt-app-no-api-connector"})
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path not in {"/mcp", "/"}:
            self.send_error(404, "not found")
            return
        try:
            payload = self._read_json()
            response = self._handle_rpc(payload)
            self._send_json(response)
        except AssistError as exc:
            self._send_json(json_response(None, error={"code": -32000, "message": str(exc)}), status=400)
        except json.JSONDecodeError as exc:
            self._send_json(json_response(None, error={"code": -32700, "message": f"invalid JSON: {exc}"}), status=400)

    def _read_json(self) -> JSON:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            raise AssistError("empty request body")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise AssistError("JSON-RPC request must be an object")
        return payload

    def _handle_rpc(self, payload: JSON) -> JSON:
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "initialize":
            return json_response(
                request_id,
                {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": "chatgpt-app-no-api-connector", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            )
        if method in {"notifications/initialized", "initialized"}:
            return json_response(request_id, {})
        if method == "tools/list":
            return json_response(
                request_id,
                {
                    "tools": [
                        {
                            "name": name,
                            "description": schema["description"],
                            "inputSchema": schema["inputSchema"],
                        }
                        for name, schema in TOOL_SCHEMAS.items()
                    ]
                },
            )
        if method == "tools/call":
            params = payload.get("params")
            if not isinstance(params, dict):
                raise AssistError("tools/call params must be an object")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name not in TOOLS:
                raise AssistError(f"unknown tool: {name}")
            if not isinstance(arguments, dict):
                raise AssistError("tool arguments must be an object")
            result = TOOLS[str(name)](arguments, self.server.storage_root)  # type: ignore[attr-defined]
            return json_response(request_id, tool_result(result))
        raise AssistError(f"unsupported JSON-RPC method: {method}")

    def _send_json(self, payload: JSON, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


class ConnectorServer(ThreadingHTTPServer):
    storage_root: Path | None


def run_server(host: str, port: int, root: Path | None = None) -> None:
    server = ConnectorServer((host, port), MCPRequestHandler)
    server.storage_root = storage_root(root)
    print(f"ChatGPT no-API connector listening on http://{host}:{port}/mcp")
    print(f"storage root: {server.storage_root}")
    server.serve_forever()


def call_tool(name: str, args: JSON, root: Path | None = None) -> JSON:
    if name not in TOOLS:
        raise AssistError(f"unknown tool: {name}")
    return TOOLS[name](args, storage_root(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or test the no-API ChatGPT App connector.")
    parser.add_argument("--storage-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start local JSON-RPC/MCP HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    tool = subparsers.add_parser("call-tool", help="Invoke a connector tool locally with JSON args")
    tool.add_argument("name", choices=sorted(TOOLS))
    tool.add_argument("arguments_json", nargs="?")
    tool.add_argument("--arguments-json-file", type=Path)

    list_tools = subparsers.add_parser("list-tools", help="Print tool schemas")

    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            run_server(args.host, args.port, args.storage_root)
            return 0
        if args.command == "call-tool":
            if args.arguments_json_file:
                arguments = json.loads(args.arguments_json_file.read_text(encoding="utf-8-sig"))
            elif args.arguments_json:
                arguments = json.loads(args.arguments_json)
            else:
                raise AssistError("call-tool requires arguments_json or --arguments-json-file")
            print(json.dumps(call_tool(args.name, arguments, args.storage_root), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "list-tools":
            print(json.dumps(TOOL_SCHEMAS, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except (AssistError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
