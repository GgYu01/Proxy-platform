from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import HostRegistrySource


DEFAULT_PROBE_TIMEOUT_SECONDS = 2.5
DEFAULT_PROBE_PORT_OFFSET = 1
DEFAULT_PROBE_SOURCE = "tcp_probe"


@dataclass(frozen=True)
class ObservationRefreshResult:
    observations_path: Path
    probed_hosts: int
    healthy_hosts: int
    down_hosts: int
    source: str


def refresh_host_observations(
    *,
    source: HostRegistrySource,
    workspace_root: str | Path,
    connect_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    port_offset: int = DEFAULT_PROBE_PORT_OFFSET,
    max_workers: int | None = None,
) -> ObservationRefreshResult:
    if source.observations_path is None:
        raise ValueError("host registry source does not define observations_path")

    resolved_workspace_root = Path(workspace_root).resolve()
    observations_path = _resolve_source_path(resolved_workspace_root, source.observations_path)
    registry = load_host_registry(source, resolved_workspace_root)
    payload = _probe_registry(
        registry=registry,
        connect_timeout_seconds=connect_timeout_seconds,
        port_offset=port_offset,
        max_workers=max_workers,
    )
    observations_path.parent.mkdir(parents=True, exist_ok=True)
    observations_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    healthy_hosts = sum(1 for item in payload["hosts"] if item["health"] == "healthy")
    down_hosts = sum(1 for item in payload["hosts"] if item["health"] == "down")
    return ObservationRefreshResult(
        observations_path=observations_path,
        probed_hosts=len(payload["hosts"]),
        healthy_hosts=healthy_hosts,
        down_hosts=down_hosts,
        source=DEFAULT_PROBE_SOURCE,
    )


def _probe_registry(
    *,
    registry,
    connect_timeout_seconds: float,
    port_offset: int,
    max_workers: int | None,
) -> dict[str, object]:
    nodes = list(registry.nodes)
    if not nodes:
        return {"generated_at": _isoformat_now(), "hosts": []}

    results: list[dict[str, str] | None] = [None] * len(nodes)
    worker_count = max(1, min(len(nodes), max_workers or len(nodes), 8))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                _probe_host,
                host=node.host,
                name=node.name,
                port=node.base_port + port_offset,
                connect_timeout_seconds=connect_timeout_seconds,
            ): index
            for index, node in enumerate(nodes)
        }
        for future in as_completed(future_map):
            results[future_map[future]] = future.result()

    return {
        "generated_at": _isoformat_now(),
        "hosts": [item for item in results if item is not None],
    }


def _probe_host(*, host: str, name: str, port: int, connect_timeout_seconds: float) -> dict[str, str]:
    observed_at = _isoformat_now()
    try:
        connection = socket.create_connection((host, port), timeout=connect_timeout_seconds)
    except Exception as exc:
        return {
            "name": name,
            "health": "down",
            "source": DEFAULT_PROBE_SOURCE,
            "observed_at": observed_at,
            "detail": f"tcp {host}:{port} failed: {type(exc).__name__}: {exc}",
        }
    try:
        return {
            "name": name,
            "health": "healthy",
            "source": DEFAULT_PROBE_SOURCE,
            "observed_at": observed_at,
            "detail": f"tcp connect ok {host}:{port}",
        }
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()


def _resolve_source_path(workspace_root: Path, source_path: Path) -> Path:
    return source_path if source_path.is_absolute() else workspace_root / source_path


def _isoformat_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
