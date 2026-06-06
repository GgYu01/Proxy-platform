#!/usr/bin/env python3
"""Validate the Codex harness provider registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


VALID_KINDS = {"executor", "future_executor", "assist_channel"}
VALID_STATUSES = {"preferred", "available", "blocked", "capability_probe", "disabled"}
VALID_AUTHORITIES = {"executor", "candidate_artifact_only"}
VALID_FAMILIES = {"chatgpt", "codex", "cursor", "antigravity", "claude", "opencode", "custom"}
VALID_CHATGPT_REASONING_RANK = ["fast", "standard", "advanced", "deep", "extended"]
KNOWN_CHATGPT_MODEL_REQUIRED_REASONING = {
    "gpt55_thinking": {
        "required": "deep",
        "ui_label": "深入",
        "available": ["fast", "standard", "advanced", "deep"],
        "fallback": ["advanced", "standard", "fast"],
    },
    "gpt55_pro": {
        "required": "extended",
        "ui_label": "Extended",
        "available": ["standard", "advanced", "extended"],
        "fallback": [],
    },
}
REQUIRED_PRO_EXTENDED_STAGES = {
    "requirements_analysis",
    "architecture_design",
    "complex_debug_root_cause",
    "rework_decision",
    "final_evaluation_summary",
}


class RegistryValidationError(ValueError):
    """Raised when the provider registry violates harness boundaries."""


class RegistryValidationResult:
    def __init__(self, ok: bool, provider_count: int) -> None:
        self.ok = ok
        self.provider_count = provider_count


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryValidationError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistryValidationError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(f"{name} must be a non-empty string")
    return value


def _validate_chatgpt_model_policy(value: Any, provider_id: str) -> None:
    policy = _require_mapping(value, f"{provider_id}.model_policy")
    selection_owner = _require_string(policy.get("selection_owner"), f"{provider_id}.model_policy.selection_owner")
    if selection_owner != "human_operator_in_chatgpt_web_ui":
        raise RegistryValidationError(f"{provider_id}.model_policy.selection_owner is invalid")
    if _require_string(policy.get("selection_strategy"), f"{provider_id}.model_policy.selection_strategy") != "highest_visible_available":
        raise RegistryValidationError(f"{provider_id}.model_policy.selection_strategy is invalid")
    rank = _require_list(policy.get("reasoning_effort_rank"), f"{provider_id}.model_policy.reasoning_effort_rank")
    if rank != VALID_CHATGPT_REASONING_RANK:
        raise RegistryValidationError(f"{provider_id}.model_policy.reasoning_effort_rank must be {VALID_CHATGPT_REASONING_RANK}")
    default_model_key = _require_string(policy.get("default_model_key"), f"{provider_id}.model_policy.default_model_key")
    models = _require_list(policy.get("models"), f"{provider_id}.model_policy.models")
    if not models:
        raise RegistryValidationError(f"{provider_id}.model_policy.models must not be empty")
    seen_model_keys: set[str] = set()
    for index, item in enumerate(models):
        model = _require_mapping(item, f"{provider_id}.model_policy.models[{index}]")
        model_key = _require_string(model.get("model_key"), f"{provider_id}.model_policy.models[{index}].model_key")
        seen_model_keys.add(model_key)
        _require_string(model.get("model"), f"{provider_id}.model_policy.models[{index}].model")
        expected = KNOWN_CHATGPT_MODEL_REQUIRED_REASONING.get(model_key)
        if expected is None:
            raise RegistryValidationError(f"{provider_id}.model_policy.models[{index}].model_key is not supported: {model_key}")
        if _require_string(model.get("required_reasoning_effort"), f"{provider_id}.model_policy.models[{index}].required_reasoning_effort") != expected["required"]:
            raise RegistryValidationError(
                f"{provider_id}.model_policy.models[{index}].required_reasoning_effort must be {expected['required']}"
            )
        if _require_string(model.get("required_reasoning_effort_ui_label"), f"{provider_id}.model_policy.models[{index}].required_reasoning_effort_ui_label") != expected["ui_label"]:
            raise RegistryValidationError(
                f"{provider_id}.model_policy.models[{index}].required_reasoning_effort_ui_label must be {expected['ui_label']}"
            )
        available = _require_list(model.get("available_reasoning_efforts"), f"{provider_id}.model_policy.models[{index}].available_reasoning_efforts")
        if available != expected["available"]:
            raise RegistryValidationError(
                f"{provider_id}.model_policy.models[{index}].available_reasoning_efforts must be {expected['available']}"
            )
        fallback = _require_list(model.get("fallback_reasoning_efforts"), f"{provider_id}.model_policy.models[{index}].fallback_reasoning_efforts")
        if fallback != expected["fallback"]:
            raise RegistryValidationError(
                f"{provider_id}.model_policy.models[{index}].fallback_reasoning_efforts must be {expected['fallback']}"
            )
    if default_model_key not in seen_model_keys:
        raise RegistryValidationError(f"{provider_id}.model_policy.default_model_key must match a listed model")
    if policy.get("availability_probe_required") is not True:
        raise RegistryValidationError(f"{provider_id}.model_policy.availability_probe_required must be true")
    if _require_string(policy.get("fallback_detection_policy"), f"{provider_id}.model_policy.fallback_detection_policy") != "try_required_first_then_detect_available_ui_options":
        raise RegistryValidationError(f"{provider_id}.model_policy.fallback_detection_policy is invalid")
    required_stages = set(_require_list(policy.get("gpt55_pro_extended_required_stages"), f"{provider_id}.model_policy.gpt55_pro_extended_required_stages"))
    missing = sorted(REQUIRED_PRO_EXTENDED_STAGES - required_stages)
    if missing:
        raise RegistryValidationError(f"{provider_id}.model_policy.gpt55_pro_extended_required_stages missing: {missing}")
    receipt_policy = _require_mapping(policy.get("ui_probe_receipt_policy"), f"{provider_id}.model_policy.ui_probe_receipt_policy")
    if _require_string(receipt_policy.get("evidence_source"), f"{provider_id}.model_policy.ui_probe_receipt_policy.evidence_source") != "current_chatgpt_web_ui":
        raise RegistryValidationError(f"{provider_id}.model_policy.ui_probe_receipt_policy.evidence_source is invalid")
    if _require_string(receipt_policy.get("missing_required_evidence"), f"{provider_id}.model_policy.ui_probe_receipt_policy.missing_required_evidence") != "write_blocked_receipt_no_downgrade":
        raise RegistryValidationError(f"{provider_id}.model_policy.ui_probe_receipt_policy.missing_required_evidence is invalid")
    allowed_fields = _require_list(receipt_policy.get("allowed_record_fields"), f"{provider_id}.model_policy.ui_probe_receipt_policy.allowed_record_fields")
    forbidden_fields = _require_list(receipt_policy.get("forbidden_record_fields"), f"{provider_id}.model_policy.ui_probe_receipt_policy.forbidden_record_fields")
    if "available_reasoning_efforts" not in allowed_fields:
        raise RegistryValidationError(f"{provider_id}.model_policy.ui_probe_receipt_policy.allowed_record_fields must include available_reasoning_efforts")
    if not {"cookies", "session", "oauth_token"}.issubset(set(forbidden_fields)):
        raise RegistryValidationError(f"{provider_id}.model_policy.ui_probe_receipt_policy.forbidden_record_fields is incomplete")
    _require_string(policy.get("source"), f"{provider_id}.model_policy.source")


def load_registry(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_registry(registry: dict[str, Any]) -> RegistryValidationResult:
    registry = _require_mapping(registry, "registry")
    if registry.get("registry_type") != "harness_provider_registry":
        raise RegistryValidationError("registry.registry_type must be harness_provider_registry")
    if registry.get("version") != 1:
        raise RegistryValidationError("registry.version must be 1")
    providers = _require_list(registry.get("providers"), "registry.providers")
    if not providers:
        raise RegistryValidationError("registry.providers must not be empty")
    family_defaults = _require_mapping(registry.get("family_defaults"), "registry.family_defaults")

    seen: set[str] = set()
    seen_aliases: dict[str, str] = {}
    provider_families: dict[str, str] = {}
    for index, provider_value in enumerate(providers):
        provider = _require_mapping(provider_value, f"registry.providers[{index}]")
        provider_id = _require_string(provider.get("id"), f"registry.providers[{index}].id")
        if provider_id in seen:
            raise RegistryValidationError(f"duplicate provider id: {provider_id}")
        seen.add(provider_id)

        family = _require_string(provider.get("family"), f"{provider_id}.family")
        selection_aliases = _require_list(provider.get("selection_aliases"), f"{provider_id}.selection_aliases")
        kind = _require_string(provider.get("kind"), f"{provider_id}.kind")
        status = _require_string(provider.get("status"), f"{provider_id}.status")
        authority = _require_string(provider.get("authority"), f"{provider_id}.authority")
        capabilities = _require_list(provider.get("capabilities"), f"{provider_id}.capabilities")
        blocked_on = _require_list(provider.get("blocked_on"), f"{provider_id}.blocked_on")
        verification_policy = _require_string(provider.get("verification_policy"), f"{provider_id}.verification_policy")

        if family not in VALID_FAMILIES:
            raise RegistryValidationError(f"{provider_id}.family is invalid: {family}")
        provider_families[provider_id] = family
        if not selection_aliases or not all(isinstance(item, str) and item for item in selection_aliases):
            raise RegistryValidationError(f"{provider_id}.selection_aliases must contain non-empty strings")
        for alias in selection_aliases:
            if alias in VALID_FAMILIES:
                raise RegistryValidationError(f"{provider_id}.selection_aliases must not use ambiguous family alias: {alias}")
            if alias in seen_aliases:
                raise RegistryValidationError(f"selection alias {alias} is used by both {seen_aliases[alias]} and {provider_id}")
            seen_aliases[alias] = provider_id
        if kind not in VALID_KINDS:
            raise RegistryValidationError(f"{provider_id}.kind is invalid: {kind}")
        if status not in VALID_STATUSES:
            raise RegistryValidationError(f"{provider_id}.status is invalid: {status}")
        if kind == "assist_channel" and authority != "candidate_artifact_only":
            raise RegistryValidationError(f"assist channel {provider_id} cannot have delivery or executor authority")
        if authority not in VALID_AUTHORITIES:
            raise RegistryValidationError(f"{provider_id}.authority is invalid: {authority}")
        if not all(isinstance(item, str) and item for item in capabilities):
            raise RegistryValidationError(f"{provider_id}.capabilities must contain non-empty strings")
        if not all(isinstance(item, str) and item for item in blocked_on):
            raise RegistryValidationError(f"{provider_id}.blocked_on must contain non-empty strings")
        if status == "blocked" and not blocked_on:
            raise RegistryValidationError(f"{provider_id} is blocked but blocked_on is empty")
        if status in {"preferred", "available"} and blocked_on:
            raise RegistryValidationError(f"{provider_id} is available but still has blockers")
        if provider_id == "codex_sdk" and verification_policy != "use_official_python_openai_codex_sdk_only_with_local_probe":
            raise RegistryValidationError("codex_sdk must use the official Python openai-codex SDK adapter policy")
        if provider_id == "chatgpt_web_manual":
            _validate_chatgpt_model_policy(provider.get("model_policy"), provider_id)
        if provider_id.startswith("cursor_") and status in {"preferred", "available"}:
            if verification_policy != "must_authenticate_with_real_cursor_account":
                raise RegistryValidationError(f"{provider_id} must require real Cursor authentication")
            raise RegistryValidationError(f"{provider_id} cannot be marked available without current real Cursor authentication evidence")
        if provider_id.startswith("antigravity_") and kind in {"executor", "future_executor"} and status in {"preferred", "available"}:
            if verification_policy != "must_authenticate_with_real_antigravity_account":
                raise RegistryValidationError(f"{provider_id} must require real Antigravity authentication")
            raise RegistryValidationError(f"{provider_id} cannot be marked available without current real Antigravity authentication evidence")

    for family, provider_id in family_defaults.items():
        if family not in VALID_FAMILIES:
            raise RegistryValidationError(f"registry.family_defaults contains invalid family: {family}")
        if provider_id not in seen:
            raise RegistryValidationError(f"registry.family_defaults.{family} points to unknown provider: {provider_id}")
        if provider_families[provider_id] != family:
            raise RegistryValidationError(f"registry.family_defaults.{family} points to provider from family {provider_families[provider_id]}")

    return RegistryValidationResult(ok=True, provider_count=len(providers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry",
        nargs="?",
        type=Path,
        default=Path("configs/harness-provider-registry.json"),
        help="Provider registry JSON file",
    )
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        result = validate_registry(registry)
    except (OSError, json.JSONDecodeError, RegistryValidationError) as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    print(f"valid: harness_provider_registry providers={result.provider_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
