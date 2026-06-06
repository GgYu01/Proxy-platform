#!/usr/bin/env python3
"""Prepare and run ChatGPT-Web-primary local harness packets.

The harness keeps local Codex in a supervisor/executor role: package safe local
context, ask ChatGPT Web to do the main analysis/generation work, import the
returned artifacts, apply patches locally, and verify with local checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from chatgpt_app_no_api_common import (
    AssistError,
    create_assist_run,
    create_workspace_bundle,
    get_registered_workspace,
    list_workspace_files,
    reject_secret_text,
    safe_chatgpt_alias,
    safe_id,
    storage_root,
)
from chatgpt_web_artifact_importer import apply_response_patches, import_chatgpt_response


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHATGPT_PROJECT_ALIAS = "harness-dev-test"
DEFAULT_UPLOAD_TARGET = "project_sources"
DEFAULT_CHATGPT_MODEL = "GPT-5.5 Thinking"
DEFAULT_CHATGPT_REASONING_EFFORT = "deep"
UPLOAD_TARGETS = {"conversation", "project_sources"}
REQUIRED_WEB_ARTIFACTS = ("codex-execution-plan.json", "report.md", "changes.patch", "testing-guide.md")
PRIVATE_HANDLE_STATE_NAME = "chatgpt-web-conversation-handles.json"
PRIVATE_HANDLE_MAX_BYTES = 4096
PRIVATE_HANDLE_TTL_MIN_DAYS = 1
PRIVATE_HANDLE_TTL_MAX_DAYS = 90
DEFAULT_CHATGPT_MODEL_KEY = "gpt55_thinking"
DEFAULT_CHATGPT_FALLBACK_DETECTION_POLICY = "try_required_first_then_detect_available_ui_options"
REASONING_EFFORT_RANK = ["fast", "standard", "advanced", "deep", "extended"]
REASONING_EFFORT_UI_LABELS = {
    "fast": "快速",
    "standard": "标准",
    "advanced": "进阶",
    "deep": "深入",
    "extended": "Extended",
}
MODEL_REASONING_CATALOG = {
    "gpt55_thinking": {
        "model": "GPT-5.5 Thinking",
        "required_reasoning_effort": "deep",
        "required_reasoning_effort_ui_label": "深入",
        "available_reasoning_efforts": ["fast", "standard", "advanced", "deep"],
        "fallback_reasoning_efforts": ["advanced", "standard", "fast"],
    },
    "gpt55_pro": {
        "model": "GPT-5.5 Pro",
        "required_reasoning_effort": "extended",
        "required_reasoning_effort_ui_label": "Extended",
        "available_reasoning_efforts": ["standard", "advanced", "extended"],
        "fallback_reasoning_efforts": [],
    },
}
MODEL_ALIASES = {
    "5.5thinking": "gpt55_thinking",
    "gpt5.5thinking": "gpt55_thinking",
    "gpt-5.5-thinking": "gpt55_thinking",
    "gpt-5.5 thinking": "gpt55_thinking",
    "chatgpt5.5thinking": "gpt55_thinking",
    "chatgpt-5.5-thinking": "gpt55_thinking",
    "gpt5.5pro": "gpt55_pro",
    "gpt-5.5-pro": "gpt55_pro",
    "gpt-5.5 pro": "gpt55_pro",
    "chatgpt5.5pro": "gpt55_pro",
    "chatgpt-5.5-pro": "gpt55_pro",
    "pro": "gpt55_pro",
}
INSTRUCTION_MODEL_PATTERNS = [
    (re.compile(r"(?i)(?:chatgpt|gpt)[-\s]*5\.5\s*thinking|5\.5\s*thinking"), "gpt55_thinking"),
    (re.compile(r"(?i)(?:chatgpt|gpt)[-\s]*5\.5\s*pro|5\.5\s*pro|(?<![A-Za-z0-9])pro(?![A-Za-z0-9])"), "gpt55_pro"),
]
REASONING_ALIASES = {
    "heavy": "deep",
    "deep": "deep",
    "max": "deep",
    "maximum": "deep",
    "highest": "deep",
    "\u6700\u9ad8": "deep",
    "\u6700\u5f3a": "deep",
    "\u6df1\u5165": "deep",
    "\u6df1\u5ea6": "deep",
    "extended": "extended",
    "advanced": "advanced",
    "\u8fdb\u9636": "advanced",
    "\u5ef6\u957f": "extended",
    "\u6269\u5c55": "extended",
    "\u6807\u51c6": "standard",
    "standard": "standard",
    "\u8f7b\u91cf": "fast",
    "\u5feb\u901f": "fast",
    "light": "fast",
    "fast": "fast",
}
VALID_REASONING_EFFORTS = set(REASONING_EFFORT_RANK)


JSON = dict[str, Any]


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return value[:48] or "chatgpt-web-run"


def write_json(path: Path, payload: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_upload_file(source: Path, upload_dir: Path, run_id: str) -> Path:
    target = upload_dir / f"{run_id}--{source.name}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def read_json_list(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        raise AssistError(f"{path} must contain a JSON string array")
    return payload


def read_json(path: Path, default: JSON | None = None) -> JSON:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise
    if not isinstance(payload, dict):
        raise AssistError(f"{path} must contain a JSON object")
    return payload


def read_text_file(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AssistError(f"cannot read {label}: {path}: {exc}") from exc


def resolve_user_instruction(
    *,
    user_instruction: str | None = None,
    user_instruction_file: str | Path | None = None,
) -> JSON:
    if user_instruction and user_instruction_file:
        raise AssistError("user_instruction and user_instruction_file are mutually exclusive")
    if user_instruction_file:
        path = Path(user_instruction_file).expanduser().resolve()
        content = read_text_file(path, "user_instruction_file")
        if not content.strip():
            raise AssistError("user_instruction_file must not be empty")
        reject_secret_text(content, "user_instruction")
        return {"source": "file", "path": str(path), "content": content}
    if user_instruction is not None:
        if not user_instruction.strip():
            raise AssistError("user_instruction must not be empty")
        reject_secret_text(user_instruction, "user_instruction")
        return {"source": "inline", "path": None, "content": user_instruction}
    return {"source": "none", "path": None, "content": ""}


def _catalog_list() -> list[JSON]:
    return [
        {
            "model_key": key,
            "model": profile["model"],
            "required_reasoning_effort": profile["required_reasoning_effort"],
            "required_reasoning_effort_ui_label": profile["required_reasoning_effort_ui_label"],
            "available_reasoning_efforts": list(profile["available_reasoning_efforts"]),
            "fallback_reasoning_efforts": list(profile["fallback_reasoning_efforts"]),
        }
        for key, profile in MODEL_REASONING_CATALOG.items()
    ]


def normalize_model_selection(value: str | None) -> tuple[str, str]:
    if value is None or not value.strip():
        return DEFAULT_CHATGPT_MODEL_KEY, DEFAULT_CHATGPT_MODEL
    reject_secret_text(value, "chatgpt_model")
    stripped = value.strip()
    lowered = stripped.lower()
    compact = lowered.replace(" ", "")
    key = MODEL_ALIASES.get(compact, MODEL_ALIASES.get(lowered))
    if key:
        return key, str(MODEL_REASONING_CATALOG[key]["model"])
    for known_key, profile in MODEL_REASONING_CATALOG.items():
        if lowered == str(profile["model"]).lower():
            return known_key, str(profile["model"])
    return "custom", stripped


def normalize_reasoning_effort(value: str | None) -> str:
    if value is None or not value.strip():
        return DEFAULT_CHATGPT_REASONING_EFFORT
    reject_secret_text(value, "chatgpt_reasoning_effort")
    stripped = value.strip()
    normalized = REASONING_ALIASES.get(stripped.lower().replace(" ", ""), REASONING_ALIASES.get(stripped.lower(), stripped))
    if normalized not in VALID_REASONING_EFFORTS:
        raise AssistError(f"chatgpt_reasoning_effort must be one of: {', '.join(sorted(VALID_REASONING_EFFORTS))}")
    return normalized


def _detect_model_key_from_instruction(content: str) -> str | None:
    for pattern, key in INSTRUCTION_MODEL_PATTERNS:
        if pattern.search(content):
            return key
    return None


def _detect_reasoning_from_instruction(content: str) -> str | None:
    lowered = content.lower()
    compact = lowered.replace(" ", "")
    for alias, canonical in REASONING_ALIASES.items():
        if alias in compact or alias in lowered:
            return canonical
    return None


def infer_model_policy(instruction: JSON, *, chatgpt_model: str | None, chatgpt_reasoning_effort: str | None) -> JSON:
    source = "default"
    model_key, model = normalize_model_selection(chatgpt_model)
    explicit_reasoning_effort = normalize_reasoning_effort(chatgpt_reasoning_effort) if chatgpt_reasoning_effort else None
    if chatgpt_model or chatgpt_reasoning_effort:
        source = "explicit_args"
    content = str(instruction.get("content") or "")
    if not chatgpt_model:
        detected_model_key = _detect_model_key_from_instruction(content)
        if detected_model_key:
            model_key = detected_model_key
            model = str(MODEL_REASONING_CATALOG[model_key]["model"])
            source = "user_instruction"
    profile = MODEL_REASONING_CATALOG.get(model_key)
    if not chatgpt_reasoning_effort:
        detected_reasoning = _detect_reasoning_from_instruction(content)
        if detected_reasoning:
            explicit_reasoning_effort = detected_reasoning
            source = "user_instruction"
    if explicit_reasoning_effort:
        reasoning_effort = explicit_reasoning_effort
    elif profile:
        reasoning_effort = str(profile["required_reasoning_effort"])
    else:
        reasoning_effort = DEFAULT_CHATGPT_REASONING_EFFORT
    highest_reasoning_required = profile is not None
    if profile:
        required_effort = str(profile["required_reasoning_effort"])
        if reasoning_effort != required_effort:
            raise AssistError(
                f"{model} requires highest configured reasoning effort {required_effort!r}; "
                f"do not request {reasoning_effort!r}. Probe current ChatGPT Web availability instead."
            )
        reasoning_effort_ui_label = str(profile["required_reasoning_effort_ui_label"])
        available_reasoning_efforts = list(profile["available_reasoning_efforts"])
        fallback_reasoning_efforts = list(profile["fallback_reasoning_efforts"])
    else:
        reasoning_effort_ui_label = reasoning_effort
        available_reasoning_efforts = []
        fallback_reasoning_efforts = []
    return {
        "model": model,
        "model_key": model_key,
        "reasoning_effort": reasoning_effort,
        "reasoning_effort_ui_label": reasoning_effort_ui_label,
        "reasoning_effort_rank": list(REASONING_EFFORT_RANK),
        "selection_strategy": "highest_visible_available",
        "source": source,
        "web_ui_selection_required": True,
        "connector_sets_model": False,
        "highest_reasoning_required": highest_reasoning_required,
        "subscription_probe_required": highest_reasoning_required,
        "fallback_detection_policy": DEFAULT_CHATGPT_FALLBACK_DETECTION_POLICY,
        "available_reasoning_efforts": available_reasoning_efforts,
        "fallback_reasoning_efforts": fallback_reasoning_efforts,
        "model_catalog": _catalog_list(),
        "availability_probe": {
            "required": highest_reasoning_required,
            "evidence_source": "current_chatgpt_web_ui",
            "record_subscription_plan": True,
            "allowed_record_fields": [
                "observed_at",
                "page_url",
                "selected_model_label",
                "available_model_labels",
                "selected_reasoning_effort_label",
                "available_reasoning_effort_labels",
                "available_reasoning_efforts",
                "subscription_plan_label",
                "blocked_reason",
            ],
            "forbidden_record_fields": [
                "account_email",
                "account_id",
                "billing_id",
                "cookies",
                "session",
                "localStorage",
                "oauth_token",
            ],
        },
    }


def _scan_for_forbidden_probe_fields(value: Any, path: str = "$") -> None:
    forbidden = {
        "account_email",
        "account_id",
        "billing_id",
        "cookie",
        "cookies",
        "session",
        "localstorage",
        "oauth",
        "oauth_token",
        "token",
        "conversation_url",
        "share_url",
        "url",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in forbidden or any(fragment in lowered for fragment in ("cookie", "session", "token", "oauth")):
                raise AssistError(f"UI probe receipt contains forbidden private field: {path}.{key}")
            _scan_for_forbidden_probe_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_for_forbidden_probe_fields(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if "chatgpt.com/" in lowered or "cookie" in lowered or "oauth" in lowered or "bearer " in lowered:
            raise AssistError(f"UI probe receipt contains forbidden private value at {path}")
        reject_secret_text(value, f"UI probe receipt {path}")


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AssistError(f"{label} must be a list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise AssistError(f"{label}[{index}] must be a string")
        result.append(item)
    return result


def _label_contains(labels: list[str], expected: str) -> bool:
    expected_lower = expected.lower()
    return any(expected_lower in label.lower() for label in labels)


def validate_ui_probe_receipt(receipt: JSON, model_policy: JSON) -> JSON:
    _scan_for_forbidden_probe_fields(receipt)
    if receipt.get("packet_type") != "chatgpt_web_ui_probe_receipt":
        raise AssistError("UI probe receipt packet_type must be chatgpt_web_ui_probe_receipt")
    if receipt.get("status") != "available":
        raise AssistError("UI probe receipt status must be available")
    if receipt.get("evidence_source") != "current_chatgpt_web_ui":
        raise AssistError("UI probe receipt evidence_source must be current_chatgpt_web_ui")
    required_model = str(model_policy["model"])
    required_effort = str(model_policy["reasoning_effort"])
    selected_model = str(receipt.get("selected_model_label") or "")
    selected_effort = str(receipt.get("selected_reasoning_effort_label") or "")
    available_models = _string_list(receipt.get("available_model_labels"), "available_model_labels")
    available_effort_labels = _string_list(receipt.get("available_reasoning_effort_labels"), "available_reasoning_effort_labels")
    available_efforts = _string_list(receipt.get("available_reasoning_efforts"), "available_reasoning_efforts")
    subscription_plan = str(receipt.get("subscription_plan_label") or "").strip()
    if not subscription_plan:
        raise AssistError("UI probe receipt must include subscription_plan_label")
    if required_model.lower() not in selected_model.lower() and not _label_contains(available_models, required_model):
        raise AssistError(f"UI probe receipt does not show required model {required_model}")
    effort_visible = required_effort in available_efforts or required_effort.lower() in selected_effort.lower()
    if not effort_visible and required_effort == "extended":
        effort_visible = _label_contains(available_effort_labels, "Extended")
    if not effort_visible:
        raise AssistError(f"UI probe receipt does not show required effort {required_effort} / Extended")
    return {
        "status": "available",
        "observed_at": str(receipt.get("observed_at") or ""),
        "evidence_source": "current_chatgpt_web_ui",
        "required_model": required_model,
        "required_effort": required_effort,
        "selected_model_label": selected_model,
        "selected_reasoning_effort_label": selected_effort,
        "available_model_labels": available_models,
        "available_reasoning_effort_labels": available_effort_labels,
        "available_reasoning_efforts": available_efforts,
        "subscription_plan_label": subscription_plan,
    }


def validate_ui_probe_receipt_file(path: Path, model_policy: JSON) -> JSON:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssistError(f"cannot read UI probe receipt: {path}: {exc}") from exc
    if not isinstance(receipt, dict):
        raise AssistError("UI probe receipt must be a JSON object")
    return validate_ui_probe_receipt(receipt, model_policy)


def write_blocked_ui_probe_receipt(root: Path, run_id: str, model_policy: JSON, blocked_reason: str) -> Path:
    path = root / run_id / "blocked-ui-probe-receipt.json"
    payload = {
        "packet_type": "chatgpt_web_ui_probe_receipt",
        "status": "blocked",
        "observed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "evidence_source": "current_chatgpt_web_ui",
        "required_model": model_policy["model"],
        "required_effort": model_policy["reasoning_effort"],
        "blocked_reason": blocked_reason,
        "downgrade_allowed": False,
    }
    write_json(path, payload)
    return path


def reserve_conversation_alias(
    root: Path,
    *,
    run_id: str,
    conversation_alias: str,
    project_alias: str,
    source_bundle_sha256: str | None = None,
    allow_followup: bool = False,
    previous_run_id: str | None = None,
) -> Path:
    index_path = root / "chatgpt-web-conversation-index.json"
    index = read_json(index_path, {"packet_type": "chatgpt_web_conversation_index", "conversations": {}})
    conversations = index.setdefault("conversations", {})
    if not isinstance(conversations, dict):
        raise AssistError("conversation index is invalid")
    existing = conversations.get(conversation_alias)
    if isinstance(existing, dict) and "run_ids" not in existing:
        first_run = existing.get("run_id")
        existing = {
            "run_id": first_run,
            "primary_run_id": first_run,
            "run_ids": [first_run] if isinstance(first_run, str) else [],
            "chatgpt_project_alias": existing.get("chatgpt_project_alias", project_alias),
            "updated_at": existing.get("updated_at"),
            "follow_up_chain": [],
            "source_bundle_sha256_by_run": {},
            "artifact_hashes_by_run": {},
        }
    if isinstance(existing, dict) and existing.get("run_id") != run_id and run_id not in existing.get("run_ids", []) and not allow_followup:
        raise AssistError(
            f"chatgpt_conversation_alias {conversation_alias!r} is already bound to local run {existing.get('run_id')!r}"
        )
    if not isinstance(existing, dict):
        existing = {
            "run_id": run_id,
            "primary_run_id": run_id,
            "run_ids": [],
            "chatgpt_project_alias": project_alias,
            "follow_up_chain": [],
            "source_bundle_sha256_by_run": {},
            "artifact_hashes_by_run": {},
        }
    run_ids = existing.setdefault("run_ids", [])
    if run_id not in run_ids:
        run_ids.append(run_id)
    if source_bundle_sha256:
        existing.setdefault("source_bundle_sha256_by_run", {})[run_id] = source_bundle_sha256
    if allow_followup and previous_run_id:
        chain = existing.setdefault("follow_up_chain", [])
        chain.append(
            {
                "previous_run_id": previous_run_id,
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            }
        )
    existing["chatgpt_project_alias"] = project_alias
    existing["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    conversations[conversation_alias] = existing
    write_json(index_path, index)
    return index_path


def normalize_private_conversation_handle(text: str) -> JSON:
    reject_secret_text(text, "chatgpt_conversation_handle")
    if len(text.encode("utf-8")) > PRIVATE_HANDLE_MAX_BYTES:
        raise AssistError("chatgpt_conversation_handle is too large")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AssistError("chatgpt_conversation_handle must contain exactly one URL or conversation id")
    handle = lines[0]
    lowered = handle.lower()
    forbidden_markers = ("cookie", "localstorage", "oauth", "access_token", "refresh_token", "bearer ")
    if any(marker in lowered for marker in forbidden_markers):
        raise AssistError("chatgpt_conversation_handle must not contain credentials, tokens, cookies, or browser storage")
    if lowered.startswith(("http://", "https://")):
        parsed = urlparse(handle)
        host = (parsed.netloc or "").lower()
        if host not in {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"}:
            raise AssistError("chatgpt_conversation_handle URL must be a ChatGPT conversation URL")
        if "/share/" in parsed.path.lower():
            raise AssistError("chatgpt_conversation_handle must not be a share URL")
        return {"kind": "conversation_url", "value": handle}
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,256}", handle):
        raise AssistError("chatgpt_conversation_handle must be a single ChatGPT conversation URL or opaque id")
    return {"kind": "conversation_id", "value": handle}


def store_private_conversation_handle(
    root: Path,
    *,
    run_id: str,
    conversation_alias: str,
    project_alias: str,
    handle_file: Path,
    ttl_days: int,
) -> JSON:
    if ttl_days < PRIVATE_HANDLE_TTL_MIN_DAYS or ttl_days > PRIVATE_HANDLE_TTL_MAX_DAYS:
        raise AssistError(
            f"private_conversation_handle_ttl_days must be between {PRIVATE_HANDLE_TTL_MIN_DAYS} and {PRIVATE_HANDLE_TTL_MAX_DAYS}"
        )
    normalized = normalize_private_conversation_handle(read_text_file(handle_file, "chatgpt_conversation_handle_file"))
    state_path = root / "private" / PRIVATE_HANDLE_STATE_NAME
    state = read_json(
        state_path,
        {
            "packet_type": "chatgpt_web_private_conversation_handle_state",
            "storage_policy": "local_private_untracked_adapter_state",
            "not_for_upload": True,
            "handles": {},
        },
    )
    handles = state.setdefault("handles", {})
    if not isinstance(handles, dict):
        raise AssistError("private ChatGPT conversation handle state is invalid")
    now = datetime.now(timezone.utc).astimezone()
    expires_at = now + timedelta(days=ttl_days)
    handle_value = normalized["value"]
    handle_sha256 = hashlib.sha256(str(handle_value).encode("utf-8")).hexdigest()
    handles[run_id] = {
        "run_id": run_id,
        "chatgpt_project_alias": project_alias,
        "chatgpt_conversation_alias": conversation_alias,
        "handle_kind": normalized["kind"],
        "handle": handle_value,
        "handle_sha256": handle_sha256,
        "created_at": now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "storage_policy": "local_private_untracked_adapter_state",
        "not_for_upload": True,
    }
    write_json(state_path, state)
    return {
        "stored": True,
        "state_file": str(state_path),
        "handle_kind": normalized["kind"],
        "handle_sha256": handle_sha256,
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "storage_policy": "local_private_untracked_adapter_state",
        "not_for_upload": True,
    }


def load_run_request(root: Path, run_id: str) -> JSON:
    request_path = root / run_id / "chatgpt-web-request.json"
    request = read_json(request_path)
    if request.get("packet_type") != "chatgpt_web_primary_request":
        raise AssistError(f"{request_path} is not a chatgpt_web_primary_request packet")
    if request.get("run_id") != run_id:
        raise AssistError(f"{request_path} run_id does not match requested run {run_id!r}")
    if not isinstance(request.get("task_id"), str) or not request["task_id"]:
        raise AssistError(f"{request_path} is missing task_id")
    if not isinstance(request.get("workspace_id"), str) or not request["workspace_id"]:
        raise AssistError(f"{request_path} is missing workspace_id")
    return request


def prepare_web_run(
    *,
    objective: str,
    workspace_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
    paths: list[str] | None = None,
    storage: str | Path | None = None,
    chatgpt_project_alias: str = DEFAULT_CHATGPT_PROJECT_ALIAS,
    chatgpt_conversation_alias: str | None = None,
    upload_target: str = DEFAULT_UPLOAD_TARGET,
    user_instruction: str | None = None,
    user_instruction_file: str | Path | None = None,
    chatgpt_model: str | None = None,
    chatgpt_reasoning_effort: str | None = None,
    ui_probe_receipt_file: Path | None = None,
    chatgpt_conversation_handle_file: Path | None = None,
    allow_private_conversation_handle: bool = False,
    private_conversation_handle_ttl_days: int = 14,
    conversation_reuse_policy: str = "new_conversation",
    allow_conversation_followup: bool = False,
    previous_run_id: str | None = None,
    followup_context: str | None = None,
) -> JSON:
    reject_secret_text(objective, "objective")
    instruction = resolve_user_instruction(user_instruction=user_instruction, user_instruction_file=user_instruction_file)
    model_policy = infer_model_policy(
        instruction,
        chatgpt_model=chatgpt_model,
        chatgpt_reasoning_effort=chatgpt_reasoning_effort,
    )
    workspace_id = safe_id(workspace_id, "workspace_id")
    task_id = safe_id(task_id or slugify(objective), "task_id")
    run_id = safe_id(run_id or f"{task_id}-{now_stamp()}", "run_id")
    project_alias = safe_chatgpt_alias(chatgpt_project_alias, "chatgpt_project_alias")
    conversation_alias = safe_chatgpt_alias(chatgpt_conversation_alias or run_id, "chatgpt_conversation_alias")
    if upload_target not in UPLOAD_TARGETS:
        raise AssistError(f"upload_target must be one of: {', '.join(sorted(UPLOAD_TARGETS))}")
    if conversation_reuse_policy not in {"new_conversation", "followup_same_conversation"}:
        raise AssistError("conversation_reuse_policy is invalid")
    if followup_context:
        reject_secret_text(followup_context, "followup_context")
    root = storage_root(storage)
    if model_policy["model_key"] == "gpt55_pro":
        if ui_probe_receipt_file is None:
            receipt_path = write_blocked_ui_probe_receipt(
                root,
                run_id,
                model_policy,
                "GPT-5.5 Pro Extended requires a current ChatGPT Web UI probe receipt; no downgrade is allowed.",
            )
            raise AssistError(f"GPT-5.5 Pro Extended requires UI probe receipt: {receipt_path}")
        model_policy["ui_probe_receipt"] = validate_ui_probe_receipt_file(ui_probe_receipt_file, model_policy)

    create_result = create_assist_run(
        {
            "task_id": task_id,
            "run_id": run_id,
            "workspace_id": workspace_id,
            "goal": objective,
            "scope": [
                "ChatGPT Web performs planning, code reading, patch drafting, and report drafting.",
                "Local Codex only packages context, applies returned files locally, runs checks, and writes receipts.",
                f"Use ChatGPT Project alias {project_alias!r}; this alias is user-visible only.",
                f"Bind this local run one-to-one to ChatGPT Web conversation alias {conversation_alias!r}.",
            ],
            "constraints": [
                "Do not include secrets, tokens, cookies, sessions, passwords, private keys, or account credentials.",
                "Do not claim ChatGPT Web ran local tests.",
                "Return every proposed change as files or unified diff artifacts.",
                "Local Codex supervisor is the only verifier.",
                "Do not persist or request real ChatGPT project IDs, conversation IDs, share links, cookies, sessions, localStorage, or OAuth tokens.",
            ],
            "expected_artifacts": list(REQUIRED_WEB_ARTIFACTS),
            "verification_commands": ["local Codex supervisor checks from --check-json-file or --check"],
            "user_instruction": [instruction["content"]] if instruction["content"] else [],
            "redaction_confirmed": True,
            "redaction_confirmed_by": "local_codex_supervisor",
        },
        root,
    )
    list_args: JSON = {"run_id": run_id}
    if paths:
        list_args["paths"] = paths
    listed = list_workspace_files(list_args, root)
    bundle = create_workspace_bundle(list_args, root)
    bundle_sha256 = str(bundle.get("bundle_sha256") or "")
    if not bundle_sha256:
        raise AssistError("source bundle result is missing bundle_sha256")
    conversation_index_path = reserve_conversation_alias(
        root,
        run_id=run_id,
        conversation_alias=conversation_alias,
        project_alias=project_alias,
        source_bundle_sha256=bundle_sha256,
        allow_followup=allow_conversation_followup,
        previous_run_id=previous_run_id,
    )
    private_handle_metadata: JSON | None = None
    if chatgpt_conversation_handle_file:
        if not allow_private_conversation_handle:
            raise AssistError("private ChatGPT conversation handle storage requires explicit allow_private_conversation_handle")
        private_handle_metadata = store_private_conversation_handle(
            root,
            run_id=run_id,
            conversation_alias=conversation_alias,
            project_alias=project_alias,
            handle_file=chatgpt_conversation_handle_file,
            ttl_days=private_conversation_handle_ttl_days,
        )

    run_path = root / run_id
    prompt_path = run_path / "chatgpt-web-task-prompt.md"
    request_path = run_path / "chatgpt-web-request.json"
    upload_manifest_path = run_path / "upload-manifest.json"
    source_bundle_path = run_path / "source-files.zip"
    source_manifest_path = run_path / "source-files-manifest.json"
    request = {
        "packet_type": "chatgpt_web_primary_request",
        "task_id": task_id,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "objective": objective,
        "user_instruction": instruction,
        "chatgpt_model_policy": model_policy,
        "chatgpt_project": {
            "alias": project_alias,
            "upload_target": upload_target,
            "persistent_sources_allowed": upload_target == "project_sources",
            "refs_are_user_visible_aliases": True,
        },
        "chatgpt_conversation": {
            "alias": conversation_alias,
            "one_to_one_with_local_run": not allow_conversation_followup,
            "reuse_policy": conversation_reuse_policy,
            "refs_are_user_visible_aliases": True,
        },
        "source_bundle": bundle,
        "workspace_files": {
            "file_count": listed["file_count"],
            "total_bytes": listed["total_bytes"],
            "files": listed["files"],
            "skipped_count": listed["skipped_count"],
        },
        "output_contract": {
            "required_artifacts": list(REQUIRED_WEB_ARTIFACTS),
            "local_supervisor_required": True,
            "execution_plan_required": True,
            "patch_format": "unified_diff_or_git_format_patch",
            "testing_guide_required": True,
        },
        "git_context": bundle.get("git_context", {}),
    }
    write_json(request_path, request)
    source_manifest_sha256 = sha256_file(source_manifest_path)
    request_sha256 = sha256_file(request_path)
    prompt = f"""# ChatGPT Web primary execution task

