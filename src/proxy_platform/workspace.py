from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from proxy_platform.manifest import PlatformManifest, RepoSpec


@dataclass(frozen=True)
class RepoStatus:
    repo_id: str
    display_name: str
    role: str
    visibility: str
    required: bool
    selected_path: Path
    exists: bool
    local_override_path: Path | None
    local_override_exists: bool
    default_url: str


@dataclass(frozen=True)
class WorkspaceDiagnosis:
    ok: bool
    mode: str
    repo_statuses: list[RepoStatus]
    missing_required: list[RepoStatus]


@dataclass(frozen=True)
class GitCommandResult:
    ok: bool
    detail: str = ""


def collect_repo_statuses(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[RepoStatus]:
    root = Path(workspace_root).resolve()
    statuses: list[RepoStatus] = []
    for repo in manifest.repos_for_mode(mode):
        selected_path = root / repo.default_path
        local_override_exists = bool(repo.local_override_path and repo.local_override_path.exists())
        statuses.append(
            RepoStatus(
                repo_id=repo.repo_id,
                display_name=repo.display_name,
                role=repo.role,
                visibility=repo.visibility,
                required=repo.required,
                selected_path=selected_path,
                exists=selected_path.exists(),
                local_override_path=repo.local_override_path,
                local_override_exists=local_override_exists,
                default_url=repo.default_url,
            )
        )
    return statuses


def diagnose_workspace(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> WorkspaceDiagnosis:
    statuses = collect_repo_statuses(manifest, workspace_root, mode)
    missing_required = [status for status in statuses if status.required and not status.exists]
    return WorkspaceDiagnosis(
        ok=not missing_required,
        mode=mode,
        repo_statuses=statuses,
        missing_required=missing_required,
    )


def build_init_plan(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[str]:
    root = Path(workspace_root).resolve()
    steps = [f"dry-run: initialize workspace at {root} in mode={mode}"]
    for repo in manifest.repos_for_mode(mode):
        workspace_path = root / repo.default_path
        steps.append(_repo_plan_line("init", repo, workspace_path))
    return steps


def build_sync_plan(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[str]:
    root = Path(workspace_root).resolve()
    steps = [f"dry-run: sync workspace at {root} in mode={mode}"]
    for repo in manifest.repos_for_mode(mode):
        workspace_path = root / repo.default_path
        steps.append(_repo_plan_line("sync", repo, workspace_path))
    return steps


def initialize_workspace(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[str]:
    root = Path(workspace_root).resolve()
    steps = [f"initialize workspace at {root} in mode={mode}"]
    for repo in manifest.repos_for_mode(mode):
        workspace_path = root / repo.default_path
        steps.append(_materialize_repo(repo, workspace_path, action="init"))
    return steps


def sync_workspace(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[str]:
    root = Path(workspace_root).resolve()
    steps = [f"sync workspace at {root} in mode={mode}"]
    for repo in manifest.repos_for_mode(mode):
        workspace_path = root / repo.default_path
        steps.append(_materialize_repo(repo, workspace_path, action="sync"))
    return steps


def _repo_plan_line(action: str, repo: RepoSpec, workspace_path: Path) -> str:
    if workspace_path.exists():
        return f"{action}: keep existing {repo.repo_id} at {workspace_path}"
    if repo.local_override_path and repo.local_override_path.exists():
        return (
            f"{action}: {repo.repo_id} missing at {workspace_path}; "
            f"local override available at {repo.local_override_path}"
        )
    return f"{action}: add {repo.repo_id} from {repo.default_url} into {workspace_path}"


def _materialize_repo(repo: RepoSpec, workspace_path: Path, *, action: str) -> str:
    if workspace_path.exists():
        if _is_git_repo(workspace_path):
            result = _run_git(["git", "-C", str(workspace_path), "fetch", "--all", "--tags"])
            if not result.ok:
                return f"{action}: failed to fetch {repo.repo_id} at {workspace_path}: {result.detail}"
            return f"{action}: fetched existing {repo.repo_id} at {workspace_path}"
        return f"{action}: keep existing {repo.repo_id} at {workspace_path}"

    if workspace_path.is_symlink():
        workspace_path.unlink()

    if repo.local_override_path and repo.local_override_path.exists():
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        workspace_path.symlink_to(repo.local_override_path.resolve(), target_is_directory=True)
        return f"{action}: linked {repo.repo_id} -> {repo.local_override_path.resolve()}"

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(["git", "clone", repo.default_url, str(workspace_path)])
    if not result.ok:
        _cleanup_failed_clone_path(workspace_path)
        return f"{action}: failed to clone {repo.repo_id} from {repo.default_url} into {workspace_path}: {result.detail}"
    return f"{action}: cloned {repo.repo_id} from {repo.default_url} into {workspace_path}"


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _run_git(argv: list[str]) -> GitCommandResult:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    if completed.returncode == 0:
        return GitCommandResult(ok=True)
    return GitCommandResult(ok=False, detail=_summarize_git_failure(completed))


def _summarize_git_failure(completed: subprocess.CompletedProcess[str]) -> str:
    for stream in (completed.stderr, completed.stdout):
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return f"git exited with code {completed.returncode}"


def _cleanup_failed_clone_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if path.exists():
        shutil.rmtree(path)
