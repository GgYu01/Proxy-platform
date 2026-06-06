#!/usr/bin/env python3
"""Local Simprint CDP bridge for supervised ChatGPT Web assistance.

This tool discovers the Simprint-launched Chromium instance and uses its local
Chrome DevTools Protocol endpoint. It does not require an HTTPS tunnel, does not
call OpenAI APIs, and does not read or persist ChatGPT cookies or sessions.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from chatgpt_app_no_api_common import AssistError, reject_secret_text


DEFAULT_PORT = 29200
DEFAULT_URL = "https://chatgpt.com/"
DEFAULT_MODEL_HINT = "GPT-5.5 Thinking"
PROBE_MODEL_LABELS = {
    "gpt55_thinking": ["gpt-5.5 thinking", "gpt 5.5 thinking", "5.5 thinking"],
    "gpt55_pro": ["gpt-5.5 pro", "gpt 5.5 pro", "5.5 pro"],
}
PROBE_REASONING_LABELS = {
    "extended": ["extended", "\u5ef6\u957f", "\u6269\u5c55"],
    "deep": ["deep", "heavy", "\u6df1\u5165"],
    "advanced": ["advanced", "\u8fdb\u9636"],
    "standard": ["standard", "\u6807\u51c6"],
    "fast": ["fast", "light", "\u5feb\u901f", "\u8f7b\u91cf"],
}
PLAN_LABEL_RE = re.compile(r"(?i)\b(free|plus|pro|team|enterprise|business|edu)\b|\u5957\u9910|\u8ba2\u9605")


JSON = dict[str, Any]


class BridgeError(RuntimeError):
    """Raised when the Simprint bridge cannot complete a requested action."""


class CDPClient:
    """Minimal local WebSocket client for Chrome DevTools Protocol calls."""

    def __init__(self, websocket_url: str, timeout: float = 5.0) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise BridgeError("only local ws://127.0.0.1 CDP endpoints are allowed")
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/"
        if parsed.query:
            self.path += f"?{parsed.query}"
        if self.port is None:
            raise BridgeError("CDP websocket URL is missing a port")
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.next_id = 1

    def __enter__(self) -> "CDPClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def connect(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        sock.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            sock.close()
            raise BridgeError("CDP websocket handshake failed")
        self.sock = sock

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def call(self, method: str, params: JSON | None = None, timeout: float = 8.0) -> JSON:
        if self.sock is None:
            raise BridgeError("CDP websocket is not connected")
        request_id = self.next_id
        self.next_id += 1
        payload = {"id": request_id, "method": method, "params": params or {}}
        self._send_text(json.dumps(payload, separators=(",", ":")))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._recv_text(max(0.1, deadline - time.monotonic()))
            if not message:
                continue
            parsed = json.loads(message)
            if parsed.get("id") == request_id:
                if "error" in parsed:
                    raise BridgeError(f"CDP {method} failed: {parsed['error']}")
                return parsed.get("result", {})
        raise BridgeError(f"timed out waiting for CDP response: {method}")

    def _send_text(self, text: str) -> None:
        if self.sock is None:
            raise BridgeError("CDP websocket is not connected")
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise BridgeError("CDP websocket is not connected")
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise BridgeError("CDP websocket closed")
            data += chunk
        return data

    def _recv_text(self, timeout: float) -> str | None:
        if self.sock is None:
            raise BridgeError("CDP websocket is not connected")
        self.sock.settimeout(timeout)
        try:
            first, second = self._recv_exact(2)
        except socket.timeout:
            return None
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise BridgeError("CDP websocket closed by peer")
        if opcode == 0x9:
            return None
        if opcode != 0x1:
            return None
        return payload.decode("utf-8")


def _read_url(url: str, timeout: float = 3.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise BridgeError(f"cannot reach {url}: {exc}") from exc
    return json.loads(body)


def _probe_port(port: int) -> JSON | None:
    try:
        version = _read_url(f"http://127.0.0.1:{port}/json/version")
    except (BridgeError, json.JSONDecodeError):
        return None
    if not isinstance(version, dict):
        return None
    browser = str(version.get("Browser", ""))
    websocket = str(version.get("webSocketDebuggerUrl", ""))
    if "Chrome/" not in browser:
        return None
    parsed = urllib.parse.urlparse(websocket)
    if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != port:
        return None
    return version


def _is_chatgpt_url(url: Any) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(url))
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().strip(".")
    return parsed.scheme in {"http", "https"} and (
        hostname == "chatgpt.com" or hostname.endswith(".chatgpt.com")
    )


def _simprint_process_ports() -> list[int]:
    """Return CDP ports explicitly launched by Simprint browser processes."""
    if os.name != "nt":
        return [DEFAULT_PORT]
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -ieq 'simprint.exe' -and $_.CommandLine -match '--remote-debugging-port=' } | "
            "ForEach-Object { $_.CommandLine }"
        ),
    ]
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        return []
    ports: list[int] = []
    for match in re.finditer(r"--remote-debugging-port=(\d+)", completed.stdout):
        port = int(match.group(1))
        if port not in ports:
            ports.append(port)
    return ports


def discover(port: int | None = None) -> JSON:
    simprint_ports = _simprint_process_ports()
    candidates = []
    if port is not None:
        if simprint_ports and port not in simprint_ports:
            raise BridgeError(
                f"port {port} is not advertised by a running Simprint browser process; "
                f"Simprint ports: {simprint_ports}"
            )
        candidates.append(port)
    candidates.extend(simprint_ports)
    candidates.append(DEFAULT_PORT)

    seen: set[int] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        version = _probe_port(candidate)
        if version is None:
            continue
        if simprint_ports and candidate not in simprint_ports:
            continue
        targets = list_targets(candidate)
        chatgpt_targets = [target for target in targets if _is_chatgpt_url(target.get("url", ""))]
        return {
            "ok": True,
            "port": candidate,
            "browser": version.get("Browser"),
            "user_agent": version.get("User-Agent"),
            "web_socket_debugger_url": version.get("webSocketDebuggerUrl"),
            "target_count": len(targets),
            "chatgpt_target_count": len(chatgpt_targets),
            "chatgpt_targets": _summarize_targets(chatgpt_targets),
        }
    raise BridgeError(
        "no reachable Simprint CDP endpoint found. Start Simprint and open a Chrome profile window first."
    )


def list_targets(port: int) -> list[JSON]:
    payload = _read_url(f"http://127.0.0.1:{port}/json/list")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise BridgeError("/json/list did not return an array")


def _summarize_targets(targets: list[JSON]) -> list[JSON]:
    summary = []
    for target in targets:
        summary.append(
            {
                "id": target.get("id"),
                "type": target.get("type"),
                "title": target.get("title"),
                "url": target.get("url"),
            }
        )
    return summary


def _select_chatgpt_target(port: int, target_id: str | None = None) -> JSON:
    targets = list_targets(port)
    if target_id:
        for target in targets:
            if target.get("id") == target_id:
                if target.get("type") != "page" or not _is_chatgpt_url(target.get("url", "")):
                    raise BridgeError(f"target {target_id} is not a ChatGPT Web page target")
                return target
        raise BridgeError(f"target not found: {target_id}")
    for target in targets:
        if target.get("type") == "page" and _is_chatgpt_url(target.get("url", "")):
            return target
    raise BridgeError("no ChatGPT Web page target found in Simprint. Open ChatGPT first.")


def open_url(port: int, url: str) -> JSON:
    if not _is_chatgpt_url(url):
        raise BridgeError("open-chatgpt only opens chatgpt.com URLs")
    version = _probe_port(port)
    if version is None:
        raise BridgeError(f"cannot reach Simprint CDP on port {port}")
    websocket_url = str(version.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise BridgeError("browser CDP endpoint has no websocket debugger URL")
    with CDPClient(websocket_url) as cdp:
        created = cdp.call("Target.createTarget", {"url": url, "newWindow": False})
    target_id = created.get("targetId")
    opened = None
    for _ in range(10):
        for target in list_targets(port):
            if target.get("id") == target_id:
                opened = target
                break
        if opened:
            break
        time.sleep(0.2)
    if opened is None:
        raise BridgeError(f"created target did not appear in /json/list: {target_id}")
    return {
        "ok": True,
        "port": port,
        "opened": {
            "id": opened.get("id"),
            "type": opened.get("type"),
            "title": opened.get("title"),
            "url": opened.get("url"),
        },
        "next_step": f"In Simprint ChatGPT Web, manually select {DEFAULT_MODEL_HINT} before starting assisted work.",
    }


def fill_prompt(port: int, *, text: str, target_id: str | None = None, submit: bool = False) -> JSON:
    reject_secret_text(text, "prompt")
    target = _select_chatgpt_target(port, target_id)
    websocket_url = str(target.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise BridgeError("selected target has no websocket debugger URL")
    js = r"""