You are the primary designer and implementation drafter for this run. Local Codex remains the supervisor: it packages context, dispatches accepted work units, applies returned changes locally, runs checks, and writes receipts.

## ChatGPT Project / Conversation

- Project alias: `{project_alias}`
- Conversation alias: `{conversation_alias}`
- Local run id: `{run_id}`
- Upload target: `{upload_target}`
- Required Web model: `{model_policy["model"]}`
- Required thinking effort: `{model_policy["reasoning_effort"]}`
- Required thinking effort UI label: `{model_policy["reasoning_effort_ui_label"]}`
- Highest-reasoning policy: first try the required model/effort pair and exact UI label. GPT-5.5 Thinking uses the highest visible `deep` / `深入` effort. GPT-5.5 Pro critical stages require `extended` / `Extended`; if Extended is not visible in the current ChatGPT Web UI, stop drafting code and return a blocked report with visible model, reasoning, and subscription-plan options only.
- This local run maps one-to-one to the current ChatGPT Web conversation. Do not mix multiple local runs into one Web conversation.
- Project alias and conversation alias are user-visible labels only. They are not ChatGPT internal IDs, URLs, or reusable login/session handles.
- The human user must manually select the model and thinking effort in ChatGPT Web. The connector and local scripts cannot set the Web model.

