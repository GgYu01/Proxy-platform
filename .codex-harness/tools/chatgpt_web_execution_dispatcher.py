#!/usr/bin/env python3
"""Validate and dispatch ChatGPT Web-authored Codex execution plans.

ChatGPT Web can propose work decomposition, but local Codex remains the
supervisor that validates the plan and decides whether to spawn serial or
parallel agents. This module records that dispatch contract and receipt; it
does not call model APIs.
"""

from __future__ import annotations

import argparse
import os
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from chatgpt_app_no_api_common import AssistError, reject_secret_text, safe_id


JSON = dict[str, Any]
DispatchBackend = Callable[[JSON, JSON], JSON]

VALID_DISPATCH_MODES = {"serial", "parallel"}
VALID_STRATEGIES = {"serial", "parallel", "serial_then_parallel", "auto"}
REQUIRED_PLAN_FIELDS = {
    "packet_type",
    "run_id",
    "task_id",
    "created_by",
    "language",
    "dispatch_strategy",
    "local_supervisor",
    "execution_units",
    "acceptance_checks",
}
REQUIRED_UNIT_FIELDS = {
    "id",
    "title",
    "dispatch_mode",
    "prompt",
    "owned_paths",
    "depends_on",
    "expected_artifacts",
}
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
OPTIONAL_PLAN_FIELDS = {"provider_selection", "delegation_policy", "goal_state", "workflow_context"}
OPTIONAL_UNIT_FIELDS = {"raw_user_requirements"}
NORMALIZED_PLAN_FIELDS = REQUIRED_PLAN_FIELDS | OPTIONAL_PLAN_FIELDS | {"dispatch_batches", "parallel_unit_count"}
DEFAULT_CODEX_SANDBOX = "workspace-write"
VALID_CODEX_BACKENDS = {"manual", "codex-cli"}
VALID_PROVIDER_SELECTION_MODES = {"registry_default", "prompt_controlled", "fixed"}
VALID_PROVIDER_RESOLUTION_POLICIES = {"respect_prompt_with_registry_and_authority_limits", "prefer_available_provider", "fixed_provider_required"}
VALID_AUTONOMY_LEVELS = {"plan_only", "supervised_patch", "supervised_act", "autonomous_candidate"}
VALID_CONTEXT_SHARING = {"summary_only", "full_user_request_with_redactions", "full_context_bundle_with_redactions"}
VALID_GOAL_OWNERS = {"harness_supervisor", "codex_thread"}
VALID_GOAL_SYNC_MODES = {"harness_only", "codex_app_server_goal_if_available"}
VALID_DELEGATED_OPERATIONS = {
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
VALID_CONFIRMATION_OPERATIONS = {"external_upload", "git_commit", "git_push", "deploy", "secret_access", "apply_untrusted_patch"}


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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _require_mapping(value: Any, label: str) -> JSON:
    if not isinstance(value, dict):
        raise AssistError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AssistError(f"{label} must be an array")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssistError(f"{label} must be a non-empty string")
    reject_secret_text(value, label)
    return value.strip()


def _reject_unknown_fields(value: JSON, allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise AssistError(f"{label} contains unknown fields: {unknown}")


def _require_english_text(value: str, label: str) -> str:
    text = _require_string(value, label)
    if HAN_RE.search(text):
        raise AssistError(f"{label} must be English runtime text")
    return text


def _normalize_relative_path(value: Any, label: str) -> str:
    path = _require_string(value, label).replace("\\", "/")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise AssistError(f"{label} must be a safe relative path")
    return pure.as_posix()


def _normalize_string_list(value: Any, label: str, *, path_items: bool = False) -> list[str]:
    items = _require_list(value, label)
    result: list[str] = []
    for index, item in enumerate(items):
        item_label = f"{label}[{index}]"
        if path_items:
            result.append(_normalize_relative_path(item, item_label))
        else:
            result.append(_require_english_text(item, item_label))
    return result


def _normalize_checks(value: Any) -> list[list[str]]:
    checks = _require_list(value, "codex_execution_plan.acceptance_checks")
    result: list[list[str]] = []
    for index, command in enumerate(checks):
        parts = _require_list(command, f"codex_execution_plan.acceptance_checks[{index}]")
        if not parts or not all(isinstance(part, str) and part.strip() for part in parts):
            raise AssistError("acceptance_checks entries must be non-empty string arrays")
        for part_index, part in enumerate(parts):
            reject_secret_text(part, f"acceptance_checks[{index}][{part_index}]")
        result.append([str(part) for part in parts])
    return result


def _relative_to_workspace(path: Path, workspace: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _truncate_output(value: str, limit: int = 12000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _normalize_unit(value: Any, index: int) -> JSON:
    label = f"codex_execution_plan.execution_units[{index}]"
    unit = _require_mapping(value, label)
    _reject_unknown_fields(unit, REQUIRED_UNIT_FIELDS | OPTIONAL_UNIT_FIELDS, label)
    for field in REQUIRED_UNIT_FIELDS:
        if field not in unit:
            raise AssistError(f"{label}.{field} is required")

    unit_id = safe_id(_require_string(unit["id"], f"{label}.id"), f"{label}.id")
    dispatch_mode = _require_string(unit["dispatch_mode"], f"{label}.dispatch_mode")
    if dispatch_mode not in VALID_DISPATCH_MODES:
        raise AssistError(f"{label}.dispatch_mode must be serial or parallel")
    normalized = {
        "id": unit_id,
        "title": _require_english_text(unit["title"], f"{label}.title"),
        "dispatch_mode": dispatch_mode,
        "prompt": _require_english_text(unit["prompt"], f"{label}.prompt"),
        "owned_paths": _normalize_string_list(unit["owned_paths"], f"{label}.owned_paths", path_items=True),
        "depends_on": [safe_id(item, f"{label}.depends_on[]") for item in _normalize_string_list(unit["depends_on"], f"{label}.depends_on")],
        "expected_artifacts": _normalize_string_list(unit["expected_artifacts"], f"{label}.expected_artifacts"),
    }
    if "raw_user_requirements" in unit:
        normalized["raw_user_requirements"] = _require_string(unit["raw_user_requirements"], f"{label}.raw_user_requirements")
    return normalized


def _normalize_provider_selection(value: Any) -> JSON:
    provider_selection = _require_mapping(value, "codex_execution_plan.provider_selection")
    _reject_unknown_fields(
        provider_selection,
        {"mode", "preferred_provider_ids", "allowed_provider_ids", "fallback_provider_ids", "selection_prompt", "resolution_policy"},
        "codex_execution_plan.provider_selection",
    )
    for field in ("mode", "preferred_provider_ids", "allowed_provider_ids", "fallback_provider_ids", "resolution_policy"):
        if field not in provider_selection:
            raise AssistError(f"codex_execution_plan.provider_selection.{field} is required")
    mode = _require_string(provider_selection["mode"], "codex_execution_plan.provider_selection.mode")
    if mode not in VALID_PROVIDER_SELECTION_MODES:
        raise AssistError("codex_execution_plan.provider_selection.mode is invalid")
    resolution_policy = _require_string(provider_selection["resolution_policy"], "codex_execution_plan.provider_selection.resolution_policy")
    if resolution_policy not in VALID_PROVIDER_RESOLUTION_POLICIES:
        raise AssistError("codex_execution_plan.provider_selection.resolution_policy is invalid")
    normalized = {
        "mode": mode,
        "preferred_provider_ids": _normalize_string_list(provider_selection["preferred_provider_ids"], "codex_execution_plan.provider_selection.preferred_provider_ids"),
        "allowed_provider_ids": _normalize_string_list(provider_selection["allowed_provider_ids"], "codex_execution_plan.provider_selection.allowed_provider_ids"),
        "fallback_provider_ids": _normalize_string_list(provider_selection["fallback_provider_ids"], "codex_execution_plan.provider_selection.fallback_provider_ids"),
        "resolution_policy": resolution_policy,
    }
    if not normalized["allowed_provider_ids"]:
        raise AssistError("codex_execution_plan.provider_selection.allowed_provider_ids must not be empty")
    known_provider_ids = _known_provider_ids()
    for key in ("preferred_provider_ids", "allowed_provider_ids", "fallback_provider_ids"):
        unknown_provider_ids = sorted({item for item in normalized[key] if known_provider_ids and item not in known_provider_ids})
        if unknown_provider_ids:
            raise AssistError(f"codex_execution_plan.provider_selection.{key} contains unknown provider ids: {unknown_provider_ids}")
    if "selection_prompt" in provider_selection:
        normalized["selection_prompt"] = _require_english_text(provider_selection["selection_prompt"], "codex_execution_plan.provider_selection.selection_prompt")
    return normalized


def _normalize_delegation_policy(value: Any) -> JSON:
    delegation_policy = _require_mapping(value, "codex_execution_plan.delegation_policy")
    _reject_unknown_fields(
        delegation_policy,
        {"autonomy_level", "context_sharing", "allowed_operations", "requires_human_confirmation", "supervisor_gate_required"},
        "codex_execution_plan.delegation_policy",
    )
    for field in ("autonomy_level", "context_sharing", "allowed_operations", "requires_human_confirmation", "supervisor_gate_required"):
        if field not in delegation_policy:
            raise AssistError(f"codex_execution_plan.delegation_policy.{field} is required")
    autonomy_level = _require_string(delegation_policy["autonomy_level"], "codex_execution_plan.delegation_policy.autonomy_level")
    if autonomy_level not in VALID_AUTONOMY_LEVELS:
        raise AssistError("codex_execution_plan.delegation_policy.autonomy_level is invalid")
    context_sharing = _require_string(delegation_policy["context_sharing"], "codex_execution_plan.delegation_policy.context_sharing")
    if context_sharing not in VALID_CONTEXT_SHARING:
        raise AssistError("codex_execution_plan.delegation_policy.context_sharing is invalid")
    allowed_operations = _normalize_string_list(delegation_policy["allowed_operations"], "codex_execution_plan.delegation_policy.allowed_operations")
    invalid_operations = [item for item in allowed_operations if item not in VALID_DELEGATED_OPERATIONS]
    if invalid_operations:
        raise AssistError(f"codex_execution_plan.delegation_policy.allowed_operations contains invalid operations: {invalid_operations}")
    confirmations = _normalize_string_list(delegation_policy["requires_human_confirmation"], "codex_execution_plan.delegation_policy.requires_human_confirmation")
    invalid_confirmations = [item for item in confirmations if item not in VALID_CONFIRMATION_OPERATIONS]
    if invalid_confirmations:
        raise AssistError(f"codex_execution_plan.delegation_policy.requires_human_confirmation contains invalid operations: {invalid_confirmations}")
    if delegation_policy["supervisor_gate_required"] is not True:
        raise AssistError("codex_execution_plan.delegation_policy.supervisor_gate_required must be true")
    return {
        "autonomy_level": autonomy_level,
        "context_sharing": context_sharing,
        "allowed_operations": allowed_operations,
        "requires_human_confirmation": confirmations,
        "supervisor_gate_required": True,
    }


def _normalize_goal_state(value: Any) -> JSON:
    goal_state = _require_mapping(value, "codex_execution_plan.goal_state")
    _reject_unknown_fields(
        goal_state,
        {"description", "owner", "sync_mode", "codex_thread_id", "source"},
        "codex_execution_plan.goal_state",
    )
    for field in ("description", "owner", "sync_mode"):
        if field not in goal_state:
            raise AssistError(f"codex_execution_plan.goal_state.{field} is required")
    owner = _require_string(goal_state["owner"], "codex_execution_plan.goal_state.owner")
    if owner not in VALID_GOAL_OWNERS:
        raise AssistError("codex_execution_plan.goal_state.owner is invalid")
    sync_mode = _require_string(goal_state["sync_mode"], "codex_execution_plan.goal_state.sync_mode")
    if sync_mode not in VALID_GOAL_SYNC_MODES:
        raise AssistError("codex_execution_plan.goal_state.sync_mode is invalid")
    normalized = {
        "description": _require_english_text(goal_state["description"], "codex_execution_plan.goal_state.description"),
        "owner": owner,
        "sync_mode": sync_mode,
    }
    if "codex_thread_id" in goal_state:
        normalized["codex_thread_id"] = _require_string(goal_state["codex_thread_id"], "codex_execution_plan.goal_state.codex_thread_id")
    if "source" in goal_state:
        normalized["source"] = _require_english_text(goal_state["source"], "codex_execution_plan.goal_state.source")
    return normalized


def _normalize_workflow_context(value: Any) -> JSON:
    workflow_context = _require_mapping(value, "codex_execution_plan.workflow_context")
    _reject_unknown_fields(
        workflow_context,
        {"original_user_request", "process_summary", "current_round", "drift_guards"},
        "codex_execution_plan.workflow_context",
    )
    for field in ("original_user_request", "process_summary", "current_round", "drift_guards"):
        if field not in workflow_context:
            raise AssistError(f"codex_execution_plan.workflow_context.{field} is required")
    return {
        "original_user_request": _require_string(
            workflow_context["original_user_request"],
            "codex_execution_plan.workflow_context.original_user_request",
        ),
        "process_summary": _normalize_string_list(
            workflow_context["process_summary"],
            "codex_execution_plan.workflow_context.process_summary",
        ),
        "current_round": _require_english_text(
            workflow_context["current_round"],
            "codex_execution_plan.workflow_context.current_round",
        ),
        "drift_guards": _normalize_string_list(
            workflow_context["drift_guards"],
            "codex_execution_plan.workflow_context.drift_guards",
        ),
    }


def _build_dispatch_batches(units: list[JSON]) -> list[list[str]]:
    pending = {str(unit["id"]): unit for unit in units}
    completed: set[str] = set()
    batches: list[list[str]] = []

    while pending:
        ready = [
            unit
            for unit in pending.values()
            if all(dep in completed for dep in unit["depends_on"])
        ]
        if not ready:
            raise AssistError("codex_execution_plan contains a dependency cycle or unknown dependency")

        serial_ready = sorted([unit for unit in ready if unit["dispatch_mode"] == "serial"], key=lambda item: item["id"])
        if serial_ready:
            batch = [serial_ready[0]["id"]]
        else:
            batch = sorted([unit["id"] for unit in ready if unit["dispatch_mode"] == "parallel"])
        batches.append(batch)
        for unit_id in batch:
            completed.add(unit_id)
            pending.pop(unit_id)
    return batches


def validate_execution_plan(plan: Any, *, expected_run_id: str | None = None) -> JSON:
    payload = _require_mapping(plan, "codex_execution_plan")
    _reject_unknown_fields(payload, REQUIRED_PLAN_FIELDS | OPTIONAL_PLAN_FIELDS, "codex_execution_plan")
    for field in REQUIRED_PLAN_FIELDS:
        if field not in payload:
            raise AssistError(f"codex_execution_plan.{field} is required")
    if payload["packet_type"] != "codex_execution_plan":
        raise AssistError("codex_execution_plan.packet_type must be codex_execution_plan")
    run_id = safe_id(_require_string(payload["run_id"], "codex_execution_plan.run_id"), "run_id")
    if expected_run_id and run_id != expected_run_id:
        raise AssistError("codex_execution_plan.run_id does not match the expected run_id")
    task_id = safe_id(_require_string(payload["task_id"], "codex_execution_plan.task_id"), "task_id")
    if _require_string(payload["created_by"], "codex_execution_plan.created_by") != "chatgpt_web":
        raise AssistError("codex_execution_plan.created_by must be chatgpt_web")
    if _require_string(payload["language"], "codex_execution_plan.language") != "en":
        raise AssistError("codex_execution_plan.language must be en")
    strategy = _require_string(payload["dispatch_strategy"], "codex_execution_plan.dispatch_strategy")
    if strategy not in VALID_STRATEGIES:
        raise AssistError("codex_execution_plan.dispatch_strategy is invalid")
    if _require_string(payload["local_supervisor"], "codex_execution_plan.local_supervisor") != "codex_main_thread":
        raise AssistError("codex_execution_plan.local_supervisor must be codex_main_thread")

    units = [_normalize_unit(unit, index) for index, unit in enumerate(_require_list(payload["execution_units"], "codex_execution_plan.execution_units"))]
    if not units:
        raise AssistError("codex_execution_plan.execution_units must not be empty")
    unit_ids = [unit["id"] for unit in units]
    if len(set(unit_ids)) != len(unit_ids):
        raise AssistError("codex_execution_plan.execution_units ids must be unique")
    known_ids = set(unit_ids)
    for unit in units:
        unknown_deps = sorted(set(unit["depends_on"]) - known_ids)
        if unknown_deps:
            raise AssistError(f"codex_execution_plan unit {unit['id']} has unknown dependencies: {unknown_deps}")
    batches = _build_dispatch_batches(units)
    checks = _normalize_checks(payload["acceptance_checks"])
    normalized = {
        "packet_type": "codex_execution_plan",
        "run_id": run_id,
        "task_id": task_id,
        "created_by": "chatgpt_web",
        "language": "en",
        "dispatch_strategy": strategy,
        "local_supervisor": "codex_main_thread",
        "execution_units": units,
        "acceptance_checks": checks,
        "dispatch_batches": batches,
        "parallel_unit_count": sum(1 for unit in units if unit["dispatch_mode"] == "parallel"),
    }
    if "provider_selection" in payload:
        normalized["provider_selection"] = _normalize_provider_selection(payload["provider_selection"])
    if "delegation_policy" in payload:
        normalized["delegation_policy"] = _normalize_delegation_policy(payload["delegation_policy"])
    if "goal_state" in payload:
        normalized["goal_state"] = _normalize_goal_state(payload["goal_state"])
    if "workflow_context" in payload:
        normalized["workflow_context"] = _normalize_workflow_context(payload["workflow_context"])
    return normalized


def load_execution_plan_from_response(response_dir: str | Path, *, expected_run_id: str | None = None) -> JSON:
    source_dir = Path(response_dir)
    plan_path = source_dir / "codex-execution-plan.json"
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise AssistError(f"missing codex execution plan artifact: {plan_path}") from exc
    except json.JSONDecodeError as exc:
        raise AssistError(f"invalid codex execution plan JSON: {plan_path}: {exc}") from exc
    return validate_execution_plan(payload, expected_run_id=expected_run_id)


def _default_backend(unit: JSON, context: JSON) -> JSON:
    return {
        "status": "ready_for_codex_main_thread",
        "backend": "manual_codex_dispatch",
        "agent_id": None,
        "instruction": (
            "The Codex main thread should dispatch this unit with the active "
            "multi-agent tool or another approved local Codex/Agents SDK backend."
        ),
        "unit_id": unit["id"],
        "batch_index": context["batch_index"],
        "batch_mode": context["batch_mode"],
    }


def default_codex_command() -> list[str]:
    configured = os.environ.get("CHATGPT_WEB_CODEX_COMMAND")
    if configured:
        return [configured]
    local_app = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    candidate = shutil.which("codex")
    if candidate and "WindowsApps" in Path(candidate).parts and local_app.exists():
        return [str(local_app)]
    if candidate:
        return [candidate]
    if local_app.exists():
        return [str(local_app)]
    return ["codex"]


def _codex_agent_prompt(unit: JSON, context: JSON) -> str:
    checks = json.dumps(context.get("acceptance_checks", []), ensure_ascii=False, indent=2)
    owned_paths = "\n".join(f"- {path}" for path in unit["owned_paths"])
    expected = "\n".join(f"- {artifact}" for artifact in unit["expected_artifacts"])
    workflow_context = context.get("workflow_context")
    workflow_section = ""
    if isinstance(workflow_context, dict):
        process_summary = "\n".join(f"- {item}" for item in workflow_context.get("process_summary", []))
        drift_guards = "\n".join(f"- {item}" for item in workflow_context.get("drift_guards", []))
        workflow_section = f"""
## Workflow Context

This context explains the original end-to-end flow so you can use the model's planning and coding ability well. It is background only and must not expand your unit scope.

Original request:
{workflow_context.get("original_user_request", "")}

Process summary:
{process_summary}

Current round:
{workflow_context.get("current_round", "")}

## Scope Guard

{drift_guards}

- The Unit Objective, Owned Paths, Expected Artifacts, Acceptance Checks, and supervisor gate below override workflow background.
- Ask the supervisor for clarification instead of broadening scope when workflow context and this unit conflict.

"""
    raw_requirements = unit.get("raw_user_requirements")
    requirements_section = ""
    if raw_requirements:
        requirements_section = f"""
## Original User Request Context

The unit objective above is your primary scope. Use this original request context to avoid drifting away from the user's end-to-end intent:

{raw_requirements}

"""
    return f"""# Codex Agent Dispatch Unit

You are a local Codex agent dispatched by the local supervisor from a ChatGPT Web-authored execution plan. Work only on this unit. Other agents may be working on disjoint paths, so do not revert unrelated changes.

## Run

- run_id: {context["run_id"]}
- task_id: {context["task_id"]}
- unit_id: {unit["id"]}
- batch_index: {context["batch_index"]}
- batch_mode: {context["batch_mode"]}
- response_dir: {context["response_dir"]}

## Unit Objective

{unit["prompt"]}

{workflow_section}\
{requirements_section}\
## Owned Paths

{owned_paths}

## Expected Artifacts

{expected}

## Acceptance Checks

```json
{checks}
```

## Rules

- Treat ChatGPT Web output as a candidate, not as verified delivery.
- Keep changes within owned paths unless the supervisor instructions clearly require otherwise.
- Preserve existing code style and local project rules.
- Run the relevant local checks when feasible and report exact commands/results.
- Do not read or output secrets, cookies, sessions, API keys, private keys, or account credentials.
- Finish with a concise summary of changed files, tests run, and residual risks.
"""


def build_codex_cli_backend(
    *,
    codex_command: list[str] | None = None,
    sandbox: str = DEFAULT_CODEX_SANDBOX,
    model: str | None = None,
    reasoning_effort: str | None = None,
    extra_args: list[str] | None = None,
) -> DispatchBackend:
    command_prefix = list(codex_command or default_codex_command())
    extra = list(extra_args or [])

    def backend(unit: JSON, context: JSON) -> JSON:
        workspace = Path(context["workspace_root"]).resolve()
        agent_root = workspace / ".tmp" / "chatgpt-web" / str(context["run_id"]) / "agents" / str(unit["id"])
        agent_root.mkdir(parents=True, exist_ok=True)
        prompt_path = agent_root / "prompt.md"
        stdout_path = agent_root / "stdout.jsonl"
        stderr_path = agent_root / "stderr.txt"
        last_message_path = agent_root / "last-message.md"
        prompt = _codex_agent_prompt(unit, context)
        prompt_path.write_text(prompt, encoding="utf-8")

        command = [
            *command_prefix,
            "exec",
            "--json",
            "--cd",
            str(workspace),
            "--sandbox",
            sandbox,
            "--output-last-message",
            str(last_message_path),
            *extra,
        ]
        if model:
            command.extend(["--model", model])
        if reasoning_effort:
            command.extend(["-c", f"model_reasoning_effort={json.dumps(reasoning_effort)}"])
        command.append("-")

        completed = subprocess.run(
            command,
            cwd=str(workspace),
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if not last_message_path.exists():
            last_message_path.write_text("", encoding="utf-8")

        return {
            "status": "completed" if completed.returncode == 0 else "failed",
            "backend": "codex_cli",
            "agent_id": f"codex-cli:{unit['id']}",
            "unit_id": unit["id"],
            "exit_code": completed.returncode,
            "command": command,
            "prompt_path": _relative_to_workspace(prompt_path, workspace),
            "stdout_path": _relative_to_workspace(stdout_path, workspace),
            "stderr_path": _relative_to_workspace(stderr_path, workspace),
            "last_message_path": _relative_to_workspace(last_message_path, workspace),
            "stdout_tail": _truncate_output(completed.stdout),
            "stderr_tail": _truncate_output(completed.stderr),
        }

    return backend


def dispatch_execution_plan(
    plan: Any,
    *,
    workspace_root: str | Path,
    response_dir: str | Path,
    dispatch_backend: DispatchBackend | None = None,
) -> JSON:
    workspace = Path(workspace_root).resolve()
    source_dir = Path(response_dir).resolve()
    validation_input = plan
    if isinstance(plan, dict) and {"dispatch_batches", "parallel_unit_count"}.issubset(plan):
        _reject_unknown_fields(plan, NORMALIZED_PLAN_FIELDS, "codex_execution_plan")
        validation_input = {key: plan[key] for key in REQUIRED_PLAN_FIELDS | OPTIONAL_PLAN_FIELDS if key in plan}
    normalized = validate_execution_plan(validation_input)
    unit_by_id = {unit["id"]: unit for unit in normalized["execution_units"]}
    backend = dispatch_backend or _default_backend
    batch_receipts: list[JSON] = []
    unit_receipts: list[JSON] = []

    def run_one(target_unit: JSON, target_context: JSON) -> JSON:
        try:
            result = backend(target_unit, target_context)
        except Exception as exc:  # Keep dispatch receipts authoritative even when an agent backend fails.
            return {
                "unit_id": target_unit["id"],
                "status": "failed",
                "backend": "dispatch_exception",
                "agent_id": None,
                "result": {
                    "status": "failed",
                    "backend": "dispatch_exception",
                    "agent_id": None,
                    "unit_id": target_unit["id"],
                    "error": str(exc),
                },
            }
        result = _require_mapping(result, f"dispatch result for {target_unit['id']}")
        status = _require_string(result.get("status"), f"dispatch result for {target_unit['id']}.status")
        if status not in {"completed", "dispatched", "ready_for_codex_main_thread", "skipped", "failed"}:
            raise AssistError(f"dispatch result for {target_unit['id']}.status is invalid")
        return {
            "unit_id": target_unit["id"],
            "status": status,
            "backend": result.get("backend", "unknown"),
            "agent_id": result.get("agent_id"),
            "result": result,
        }

    for batch_index, batch in enumerate(normalized["dispatch_batches"]):
        batch_mode = "parallel" if len(batch) > 1 else unit_by_id[batch[0]]["dispatch_mode"]
        results: list[JSON] = []
        context = {
            "workspace_root": str(workspace),
            "response_dir": str(source_dir),
            "batch_index": batch_index,
            "batch_mode": batch_mode,
            "run_id": normalized["run_id"],
            "task_id": normalized["task_id"],
            "acceptance_checks": normalized["acceptance_checks"],
            "provider_selection": normalized.get("provider_selection"),
            "delegation_policy": normalized.get("delegation_policy"),
            "goal_state": normalized.get("goal_state"),
            "workflow_context": normalized.get("workflow_context"),
        }
        if batch_mode == "parallel" and len(batch) > 1:
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                future_by_unit = {
                    executor.submit(run_one, unit_by_id[parallel_id], context): parallel_id
                    for parallel_id in batch
                }
                by_unit: dict[str, JSON] = {}
                for future in as_completed(future_by_unit):
                    unit_id_done = future_by_unit[future]
                    by_unit[unit_id_done] = future.result()
                results = [by_unit[parallel_id] for parallel_id in batch]
        else:
            results = [run_one(unit_by_id[unit_id], context) for unit_id in batch]
        unit_receipts.extend(results)
        batch_receipts.append(
            {
                "batch_index": batch_index,
                "execution_mode": batch_mode,
                "unit_ids": batch,
                "results": results,
            }
        )

    receipt = {
        "packet_type": "codex_dispatch_receipt",
        "run_id": normalized["run_id"],
        "task_id": normalized["task_id"],
        "created_at": now_iso(),
        "local_gate_status": "failed" if any(item["status"] == "failed" for item in unit_receipts) else "dispatched",
        "supervisor": "codex_main_thread",
        "source_plan": normalized,
        "dispatch_batches": batch_receipts,
        "unit_receipts": unit_receipts,
        "acceptance_checks": normalized["acceptance_checks"],
        "next_step": "Run the dispatched Codex work units, integrate accepted artifacts, then run the local supervisor verification gate.",
    }
    receipt_path = source_dir.parent / "codex-dispatch-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--response-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--backend", choices=sorted(VALID_CODEX_BACKENDS), default="manual")
    parser.add_argument("--codex-command", action="append", help="Command prefix for Codex CLI backend. Repeat for each argv part.")
    parser.add_argument("--sandbox", default=DEFAULT_CODEX_SANDBOX)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort")
    args = parser.parse_args(argv)
    try:
        plan = load_execution_plan_from_response(args.response_dir, expected_run_id=args.run_id)
        backend = None
        if args.backend == "codex-cli":
            backend = build_codex_cli_backend(
                codex_command=args.codex_command,
                sandbox=args.sandbox,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        receipt = dispatch_execution_plan(
            plan,
            workspace_root=args.workspace_root,
            response_dir=args.response_dir,
            dispatch_backend=backend,
        )
    except (AssistError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