async ({ text, submit }) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const isUsableEditor = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = window.getComputedStyle(node);
    if (rect.width <= 0 || rect.height <= 0) return false;
    if (style.display === "none" || style.visibility === "hidden") return false;
    return true;
  };
  const candidates = [
    "[contenteditable='true'][data-testid='prompt-textarea']",
    "div#prompt-textarea[contenteditable='true']",
    "[contenteditable='true'].ProseMirror",
    "div.ProseMirror",
    "[contenteditable='true']",
    "textarea[data-testid='prompt-textarea']",
    "textarea#prompt-textarea",
    "textarea[name='prompt-textarea']",
    "textarea"
  ];
  let editor = null;
  for (const selector of candidates) {
    for (const candidate of document.querySelectorAll(selector)) {
      if (isUsableEditor(candidate)) {
        editor = candidate;
        break;
      }
    }
    if (editor) break;
  }
  if (!editor) {
    return { ok: false, reason: "composer_not_found", title: document.title, url: location.href };
  }
  editor.focus();
  if (editor.tagName === "TEXTAREA" || editor.tagName === "INPUT") {
    editor.value = text;
    editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    editor.dispatchEvent(new Event("change", { bubbles: true }));
  } else {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(editor);
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand("insertText", false, text);
    if ((editor.innerText || "").trim() !== text.trim()) {
      editor.textContent = text;
      editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    }
  }
  await sleep(300);
  let clicked = false;
  let send_label = "";
  if (submit) {
    const buttons = Array.from(document.querySelectorAll("button")).filter((button) => {
      const rect = button.getBoundingClientRect();
      const style = window.getComputedStyle(button);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    });
    const send = buttons.find((button) => {
      const label = [
        button.getAttribute("data-testid"),
        button.getAttribute("aria-label"),
        button.getAttribute("title"),
        button.innerText
      ].filter(Boolean).join(" ").toLowerCase();
      const html = button.outerHTML.toLowerCase();
      const looksLikeSend = /send|发送|提交/.test(label)
        || /composer-submit|data-testid=["']send-button["']/.test(html)
        || (button.className && String(button.className).includes("composer-submit-button-color"));
      if (looksLikeSend && !button.disabled && button.getAttribute("aria-disabled") !== "true") {
        send_label = label || button.outerHTML.slice(0, 120);
        return true;
      }
      return false;
    });
    if (send) {
      send.click();
      clicked = true;
    }
  }
  return {
    ok: true,
    submitted: clicked,
    title: document.title,
    url: location.href,
    editor_tag: editor.tagName,
    editor_visible: isUsableEditor(editor),
    send_label,
    prompt_chars: text.length
  };
}
"""
    expression = f"({js})({json.dumps({'text': text, 'submit': submit}, ensure_ascii=False)})"
    with CDPClient(websocket_url) as cdp:
        result = cdp.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    value = result.get("result", {}).get("value")
    if not isinstance(value, dict):
        raise BridgeError("fill prompt did not return a structured result")
    return {
        "ok": bool(value.get("ok")),
        "port": port,
        "target_id": target.get("id"),
        "target_url": target.get("url"),
        "result": value,
        "next_step": (
            "Review the prompt and manually send it after confirming the target model and required thinking effort for that stage: GPT-5.5 Thinking defaults to 深入 when available; critical GPT-5.5 Pro stages require Extended and must block if Extended is not visible."
            if not submit
            else "If ChatGPT Web accepted the prompt, wait for its draft and bring artifacts back to local supervisor."
        ),
    }


def _node_attribute_map(node: JSON) -> dict[str, str]:
    attributes = node.get("attributes", [])
    if not isinstance(attributes, list):
        return {}
    result: dict[str, str] = {}
    for index in range(0, len(attributes) - 1, 2):
        result[str(attributes[index])] = str(attributes[index + 1])
    return result


def upload_files(
    port: int,
    *,
    file_paths: list[Path],
    target_id: str | None = None,
    file_input_index: int | None = None,
) -> JSON:
    if not file_paths:
        raise BridgeError("at least one file path is required")
    resolved: list[str] = []
    for path in file_paths:
        absolute = path.resolve()
        if not absolute.exists() or not absolute.is_file():
            raise BridgeError(f"upload file does not exist: {path}")
        reject_secret_text(str(absolute), "upload file path")
        resolved.append(str(absolute))
    target = _select_chatgpt_target(port, target_id)
    websocket_url = str(target.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise BridgeError("selected target has no websocket debugger URL")
    with CDPClient(websocket_url) as cdp:
        doc = cdp.call("DOM.getDocument", {"depth": -1, "pierce": True})
        root_node_id = doc.get("root", {}).get("nodeId")
        if not root_node_id:
            raise BridgeError("cannot inspect ChatGPT page DOM")
        selectors = ["input[type='file']", "input[accept]"]
        node_ids: list[int] = []
        for selector in selectors:
            try:
                found = cdp.call("DOM.querySelectorAll", {"nodeId": root_node_id, "selector": selector})
            except BridgeError:
                continue
            for node_id in found.get("nodeIds", []):
                if isinstance(node_id, int) and node_id not in node_ids:
                    node_ids.append(node_id)
        if not node_ids:
            raise BridgeError("no file input found in ChatGPT page. Open the attachment menu first, then retry.")

        selected_index = 0 if file_input_index is None else file_input_index
        if selected_index < 0 or selected_index >= len(node_ids):
            raise BridgeError(
                f"file input index {selected_index} is out of range; "
                f"found {len(node_ids)} candidate file inputs"
            )
        described = cdp.call("DOM.describeNode", {"nodeId": node_ids[selected_index]})
        node = described.get("node", {})
        backend_node_id = node.get("backendNodeId")
        if not backend_node_id:
            raise BridgeError(f"selected file input index {selected_index} has no backend node id")
        attributes = _node_attribute_map(node)
        cdp.call("DOM.setFileInputFiles", {"backendNodeId": backend_node_id, "files": resolved})
    return {
        "ok": True,
        "port": port,
        "target_id": target.get("id"),
        "target_url": target.get("url"),
        "uploaded_files": resolved,
        "file_input": {
            "index": selected_index,
            "candidate_count": len(node_ids),
            "attributes": attributes,
        },
        "next_step": "Review ChatGPT Web upload chips and manually send or continue after confirming the model and files.",
    }


def extract_latest_response(port: int, *, target_id: str | None = None, output: Path | None = None) -> JSON:
    target = _select_chatgpt_target(port, target_id)
    websocket_url = str(target.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise BridgeError("selected target has no websocket debugger URL")
    js = r"""