## Run identity / consistency gate

- Expected run_id: `{run_id}`
- Expected task_id: `{task_id}`
- Expected workspace_id: `{workspace_id}`
- Expected source bundle SHA-256: `{bundle_sha256}`
- Expected source manifest SHA-256: `{source_manifest_sha256}`
- Expected request SHA-256: `{request_sha256}`
- Before reading source or drafting changes, compare `chatgpt-web-request.json`, `source-files-manifest.json`, and this prompt. The run_id, task_id, workspace_id, upload target, and bundle hashes must match.
- If Project sources, conversation attachments, or this prompt belong to different runs, stop drafting code changes. Return `report.md` and `LIMITATIONS` explaining the mixed-run input.

## Objective

{objective}

## User-provided additional instruction

{instruction["content"] if instruction["content"] else "- None."}

## Follow-up local evidence

{followup_context if followup_context else "- None."}

## Uploaded files

- `{run_id}--source-files.zip`
- `{run_id}--source-files-manifest.json`
- `{run_id}--chatgpt-web-request.json`

## Mandatory rules

- You may use ChatGPT Web file analysis and container features to read the uploaded zip, analyze code, design the implementation, and draft artifacts.
- If files were uploaded to Project sources, treat them as read-only context for this run. If they were uploaded as conversation attachments, use them only in this conversation.
- Do not claim that you ran local tests, applied patches locally, committed Git changes, deployed anything, or completed delivery.
- Do not output tokens, API keys, SSH private keys, cookies, sessions, passwords, or real account credentials.
- Return all proposed work as artifacts. Prefer unified diff for code changes.
- Always return `codex-execution-plan.json`. This is the model-authored work decomposition that local Codex may dispatch serially or in parallel.
- Always return at least `changes.patch`, `report.md`, and `testing-guide.md`.
- `changes.patch` should preferably be a unified diff that passes `git apply --check`. If you need commit semantics, explain how local Codex can convert your work with `git format-patch` or `git am`.
- The source package is not a fake repository and ChatGPT Project sources are not a Git remote. It contains manifested files, `.chatgpt-harness` metadata, and metadata-only Git context. The .git history is not uploaded. `snapshot_head_commit` records the original `head_commit`, and dirty worktree file contents for manifested files are preserved in the bundle.
- Non-uploaded paths are intentionally absent, so do not report them as deleted. `.chatgpt-harness/directory-structure.json` is the real relative path manifest for the packaged subset, not a claim that the full repository tree was uploaded. Preserve relative paths in patch or replacement file artifacts; do not use absolute ChatGPT Web container paths. Do not run `git init` over the bundled source unless the local supervisor explicitly asks for a scratch repo for diff drafting.
- `testing-guide.md` must be detailed: include tests that cannot run inside ChatGPT Web, local Codex commands to run, each command's purpose, expected output, logs/screenshots/debug data to collect on failure, and the debug bundle content to send back in the next round.
- If the required model or thinking effort is unavailable in the current account/subscription, do not produce implementation artifacts under a lower-effort setting. Return `report.md` with `LIMITATIONS` describing the unavailable model/effort pair and the visible available options, without account identifiers.

