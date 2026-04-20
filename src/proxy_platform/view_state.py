from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import ManifestError
from proxy_platform.manifest import PlatformManifest
from proxy_platform.projections import build_host_views
from proxy_platform.projections import build_subscription_projection
from proxy_platform.public_state import load_public_host_console
from proxy_platform.public_state import load_public_subscriptions


PUBLIC_HOST_SNAPSHOT_SOURCE_ID = "public_host_console_snapshot"
PUBLIC_SUBSCRIPTION_SNAPSHOT_SOURCE_ID = "public_subscription_snapshot"


def load_view_state(
    *,
    manifest: PlatformManifest,
    workspace_root: str | Path,
    mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolved_workspace_root = Path(workspace_root).resolve()
    if manifest.host_registry is not None and manifest.host_registry.applies_to_mode(mode):
        registry = load_host_registry(manifest.host_registry, resolved_workspace_root)
        return (
            [asdict(item) for item in build_host_views(registry)],
            asdict(build_subscription_projection(registry)),
        )

    return (
        load_public_host_console(_resolve_public_source_path(manifest, resolved_workspace_root, PUBLIC_HOST_SNAPSHOT_SOURCE_ID, mode)),
        load_public_subscriptions(
            _resolve_public_source_path(manifest, resolved_workspace_root, PUBLIC_SUBSCRIPTION_SNAPSHOT_SOURCE_ID, mode)
        ),
    )


def _resolve_public_source_path(
    manifest: PlatformManifest,
    workspace_root: Path,
    source_id: str,
    mode: str,
) -> Path:
    source = manifest.state_sources.get(source_id)
    if source is None or not source.applies_to_mode(mode):
        raise ManifestError(f"{_describe_source(source_id, source)} is not configured for mode {mode}")
    return source.path if source.path.is_absolute() else workspace_root / source.path


def _describe_source(source_id: str, source: Any | None) -> str:
    if source is not None:
        return source.display_name.lower()
    return source_id.replace("_", " ")