() => {
  const selectors = [
    "[data-message-author-role='assistant']",
    "[data-testid*='conversation-turn'] [data-message-author-role='assistant']",
    "article"
  ];
  const nodes = [];
  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((node) => nodes.push(node));
    if (nodes.length) break;
  }
  const texts = nodes
    .map((node) => (node.innerText || node.textContent || "").trim())
    .filter(Boolean);
  const text = texts.length ? texts[texts.length - 1] : "";
  return { ok: Boolean(text), text, text_chars: text.length, title: document.title, url: location.href };
}
"""
    with CDPClient(websocket_url) as cdp:
        result = cdp.call(
            "Runtime.evaluate",
            {
                "expression": f"({js})()",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    value = result.get("result", {}).get("value")
    if not isinstance(value, dict) or not value.get("ok"):
        raise BridgeError("no assistant response text found in ChatGPT page")
    text = str(value["text"])
    reject_secret_text(text, "ChatGPT latest response")
    output_path = None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        output_path = output.resolve().as_posix()
    return {
        "ok": True,
        "port": port,
        "target_id": target.get("id"),
        "target_url": target.get("url"),
        "text_chars": len(text),
        "output": output_path,
        "preview": text[:1000],
    }


def _label_hits(blob: str, labels_by_key: dict[str, list[str]]) -> list[JSON]:
    lowered = blob.lower()
    hits = []
    for key, labels in labels_by_key.items():
        matched = sorted({label for label in labels if label.lower() in lowered})
        if matched:
            hits.append({"key": key, "matched_labels": matched})
    return hits


def _extract_plan_label(value: str) -> str:
    match = PLAN_LABEL_RE.search(value)
    return match.group(0) if match else ""


def _sanitize_probe_record(record: Any) -> JSON | None:
    if not isinstance(record, dict):
        return None
    sanitized = {str(key): str(value or "") for key, value in record.items()}
    tag = sanitized.get("tag", "").upper()
    text = sanitized.get("text", "")
    role = sanitized.get("role", "")
    test_id = sanitized.get("test_id", "")
    if tag == "NAV" or "history-item" in test_id.lower() or "\u5386\u53f2\u804a\u5929\u8bb0\u5f55" in text:
        return None
    haystack = " ".join(sanitized.values()).lower()
    if len(text) > 180 and not role and not test_id:
        return None
    redacted_fields: list[str] = []
    if test_id == "accounts-profile-button" or "account" in test_id.lower():
        plan_label = _extract_plan_label(" ".join(sanitized.values()))
        sanitized["text"] = plan_label
        sanitized["aria_label"] = "[account_profile_redacted]"
        redacted_fields.extend(["text_except_plan", "aria_label"])
    elif PLAN_LABEL_RE.search(text) and "gpt" not in haystack and "chatgpt" not in haystack and text.strip() != _extract_plan_label(text):
        sanitized["text"] = _extract_plan_label(text)
        redacted_fields.append("text_except_plan")
    aria_label = sanitized.get("aria_label", "")
    if PLAN_LABEL_RE.search(aria_label) and "gpt" not in aria_label.lower() and "chatgpt" not in aria_label.lower() and aria_label.strip() != _extract_plan_label(aria_label):
        sanitized["aria_label"] = "[account_profile_redacted]"
        redacted_fields.append("aria_label")
    if redacted_fields:
        sanitized["redacted_fields"] = ",".join(sorted(set(redacted_fields)))
    return sanitized


def _sanitize_probe_records(records: Any) -> list[JSON]:
    if not isinstance(records, list):
        return []
    result = []
    for record in records:
        sanitized = _sanitize_probe_record(record)
        if sanitized is not None:
            result.append(sanitized)
    return result


def inspect_model_controls(port: int, *, target_id: str | None = None, output: Path | None = None) -> JSON:
    target = _select_chatgpt_target(port, target_id)
    websocket_url = str(target.get("webSocketDebuggerUrl") or "")
    if not websocket_url:
        raise BridgeError("selected target has no websocket debugger URL")
    js = r"""