## Required `codex-execution-plan.json`

Return a JSON object with this shape:

```json
{{
  "packet_type": "codex_execution_plan",
  "run_id": "{run_id}",
  "task_id": "{task_id}",
  "created_by": "chatgpt_web",
  "language": "en",
  "dispatch_strategy": "serial_then_parallel",
  "local_supervisor": "codex_main_thread",
  "workflow_context": {{
    "original_user_request": "Preserve the user's original request after redacting secrets.",
    "process_summary": [
      "The local harness packages scoped source context for ChatGPT Web analysis.",
      "ChatGPT Web drafts task decomposition, prompts, candidate patches, reports, and test guidance.",
      "Local Codex dispatches scoped units, verifies locally, and remains the delivery authority."
    ],
    "current_round": "Dispatch scoped implementation units after local validation.",
    "drift_guards": [
      "Workflow context is background only.",
      "Unit objective, owned paths, expected artifacts, acceptance checks, and supervisor gate override workflow background."
    ]
  }},
  "execution_units": [
    {{
      "id": "design",
      "title": "Design the implementation",
      "dispatch_mode": "serial",
      "prompt": "Produce the concrete design and acceptance criteria for local Codex.",
      "owned_paths": ["docs/example.md"],
      "depends_on": [],
      "expected_artifacts": ["design-notes.md"]
    }}
  ],
  "acceptance_checks": [
    ["python", "-m", "unittest", "tests.test_executor_contract_tools"]
  ]
}}
```

