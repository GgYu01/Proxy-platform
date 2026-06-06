#!/usr/bin/env python3
"""Validate ChatGPT Web manual-assist packet manifests.

The manual-assist workflow is intentionally separate from the Executor Run
Contract because ChatGPT Web is a human-operated external assist channel, not a
programmatic executor adapter.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


VALID_PACKET_TYPES = {
    "chatgpt_web_request",
    "chatgpt_web_primary_request",
    "chatgpt_web_upload_manifest",
    "chatgpt_web_response",
    "local_supervisor_receipt",
}
VALID_UPLOAD_TARGETS = {"conversation", "project_sources"}
REQUIRED_WEB_ARTIFACTS = {"codex-execution-plan.json", "report.md", "changes.patch", "testing-guide.md"}
VALID_PURPOSES = {
    "implementation_draft",
    "review",
    "repair",
    "final_report_draft",
}
VALID_LEVELS = {"R0", "D0", "L0", "L1", "L2", "L3", "L4", "L5", "L6", "G0"}
VALID_REASONING_EFFORTS = {"fast", "standard", "advanced", "deep", "extended"}
REASONING_EFFORT_RANK = ["fast", "standard", "advanced", "deep", "extended"]
VALID_CHATGPT_MODEL_KEYS = {"gpt55_thinking", "gpt55_pro", "custom"}
KNOWN_MODEL_REQUIRED_REASONING = {
    "gpt55_thinking": "deep",
    "gpt55_pro": "extended",
}
SENSITIVE_KEY_FRAGMENTS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "database_password",
    "db_password",
    "id_rsa",
    "id_ed25519",
    "password",
    "private_key",
    "session",
    "ssh_key",
    "token",
}
FORBIDDEN_ALIAS_FRAGMENTS = SENSITIVE_KEY_FRAGMENTS | {
    "chatgpt.com",
    "localstorage",
    "oauth",
    "share",
}
SECRET_TEXT_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|authorization|bearer|password|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}"),
]


class ValidationError(ValueError):
    """Raised when a manual-assist packet is invalid."""


class ValidationResult:
    def __init__(self, ok: bool, kind: str) -> None:
        self.ok = ok
        self.kind = kind


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{name} must be a boolean")
    return value


def _require_plain_alias(value: Any, name: str) -> str:
    alias = _require_string(value, name).strip()
    if len(alias) > 80:
        raise ValidationError(f"{name} must be at most 80 characters")
    if "://" in alias or "/" in alias or "\\" in alias:
        raise ValidationError(f"{name} must be a plain user-visible alias, not a URL or path")
    if any(ord(char) < 32 or ord(char) == 127 for char in alias):
        raise ValidationError(f"{name} must not contain control characters")
    lowered = alias.lower()
    for fragment in FORBIDDEN_ALIAS_FRAGMENTS:
        if fragment in lowered:
            raise ValidationError(f"{name} appears to contain a private or sensitive reference")
    return alias


def _reject_secret_text(value: str, name: str) -> None:
    for pattern in SECRET_TEXT_PATTERNS:
        if pattern.search(value):
            raise ValidationError(f"{name} appears to contain plaintext secret material")


def _require_keys(payload: dict[str, Any], keys: list[str], prefix: str) -> None:
    for key in keys:
        if key not in payload:
            raise ValidationError(f"{prefix}.{key} is required")


def _reject_unknown_fields(payload: dict[str, Any], allowed: set[str], prefix: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValidationError(f"{prefix} contains unknown fields: {unknown}")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _require_non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValidationError(f"{name} must be a non-negative integer")
    return value


def _validate_source_file_record(value: Any, name: str) -> dict[str, Any]:
    record = _require_mapping(value, name)
    _reject_unknown_fields(record, {"path", "sha256", "size_bytes"}, name)
    path_value = _require_string(record.get("path"), f"{name}.path")
    normalized = path_value.replace("\\", "/")
    if path_value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path_value) or ".." in normalized.split("/"):
        raise ValidationError(f"{name}.path must be a safe relative path")
    sha256 = _require_string(record.get("sha256"), f"{name}.sha256")
    if not _is_sha256(sha256):
        raise ValidationError(f"{name}.sha256 must be 64 hex characters")
    _require_non_negative_int(record.get("size_bytes"), f"{name}.size_bytes")
    return record


def _path_is_ignored_workspace_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/")
    return normalized.startswith(".tmp/") or normalized.startswith("tmp/")


def _validate_safe_relative_path(path_value: str, name: str, *, allow_tmp: bool) -> str:
    normalized = path_value.replace("\\", "/")
    parts = normalized.split("/")
    if path_value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path_value) or ".." in parts or "" in parts:
        raise ValidationError(f"{name} must be a safe relative path")
    if not allow_tmp and (normalized.startswith(".tmp/") or normalized.startswith("tmp/") or normalized.startswith(".git/")):
        raise ValidationError(f"{name} must be a non-temporary worktree path")
    return normalized


def _validate_candidate_target_path(path_value: str, name: str) -> str:
    normalized = path_value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        path_value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", path_value)
        or ".." in parts
        or "" in parts
        or normalized.startswith(".git/")
        or normalized.startswith(".tmp/")
        or normalized.startswith("tmp/")
    ):
        raise ValidationError(f"{name} must be a safe non-temporary relative path")
    return normalized


def _scan_sensitive_keys(value: Any, path: str = "packet") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = key.lower()
            for fragment in SENSITIVE_KEY_FRAGMENTS:
                if fragment in lowered:
                    raise ValidationError(f"{path}.{key} contains forbidden sensitive field name")
            _scan_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_sensitive_keys(nested, f"{path}[{index}]")


def _validate_artifact_like(payload: dict[str, Any], prefix: str, require_contains_secrets: bool = False) -> None:
    allowed = {"name", "path", "sha256", "type", "content_class", "contains_secrets", "delivery_mode", "target_path"}
    _reject_unknown_fields(payload, allowed, prefix)
    _require_keys(payload, ["name", "path", "sha256"], prefix)
    _require_string(payload["name"], f"{prefix}.name")
    path_value = _require_string(payload["path"], f"{prefix}.path")
    if not _path_is_ignored_workspace_path(path_value):
        raise ValidationError(f"{prefix}.path must be under .tmp/ or tmp/")
    sha256 = _require_string(payload["sha256"], f"{prefix}.sha256")
    if sha256 != "<LOCAL_SUPERVISOR_TO_FILL>" and not _is_sha256(sha256):
        raise ValidationError(f"{prefix}.sha256 must be 64 hex characters")
    if "contains_secrets" in payload:
        contains_secrets = _require_bool(payload["contains_secrets"], f"{prefix}.contains_secrets")
        if contains_secrets:
            raise ValidationError(f"{prefix}.contains_secrets must be false")
    elif require_contains_secrets:
        raise ValidationError(f"{prefix}.contains_secrets is required")
    if "delivery_mode" in payload:
        delivery_mode = _require_string(payload["delivery_mode"], f"{prefix}.delivery_mode")
        if delivery_mode not in {"artifact", "full_file_candidate"}:
            raise ValidationError(f"{prefix}.delivery_mode is invalid")
        if delivery_mode == "full_file_candidate":
            _validate_candidate_target_path(_require_string(payload.get("target_path"), f"{prefix}.target_path"), f"{prefix}.target_path")
    elif "target_path" in payload:
        raise ValidationError(f"{prefix}.delivery_mode is required when target_path is set")


def _require_upload_file_list(value: Any, name: str) -> list[str]:
    files = _require_list(value, name)
    result: list[str] = []
    for index, item in enumerate(files):
        path = _require_string(item, f"{name}[{index}]")
        filename = path.replace("\\", "/").rsplit("/", 1)[-1]
        if not (
            filename == "source-files.zip"
            or filename.endswith("--source-files.zip")
            or filename == "source-files-manifest.json"
            or filename.endswith("--source-files-manifest.json")
            or filename == "chatgpt-web-request.json"
            or filename.endswith("--chatgpt-web-request.json")
        ):
            raise ValidationError(f"{name}[{index}] is not an expected upload file")
        result.append(path)
    return result


def _classify_run_scoped_upload(path_value: str, run_id: str) -> str:
    filename = path_value.replace("\\", "/").rsplit("/", 1)[-1]
    prefix = f"{run_id}--"
    if not filename.startswith(prefix):
        raise ValidationError(f"upload file {filename!r} is not scoped to run_id {run_id!r}")
    bare_name = filename[len(prefix) :]
    if bare_name == "source-files.zip":
        return "source_bundle"
    if bare_name == "source-files-manifest.json":
        return "source_manifest"
    if bare_name == "chatgpt-web-request.json":
        return "request"
    raise ValidationError(f"upload file {filename!r} has an unexpected run-scoped suffix")


def _require_exact_run_scoped_upload_set(paths: list[str], run_id: str, name: str) -> None:
    counts = {"source_bundle": 0, "source_manifest": 0, "request": 0}
    for path in paths:
        counts[_classify_run_scoped_upload(path, run_id)] += 1
    bad_counts = {kind: count for kind, count in counts.items() if count != 1}
    if bad_counts:
        raise ValidationError(f"{name} must contain exactly one run-scoped source zip, manifest, and request JSON: {bad_counts}")


def _validate_run_identity(payload: dict[str, Any], prefix: str, parent: dict[str, Any]) -> None:
    _reject_unknown_fields(
        payload,
        {
            "run_id",
            "task_id",
            "workspace_id",
            "chatgpt_project_alias",
            "chatgpt_conversation_alias",
            "upload_target",
            "source_bundle_sha256",
            "source_manifest_sha256",
            "chatgpt_web_request_sha256",
            "chatgpt_web_task_prompt_sha256",
            "chatgpt_model",
            "chatgpt_model_key",
            "chatgpt_reasoning_effort",
            "chatgpt_reasoning_effort_ui_label",
            "chatgpt_highest_reasoning_required",
            "chatgpt_subscription_probe_required",
        },
        prefix,
    )
    _require_keys(
        payload,
        [
            "run_id",
            "task_id",
            "workspace_id",
            "chatgpt_project_alias",
            "chatgpt_conversation_alias",
            "upload_target",
            "source_bundle_sha256",
            "source_manifest_sha256",
            "chatgpt_web_request_sha256",
            "chatgpt_web_task_prompt_sha256",
            "chatgpt_model",
            "chatgpt_model_key",
            "chatgpt_reasoning_effort",
            "chatgpt_reasoning_effort_ui_label",
            "chatgpt_highest_reasoning_required",
            "chatgpt_subscription_probe_required",
        ],
        prefix,
    )
    for key in ("run_id", "task_id", "workspace_id"):
        _require_string(payload[key], f"{prefix}.{key}")
    _require_plain_alias(payload["chatgpt_project_alias"], f"{prefix}.chatgpt_project_alias")
    _require_plain_alias(payload["chatgpt_conversation_alias"], f"{prefix}.chatgpt_conversation_alias")
    upload_target = _require_string(payload["upload_target"], f"{prefix}.upload_target")
    if upload_target not in VALID_UPLOAD_TARGETS:
        raise ValidationError(f"{prefix}.upload_target is invalid")
    for key in (
        "source_bundle_sha256",
        "source_manifest_sha256",
        "chatgpt_web_request_sha256",
        "chatgpt_web_task_prompt_sha256",
    ):
        if not _is_sha256(_require_string(payload[key], f"{prefix}.{key}")):
            raise ValidationError(f"{prefix}.{key} must be 64 hex characters")
    for key in ("run_id", "chatgpt_project_alias", "chatgpt_conversation_alias", "upload_target"):
        if payload[key] != parent[key]:
            raise ValidationError(f"{prefix}.{key} must match ChatGPTWebUploadManifest.{key}")
    if _require_string(payload["chatgpt_model_key"], f"{prefix}.chatgpt_model_key") not in VALID_CHATGPT_MODEL_KEYS:
        raise ValidationError(f"{prefix}.chatgpt_model_key is invalid")
    if _require_string(payload["chatgpt_reasoning_effort"], f"{prefix}.chatgpt_reasoning_effort") not in VALID_REASONING_EFFORTS:
        raise ValidationError(f"{prefix}.chatgpt_reasoning_effort is invalid")
    _require_string(payload["chatgpt_reasoning_effort_ui_label"], f"{prefix}.chatgpt_reasoning_effort_ui_label")
    _require_bool(payload["chatgpt_highest_reasoning_required"], f"{prefix}.chatgpt_highest_reasoning_required")
    _require_bool(payload["chatgpt_subscription_probe_required"], f"{prefix}.chatgpt_subscription_probe_required")


def _validate_chatgpt_model_policy(value: Any, label: str) -> dict[str, Any]:
    model_policy = _require_mapping(value, label)
    _reject_unknown_fields(
        model_policy,
        {
            "model",
            "model_key",
            "reasoning_effort",
            "reasoning_effort_ui_label",
            "reasoning_effort_rank",
            "selection_strategy",
            "source",
            "web_ui_selection_required",
            "connector_sets_model",
            "highest_reasoning_required",
            "subscription_probe_required",
            "fallback_detection_policy",
            "available_reasoning_efforts",
            "fallback_reasoning_efforts",
            "model_catalog",
            "availability_probe",
            "ui_probe_receipt",
        },
        label,
    )
    _require_keys(
        model_policy,
        [
            "model",
            "model_key",
            "reasoning_effort",
            "reasoning_effort_ui_label",
            "reasoning_effort_rank",
            "selection_strategy",
            "source",
            "web_ui_selection_required",
            "connector_sets_model",
            "highest_reasoning_required",
            "subscription_probe_required",
            "fallback_detection_policy",
            "available_reasoning_efforts",
            "fallback_reasoning_efforts",
            "model_catalog",
            "availability_probe",
        ],
        label,
    )
    _require_string(model_policy["model"], f"{label}.model")
    model_key = _require_string(model_policy["model_key"], f"{label}.model_key")
    if model_key not in VALID_CHATGPT_MODEL_KEYS:
        raise ValidationError(f"{label}.model_key is invalid")
    reasoning_effort = _require_string(model_policy["reasoning_effort"], f"{label}.reasoning_effort")
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        raise ValidationError(f"{label}.reasoning_effort is invalid")
    _require_string(model_policy["reasoning_effort_ui_label"], f"{label}.reasoning_effort_ui_label")
    rank = _require_list(model_policy["reasoning_effort_rank"], f"{label}.reasoning_effort_rank")
    if rank != REASONING_EFFORT_RANK:
        raise ValidationError(f"{label}.reasoning_effort_rank must be {REASONING_EFFORT_RANK}")
    if model_policy["selection_strategy"] != "highest_visible_available":
        raise ValidationError(f"{label}.selection_strategy is invalid")
    if model_policy["source"] not in {"default", "explicit_args", "user_instruction"}:
        raise ValidationError(f"{label}.source is invalid")
    if _require_bool(model_policy["web_ui_selection_required"], f"{label}.web_ui_selection_required") is not True:
        raise ValidationError(f"{label}.web_ui_selection_required must be true")
    if _require_bool(model_policy["connector_sets_model"], f"{label}.connector_sets_model") is not False:
        raise ValidationError(f"{label}.connector_sets_model must be false")
    highest_required = _require_bool(model_policy["highest_reasoning_required"], f"{label}.highest_reasoning_required")
    subscription_probe = _require_bool(model_policy["subscription_probe_required"], f"{label}.subscription_probe_required")
    if model_key in {"gpt55_thinking", "gpt55_pro"}:
        required = KNOWN_MODEL_REQUIRED_REASONING[model_key]
        if reasoning_effort != required:
            raise ValidationError(f"{label}.reasoning_effort must be {required} for known GPT-5.5 model {model_key}")
        if not highest_required or not subscription_probe:
            raise ValidationError(f"{label} must require highest reasoning and subscription probe for known GPT-5.5 models")
    _require_string(model_policy["fallback_detection_policy"], f"{label}.fallback_detection_policy")
    available_top = _require_list(model_policy["available_reasoning_efforts"], f"{label}.available_reasoning_efforts")
    if not all(isinstance(item, str) and item in VALID_REASONING_EFFORTS for item in available_top):
        raise ValidationError(f"{label}.available_reasoning_efforts contains invalid entries")
    if reasoning_effort not in available_top and model_key in {"gpt55_thinking", "gpt55_pro"}:
        raise ValidationError(f"{label}.available_reasoning_efforts must include reasoning_effort")
    fallback = _require_list(model_policy["fallback_reasoning_efforts"], f"{label}.fallback_reasoning_efforts")
    if not all(isinstance(item, str) and item in VALID_REASONING_EFFORTS for item in fallback):
        raise ValidationError(f"{label}.fallback_reasoning_efforts contains invalid entries")
    catalog = _require_list(model_policy["model_catalog"], f"{label}.model_catalog")
    for index, item in enumerate(catalog):
        entry = _require_mapping(item, f"{label}.model_catalog[{index}]")
        _reject_unknown_fields(
            entry,
            {
                "model_key",
                "model",
                "required_reasoning_effort",
                "required_reasoning_effort_ui_label",
                "available_reasoning_efforts",
                "fallback_reasoning_efforts",
            },
            f"{label}.model_catalog[{index}]",
        )
        catalog_model_key = _require_string(entry.get("model_key"), f"{label}.model_catalog[{index}].model_key")
        if catalog_model_key not in VALID_CHATGPT_MODEL_KEYS - {"custom"}:
            raise ValidationError(f"{label}.model_catalog[{index}].model_key is invalid")
        _require_string(entry.get("model"), f"{label}.model_catalog[{index}].model")
        catalog_required = _require_string(
            entry.get("required_reasoning_effort"),
            f"{label}.model_catalog[{index}].required_reasoning_effort",
        )
        if catalog_required != KNOWN_MODEL_REQUIRED_REASONING[catalog_model_key]:
            raise ValidationError(
                f"{label}.model_catalog[{index}].required_reasoning_effort must be {KNOWN_MODEL_REQUIRED_REASONING[catalog_model_key]}"
            )
        _require_string(entry.get("required_reasoning_effort_ui_label"), f"{label}.model_catalog[{index}].required_reasoning_effort_ui_label")
        available = _require_list(entry.get("available_reasoning_efforts"), f"{label}.model_catalog[{index}].available_reasoning_efforts")
        if not all(isinstance(item, str) and item in VALID_REASONING_EFFORTS for item in available):
            raise ValidationError(f"{label}.model_catalog[{index}].available_reasoning_efforts contains invalid entries")
        if catalog_required not in available:
            raise ValidationError(f"{label}.model_catalog[{index}].available_reasoning_efforts must include required_reasoning_effort")
        catalog_fallback = _require_list(entry.get("fallback_reasoning_efforts"), f"{label}.model_catalog[{index}].fallback_reasoning_efforts")
        if not all(isinstance(item, str) and item in VALID_REASONING_EFFORTS for item in catalog_fallback):
            raise ValidationError(f"{label}.model_catalog[{index}].fallback_reasoning_efforts contains invalid entries")
    probe = _require_mapping(model_policy["availability_probe"], f"{label}.availability_probe")
    _reject_unknown_fields(
        probe,
        {"required", "evidence_source", "record_subscription_plan", "allowed_record_fields", "forbidden_record_fields"},
        f"{label}.availability_probe",
    )
    if _require_bool(probe.get("required"), f"{label}.availability_probe.required") is not subscription_probe:
        raise ValidationError(f"{label}.availability_probe.required must match subscription_probe_required")
    if _require_string(probe.get("evidence_source"), f"{label}.availability_probe.evidence_source") != "current_chatgpt_web_ui":
        raise ValidationError(f"{label}.availability_probe.evidence_source is invalid")
    if _require_bool(probe.get("record_subscription_plan"), f"{label}.availability_probe.record_subscription_plan") is not True:
        raise ValidationError(f"{label}.availability_probe.record_subscription_plan must be true")
    for key in ("allowed_record_fields", "forbidden_record_fields"):
        values = _require_list(probe.get(key), f"{label}.availability_probe.{key}")
        if not all(isinstance(item, str) and item.strip() for item in values):
            raise ValidationError(f"{label}.availability_probe.{key} must contain non-empty strings")
    if "ui_probe_receipt" in model_policy:
        receipt = _require_mapping(model_policy["ui_probe_receipt"], f"{label}.ui_probe_receipt")
        _reject_unknown_fields(
            receipt,
            {"status", "observed_at", "evidence_source", "required_model", "required_effort", "selected_model_label", "selected_reasoning_effort_label", "available_model_labels", "available_reasoning_effort_labels", "available_reasoning_efforts", "subscription_plan_label"},
            f"{label}.ui_probe_receipt",
        )
        if _require_string(receipt.get("status"), f"{label}.ui_probe_receipt.status") != "available":
            raise ValidationError(f"{label}.ui_probe_receipt.status must be available")
        if _require_string(receipt.get("evidence_source"), f"{label}.ui_probe_receipt.evidence_source") != "current_chatgpt_web_ui":
            raise ValidationError(f"{label}.ui_probe_receipt.evidence_source is invalid")
        if _require_string(receipt.get("required_effort"), f"{label}.ui_probe_receipt.required_effort") != reasoning_effort:
            raise ValidationError(f"{label}.ui_probe_receipt.required_effort must match reasoning_effort")
    return model_policy


def validate_request(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ChatGPTWebRequest")
    _reject_unknown_fields(
        payload,
        {
            "packet_type",
            "packet_id",
            "task_id",
            "run_id",
            "channel",
            "purpose",
            "created_at",
            "redaction",
            "inputs",
            "output_contract",
            "verification",
            "operator_actions",
        },
        "ChatGPTWebRequest",
    )
    _require_keys(
        payload,
        [
            "packet_type",
            "packet_id",
            "task_id",
            "run_id",
            "channel",
            "purpose",
            "created_at",
            "redaction",
            "inputs",
            "output_contract",
            "verification",
        ],
        "ChatGPTWebRequest",
    )
    if payload["packet_type"] != "chatgpt_web_request":
        raise ValidationError("ChatGPTWebRequest.packet_type is invalid")
    if payload["channel"] != "chatgpt_web_manual":
        raise ValidationError("ChatGPTWebRequest.channel must be chatgpt_web_manual")
    if payload["purpose"] not in VALID_PURPOSES:
        raise ValidationError("ChatGPTWebRequest.purpose is invalid")
    for key in ("packet_id", "task_id", "run_id", "created_at"):
        _require_string(payload[key], f"ChatGPTWebRequest.{key}")

    redaction = _require_mapping(payload["redaction"], "ChatGPTWebRequest.redaction")
    _reject_unknown_fields(redaction, {"status", "excluded"}, "ChatGPTWebRequest.redaction")
    _require_keys(redaction, ["status", "excluded"], "ChatGPTWebRequest.redaction")
    if redaction["status"] != "confirmed":
        raise ValidationError("ChatGPTWebRequest.redaction.status must be confirmed")
    excluded = _require_list(redaction["excluded"], "ChatGPTWebRequest.redaction.excluded")
    if not excluded:
        raise ValidationError("ChatGPTWebRequest.redaction.excluded must not be empty")

    inputs = _require_list(payload["inputs"], "ChatGPTWebRequest.inputs")
    if not inputs:
        raise ValidationError("ChatGPTWebRequest.inputs must not be empty")
    for index, artifact in enumerate(inputs):
        _validate_artifact_like(
            _require_mapping(artifact, f"ChatGPTWebRequest.inputs[{index}]"),
            f"ChatGPTWebRequest.inputs[{index}]",
            require_contains_secrets=True,
        )

    output_contract = _require_mapping(payload["output_contract"], "ChatGPTWebRequest.output_contract")
    _reject_unknown_fields(
        output_contract,
        {"required_artifacts", "forbidden_outputs"},
        "ChatGPTWebRequest.output_contract",
    )
    _require_keys(output_contract, ["required_artifacts", "forbidden_outputs"], "ChatGPTWebRequest.output_contract")
    if not _require_list(output_contract["required_artifacts"], "ChatGPTWebRequest.output_contract.required_artifacts"):
        raise ValidationError("ChatGPTWebRequest.output_contract.required_artifacts must not be empty")
    if not _require_list(output_contract["forbidden_outputs"], "ChatGPTWebRequest.output_contract.forbidden_outputs"):
        raise ValidationError("ChatGPTWebRequest.output_contract.forbidden_outputs must not be empty")

    verification = _require_mapping(payload["verification"], "ChatGPTWebRequest.verification")
    _reject_unknown_fields(verification, {"local_supervisor_required", "commands"}, "ChatGPTWebRequest.verification")
    _require_keys(verification, ["local_supervisor_required", "commands"], "ChatGPTWebRequest.verification")
    if _require_bool(verification["local_supervisor_required"], "ChatGPTWebRequest.verification.local_supervisor_required") is not True:
        raise ValidationError("ChatGPTWebRequest.verification.local_supervisor_required must be true")
    _require_list(verification["commands"], "ChatGPTWebRequest.verification.commands")
    return ValidationResult(ok=True, kind="ChatGPTWebRequest")


def validate_primary_request(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ChatGPTWebPrimaryRequest")
    _reject_unknown_fields(
        payload,
        {
            "packet_type",
            "task_id",
            "run_id",
            "workspace_id",
            "created_at",
            "objective",
            "user_instruction",
            "chatgpt_model_policy",
            "chatgpt_project",
            "chatgpt_conversation",
            "source_bundle",
            "workspace_files",
            "output_contract",
            "git_context",
        },
        "ChatGPTWebPrimaryRequest",
    )
    _require_keys(
        payload,
        [
            "packet_type",
            "task_id",
            "run_id",
            "workspace_id",
            "created_at",
            "objective",
            "chatgpt_model_policy",
            "chatgpt_project",
            "chatgpt_conversation",
            "source_bundle",
            "workspace_files",
            "output_contract",
        ],
        "ChatGPTWebPrimaryRequest",
    )
    if payload["packet_type"] != "chatgpt_web_primary_request":
        raise ValidationError("ChatGPTWebPrimaryRequest.packet_type is invalid")
    for key in ("task_id", "run_id", "workspace_id", "created_at", "objective"):
        _require_string(payload[key], f"ChatGPTWebPrimaryRequest.{key}")
    if "user_instruction" in payload:
        instruction = _require_mapping(payload["user_instruction"], "ChatGPTWebPrimaryRequest.user_instruction")
        _reject_unknown_fields(
            instruction,
            {"source", "path", "content"},
            "ChatGPTWebPrimaryRequest.user_instruction",
        )
        _require_keys(instruction, ["source", "path", "content"], "ChatGPTWebPrimaryRequest.user_instruction")
        source = _require_string(instruction["source"], "ChatGPTWebPrimaryRequest.user_instruction.source")
        if source not in {"none", "inline", "file"}:
            raise ValidationError("ChatGPTWebPrimaryRequest.user_instruction.source is invalid")
        if not isinstance(instruction["content"], str):
            raise ValidationError("ChatGPTWebPrimaryRequest.user_instruction.content must be a string")
        _reject_secret_text(instruction["content"], "ChatGPTWebPrimaryRequest.user_instruction.content")
        if source == "file":
            _require_string(instruction["path"], "ChatGPTWebPrimaryRequest.user_instruction.path")
            if not instruction["content"].strip():
                raise ValidationError("ChatGPTWebPrimaryRequest.user_instruction.content must not be empty for file source")
        elif instruction["path"] is not None:
            raise ValidationError("ChatGPTWebPrimaryRequest.user_instruction.path must be null unless source is file")

    _validate_chatgpt_model_policy(
        payload["chatgpt_model_policy"],
        "ChatGPTWebPrimaryRequest.chatgpt_model_policy",
    )

    project = _require_mapping(payload["chatgpt_project"], "ChatGPTWebPrimaryRequest.chatgpt_project")
    _reject_unknown_fields(
        project,
        {"alias", "upload_target", "persistent_sources_allowed", "refs_are_user_visible_aliases"},
        "ChatGPTWebPrimaryRequest.chatgpt_project",
    )
    _require_keys(
        project,
        ["alias", "upload_target", "persistent_sources_allowed", "refs_are_user_visible_aliases"],
        "ChatGPTWebPrimaryRequest.chatgpt_project",
    )
    _require_plain_alias(project["alias"], "ChatGPTWebPrimaryRequest.chatgpt_project.alias")
    if project["upload_target"] not in VALID_UPLOAD_TARGETS:
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_project.upload_target is invalid")
    persistent = _require_bool(
        project["persistent_sources_allowed"],
        "ChatGPTWebPrimaryRequest.chatgpt_project.persistent_sources_allowed",
    )
    if persistent != (project["upload_target"] == "project_sources"):
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_project.persistent_sources_allowed must match upload_target")
    if _require_bool(
        project["refs_are_user_visible_aliases"],
        "ChatGPTWebPrimaryRequest.chatgpt_project.refs_are_user_visible_aliases",
    ) is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_project.refs_are_user_visible_aliases must be true")

    conversation = _require_mapping(payload["chatgpt_conversation"], "ChatGPTWebPrimaryRequest.chatgpt_conversation")
    _reject_unknown_fields(
        conversation,
        {"alias", "one_to_one_with_local_run", "reuse_policy", "refs_are_user_visible_aliases"},
        "ChatGPTWebPrimaryRequest.chatgpt_conversation",
    )
    _require_keys(
        conversation,
        ["alias", "one_to_one_with_local_run", "refs_are_user_visible_aliases"],
        "ChatGPTWebPrimaryRequest.chatgpt_conversation",
    )
    _require_plain_alias(conversation["alias"], "ChatGPTWebPrimaryRequest.chatgpt_conversation.alias")
    one_to_one = _require_bool(
        conversation["one_to_one_with_local_run"],
        "ChatGPTWebPrimaryRequest.chatgpt_conversation.one_to_one_with_local_run",
    )
    reuse_policy = conversation.get("reuse_policy", "new_conversation")
    if reuse_policy not in {"new_conversation", "followup_same_conversation"}:
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_conversation.reuse_policy is invalid")
    if one_to_one is not True and reuse_policy != "followup_same_conversation":
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_conversation.one_to_one_with_local_run can be false only for follow-up reuse")
    if _require_bool(
        conversation["refs_are_user_visible_aliases"],
        "ChatGPTWebPrimaryRequest.chatgpt_conversation.refs_are_user_visible_aliases",
    ) is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.chatgpt_conversation.refs_are_user_visible_aliases must be true")

    source_bundle = _require_mapping(payload["source_bundle"], "ChatGPTWebPrimaryRequest.source_bundle")
    _reject_unknown_fields(
        source_bundle,
        {
            "ok",
            "run_id",
            "workspace_id",
            "bundle_path",
            "manifest_path",
            "bundle_sha256",
            "file_count",
            "total_bytes",
            "next_step",
            "path_preservation",
            "git_context",
        },
        "ChatGPTWebPrimaryRequest.source_bundle",
    )
    _require_keys(
        source_bundle,
        ["bundle_path", "manifest_path", "bundle_sha256", "file_count", "total_bytes"],
        "ChatGPTWebPrimaryRequest.source_bundle",
    )
    if "ok" in source_bundle and _require_bool(source_bundle["ok"], "ChatGPTWebPrimaryRequest.source_bundle.ok") is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.ok must be true")
    if "run_id" in source_bundle and _require_string(source_bundle["run_id"], "ChatGPTWebPrimaryRequest.source_bundle.run_id") != payload["run_id"]:
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.run_id must match ChatGPTWebPrimaryRequest.run_id")
    if "workspace_id" in source_bundle and _require_string(source_bundle["workspace_id"], "ChatGPTWebPrimaryRequest.source_bundle.workspace_id") != payload["workspace_id"]:
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.workspace_id must match ChatGPTWebPrimaryRequest.workspace_id")
    _require_string(source_bundle.get("bundle_path"), "ChatGPTWebPrimaryRequest.source_bundle.bundle_path")
    _require_string(source_bundle.get("manifest_path"), "ChatGPTWebPrimaryRequest.source_bundle.manifest_path")
    if not _path_is_ignored_workspace_path(str(source_bundle["bundle_path"])):
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.bundle_path must be under .tmp/ or tmp/")
    if not _path_is_ignored_workspace_path(str(source_bundle["manifest_path"])):
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.manifest_path must be under .tmp/ or tmp/")
    if not _is_sha256(_require_string(source_bundle["bundle_sha256"], "ChatGPTWebPrimaryRequest.source_bundle.bundle_sha256")):
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle.bundle_sha256 must be 64 hex characters")
    bundle_file_count = _require_non_negative_int(source_bundle["file_count"], "ChatGPTWebPrimaryRequest.source_bundle.file_count")
    bundle_total_bytes = _require_non_negative_int(source_bundle["total_bytes"], "ChatGPTWebPrimaryRequest.source_bundle.total_bytes")

    workspace_files = _require_mapping(payload["workspace_files"], "ChatGPTWebPrimaryRequest.workspace_files")
    _reject_unknown_fields(
        workspace_files,
        {"file_count", "total_bytes", "files", "skipped_count"},
        "ChatGPTWebPrimaryRequest.workspace_files",
    )
    _require_keys(workspace_files, ["file_count", "total_bytes", "files", "skipped_count"], "ChatGPTWebPrimaryRequest.workspace_files")
    workspace_file_count = _require_non_negative_int(workspace_files["file_count"], "ChatGPTWebPrimaryRequest.workspace_files.file_count")
    workspace_total_bytes = _require_non_negative_int(workspace_files["total_bytes"], "ChatGPTWebPrimaryRequest.workspace_files.total_bytes")
    _require_non_negative_int(workspace_files["skipped_count"], "ChatGPTWebPrimaryRequest.workspace_files.skipped_count")
    files = _require_list(workspace_files["files"], "ChatGPTWebPrimaryRequest.workspace_files.files")
    if workspace_file_count != len(files):
        raise ValidationError("ChatGPTWebPrimaryRequest.workspace_files.file_count must match files length")
    computed_total_bytes = 0
    for index, file_record in enumerate(files):
        record = _validate_source_file_record(file_record, f"ChatGPTWebPrimaryRequest.workspace_files.files[{index}]")
        computed_total_bytes += int(record["size_bytes"])
    if workspace_total_bytes != computed_total_bytes:
        raise ValidationError("ChatGPTWebPrimaryRequest.workspace_files.total_bytes must match file size sum")
    if bundle_file_count != workspace_file_count or bundle_total_bytes != workspace_total_bytes:
        raise ValidationError("ChatGPTWebPrimaryRequest.source_bundle counts must match workspace_files counts")

    output_contract = _require_mapping(payload["output_contract"], "ChatGPTWebPrimaryRequest.output_contract")
    _reject_unknown_fields(
        output_contract,
        {"required_artifacts", "local_supervisor_required", "execution_plan_required", "patch_format", "testing_guide_required"},
        "ChatGPTWebPrimaryRequest.output_contract",
    )
    required_artifacts = _require_list(output_contract.get("required_artifacts"), "ChatGPTWebPrimaryRequest.output_contract.required_artifacts")
    if not required_artifacts:
        raise ValidationError("ChatGPTWebPrimaryRequest.output_contract.required_artifacts must not be empty")
    if not REQUIRED_WEB_ARTIFACTS.issubset(set(required_artifacts)):
        raise ValidationError("ChatGPTWebPrimaryRequest.output_contract.required_artifacts must include codex-execution-plan.json, report.md, changes.patch, and testing-guide.md")
    if _require_bool(
        output_contract.get("local_supervisor_required"),
        "ChatGPTWebPrimaryRequest.output_contract.local_supervisor_required",
    ) is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.output_contract.local_supervisor_required must be true")
    if "testing_guide_required" in output_contract and _require_bool(
        output_contract["testing_guide_required"],
        "ChatGPTWebPrimaryRequest.output_contract.testing_guide_required",
    ) is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.output_contract.testing_guide_required must be true")
    if "execution_plan_required" in output_contract and _require_bool(
        output_contract["execution_plan_required"],
        "ChatGPTWebPrimaryRequest.output_contract.execution_plan_required",
    ) is not True:
        raise ValidationError("ChatGPTWebPrimaryRequest.output_contract.execution_plan_required must be true")
    if "patch_format" in output_contract:
        _require_string(output_contract["patch_format"], "ChatGPTWebPrimaryRequest.output_contract.patch_format")
    return ValidationResult(ok=True, kind="ChatGPTWebPrimaryRequest")


def validate_upload_manifest(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ChatGPTWebUploadManifest")
    _reject_unknown_fields(
        payload,
        {
            "packet_type",
            "run_id",
            "chatgpt_project_alias",
            "chatgpt_conversation_alias",
            "upload_target",
            "run_identity",
            "chatgpt_model_policy",
            "user_instruction_source",
            "user_instruction_file",
            "user_instruction",
            "conversation_index",
            "upload_files",
            "prompt_file",
            "project_sources_files",
            "conversation_attachment_files",
            "operator_steps",
        },
        "ChatGPTWebUploadManifest",
    )
    _require_keys(
        payload,
        [
            "packet_type",
            "run_id",
            "chatgpt_project_alias",
            "chatgpt_conversation_alias",
            "upload_target",
            "run_identity",
            "chatgpt_model_policy",
            "user_instruction_source",
            "user_instruction",
            "upload_files",
            "prompt_file",
            "project_sources_files",
            "conversation_attachment_files",
            "operator_steps",
        ],
        "ChatGPTWebUploadManifest",
    )
    if payload["packet_type"] != "chatgpt_web_upload_manifest":
        raise ValidationError("ChatGPTWebUploadManifest.packet_type is invalid")
    _require_string(payload["run_id"], "ChatGPTWebUploadManifest.run_id")
    _require_plain_alias(payload["chatgpt_project_alias"], "ChatGPTWebUploadManifest.chatgpt_project_alias")
    _require_plain_alias(payload["chatgpt_conversation_alias"], "ChatGPTWebUploadManifest.chatgpt_conversation_alias")
    upload_target = _require_string(payload["upload_target"], "ChatGPTWebUploadManifest.upload_target")
    if upload_target not in VALID_UPLOAD_TARGETS:
        raise ValidationError("ChatGPTWebUploadManifest.upload_target is invalid")
    run_identity = _require_mapping(payload["run_identity"], "ChatGPTWebUploadManifest.run_identity")
    _validate_run_identity(run_identity, "ChatGPTWebUploadManifest.run_identity", payload)
    model_policy = _validate_chatgpt_model_policy(
        payload["chatgpt_model_policy"],
        "ChatGPTWebUploadManifest.chatgpt_model_policy",
    )
    if model_policy["model"] != run_identity.get("chatgpt_model"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.model must match run_identity.chatgpt_model")
    if model_policy["model_key"] != run_identity.get("chatgpt_model_key"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.model_key must match run_identity.chatgpt_model_key")
    if model_policy["reasoning_effort"] != run_identity.get("chatgpt_reasoning_effort"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.reasoning_effort must match run_identity.chatgpt_reasoning_effort")
    if model_policy["reasoning_effort_ui_label"] != run_identity.get("chatgpt_reasoning_effort_ui_label"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.reasoning_effort_ui_label must match run_identity.chatgpt_reasoning_effort_ui_label")
    if model_policy["highest_reasoning_required"] != run_identity.get("chatgpt_highest_reasoning_required"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.highest_reasoning_required must match run_identity.chatgpt_highest_reasoning_required")
    if model_policy["subscription_probe_required"] != run_identity.get("chatgpt_subscription_probe_required"):
        raise ValidationError("ChatGPTWebUploadManifest.chatgpt_model_policy.subscription_probe_required must match run_identity.chatgpt_subscription_probe_required")
    source = _require_string(payload["user_instruction_source"], "ChatGPTWebUploadManifest.user_instruction_source")
    if source not in {"none", "inline", "file"}:
        raise ValidationError("ChatGPTWebUploadManifest.user_instruction_source is invalid")
    if source == "file":
        _require_string(payload.get("user_instruction_file"), "ChatGPTWebUploadManifest.user_instruction_file")
    elif payload.get("user_instruction_file") is not None:
        raise ValidationError("ChatGPTWebUploadManifest.user_instruction_file must be null unless user_instruction_source is file")
    if not isinstance(payload["user_instruction"], str):
        raise ValidationError("ChatGPTWebUploadManifest.user_instruction must be a string")
    _reject_secret_text(payload["user_instruction"], "ChatGPTWebUploadManifest.user_instruction")
    if source == "none" and payload["user_instruction"]:
        raise ValidationError("ChatGPTWebUploadManifest.user_instruction must be empty when user_instruction_source is none")
    if source in {"inline", "file"} and not payload["user_instruction"].strip():
        raise ValidationError("ChatGPTWebUploadManifest.user_instruction must not be empty for inline/file source")
    _require_string(payload["prompt_file"], "ChatGPTWebUploadManifest.prompt_file")

    upload_files = _require_upload_file_list(payload["upload_files"], "ChatGPTWebUploadManifest.upload_files")
    _require_exact_run_scoped_upload_set(upload_files, payload["run_id"], "ChatGPTWebUploadManifest.upload_files")
    project_sources = _require_upload_file_list(
        payload["project_sources_files"],
        "ChatGPTWebUploadManifest.project_sources_files",
    )
    conversation_files = _require_upload_file_list(
        payload["conversation_attachment_files"],
        "ChatGPTWebUploadManifest.conversation_attachment_files",
    )
    steps = _require_list(payload["operator_steps"], "ChatGPTWebUploadManifest.operator_steps")
    if not steps or not all(isinstance(item, str) and item.strip() for item in steps):
        raise ValidationError("ChatGPTWebUploadManifest.operator_steps must contain non-empty strings")
    if upload_target == "project_sources":
        if project_sources != upload_files or conversation_files:
            raise ValidationError("ChatGPTWebUploadManifest project_sources target must put all upload_files in project_sources_files only")
        _require_exact_run_scoped_upload_set(project_sources, payload["run_id"], "ChatGPTWebUploadManifest.project_sources_files")
    if upload_target == "conversation":
        if conversation_files != upload_files or project_sources:
            raise ValidationError("ChatGPTWebUploadManifest conversation target must put all upload_files in conversation_attachment_files only")
        _require_exact_run_scoped_upload_set(conversation_files, payload["run_id"], "ChatGPTWebUploadManifest.conversation_attachment_files")
    return ValidationResult(ok=True, kind="ChatGPTWebUploadManifest")


def validate_response(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ChatGPTWebResponse")
    _reject_unknown_fields(
        payload,
        {
            "packet_type",
            "packet_id",
            "request_packet_id",
            "task_id",
            "run_id",
            "channel",
            "producer",
            "artifacts",
            "self_reported_verification",
            "limitations",
        },
        "ChatGPTWebResponse",
    )
    _require_keys(
        payload,
        [
            "packet_type",
            "packet_id",
            "request_packet_id",
            "task_id",
            "run_id",
            "channel",
            "producer",
            "artifacts",
            "self_reported_verification",
            "limitations",
        ],
        "ChatGPTWebResponse",
    )
    if payload["packet_type"] != "chatgpt_web_response":
        raise ValidationError("ChatGPTWebResponse.packet_type is invalid")
    if payload["channel"] != "chatgpt_web_manual":
        raise ValidationError("ChatGPTWebResponse.channel must be chatgpt_web_manual")
    if payload["producer"] != "chatgpt_web":
        raise ValidationError("ChatGPTWebResponse.producer must be chatgpt_web")
    for key in ("packet_id", "request_packet_id", "task_id", "run_id"):
        _require_string(payload[key], f"ChatGPTWebResponse.{key}")

    artifacts = _require_list(payload["artifacts"], "ChatGPTWebResponse.artifacts")
    if not artifacts:
        raise ValidationError("ChatGPTWebResponse.artifacts must not be empty")
    for index, artifact in enumerate(artifacts):
        _validate_artifact_like(
            _require_mapping(artifact, f"ChatGPTWebResponse.artifacts[{index}]"),
            f"ChatGPTWebResponse.artifacts[{index}]",
        )
    _require_list(payload["self_reported_verification"], "ChatGPTWebResponse.self_reported_verification")
    _require_list(payload["limitations"], "ChatGPTWebResponse.limitations")
    return ValidationResult(ok=True, kind="ChatGPTWebResponse")


def validate_supervisor_receipt(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "LocalSupervisorReceipt")
    _reject_unknown_fields(
        payload,
        {
            "packet_type",
            "packet_id",
            "request_packet_id",
            "response_packet_id",
            "task_id",
            "run_id",
            "local_gate_status",
            "checks",
            "accepted_artifacts",
            "accepted_worktree_paths",
            "known_risks",
        },
        "LocalSupervisorReceipt",
    )
    _require_keys(
        payload,
        [
            "packet_type",
            "packet_id",
            "request_packet_id",
            "response_packet_id",
            "task_id",
            "run_id",
            "local_gate_status",
            "checks",
            "accepted_artifacts",
            "known_risks",
        ],
        "LocalSupervisorReceipt",
    )
    if payload["packet_type"] != "local_supervisor_receipt":
        raise ValidationError("LocalSupervisorReceipt.packet_type is invalid")
    if payload["local_gate_status"] not in {"passed", "failed", "blocked"}:
        raise ValidationError("LocalSupervisorReceipt.local_gate_status is invalid")
    for key in ("packet_id", "request_packet_id", "response_packet_id", "task_id", "run_id"):
        _require_string(payload[key], f"LocalSupervisorReceipt.{key}")

    checks = _require_list(payload["checks"], "LocalSupervisorReceipt.checks")
    if payload["local_gate_status"] == "passed" and not checks:
        raise ValidationError("LocalSupervisorReceipt passed requires at least one check")
    for index, check in enumerate(checks):
        check = _require_mapping(check, f"LocalSupervisorReceipt.checks[{index}]")
        _reject_unknown_fields(
            check,
            {"name", "level", "status", "command", "exit_code", "log_uri"},
            f"LocalSupervisorReceipt.checks[{index}]",
        )
        _require_keys(check, ["name", "level", "status", "command", "exit_code"], f"LocalSupervisorReceipt.checks[{index}]")
        _require_string(check["name"], f"LocalSupervisorReceipt.checks[{index}].name")
        if check["level"] not in VALID_LEVELS:
            raise ValidationError(f"LocalSupervisorReceipt.checks[{index}].level is invalid")
        if check["status"] not in {"passed", "failed", "skipped", "blocked"}:
            raise ValidationError(f"LocalSupervisorReceipt.checks[{index}].status is invalid")
        if not isinstance(check["command"], str):
            raise ValidationError(f"LocalSupervisorReceipt.checks[{index}].command must be a string")
        if not isinstance(check["exit_code"], int):
            raise ValidationError(f"LocalSupervisorReceipt.checks[{index}].exit_code must be an integer")
    if payload["local_gate_status"] == "passed":
        incomplete = [
            check["name"]
            for check in checks
            if check["status"] != "passed" or check["exit_code"] != 0
        ]
        if incomplete:
            raise ValidationError(f"LocalSupervisorReceipt passed requires all checks to pass: {incomplete}")
    _require_list(payload["accepted_artifacts"], "LocalSupervisorReceipt.accepted_artifacts")
    if "accepted_worktree_paths" in payload:
        for index, path_value in enumerate(_require_list(payload["accepted_worktree_paths"], "LocalSupervisorReceipt.accepted_worktree_paths")):
            _validate_safe_relative_path(
                _require_string(path_value, f"LocalSupervisorReceipt.accepted_worktree_paths[{index}]"),
                f"LocalSupervisorReceipt.accepted_worktree_paths[{index}]",
                allow_tmp=False,
            )
    _require_list(payload["known_risks"], "LocalSupervisorReceipt.known_risks")
    return ValidationResult(ok=True, kind="LocalSupervisorReceipt")


def detect_and_validate(payload: Any) -> ValidationResult:
    packet = _require_mapping(payload, "packet")
    _scan_sensitive_keys(packet)
    packet_type = packet.get("packet_type")
    if packet_type not in VALID_PACKET_TYPES:
        raise ValidationError(f"packet.packet_type is invalid: {packet_type}")
    if packet_type == "chatgpt_web_request":
        return validate_request(packet)
    if packet_type == "chatgpt_web_primary_request":
        return validate_primary_request(packet)
    if packet_type == "chatgpt_web_upload_manifest":
        return validate_upload_manifest(packet)
    if packet_type == "chatgpt_web_response":
        return validate_response(packet)
    return validate_supervisor_receipt(packet)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="Manual-assist packet JSON file")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.packet.read_text(encoding="utf-8"))
        result = detect_and_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    print(f"valid: {result.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