() => {
  const isVisible = (node) => {
    const rect = node.getBoundingClientRect();
    const style = window.getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  };
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const interesting = /(gpt|thinking|pro\b|reason|reasoning|heavy|extended|standard|light|advanced|deep|fast|model|plan|subscription|plus|team|enterprise|\u63a8\u7406|\u601d\u8003|\u6a21\u578b|\u5957\u9910|\u8ba2\u9605|\u5f3a\u5ea6|\u5feb\u901f|\u6807\u51c6|\u8fdb\u9636|\u6df1\u5165)/i;
  const nodes = Array.from(document.querySelectorAll("button,[role='button'],[role='menuitem'],[role='option'],[aria-label],label,span,div"));
  const matches = [];
  const seen = new Set();
  for (const node of nodes) {
    if (!isVisible(node)) continue;
    const record = {
      tag: node.tagName,
      role: node.getAttribute("role") || "",
      text: clean(node.innerText || node.textContent || ""),
      aria_label: clean(node.getAttribute("aria-label")),
      title_attr: clean(node.getAttribute("title")),
      test_id: clean(node.getAttribute("data-testid")),
      aria_checked: clean(node.getAttribute("aria-checked")),
      aria_selected: clean(node.getAttribute("aria-selected")),
      aria_pressed: clean(node.getAttribute("aria-pressed"))
    };
    const haystack = Object.values(record).join(" ");
    if (!interesting.test(haystack)) continue;
    const key = haystack.slice(0, 220);
    if (seen.has(key)) continue;
    seen.add(key);
    matches.push(record);
    if (matches.length >= 100) break;
  }
  return {
    ok: true,
    observed_at: new Date().toISOString(),
    title: document.title,
    url: location.href,
    match_count: matches.length,
    matches
  };
}
"""
    with CDPClient(websocket_url) as cdp:
        result = cdp.call(
            "Runtime.evaluate",
            {
                "expression": f"({js})()",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
    value = result.get("result", {}).get("value")
    if not isinstance(value, dict) or not value.get("ok"):
        raise BridgeError("inspect model controls did not return a structured result")
    visible_matches = _sanitize_probe_records(value.get("matches", []))
    blob = json.dumps(visible_matches, ensure_ascii=False)
    payload = {
        "ok": True,
        "port": port,
        "target_id": target.get("id"),
        "target_url": target.get("url"),
        "observed_at": value.get("observed_at"),
        "title": value.get("title"),
        "url": value.get("url"),
        "probe_method": "visible_dom_text_only",
        "inferred_models": _label_hits(blob, PROBE_MODEL_LABELS),
        "inferred_reasoning_efforts": _label_hits(blob, PROBE_REASONING_LABELS),
        "subscription_label_candidates": [
            item
            for item in visible_matches
            if PLAN_LABEL_RE.search(json.dumps(item, ensure_ascii=False))
        ][:20],
        "visible_matches": visible_matches,
        "limitations": [
            "This probe reads only visible DOM labels from the current ChatGPT Web page.",
            "Open the model and reasoning menus before running it if hidden options need to be captured.",
            "It must not be treated as proof of a successful model run.",
        ],
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["output"] = str(output.resolve())
    return payload


def write_operator_prompt(path: Path, *, task: str, model_hint: str = DEFAULT_MODEL_HINT) -> Path:
    reject_secret_text(task, "task")
    reject_secret_text(model_hint, "model_hint")
    path.parent.mkdir(parents=True, exist_ok=True)
    prompt = f"""# ChatGPT Web Simprint operator prompt