Use `workflow_context` to give downstream agents enough original intent and process history to use their reasoning ability well. It must also include `drift_guards` that prevent scope expansion. Use `dispatch_mode: "parallel"` only for units with disjoint owned paths. The plan text itself must be English runtime text. User-facing report prose can mention user language requirements separately.

## Return format

Use this exact artifact block format:

```text
ARTIFACT: codex-execution-plan.json
<complete JSON execution plan>

ARTIFACT: report.md
<markdown report>

ARTIFACT: changes.patch
<complete unified diff>

ARTIFACT: testing-guide.md
<detailed test standards, steps, expected results, failure diagnosis, and debug bundle guide>

LIMITATIONS:
- No local tests were run inside ChatGPT Web.

SUGGESTED_LOCAL_CHECKS:
- <checks local Codex should run>
```
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    prompt_sha256 = sha256_file(prompt_path)
    upload_dir = run_path / "upload"
    upload_files = [
        str(copy_upload_file(source_bundle_path, upload_dir, run_id).resolve()),
        str(copy_upload_file(source_manifest_path, upload_dir, run_id).resolve()),
        str(copy_upload_file(request_path, upload_dir, run_id).resolve()),
    ]
    run_identity = {
        "run_id": run_id,
        "task_id": task_id,
        "workspace_id": workspace_id,
        "chatgpt_project_alias": project_alias,
        "chatgpt_conversation_alias": conversation_alias,
        "upload_target": upload_target,
        "source_bundle_sha256": bundle_sha256,
        "source_manifest_sha256": source_manifest_sha256,
        "chatgpt_web_request_sha256": request_sha256,
        "chatgpt_web_task_prompt_sha256": prompt_sha256,
        "chatgpt_model": model_policy["model"],
        "chatgpt_model_key": model_policy["model_key"],
        "chatgpt_reasoning_effort": model_policy["reasoning_effort"],
        "chatgpt_reasoning_effort_ui_label": model_policy["reasoning_effort_ui_label"],
        "chatgpt_highest_reasoning_required": model_policy["highest_reasoning_required"],
        "chatgpt_subscription_probe_required": model_policy["subscription_probe_required"],
    }
    upload_manifest = {
        "packet_type": "chatgpt_web_upload_manifest",
        "run_id": run_id,
        "chatgpt_project_alias": project_alias,
        "chatgpt_conversation_alias": conversation_alias,
        "upload_target": upload_target,
        "run_identity": run_identity,
        "chatgpt_model_policy": model_policy,
        "user_instruction_source": instruction["source"],
        "user_instruction_file": instruction["path"],
        "user_instruction": instruction["content"],
        "conversation_index": str(conversation_index_path.resolve()),
        "upload_files": upload_files,
        "prompt_file": str(prompt_path.resolve()),
        "project_sources_files": [],
        "conversation_attachment_files": [],
        "operator_steps": [],
    }
    if upload_target == "project_sources":
        upload_manifest["project_sources_files"] = list(upload_manifest["upload_files"])
        upload_manifest["operator_steps"] = [
            f"Open ChatGPT Project {project_alias!r}.",
            "Upload the run-scoped project_sources_files to Project sources / files after manually reviewing the matching source-files-manifest JSON.",
            "Before sending, remove or ignore stale Project Sources bundles from previous local runs; never mix them with this run-scoped upload set.",
            "Confirm upload-manifest.json run_identity matches the prompt header and chatgpt-web-request JSON before sending.",
            "If any Project Sources file, conversation attachment, prompt, or request metadata belongs to a different run_id, stop and record a mixed-run limitation instead of drafting a patch.",
            f"Create exactly one new conversation for local run {run_id!r} and label it {conversation_alias!r} in your own notes.",
            f"Paste prompt_file into that conversation and first try model {model_policy['model']!r} with thinking effort {model_policy['reasoning_effort']!r} ({model_policy['reasoning_effort_ui_label']!r}) before sending.",
            "If that model/effort pair is unavailable, open the visible model/reasoning controls, run tools/chatgpt_web_simprint_bridge.py inspect-model-controls, and record only visible model labels, reasoning labels, and subscription plan label for local supervisor review.",
        ]
    else:
        upload_manifest["conversation_attachment_files"] = list(upload_manifest["upload_files"])
        upload_manifest["operator_steps"] = [
            f"Open ChatGPT Project {project_alias!r}.",
            f"Create exactly one new conversation for local run {run_id!r} and label it {conversation_alias!r} in your own notes.",
            "Attach the run-scoped conversation_attachment_files to the current conversation after manually reviewing the matching source-files-manifest JSON.",
            "Confirm upload-manifest.json run_identity matches the prompt header and chatgpt-web-request JSON before sending.",
            f"Paste prompt_file into that conversation and first try model {model_policy['model']!r} with thinking effort {model_policy['reasoning_effort']!r} ({model_policy['reasoning_effort_ui_label']!r}) before sending.",
            "If that model/effort pair is unavailable, open the visible model/reasoning controls, run tools/chatgpt_web_simprint_bridge.py inspect-model-controls, and record only visible model labels, reasoning labels, and subscription plan label for local supervisor review.",
        ]
    write_json(upload_manifest_path, upload_manifest)
    return {
        "ok": True,
        "run_id": run_id,
        "task_id": task_id,
        "workspace_id": workspace_id,
        "chatgpt_project_alias": project_alias,
        "chatgpt_conversation_alias": conversation_alias,
        "upload_target": upload_target,
        "user_instruction_source": instruction["source"],
        "conversation_index": str(conversation_index_path),
        "storage_root": str(root),
        "run_dir": str(run_path),
        "prompt_file": str(prompt_path),
        "request_file": str(request_path),
        "upload_manifest": str(upload_manifest_path),
        "run_identity": run_identity,
        "chatgpt_model_policy": model_policy,
        "private_conversation_handle": private_handle_metadata or {"stored": False},
        "bundle": bundle,
        "file_count": listed["file_count"],
        "total_bytes": listed["total_bytes"],
        "next_step": "Review upload-manifest.json, manually upload the listed files to ChatGPT Web, fill prompt_file, then import/apply returned artifacts.",
        "create_result": create_result,
    }


