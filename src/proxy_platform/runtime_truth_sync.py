from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(frozen=True)
class RuntimeTruthSyncResult:
    seeded_files: tuple[str, ...]
    refreshed_files: tuple[str, ...]
    preserved_files: tuple[str, ...]


TRUTH_REFRESH_TARGETS: tuple[tuple[Path, Path], ...] = (
    (
        Path("operator/nodes.yaml"),
        Path("repos/proxy_ops_private/inventory/nodes.yaml"),
    ),
    (
        Path("operator/subscriptions.yaml"),
        Path("repos/proxy_ops_private/inventory/subscriptions.yaml"),
    ),
)


def refresh_runtime_truth_from_seed(
    *,
    previous_seed_root: str | Path,
    current_seed_root: str | Path,
    workspace_root: str | Path,
) -> RuntimeTruthSyncResult:
    resolved_previous_seed_root = Path(previous_seed_root).resolve()
    resolved_current_seed_root = Path(current_seed_root).resolve()
    resolved_workspace_root = Path(workspace_root).resolve()

    seeded_files: list[str] = []
    refreshed_files: list[str] = []
    preserved_files: list[str] = []

    for source_relative, destination_relative in TRUTH_REFRESH_TARGETS:
        current_seed_path = resolved_current_seed_root / source_relative
        if not current_seed_path.exists():
            raise ValueError(f"missing current runtime truth seed file: {current_seed_path}")

        previous_seed_path = resolved_previous_seed_root / source_relative
        destination_path = resolved_workspace_root / destination_relative

        if not destination_path.exists():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current_seed_path, destination_path)
            seeded_files.append(str(destination_relative))
            continue

        if previous_seed_path.exists() and _same_file_content(destination_path, previous_seed_path):
            if not _same_file_content(destination_path, current_seed_path):
                shutil.copy2(current_seed_path, destination_path)
                refreshed_files.append(str(destination_relative))
                continue

        preserved_files.append(str(destination_relative))

    return RuntimeTruthSyncResult(
        seeded_files=tuple(seeded_files),
        refreshed_files=tuple(refreshed_files),
        preserved_files=tuple(preserved_files),
    )


def _same_file_content(left: Path, right: Path) -> bool:
    return left.read_bytes() == right.read_bytes()
