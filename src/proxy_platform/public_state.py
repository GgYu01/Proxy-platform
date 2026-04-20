from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import json
from pathlib import Path
from typing import Any

from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import ManifestError
from proxy_platform.manifest import PlatformManifest
from proxy_platform.projections import build_host_views
from proxy_platform.projections import build_subscription_projection


class PublicStateError(ValueError):
    """Raised when public snapshot files are missing or invalid."""


@dataclass(frozen=True)
class PublicStateExportResult:
    host_console_path: Path
    subscription_path: Path
    generated_at: str


def export_public_state(
    *,
    manifest: PlatformManifest,
    workspace_root: str | Path,
    output_root: str | Path,
) -> PublicStateExportResult:
    if manifest.host_registry is None or not manifest.host_registry.applies_to_mode("operator"):
        raise ManifestError("operator host registry source is not configured for public export")

    resolved_workspace_root = Path(workspace_root).resolve()
    resolved_output_root = Path(output_root).resolve()
    registry = load_host_registry(manifest.host_registry, resolved_workspace_root)
    host_views = build_host_views(registry)
    subscription_projection = build_subscription_projection(registry)
    generated_at = _isoformat_now()

    host_console_payload = {
        "generated_at": generated_at,
        "hosts": [
            {
                "name": item.name,
                "provider": item.provider,
                "deployment_topology": item.deployment_topology,
                "runtime_service": item.runtime_service,
                "observed_health": item.observed_health,
                "should_publish": item.should_publish,
                "publish_reason": item.publish_reason,
            }
            for item in host_views
        ],
    }
    subscription_payload = {
        "generated_at": generated_at,
        "profile_name": registry.subscriptions.profile_name,
        "multi_node_url": subscription_projection.multi_node_url,
        "multi_node_hiddify_import": subscription_projection.multi_node_hiddify_import,
        "remote_profile_url": subscription_projection.remote_profile_url,
        "per_node": [
            {
                "name": item.name,
                "alias": item.alias,
                "observed_health": _observed_health_for_node(host_views, item.name),
                "v2ray_url": item.v2ray_url,
                "hiddify_import_url": item.hiddify_import_url,
            }
            for item in subscription_projection.per_node
        ],
    }

    resolved_output_root.mkdir(parents=True, exist_ok=True)
    host_console_path = resolved_output_root / "host_console.json"
    subscription_path = resolved_output_root / "subscriptions.json"
    host_console_path.write_text(json.dumps(host_console_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subscription_path.write_text(json.dumps(subscription_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return PublicStateExportResult(
        host_console_path=host_console_path,
        subscription_path=subscription_path,
        generated_at=generated_at,
    )


def load_public_host_console(path: str | Path) -> list[dict[str, Any]]:
    resolved_path, payload = _load_public_snapshot(path)
    hosts = payload.get("hosts")
    if not isinstance(hosts, list):
        raise PublicStateError(f"{resolved_path} must define a hosts list")
    normalized: list[dict[str, Any]] = []
    for item in hosts:
        if not isinstance(item, dict):
            raise PublicStateError(f"{resolved_path} contains an invalid host entry")
        normalized.append(
            {
                "name": _require_string(item.get("name"), resolved_path, "name"),
                "provider": _require_string(item.get("provider"), resolved_path, "provider"),
                "deployment_topology": _require_string(
                    item.get("deployment_topology"), resolved_path, "deployment_topology"
                ),
                "runtime_service": _require_string(item.get("runtime_service"), resolved_path, "runtime_service"),
                "observed_health": _require_string(item.get("observed_health"), resolved_path, "observed_health"),
                "should_publish": _require_bool(item.get("should_publish"), resolved_path, "should_publish"),
                "publish_reason": _require_string(item.get("publish_reason"), resolved_path, "publish_reason"),
            }
        )
    return normalized


def load_public_subscriptions(path: str | Path) -> dict[str, Any]:
    resolved_path, payload = _load_public_snapshot(path)
    per_node = payload.get("per_node")
    if not isinstance(per_node, list):
        raise PublicStateError(f"{resolved_path} must define a per_node list")
    return {
        "generated_at": _require_string(payload.get("generated_at"), resolved_path, "generated_at"),
        "profile_name": _require_string(payload.get("profile_name"), resolved_path, "profile_name"),
        "multi_node_url": _require_string(payload.get("multi_node_url"), resolved_path, "multi_node_url"),
        "multi_node_hiddify_import": _require_string(
            payload.get("multi_node_hiddify_import"), resolved_path, "multi_node_hiddify_import"
        ),
        "remote_profile_url": _require_string(payload.get("remote_profile_url"), resolved_path, "remote_profile_url"),
        "per_node": [
            {
                "name": _require_string(_require_mapping(item, resolved_path).get("name"), resolved_path, "name"),
                "alias": _require_string(_require_mapping(item, resolved_path).get("alias"), resolved_path, "alias"),
                "observed_health": _require_string(
                    _require_mapping(item, resolved_path).get("observed_health"), resolved_path, "observed_health"
                ),
                "v2ray_url": _require_string(
                    _require_mapping(item, resolved_path).get("v2ray_url"), resolved_path, "v2ray_url"
                ),
                "hiddify_import_url": _require_string(
                    _require_mapping(item, resolved_path).get("hiddify_import_url"),
                    resolved_path,
                    "hiddify_import_url",
                ),
            }
            for item in per_node
        ],
    }


def _load_public_snapshot(path: str | Path) -> tuple[Path, dict[str, Any]]:
    resolved_path = Path(path).resolve()
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicStateError(f"failed to load public snapshot {resolved_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PublicStateError(f"{resolved_path} must contain a JSON object")
    return resolved_path, payload


def _require_mapping(value: Any, resolved_path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PublicStateError(f"{resolved_path} contains an invalid per_node entry")
    return value


def _require_string(value: Any, resolved_path: Path, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicStateError(f"{resolved_path} must define a string {field_name}")
    return value


def _require_bool(value: Any, resolved_path: Path, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicStateError(f"{resolved_path} must define a boolean {field_name}")
    return value


def _observed_health_for_node(host_views: list[Any], host_name: str) -> str:
    for item in host_views:
        if item.name == host_name:
            return item.observed_health
    return "unknown"


def _isoformat_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