def import_web_run(*, run_id: str, raw_text_file: Path, storage: str | Path | None = None) -> JSON:
    run_id = safe_id(run_id, "run_id")
    root = storage_root(storage)
    request = load_run_request(root, run_id)
    workspace = get_registered_workspace(str(request["workspace_id"]), root)
    return import_chatgpt_response(
        raw_text=raw_text_file.read_text(encoding="utf-8-sig"),
        workspace_root=workspace["root"],
        response_dir=Path(workspace["root"]) / ".tmp" / "chatgpt-web" / run_id / "response",
        request_packet_id=f"cgw_req_{run_id}",
        task_id=str(request["task_id"]),
        run_id=run_id,
    )


def apply_web_run(
    *,
    run_id: str,
    checks: list[list[str]],
    storage: str | Path | None = None,
    keep_failed: bool = False,
) -> JSON:
    run_id = safe_id(run_id, "run_id")
    root = storage_root(storage)
    request = load_run_request(root, run_id)
    workspace = get_registered_workspace(str(request["workspace_id"]), root)
    return apply_response_patches(
        workspace_root=workspace["root"],
        response_dir=Path(workspace["root"]) / ".tmp" / "chatgpt-web" / run_id / "response",
        receipt_path=Path(workspace["root"]) / ".tmp" / "chatgpt-web" / run_id / "local-supervisor-receipt.json",
        check_commands=checks,
        keep_failed=keep_failed,
    )


