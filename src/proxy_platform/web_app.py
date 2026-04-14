from __future__ import annotations

from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from proxy_platform.inventory import add_host_record, load_host_registry, remove_host_record
from proxy_platform.manifest import load_manifest
from proxy_platform.projections import build_host_views, build_subscription_projection
from proxy_platform.providers import describe_local_providers


def create_app(
    manifest_path: str | Path,
    workspace_root: str | Path | None = None,
    mode: str | None = None,
) -> FastAPI:
    manifest = load_manifest(Path(manifest_path).resolve())
    resolved_workspace_root = Path(workspace_root or manifest.source_path.parent).resolve()
    active_mode = mode or manifest.default_mode
    app = FastAPI(title="proxy-platform web console")

    def require_host_registry():
        if manifest.host_registry is None:
            raise HTTPException(status_code=500, detail="host registry source is not configured")
        if not manifest.host_registry.applies_to_mode(active_mode):
            raise HTTPException(
                status_code=500,
                detail=f"host registry source is not configured for mode {active_mode}",
            )
        return manifest.host_registry

    def load_current_state() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        host_registry_source = require_host_registry()
        registry = load_host_registry(host_registry_source, resolved_workspace_root)
        host_views = [asdict(item) for item in build_host_views(registry)]
        subscriptions = asdict(build_subscription_projection(registry))
        providers = [asdict(item) for item in describe_local_providers(manifest)]
        return host_views, subscriptions, providers

    @app.get("/api/hosts")
    def api_hosts() -> dict[str, Any]:
        host_views, _, _ = load_current_state()
        return {"hosts": host_views}

    @app.get("/api/subscriptions")
    def api_subscriptions() -> dict[str, Any]:
        _, subscriptions, _ = load_current_state()
        return subscriptions

    @app.get("/api/providers")
    def api_providers() -> dict[str, Any]:
        _, _, providers = load_current_state()
        return {"providers": providers}

    @app.post("/api/hosts")
    def api_add_host(payload: dict[str, Any]) -> dict[str, Any]:
        host_registry_source = require_host_registry()
        try:
            record = add_host_record(host_registry_source, resolved_workspace_root, payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"host": asdict(record)}

    @app.delete("/api/hosts/{host_name}")
    def api_delete_host(host_name: str) -> dict[str, Any]:
        host_registry_source = require_host_registry()
        try:
            removed = remove_host_record(host_registry_source, resolved_workspace_root, host_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown host: {host_name}") from exc
        return {"removed": removed}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        host_views, subscriptions, providers = load_current_state()
        host_rows = "".join(
            (
                "<tr>"
                f"<td>{escape(item['name'])}</td>"
                f"<td>{escape(item['provider'])}</td>"
                f"<td>{escape(item['observed_health'])}</td>"
                f"<td>{escape(str(item['should_publish']).lower())}</td>"
                "</tr>"
            )
            for item in host_views
        )
        subscription_rows = "".join(
            (
                "<li>"
                f"{escape(item['name'])}: "
                f"<button data-copy=\"{escape(item['v2ray_url'])}\">copy v2ray</button> "
                f"<button data-copy=\"{escape(item['hiddify_import_url'])}\">copy hiddify</button>"
                "</li>"
            )
            for item in subscriptions["per_node"]
        )
        provider_rows = "".join(
            (
                "<li>"
                f"{escape(item['provider_id'])}: startup_timeout={item['startup_timeout_seconds']} "
                f"request_timeout={item['request_timeout_seconds']}"
                "</li>"
            )
            for item in providers
        )
        return f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>proxy-platform web console</title>
  </head>
  <body>
    <h1>proxy-platform web console</h1>
    <section>
      <h2>主机现场清单</h2>
      <table border="1">
        <thead>
          <tr><th>name</th><th>provider</th><th>observed</th><th>publish</th></tr>
        </thead>
        <tbody>{host_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>订阅入口</h2>
      <p>{escape(subscriptions['multi_node_url'])}</p>
      <p>{escape(subscriptions['multi_node_hiddify_import'])}</p>
      <ul>{subscription_rows}</ul>
    </section>
    <section>
      <h2>本地 provider 生命周期</h2>
      <ul>{provider_rows}</ul>
    </section>
    <script>
      document.querySelectorAll('[data-copy]').forEach((button) => {{
        button.addEventListener('click', async () => {{
          await navigator.clipboard.writeText(button.dataset.copy);
        }});
      }});
    </script>
  </body>
</html>
"""

    return app


def run_web_console(
    manifest_path: str | Path,
    workspace_root: str | Path | None,
    mode: str | None,
    host: str,
    port: int,
) -> None:
    import uvicorn

    app = create_app(manifest_path, workspace_root, mode=mode)
    uvicorn.run(app, host=host, port=port)
