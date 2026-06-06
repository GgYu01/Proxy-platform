#!/usr/bin/env python3
"""Validate active Codex-led harness alignment.

This check intentionally rejects removed platform-specific surfaces in active
entrypoints. It is narrow by design: generic protocol words such as "control
plane" are allowed, but old platform names are not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


BLOCKED_TOKENS = (
    "OpenClaw",
    "openclaw",
    "MCO",
    "MCOVerdict",
    "mco_",
    "openclaw-codeagent",
)

ACTIVE_PATHS = (
    "AGENTS.md",
    "docs/codex-led-harness-architecture.md",
    "docs/codex-sdk-language-decision.md",
    "docs/codex_tooling_inventory.md",
    "docs/harness-evaluation-standards-2026-06-02.md",
    "docs/project-local-harness-installation.md",
    "docs/executor-run-contract.md",
    "docs/executor-materialization-profile.md",
    "docs/project-capability-profile.md",
    "docs/protocol-boundaries.md",
    "docs/chatgpt-web-manual-assist-workflow.md",
    "docs/chatgpt-app-no-api-supervised-workflow.md",
    "docs/chatgpt-web-workload-and-entry-design.md",
    "prompt_groups/codex_harness/README.md",
    "prompt_groups/codex_harness/codex_executor.md",
    "prompt_groups/codex_harness/task_payload_template.md",
    "prompt_groups/codex_harness/chatgpt_web_manual_assist.md",
    "configs/harness-provider-registry.json",
    "configs/harness-evaluation-registry.json",
    "schemas/executor_run_contract.schema.json",
    "tools/validate_executor_contract.py",
    "tools/validate_harness_provider_registry.py",
    "tools/validate_harness_evaluation_registry.py",
    "tools/package_harness.py",
)

SOURCE_ONLY_ACTIVE_PATHS = (
    "tests/test_harness_package_tools.py",
)

BLOCKED_PATH_FRAGMENTS = (
    "prompt_groups/openclaw_codex",
    "tools/openclaw_contract_overlay.py",
    "tools/remote_openclaw_model_audit.py",
    "docs/openclaw_",
    "docs/latest-preview-update-strategy.md",
)

IGNORED_DIRS = {
    ".git",
    ".tmp",
    "__pycache__",
    "repos",
}

REQUIRED_TERM_GROUPS = {
    "requirement_context": (
        "schemas/executor_run_contract.schema.json",
        "tools/validate_executor_contract.py",
        "docs/executor-run-contract.md",
        "prompt_groups/codex_harness/task_payload_template.md",
    ),
    "provider_selection": (
        "schemas/executor_run_contract.schema.json",
        "tools/validate_executor_contract.py",
        "docs/executor-run-contract.md",
        "docs/protocol-boundaries.md",
        "prompt_groups/codex_harness/task_payload_template.md",
        "prompt_groups/codex_harness/README.md",
    ),
    "delegation_policy": (
        "schemas/executor_run_contract.schema.json",
        "tools/validate_executor_contract.py",
        "docs/executor-run-contract.md",
        "prompt_groups/codex_harness/task_payload_template.md",
        "prompt_groups/codex_harness/README.md",
    ),
    "workflow_context": (
        "tools/chatgpt_web_execution_dispatcher.py",
        "tools/chatgpt_web_harness.py",
        "docs/codex-led-harness-architecture.md",
        "docs/executor-run-contract.md",
        "prompt_groups/codex_harness/chatgpt_web_manual_assist.md",
        "prompt_groups/codex_harness/README.md",
    ),
    "antigravity": (
        "configs/harness-provider-registry.json",
        "tools/validate_harness_provider_registry.py",
        "docs/codex-led-harness-architecture.md",
        "docs/protocol-boundaries.md",
        "prompt_groups/codex_harness/README.md",
    ),
    "openai-codex": (
        "AGENTS.md",
        "configs/harness-provider-registry.json",
        "docs/codex-led-harness-architecture.md",
        "docs/codex-sdk-language-decision.md",
        "docs/codex_tooling_inventory.md",
        "docs/protocol-boundaries.md",
    ),
    "keep_one_codex_sdk_adapter_python_only": (
        "docs/codex-sdk-language-decision.md",
        "tools/probe_codex_sdk_capabilities.py",
    ),
}


class AlignmentFinding:
    def __init__(self, path: str, line: int | None, token: str, text: str) -> None:
        self.path = path
        self.line = line
        self.token = token
        self.text = text

    path: str
    line: int | None
    token: str
    text: str

    def format(self) -> str:
        if self.line is None:
            return f"{self.path}: blocked path token {self.token}"
        return f"{self.path}:{self.line}: blocked token {self.token}: {self.text}"


class AlignmentReport:
    def __init__(self, findings: list[AlignmentFinding]) -> None:
        self.findings = findings

    @property
    def ok(self) -> bool:
        return not self.findings

    def format_findings(self) -> str:
        return "\n".join(finding.format() for finding in self.findings)


def _to_posix(path: Path) -> str:
    return path.as_posix()


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored(path.relative_to(root)):
            continue
        files.append(path)
    return files


def _is_installed_harness(root: Path) -> bool:
    manifest = root / "harness-package.json"
    if not manifest.is_file():
        return False
    text = manifest.read_text(encoding="utf-8-sig", errors="replace")
    return '"package_id": "codex_project_harness"' in text


def validate_workspace(root: str | Path = ".") -> AlignmentReport:
    root = Path(root)
    findings: list[AlignmentFinding] = []
    active_paths = list(ACTIVE_PATHS)
    if not _is_installed_harness(root):
        active_paths.extend(SOURCE_ONLY_ACTIVE_PATHS)

    for path in _iter_files(root):
        rel = _to_posix(path.relative_to(root))
        for fragment in BLOCKED_PATH_FRAGMENTS:
            if fragment in rel:
                findings.append(AlignmentFinding(rel, None, fragment, ""))

    for rel in active_paths:
        path = root / rel
        if not path.exists():
            findings.append(AlignmentFinding(rel, None, "missing", "active harness file is missing"))
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for token in BLOCKED_TOKENS:
                if token in line:
                    findings.append(AlignmentFinding(rel, line_no, token, line.strip()))

    for term, rel_paths in REQUIRED_TERM_GROUPS.items():
        for rel in rel_paths:
            path = root / rel
            if not path.exists():
                findings.append(AlignmentFinding(rel, None, "missing", f"required term {term} cannot be checked"))
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace").lower()
            if term.lower() not in text:
                findings.append(AlignmentFinding(rel, None, term, f"active harness file must mention {term}"))

    return AlignmentReport(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    report = validate_workspace(args.root)
    if not report.ok:
        print(report.format_findings(), file=sys.stderr)
        return 1
    print("valid: harness_alignment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