You are assisting the local Codex supervisor through a Simprint-launched Chromium browser.

Rules:

1. Use the `{model_hint}` model selected manually by the user in ChatGPT Web. Select the thinking effort required by the uploaded packet. GPT-5.5 Thinking defaults to the highest visible effort, currently `深入`; critical GPT-5.5 Pro stages require `Extended` with current UI probe evidence. If the current subscription/UI does not expose the required effort, stop and record visible available options instead of drafting lower-effort implementation artifacts.
2. You are not the final delivery authority; only the local Codex supervisor can accept the work.
3. Do not claim that you ran local tests, applied patches locally, committed Git changes, or deployed anything.
4. Do not request, output, or store tokens, API keys, SSH private keys, cookies, sessions, database passwords, or real account credentials.
5. Take on as much design, analysis, rewrite, candidate patch, and report drafting work as possible.
6. Output must be easy to save as artifacts and must include limitations plus suggested local verification commands.
7. Prefer `ARTIFACT: <filename>` blocks. The local workflow imports these blocks with `tools/chatgpt_web_artifact_importer.py`, writes response.json, and only publishes artifacts after a passed local receipt.

Task:

{task}

Suggested output format:

```text
ARTIFACT: report.md
<markdown report content>

ARTIFACT: changes.patch
<unified diff if applicable>

LIMITATIONS:
- No local tests were run inside ChatGPT Web.

SUGGESTED_LOCAL_CHECKS:
- <commands for local Codex supervisor>
```
"""
    path.write_text(prompt, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=None, help="Expected Simprint CDP port. Defaults to auto-discovery.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("discover", help="Discover a running Simprint CDP endpoint")
    subparsers.add_parser("list-tabs", help="List current Simprint CDP targets")

    open_parser = subparsers.add_parser("open-chatgpt", help="Open ChatGPT Web in Simprint through CDP")
    open_parser.add_argument("--url", default=DEFAULT_URL)

    prompt_parser = subparsers.add_parser("write-prompt", help="Write a reusable operator prompt for ChatGPT Web")
    prompt_parser.add_argument("--task", required=True)
    prompt_parser.add_argument("--output", type=Path, default=Path(".tmp/chatgpt-web/simprint-operator-prompt.md"))
    prompt_parser.add_argument("--model-hint", default=DEFAULT_MODEL_HINT)

    fill_parser = subparsers.add_parser("fill-prompt", help="Fill the ChatGPT composer in a Simprint ChatGPT tab")
    fill_group = fill_parser.add_mutually_exclusive_group(required=True)
    fill_group.add_argument("--text")
    fill_group.add_argument("--text-file", type=Path)
    fill_parser.add_argument("--target-id")
    fill_parser.add_argument("--submit", action="store_true", help="Also click the send button after filling")

    clear_parser = subparsers.add_parser("clear-prompt", help="Clear the ChatGPT composer in a Simprint ChatGPT tab")
    clear_parser.add_argument("--target-id")

    upload_parser = subparsers.add_parser("upload-files", help="Attach local files through a ChatGPT Web file input via CDP")
    upload_parser.add_argument("--target-id")
    upload_parser.add_argument(
        "--file-input-index",
        type=int,
        default=None,
        help=(
            "0-based input[type=file] candidate index. Use the Project Sources / files input index "
            "on the Project sources page; default 0 keeps legacy composer-attachment behavior."
        ),
    )
    upload_parser.add_argument("files", nargs="+", type=Path)

    extract_parser = subparsers.add_parser("extract-latest-response", help="Extract latest assistant response text from ChatGPT Web")
    extract_parser.add_argument("--target-id")
    extract_parser.add_argument("--output", type=Path)

    inspect_parser = subparsers.add_parser("inspect-model-controls", help="Inspect visible ChatGPT Web model, reasoning, and subscription labels")
    inspect_parser.add_argument("--target-id")
    inspect_parser.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            result = discover(args.port)
        elif args.command == "list-tabs":
            found = discover(args.port)
            result = {
                "ok": True,
                "port": found["port"],
                "targets": _summarize_targets(list_targets(int(found["port"]))),
            }
        elif args.command == "open-chatgpt":
            found = discover(args.port)
            result = open_url(int(found["port"]), args.url)
        elif args.command == "write-prompt":
            output = write_operator_prompt(args.output, task=args.task, model_hint=args.model_hint)
            result = {"ok": True, "path": output.as_posix()}
        elif args.command == "fill-prompt":
            found = discover(args.port)
            text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
            result = fill_prompt(
                int(found["port"]),
                text=text,
                target_id=args.target_id,
                submit=bool(args.submit),
            )
        elif args.command == "clear-prompt":
            found = discover(args.port)
            result = fill_prompt(
                int(found["port"]),
                text="",
                target_id=args.target_id,
                submit=False,
            )
        elif args.command == "upload-files":
            found = discover(args.port)
            result = upload_files(
                int(found["port"]),
                file_paths=args.files,
                target_id=args.target_id,
                file_input_index=args.file_input_index,
            )
        elif args.command == "extract-latest-response":
            found = discover(args.port)
            result = extract_latest_response(
                int(found["port"]),
                target_id=args.target_id,
                output=args.output,
            )
        elif args.command == "inspect-model-controls":
            found = discover(args.port)
            result = inspect_model_controls(
                int(found["port"]),
                target_id=args.target_id,
                output=args.output,
            )
        else:
            raise BridgeError(f"unknown command: {args.command}")
    except (OSError, BridgeError, AssistError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
