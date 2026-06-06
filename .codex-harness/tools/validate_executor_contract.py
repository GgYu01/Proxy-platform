#!/usr/bin/env python3
"""Validate Harness Run Contract payloads.

This tool intentionally uses only the Python standard library so it can run in
fresh preview worktrees before project dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


VALID_EXECUTOR_KINDS = {
    "codex_multi_agent_harness",
    "codex_gpt55_local",
    "cursor_acp_worker",
    "cursor_cli_worker",
    "cursor_cloud_agent",
    "claude_code_worker",
    "opencode_worker",
    "reviewer",
    "custom_executor",
}

VALID_LEVELS = {"R0", "D0", "L0", "L1", "L2", "L3", "L4", "L5", "L6", "G0"}
VALID_EVENT_TYPES = {
    "run.accepted",
    "run.leased",
    "workspace.prepared",
    "agent.started",
    "agent.plan",
    "agent.message",
    "tool.started",
    "tool.completed",
    "diff.updated",
    "artifact.created",
    "verification.started",
    "verification.completed",
    "run.needs_input",
    "run.blocked",
    "run.failed",
    "run.cancelled",
    "run.executor_succeeded",
    "run.gate_passed",
    "run.rework_required",
    "run.delivery_failed",
    "run.delivered",
}

VALID_RUN_RESULT_STATUSES = {
    "executor_succeeded",
    "gate_passed",
    "delivered",
    "rework_required",
    "delivery_failed",
    "failed",
    "blocked",
    "cancelled",
}
VALID_STAGE_EFFORTS = {"fast", "standard", "advanced", "deep", "extended", "local"}
VALID_STAGE_AUTHORITIES = {"candidate_artifact", "executor"}
VALID_CONVERSATION_REUSE_POLICIES = {
    "new_conversation",
    "reuse_existing_when_available",
    "new_or_followup_same_conversation",
    "followup_same_conversation",
    "not_applicable",
}
GPT55_PRO_EXTENDED_REQUIRED_STAGES = {
    "requirements_analysis",
    "architecture_design",
    "complex_debug_root_cause",
    "rework_decision",
    "final_evaluation_summary",
}


def _known_provider_ids() -> set[str]:
    registry_path = Path(__file__).resolve().parents[1] / "configs" / "harness-provider-registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    providers = registry.get("providers")
    if not isinstance(providers, list):
        return set()
    return {str(provider.get("id")) for provider in providers if isinstance(provider, dict) and provider.get("id")}


class ValidationError(ValueError):
    """Raised when a payload violates the contract."""


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


def _require_keys(payload: dict[str, Any], keys: list[str], prefix: str) -> None:
    for key in keys:
        if key not in payload:
            raise ValidationError(f"{prefix}.{key} is required")


def _reject_unknown_fields(payload: dict[str, Any], allowed: set[str], prefix: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValidationError(f"{prefix} contains unknown fields: {unknown}")


def validate_run_request(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "RunRequest")
    _reject_unknown_fields(
        payload,
        {
            "task_id",
            "run_id",
            "idempotency_key",
            "tenant_id",
            "project_id",
            "executor",
            "workspace",
            "objective",
            "goal_state",
            "requirement_context",
            "provider_selection",
            "delegation_policy",
            "scope",
            "constraints",
            "credentials_ref",
            "verification",
            "artifacts",
            "worker_stages",
        },
        "RunRequest",
    )
    _require_keys(
        payload,
        [
            "task_id",
            "run_id",
            "idempotency_key",
            "executor",
            "workspace",
            "objective",
            "scope",
            "constraints",
            "verification",
            "artifacts",
        ],
        "RunRequest",
    )
    for key in ("task_id", "run_id", "idempotency_key", "objective"):
        _require_string(payload[key], f"RunRequest.{key}")

    if "goal_state" in payload:
        goal_state = _require_mapping(payload["goal_state"], "RunRequest.goal_state")
        _reject_unknown_fields(
            goal_state,
            {"description", "owner", "sync_mode", "codex_thread_id", "source"},
            "RunRequest.goal_state",
        )
        _require_keys(goal_state, ["description", "owner", "sync_mode"], "RunRequest.goal_state")
        _require_string(goal_state["description"], "RunRequest.goal_state.description")
        if goal_state["owner"] not in {"harness_supervisor", "codex_thread"}:
            raise ValidationError("RunRequest.goal_state.owner is invalid")
        if goal_state["sync_mode"] not in {"harness_only", "codex_app_server_goal_if_available"}:
            raise ValidationError("RunRequest.goal_state.sync_mode is invalid")
        if "codex_thread_id" in goal_state:
            _require_string(goal_state["codex_thread_id"], "RunRequest.goal_state.codex_thread_id")
        if "source" in goal_state:
            _require_string(goal_state["source"], "RunRequest.goal_state.source")

    executor = _require_mapping(payload["executor"], "RunRequest.executor")
    _reject_unknown_fields(
        executor,
        {"kind", "model_hint", "host_affinity", "capability_requirements"},
        "RunRequest.executor",
    )
    _require_keys(executor, ["kind", "model_hint", "capability_requirements"], "RunRequest.executor")
    if executor["kind"] not in VALID_EXECUTOR_KINDS:
        raise ValidationError(f"RunRequest.executor.kind is unsupported: {executor['kind']}")
    _require_string(executor["model_hint"], "RunRequest.executor.model_hint")
    if "host_affinity" in executor and executor["host_affinity"] not in {"local", "remote", "any"}:
        raise ValidationError("RunRequest.executor.host_affinity is invalid")
    _require_list(executor["capability_requirements"], "RunRequest.executor.capability_requirements")

    workspace = _require_mapping(payload["workspace"], "RunRequest.workspace")
    _reject_unknown_fields(
        workspace,
        {"repo", "workdir", "base_ref", "worktree_policy"},
        "RunRequest.workspace",
    )
    _require_keys(workspace, ["workdir", "worktree_policy"], "RunRequest.workspace")
    _require_string(workspace["workdir"], "RunRequest.workspace.workdir")
    if workspace["worktree_policy"] not in {"isolated", "in_place", "read_only"}:
        raise ValidationError("RunRequest.workspace.worktree_policy is invalid")

    scope = _require_mapping(payload["scope"], "RunRequest.scope")
    _reject_unknown_fields(scope, {"in_scope", "out_of_scope", "paths"}, "RunRequest.scope")
    _require_keys(scope, ["in_scope", "out_of_scope", "paths"], "RunRequest.scope")
    for key in ("in_scope", "out_of_scope", "paths"):
        _require_list(scope[key], f"RunRequest.scope.{key}")

    constraints = _require_mapping(payload["constraints"], "RunRequest.constraints")
    _reject_unknown_fields(
        constraints,
        {"network", "write_policy", "secrets_policy", "approval_policy"},
        "RunRequest.constraints",
    )
    _require_keys(
        constraints,
        ["network", "write_policy", "secrets_policy", "approval_policy"],
        "RunRequest.constraints",
    )
    if constraints["network"] not in {"deny", "allow", "mirror-first"}:
        raise ValidationError("RunRequest.constraints.network is invalid")
    if constraints["write_policy"] not in {"plan_only", "patch_allowed", "direct_edit_allowed"}:
        raise ValidationError("RunRequest.constraints.write_policy is invalid")
    if constraints["secrets_policy"] not in {"credential_ref_only", "no_secrets", "explicit_secret_refs"}:
        raise ValidationError("RunRequest.constraints.secrets_policy is invalid")
    if constraints["approval_policy"] not in {"auto", "require_human", "deny_sensitive"}:
        raise ValidationError("RunRequest.constraints.approval_policy is invalid")

    if "requirement_context" in payload:
        requirement_context = _require_mapping(payload["requirement_context"], "RunRequest.requirement_context")
        _reject_unknown_fields(
            requirement_context,
            {
                "original_user_request",
                "requirement_items",
                "must_preserve",
                "assumptions",
                "open_questions",
                "explicit_user_overrides",
            },
            "RunRequest.requirement_context",
        )
        _require_string(requirement_context.get("original_user_request"), "RunRequest.requirement_context.original_user_request")
        for key in ("requirement_items", "must_preserve", "assumptions", "open_questions", "explicit_user_overrides"):
            _require_list(requirement_context.get(key, []), f"RunRequest.requirement_context.{key}")
        for index, item in enumerate(requirement_context.get("requirement_items", [])):
            item = _require_mapping(item, f"RunRequest.requirement_context.requirement_items[{index}]")
            _reject_unknown_fields(item, {"id", "text", "source", "priority"}, f"RunRequest.requirement_context.requirement_items[{index}]")
            _require_keys(item, ["id", "text", "source", "priority"], f"RunRequest.requirement_context.requirement_items[{index}]")
            for key in ("id", "text", "source", "priority"):
                _require_string(item[key], f"RunRequest.requirement_context.requirement_items[{index}].{key}")
            if item["priority"] not in {"must", "should", "could", "won't"}:
                raise ValidationError(f"RunRequest.requirement_context.requirement_items[{index}].priority is invalid")

    if "provider_selection" in payload:
        provider_selection = _require_mapping(payload["provider_selection"], "RunRequest.provider_selection")
        _reject_unknown_fields(
            provider_selection,
            {
                "mode",
                "preferred_provider_ids",
                "allowed_provider_ids",
                "fallback_provider_ids",
                "selection_prompt",
                "resolution_policy",
            },
            "RunRequest.provider_selection",
        )
        _require_keys(
            provider_selection,
            ["mode", "preferred_provider_ids", "allowed_provider_ids", "fallback_provider_ids", "resolution_policy"],
            "RunRequest.provider_selection",
        )
        if provider_selection["mode"] not in {"registry_default", "prompt_controlled", "fixed"}:
            raise ValidationError("RunRequest.provider_selection.mode is invalid")
        if provider_selection["resolution_policy"] not in {"respect_prompt_with_registry_and_authority_limits", "prefer_available_provider", "fixed_provider_required"}:
            raise ValidationError("RunRequest.provider_selection.resolution_policy is invalid")
        allowed_provider_ids = _require_list(provider_selection["allowed_provider_ids"], "RunRequest.provider_selection.allowed_provider_ids")
        if not allowed_provider_ids:
            raise ValidationError("RunRequest.provider_selection.allowed_provider_ids must not be empty")
        known_provider_ids = _known_provider_ids()
        for key in ("preferred_provider_ids", "allowed_provider_ids", "fallback_provider_ids"):
            values = _require_list(provider_selection[key], f"RunRequest.provider_selection.{key}")
            if not all(isinstance(item, str) and item.strip() for item in values):
                raise ValidationError(f"RunRequest.provider_selection.{key} must contain non-empty strings")
            unknown_provider_ids = sorted({item for item in values if known_provider_ids and item not in known_provider_ids})
            if unknown_provider_ids:
                raise ValidationError(f"RunRequest.provider_selection.{key} contains unknown provider ids: {unknown_provider_ids}")
        if "selection_prompt" in provider_selection:
            _require_string(provider_selection["selection_prompt"], "RunRequest.provider_selection.selection_prompt")

    if "delegation_policy" in payload:
        delegation_policy = _require_mapping(payload["delegation_policy"], "RunRequest.delegation_policy")
        _reject_unknown_fields(
            delegation_policy,
            {"autonomy_level", "context_sharing", "allowed_operations", "requires_human_confirmation", "supervisor_gate_required"},
            "RunRequest.delegation_policy",
        )
        _require_keys(
            delegation_policy,
            ["autonomy_level", "context_sharing", "allowed_operations", "requires_human_confirmation", "supervisor_gate_required"],
            "RunRequest.delegation_policy",
        )
        if delegation_policy["autonomy_level"] not in {"plan_only", "supervised_patch", "supervised_act", "autonomous_candidate"}:
            raise ValidationError("RunRequest.delegation_policy.autonomy_level is invalid")
        if delegation_policy["context_sharing"] not in {"summary_only", "full_user_request_with_redactions", "full_context_bundle_with_redactions"}:
            raise ValidationError("RunRequest.delegation_policy.context_sharing is invalid")
        allowed_operations = _require_list(delegation_policy["allowed_operations"], "RunRequest.delegation_policy.allowed_operations")
        invalid_operations = [
            item
            for item in allowed_operations
            if item
            not in {
                "read_repo",
                "edit_owned_paths",
                "run_tests",
                "run_shell",
                "network_access",
                "browser_access",
                "draft_patch",
                "apply_patch",
                "spawn_subagents",
                "package_artifacts",
                "write_receipts",
            }
        ]
        if invalid_operations:
            raise ValidationError(f"RunRequest.delegation_policy.allowed_operations contains invalid operations: {invalid_operations}")
        confirmations = _require_list(delegation_policy["requires_human_confirmation"], "RunRequest.delegation_policy.requires_human_confirmation")
        invalid_confirmations = [
            item
            for item in confirmations
            if item not in {"external_upload", "git_commit", "git_push", "deploy", "secret_access", "apply_untrusted_patch"}
        ]
        if invalid_confirmations:
            raise ValidationError(f"RunRequest.delegation_policy.requires_human_confirmation contains invalid operations: {invalid_confirmations}")
        if delegation_policy["supervisor_gate_required"] is not True:
            raise ValidationError("RunRequest.delegation_policy.supervisor_gate_required must be true")

    if "worker_stages" in payload:
        validate_worker_stages(payload["worker_stages"])

    verification = _require_mapping(payload["verification"], "RunRequest.verification")
    _reject_unknown_fields(
        verification,
        {"required_levels", "commands", "acceptance_criteria"},
        "RunRequest.verification",
    )
    _require_keys(
        verification,
        ["required_levels", "commands", "acceptance_criteria"],
        "RunRequest.verification",
    )
    levels = _require_list(verification["required_levels"], "RunRequest.verification.required_levels")
    unknown_levels = [level for level in levels if level not in VALID_LEVELS]
    if unknown_levels:
        raise ValidationError(f"RunRequest.verification.required_levels contains invalid levels: {unknown_levels}")
    _require_list(verification["commands"], "RunRequest.verification.commands")
    _require_list(verification["acceptance_criteria"], "RunRequest.verification.acceptance_criteria")

    artifacts = _require_mapping(payload["artifacts"], "RunRequest.artifacts")
    _reject_unknown_fields(artifacts, {"required", "optional"}, "RunRequest.artifacts")
    _require_keys(artifacts, ["required", "optional"], "RunRequest.artifacts")
    _require_list(artifacts["required"], "RunRequest.artifacts.required")
    _require_list(artifacts["optional"], "RunRequest.artifacts.optional")
    return ValidationResult(ok=True, kind="RunRequest")


def validate_worker_stages(value: Any) -> None:
    stages = _require_list(value, "RunRequest.worker_stages")
    if not stages:
        raise ValidationError("RunRequest.worker_stages must not be empty")
    known_provider_ids = _known_provider_ids()
    for index, item in enumerate(stages):
        stage = _require_mapping(item, f"RunRequest.worker_stages[{index}]")
        _reject_unknown_fields(
            stage,
            {
                "stage_kind",
                "provider_id",
                "required_model",
                "required_effort",
                "conversation_reuse_policy",
                "expected_artifacts",
                "local_gate_checks",
                "authority",
            },
            f"RunRequest.worker_stages[{index}]",
        )
        _require_keys(
            stage,
            [
                "stage_kind",
                "provider_id",
                "required_model",
                "required_effort",
                "conversation_reuse_policy",
                "expected_artifacts",
                "local_gate_checks",
                "authority",
            ],
            f"RunRequest.worker_stages[{index}]",
        )
        stage_kind = _require_string(stage["stage_kind"], f"RunRequest.worker_stages[{index}].stage_kind")
        provider_id = _require_string(stage["provider_id"], f"RunRequest.worker_stages[{index}].provider_id")
        required_model = _require_string(stage["required_model"], f"RunRequest.worker_stages[{index}].required_model")
        required_effort = _require_string(stage["required_effort"], f"RunRequest.worker_stages[{index}].required_effort")
        conversation_reuse_policy = _require_string(
            stage["conversation_reuse_policy"],
            f"RunRequest.worker_stages[{index}].conversation_reuse_policy",
        )
        authority = _require_string(stage["authority"], f"RunRequest.worker_stages[{index}].authority")
        expected_artifacts = _require_list(stage["expected_artifacts"], f"RunRequest.worker_stages[{index}].expected_artifacts")
        local_gate_checks = _require_list(stage["local_gate_checks"], f"RunRequest.worker_stages[{index}].local_gate_checks")
        if known_provider_ids and provider_id not in known_provider_ids:
            raise ValidationError(f"RunRequest.worker_stages[{index}].provider_id contains unknown provider id: {provider_id}")
        if required_effort not in VALID_STAGE_EFFORTS:
            raise ValidationError(f"RunRequest.worker_stages[{index}].required_effort is invalid")
        if conversation_reuse_policy not in VALID_CONVERSATION_REUSE_POLICIES:
            raise ValidationError(f"RunRequest.worker_stages[{index}].conversation_reuse_policy is invalid")
        if authority not in VALID_STAGE_AUTHORITIES:
            raise ValidationError(f"RunRequest.worker_stages[{index}].authority is invalid")
        if not all(isinstance(artifact, str) and artifact.strip() for artifact in expected_artifacts):
            raise ValidationError(f"RunRequest.worker_stages[{index}].expected_artifacts must contain non-empty strings")
        if not all(isinstance(check, str) and check.strip() for check in local_gate_checks):
            raise ValidationError(f"RunRequest.worker_stages[{index}].local_gate_checks must contain non-empty strings")

        if provider_id == "chatgpt_web_manual":
            if authority != "candidate_artifact":
                raise ValidationError("ChatGPT Web worker stages must use candidate_artifact authority")
            if conversation_reuse_policy == "not_applicable":
                raise ValidationError("ChatGPT Web worker stages require an explicit conversation reuse policy")
            if any(artifact.endswith((".patch", ".diff")) or artifact.startswith("files/") for artifact in expected_artifacts):
                if not local_gate_checks:
                    raise ValidationError("ChatGPT Web candidate code artifacts require local gate checks")
        if stage_kind in GPT55_PRO_EXTENDED_REQUIRED_STAGES:
            if provider_id != "chatgpt_web_manual" or required_model != "GPT-5.5 Pro" or required_effort != "extended":
                raise ValidationError(f"RunRequest.worker_stages[{index}] {stage_kind} requires GPT-5.5 Pro Extended via ChatGPT Web")
            if "ui_probe_receipt:gpt55_pro_extended" not in local_gate_checks:
                raise ValidationError(f"RunRequest.worker_stages[{index}] GPT-5.5 Pro Extended requires ui_probe_receipt:gpt55_pro_extended")


def validate_artifact_manifest(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ArtifactManifest")
    _reject_unknown_fields(payload, {"run_id", "artifacts"}, "ArtifactManifest")
    _require_keys(payload, ["artifacts"], "ArtifactManifest")
    artifacts = _require_list(payload["artifacts"], "ArtifactManifest.artifacts")
    if not artifacts:
        raise ValidationError("ArtifactManifest.artifacts must not be empty")
    for index, artifact in enumerate(artifacts):
        artifact = _require_mapping(artifact, f"ArtifactManifest.artifacts[{index}]")
        _reject_unknown_fields(
            artifact,
            {"name", "path", "type", "sha256", "producer"},
            f"ArtifactManifest.artifacts[{index}]",
        )
        _require_keys(artifact, ["name", "path", "type", "sha256", "producer"], f"ArtifactManifest.artifacts[{index}]")
        for key in ("name", "path", "type", "producer"):
            _require_string(artifact[key], f"ArtifactManifest.artifacts[{index}].{key}")
        sha256 = _require_string(artifact["sha256"], f"ArtifactManifest.artifacts[{index}].sha256")
        if len(sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in sha256):
            raise ValidationError(f"ArtifactManifest.artifacts[{index}].sha256 must be 64 hex characters")
    return ValidationResult(ok=True, kind="ArtifactManifest")


def validate_verification_receipt(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "VerificationReceipt")
    _reject_unknown_fields(payload, {"run_id", "status", "checks", "known_risks"}, "VerificationReceipt")
    _require_keys(payload, ["status", "checks"], "VerificationReceipt")
    if payload["status"] not in {"passed", "failed", "skipped", "blocked"}:
        raise ValidationError("VerificationReceipt.status is invalid")
    checks = _require_list(payload["checks"], "VerificationReceipt.checks")
    if payload["status"] == "passed" and not checks:
        raise ValidationError("VerificationReceipt passed requires at least one check")
    for index, check in enumerate(checks):
        check = _require_mapping(check, f"VerificationReceipt.checks[{index}]")
        _reject_unknown_fields(
            check,
            {"name", "level", "status", "command", "exit_code", "log_uri"},
            f"VerificationReceipt.checks[{index}]",
        )
        _require_keys(check, ["name", "level", "status", "command", "exit_code"], f"VerificationReceipt.checks[{index}]")
        _require_string(check["name"], f"VerificationReceipt.checks[{index}].name")
        if check["level"] not in VALID_LEVELS:
            raise ValidationError(f"VerificationReceipt.checks[{index}].level is invalid")
        if check["status"] not in {"passed", "failed", "skipped", "blocked"}:
            raise ValidationError(f"VerificationReceipt.checks[{index}].status is invalid")
        if not isinstance(check["command"], str):
            raise ValidationError(f"VerificationReceipt.checks[{index}].command must be a string")
        if not isinstance(check["exit_code"], int):
            raise ValidationError(f"VerificationReceipt.checks[{index}].exit_code must be an integer")
    return ValidationResult(ok=True, kind="VerificationReceipt")


def validate_review_verdict(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "ReviewVerdict")
    _reject_unknown_fields(payload, {"run_id", "status", "reviewers", "findings"}, "ReviewVerdict")
    _require_keys(payload, ["status", "reviewers"], "ReviewVerdict")
    if payload["status"] not in {"accepted", "rework_required", "blocked", "not_run"}:
        raise ValidationError("ReviewVerdict.status is invalid")
    _require_list(payload["reviewers"], "ReviewVerdict.reviewers")
    return ValidationResult(ok=True, kind="ReviewVerdict")


def validate_run_event(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "RunEvent")
    _reject_unknown_fields(payload, {"type", "run_id", "payload"}, "RunEvent")
    _require_keys(payload, ["type", "run_id"], "RunEvent")
    if payload["type"] not in VALID_EVENT_TYPES:
        raise ValidationError(f"RunEvent.type is invalid: {payload['type']}")
    _require_string(payload["run_id"], "RunEvent.run_id")
    return ValidationResult(ok=True, kind="RunEvent")


def validate_event_sequence(events: list[dict[str, Any]]) -> ValidationResult:
    _require_list(events, "RunEventSequence")
    seen_gate = False
    for index, event in enumerate(events):
        validate_run_event(event)
        event_type = event["type"]
        if event_type == "run.gate_passed":
            seen_gate = True
        if event_type == "run.delivered" and not seen_gate:
            raise ValidationError(f"RunEventSequence[{index}] run.delivered requires run.gate_passed first")
    return ValidationResult(ok=True, kind="RunEventSequence")


def validate_run_result(payload: dict[str, Any]) -> ValidationResult:
    payload = _require_mapping(payload, "RunResult")
    _reject_unknown_fields(
        payload,
        {"run_id", "status", "artifact_manifest", "verification_receipt", "review_verdict", "gate_decision"},
        "RunResult",
    )
    _require_keys(
        payload,
        ["run_id", "status", "artifact_manifest", "verification_receipt", "gate_decision"],
        "RunResult",
    )
    _require_string(payload["run_id"], "RunResult.run_id")
    if payload["status"] not in VALID_RUN_RESULT_STATUSES:
        raise ValidationError("RunResult.status is invalid")
    if payload["status"] == "delivered":
        verification_receipt = _require_mapping(payload["verification_receipt"], "RunResult.verification_receipt")
        checks = _require_list(verification_receipt.get("checks"), "RunResult.verification_receipt.checks")
        if not checks:
            raise ValidationError("RunResult delivered requires at least one verification check")
    validate_artifact_manifest(payload["artifact_manifest"])
    validate_verification_receipt(payload["verification_receipt"])
    gate_decision = _require_mapping(payload["gate_decision"], "RunResult.gate_decision")
    _reject_unknown_fields(gate_decision, {"status", "reasons"}, "RunResult.gate_decision")
    _require_keys(gate_decision, ["status", "reasons"], "RunResult.gate_decision")
    if gate_decision["status"] not in {"passed", "failed", "blocked"}:
        raise ValidationError("RunResult.gate_decision.status is invalid")
    _require_list(gate_decision["reasons"], "RunResult.gate_decision.reasons")
    if "review_verdict" in payload:
        validate_review_verdict(payload["review_verdict"])

    if payload["status"] == "delivered":
        if payload["verification_receipt"]["status"] != "passed":
            raise ValidationError("RunResult delivered requires verification_receipt.status == passed")
        checks = payload["verification_receipt"]["checks"]
        if not checks:
            raise ValidationError("RunResult delivered requires at least one verification check")
        incomplete_checks = [
            check["name"]
            for check in checks
            if check["status"] != "passed" or check["exit_code"] != 0
        ]
        if incomplete_checks:
            raise ValidationError(f"RunResult delivered requires all checks to pass: {incomplete_checks}")
        if gate_decision["status"] != "passed":
            raise ValidationError("RunResult delivered requires gate_decision.status == passed")
        review_verdict = payload.get("review_verdict", {})
        if isinstance(review_verdict, dict) and review_verdict.get("status") in {"rework_required", "blocked"}:
            raise ValidationError("RunResult delivered is invalid when review_verdict blocks delivery")
    return ValidationResult(ok=True, kind="RunResult")


def detect_and_validate(payload: Any) -> ValidationResult:
    if isinstance(payload, list):
        return validate_event_sequence(payload)
    mapping = _require_mapping(payload, "payload")
    if "idempotency_key" in mapping and "executor" in mapping:
        return validate_run_request(mapping)
    if "type" in mapping and "run_id" in mapping:
        return validate_run_event(mapping)
    if "artifact_manifest" in mapping and "verification_receipt" in mapping:
        return validate_run_result(mapping)
    if "artifacts" in mapping:
        return validate_artifact_manifest(mapping)
    if "checks" in mapping and "status" in mapping:
        return validate_verification_receipt(mapping)
    if "reviewers" in mapping and "status" in mapping:
        return validate_review_verdict(mapping)
    raise ValidationError("Cannot detect Harness Run Contract payload kind")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path, help="JSON payload file to validate")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.payload.read_text(encoding="utf-8-sig"))
        result = detect_and_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    print(f"valid: {result.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