def _read_followup_file(path: Path, label: str) -> str:
    resolved = path.resolve()
    content = read_text_file(resolved, label)
    reject_secret_text(content, label)
    return content


def prepare_followup(
    *,
    previous_run_id: str,
    objective: str,
    run_id: str | None = None,
    task_id: str | None = None,
    storage: str | Path | None = None,
    local_receipt_file: Path | None = None,
    log_file: Path | None = None,
    diff_file: Path | None = None,
    ui_probe_receipt_file: Path | None = None,
) -> JSON:
    previous_run_id = safe_id(previous_run_id, "previous_run_id")
    root = storage_root(storage)
    previous_request = load_run_request(root, previous_run_id)
    project = previous_request.get("chatgpt_project", {})
    conversation = previous_request.get("chatgpt_conversation", {})
    model_policy = previous_request.get("chatgpt_model_policy", {})
    evidence_sections = [
        "This is a follow-up to the same ChatGPT Web conversation. Reuse the previous context and focus on the local failure evidence below.",
        f"Previous run id: {previous_run_id}",
    ]
    if local_receipt_file:
        evidence_sections.append("### Local supervisor receipt\n```json\n" + _read_followup_file(local_receipt_file, "local_receipt_file") + "\n```")
    if log_file:
        evidence_sections.append("### Local log tail\n```text\n" + _read_followup_file(log_file, "log_file") + "\n```")
    if diff_file:
        evidence_sections.append("### Local diff\n```diff\n" + _read_followup_file(diff_file, "diff_file") + "\n```")
    followup_context = "\n\n".join(evidence_sections)
    return prepare_web_run(
        objective=objective,
        workspace_id=str(previous_request["workspace_id"]),
        run_id=run_id,
        task_id=task_id,
        paths=[str(item["path"]) for item in previous_request.get("workspace_files", {}).get("files", []) if isinstance(item, dict) and item.get("path")],
        storage=root,
        chatgpt_project_alias=str(project.get("alias") or DEFAULT_CHATGPT_PROJECT_ALIAS),
        chatgpt_conversation_alias=str(conversation.get("alias") or previous_run_id),
        upload_target=str(project.get("upload_target") or DEFAULT_UPLOAD_TARGET),
        user_instruction=followup_context,
        chatgpt_model=str(model_policy.get("model") or DEFAULT_CHATGPT_MODEL),
        chatgpt_reasoning_effort=str(model_policy.get("reasoning_effort") or DEFAULT_CHATGPT_REASONING_EFFORT),
        ui_probe_receipt_file=ui_probe_receipt_file,
        conversation_reuse_policy="followup_same_conversation",
        allow_conversation_followup=True,
        previous_run_id=previous_run_id,
        followup_context=followup_context,
    )


