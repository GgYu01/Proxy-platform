from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


class RuntimeBootstrapError(ValueError):
    """Raised when runtime seed content is incomplete."""


@dataclass(frozen=True)
class RuntimeBootstrapResult:
    created_directories: tuple[str, ...]
    seeded_files: tuple[str, ...]
    refreshed_files: tuple[str, ...]
    preserved_files: tuple[str, ...]


PRESERVED_RUNTIME_SEEDS: tuple[tuple[Path, Path], ...] = (
    (
        Path("operator/nodes.yaml"),
        Path("repos/proxy_ops_private/inventory/nodes.yaml"),
    ),
    (
        Path("operator/subscriptions.yaml"),
        Path("repos/proxy_ops_private/inventory/subscriptions.yaml"),
    ),
)

REFRESHED_RUNTIME_SEEDS: tuple[tuple[Path, Path], ...] = (
    (
        Path("authority/remote_proxy/scripts/service.sh"),
        Path("repos/remote_proxy/scripts/service.sh"),
    ),
    (
        Path("authority/remote_proxy/config/cliproxy-plus.env"),
        Path("repos/remote_proxy/config/cliproxy-plus.env"),
    ),
    (
        Path("authority/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md"),
        Path("repos/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md"),
    ),
    (
        Path("authority/remote_proxy/docs/deploy/infra-core-ubuntu-online.md"),
        Path("repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md"),
    ),
)

OPTIONAL_RUNTIME_SEEDS: tuple[tuple[Path, Path], ...] = (
    (
        Path("state/observations/hosts.json"),
        Path("state/observations/hosts.json"),
    ),
)

REQUIRED_RUNTIME_DIRECTORIES: tuple[Path, ...] = (
    Path("state/jobs/audit"),
    Path("state/jobs/handoffs"),
    Path("state/jobs/plans"),
)


def bootstrap_runtime_workspace(*, seed_root: str | Path, workspace_root: str | Path) -> RuntimeBootstrapResult:
    resolved_seed_root = Path(seed_root).resolve()
    resolved_workspace_root = Path(workspace_root).resolve()

    created_directories: list[str] = []
    seeded_files: list[str] = []
    refreshed_files: list[str] = []
    preserved_files: list[str] = []

    if not resolved_seed_root.exists():
        raise RuntimeBootstrapError(f"runtime seed root does not exist: {resolved_seed_root}")

    for relative_path in REQUIRED_RUNTIME_DIRECTORIES:
        directory_path = resolved_workspace_root / relative_path
        if not directory_path.exists():
            directory_path.mkdir(parents=True, exist_ok=True)
            created_directories.append(str(relative_path))

    for source_relative, destination_relative in PRESERVED_RUNTIME_SEEDS:
        source_path = resolved_seed_root / source_relative
        if not source_path.exists():
            raise RuntimeBootstrapError(f"missing required runtime seed file: {source_path}")
        _sync_seed_file(
            source_path=source_path,
            destination_path=resolved_workspace_root / destination_relative,
            destination_relative=destination_relative,
            seeded_files=seeded_files,
            refreshed_files=refreshed_files,
            preserved_files=preserved_files,
            refresh_existing=False,
        )

    for source_relative, destination_relative in REFRESHED_RUNTIME_SEEDS:
        source_path = resolved_seed_root / source_relative
        if not source_path.exists():
            raise RuntimeBootstrapError(f"missing required runtime seed file: {source_path}")
        _sync_seed_file(
            source_path=source_path,
            destination_path=resolved_workspace_root / destination_relative,
            destination_relative=destination_relative,
            seeded_files=seeded_files,
            refreshed_files=refreshed_files,
            preserved_files=preserved_files,
            refresh_existing=True,
        )

    for source_relative, destination_relative in OPTIONAL_RUNTIME_SEEDS:
        source_path = resolved_seed_root / source_relative
        if not source_path.exists():
            continue
        _sync_seed_file(
            source_path=source_path,
            destination_path=resolved_workspace_root / destination_relative,
            destination_relative=destination_relative,
            seeded_files=seeded_files,
            refreshed_files=refreshed_files,
            preserved_files=preserved_files,
            refresh_existing=False,
        )

    return RuntimeBootstrapResult(
        created_directories=tuple(created_directories),
        seeded_files=tuple(seeded_files),
        refreshed_files=tuple(refreshed_files),
        preserved_files=tuple(preserved_files),
    )


def _sync_seed_file(
    *,
    source_path: Path,
    destination_path: Path,
    destination_relative: Path,
    seeded_files: list[str],
    refreshed_files: list[str],
    preserved_files: list[str],
    refresh_existing: bool,
) -> None:
    if destination_path.exists():
        if refresh_existing:
            shutil.copy2(source_path, destination_path)
            refreshed_files.append(str(destination_relative))
            return
        preserved_files.append(str(destination_relative))
        return
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    seeded_files.append(str(destination_relative))