def upload_project_sources(*, run_id: str, mode: str, storage: str | Path | None = None) -> JSON:
    if mode not in {"manual", "cdp-if-available"}:
        raise AssistError("upload mode must be manual or cdp-if-available")
    run_id = safe_id(run_id, "run_id")
    root = storage_root(storage)
    run_path = root / run_id
    manifest = read_json(run_path / "upload-manifest.json")
    upload_files = manifest.get("project_sources_files") or manifest.get("upload_files") or []
    if not isinstance(upload_files, list) or not upload_files:
        raise AssistError("upload manifest has no project source files")
    receipt = {
        "packet_type": "chatgpt_web_project_sources_upload_receipt",
        "run_id": run_id,
        "mode": mode,
        "status": "manual_steps_required" if mode == "manual" else "cdp_not_attempted_manual_fallback",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "chatgpt_project_alias": manifest.get("chatgpt_project_alias"),
        "chatgpt_conversation_alias": manifest.get("chatgpt_conversation_alias"),
        "source_bundle_sha256": manifest.get("run_identity", {}).get("source_bundle_sha256"),
        "upload_files": upload_files,
        "operator_steps": manifest.get("operator_steps", []),
        "private_handles_recorded": False,
    }
    receipt_path = run_path / "project-sources-upload-receipt.json"
    write_json(receipt_path, receipt)
    return {**receipt, "receipt_path": str(receipt_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_prepare_parser(name: str) -> argparse.ArgumentParser:
        prepare_parser = subparsers.add_parser(name, help="Create source bundle, request file, and ChatGPT Web prompt")
        prepare_parser.add_argument("--objective", required=True)
        prepare_parser.add_argument("--user-instruction")
        prepare_parser.add_argument("--user-instruction-file", type=Path)
        prepare_parser.add_argument("--workspace-id", required=True)
        prepare_parser.add_argument("--run-id")
        prepare_parser.add_argument("--task-id")
        prepare_parser.add_argument("--path", action="append", dest="paths")
        prepare_parser.add_argument("--chatgpt-project-alias", default=DEFAULT_CHATGPT_PROJECT_ALIAS)
        prepare_parser.add_argument("--chatgpt-conversation-alias")
        prepare_parser.add_argument("--chatgpt-conversation-handle-file", type=Path)
        prepare_parser.add_argument("--allow-private-conversation-handle", action="store_true")
        prepare_parser.add_argument("--private-conversation-handle-ttl-days", type=int, default=14)
        prepare_parser.add_argument("--chatgpt-model", default=None)
        prepare_parser.add_argument("--chatgpt-reasoning-effort", default=None)
        prepare_parser.add_argument("--ui-probe-receipt-file", type=Path)
        prepare_parser.add_argument("--upload-target", choices=sorted(UPLOAD_TARGETS), default=DEFAULT_UPLOAD_TARGET)
        return prepare_parser

    add_prepare_parser("prepare")
    add_prepare_parser("prepare-run")

    followup = subparsers.add_parser("prepare-followup", help="Prepare a follow-up packet for the same ChatGPT Web conversation")
    followup.add_argument("--previous-run-id", required=True)
    followup.add_argument("--objective", required=True)
    followup.add_argument("--run-id")
    followup.add_argument("--task-id")
    followup.add_argument("--local-receipt-file", type=Path)
    followup.add_argument("--log-file", type=Path)
    followup.add_argument("--diff-file", type=Path)
    followup.add_argument("--ui-probe-receipt-file", type=Path)

    import_cmd = subparsers.add_parser("import-response", help="Import copied/extracted ChatGPT Web artifact response")
    import_cmd.add_argument("--run-id", required=True)
    import_cmd.add_argument("--raw-text-file", required=True, type=Path)

    import_alias = subparsers.add_parser("import-web-artifacts", help="Alias for import-response")
    import_alias.add_argument("--run-id", required=True)
    import_alias.add_argument("--raw-text-file", required=True, type=Path)

    apply_cmd = subparsers.add_parser("apply-and-verify", help="Apply returned patches and run local checks")
    apply_cmd.add_argument("--run-id", required=True)
    apply_cmd.add_argument("--keep-failed", action="store_true")
    apply_cmd.add_argument("--check", action="append")
    apply_cmd.add_argument("--check-json-file", action="append", type=Path)

    upload_cmd = subparsers.add_parser("upload-project-sources", help="Write manual/CDP-if-available project source upload receipt")
    upload_cmd.add_argument("--run-id", required=True)
    upload_cmd.add_argument("--mode", choices=["manual", "cdp-if-available"], default="manual")

    inspect_cmd = subparsers.add_parser("inspect-model-controls", help="Inspect visible ChatGPT Web model controls through Simprint/CDP")
    inspect_cmd.add_argument("--port", type=int)
    inspect_cmd.add_argument("--target-id")
    inspect_cmd.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command in {"prepare", "prepare-run"}:
            result = prepare_web_run(
                objective=args.objective,
                workspace_id=args.workspace_id,
                run_id=args.run_id,
                task_id=args.task_id,
                paths=args.paths,
                storage=args.storage_root,
                chatgpt_project_alias=args.chatgpt_project_alias,
                chatgpt_conversation_alias=args.chatgpt_conversation_alias,
                upload_target=args.upload_target,
                user_instruction=args.user_instruction,
                user_instruction_file=args.user_instruction_file,
                chatgpt_model=args.chatgpt_model,
                chatgpt_reasoning_effort=args.chatgpt_reasoning_effort,
                ui_probe_receipt_file=args.ui_probe_receipt_file,
                chatgpt_conversation_handle_file=args.chatgpt_conversation_handle_file,
                allow_private_conversation_handle=args.allow_private_conversation_handle,
                private_conversation_handle_ttl_days=args.private_conversation_handle_ttl_days,
            )
        elif args.command == "prepare-followup":
            result = prepare_followup(
                previous_run_id=args.previous_run_id,
                objective=args.objective,
                run_id=args.run_id,
                task_id=args.task_id,
                storage=args.storage_root,
                local_receipt_file=args.local_receipt_file,
                log_file=args.log_file,
                diff_file=args.diff_file,
                ui_probe_receipt_file=args.ui_probe_receipt_file,
            )
        elif args.command in {"import-response", "import-web-artifacts"}:
            result = import_web_run(run_id=args.run_id, raw_text_file=args.raw_text_file, storage=args.storage_root)
        elif args.command == "apply-and-verify":
            checks: list[list[str]] = []
            for value in args.check or []:
                parsed = json.loads(value)
                if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
                    raise AssistError("--check must be a JSON string array")
                checks.append(parsed)
            for path in args.check_json_file or []:
                checks.append(read_json_list(path))
            result = apply_web_run(
                run_id=args.run_id,
                checks=checks,
                storage=args.storage_root,
                keep_failed=args.keep_failed,
            )
        elif args.command == "upload-project-sources":
            result = upload_project_sources(run_id=args.run_id, mode=args.mode, storage=args.storage_root)
        elif args.command == "inspect-model-controls":
            from chatgpt_web_simprint_bridge import discover, inspect_model_controls

            found = discover(args.port)
            result = inspect_model_controls(int(found["port"]), target_id=args.target_id, output=args.output)
        else:
            raise AssistError(f"unknown command: {args.command}")
    except (AssistError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
