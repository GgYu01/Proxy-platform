from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
import json
from pathlib import Path
import secrets
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from proxy_platform.control_plane_read_model import ControlPlaneReadClient
from proxy_platform.jobs import (
    JobApplyUnsupportedError,
    JobConfigError,
    JobPlanIntegrityError,
    apply_job_plan,
    list_audit_records,
    load_job_plan,
    plan_job,
    resolve_job_plan_path,
)
from proxy_platform.manifest import ManifestError
from proxy_platform.manifest import load_manifest
from proxy_platform.observation_probe import refresh_host_observations
from proxy_platform.providers import describe_local_providers
from proxy_platform.view_state import load_view_state
from proxy_platform.web_view import (
    build_audit_page_context,
    build_hosts_page_context,
    build_jobs_page_context,
    build_overview_page_context,
    build_providers_page_context,
    build_subscriptions_page_context,
    build_worker_quotas_page_context,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
STATIC_ROOT = PACKAGE_ROOT / "static"


def create_app(
    manifest_path: str | Path,
    workspace_root: str | Path | None = None,
    mode: str | None = None,
    basic_auth_username: str | None = None,
    basic_auth_password: str | None = None,
    control_plane_read_client: ControlPlaneReadClient | None = None,
) -> FastAPI:
    manifest = load_manifest(Path(manifest_path).resolve())
    resolved_workspace_root = Path(workspace_root or manifest.source_path.parent).resolve()
    active_mode = mode or manifest.default_mode
    app = FastAPI(title="proxy-platform web console")
    app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")
    auth_enabled = bool(basic_auth_username and basic_auth_password)

    @app.middleware("http")
    async def maybe_require_basic_auth(request: Request, call_next):
        if not auth_enabled or request.url.path == "/health":
            return await call_next(request)
        if _is_basic_auth_authorized(
            authorization_header=request.headers.get("Authorization"),
            expected_username=str(basic_auth_username),
            expected_password=str(basic_auth_password),
        ):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"detail": "authentication required"},
            headers={"WWW-Authenticate": 'Basic realm="proxy-platform"'},
        )

    def require_host_registry():
        if manifest.host_registry is None:
            raise HTTPException(status_code=500, detail="host registry source is not configured")
        if not manifest.host_registry.applies_to_mode(active_mode):
            raise HTTPException(
                status_code=500,
                detail=f"host registry source is not configured for mode {active_mode}",
            )
        return manifest.host_registry

    def observations_refresh_enabled() -> bool:
        return (
            manifest.host_registry is not None
            and manifest.host_registry.applies_to_mode(active_mode)
            and manifest.host_registry.observations_path is not None
        )

    def refresh_observations(*, force: bool, fail_silently: bool):
        if not observations_refresh_enabled():
            return None
        source = manifest.host_registry
        assert source is not None and source.observations_path is not None
        observations_path = (
            source.observations_path
            if source.observations_path.is_absolute()
            else resolved_workspace_root / source.observations_path
        )
        if not force and observations_path.exists():
            return None
        try:
            return refresh_host_observations(source=source, workspace_root=resolved_workspace_root)
        except (OSError, ValueError) as exc:
            if fail_silently:
                print(f"[proxy-platform] observation refresh skipped: {exc}", file=sys.stderr)
                return None
            raise HTTPException(status_code=500, detail=f"failed to refresh observations: {exc}") from exc

    def jobs_enabled() -> bool:
        return manifest.jobs is not None and manifest.jobs.applies_to_mode(active_mode)

    def worker_quotas_enabled() -> bool:
        return control_plane_read_client is not None

    def require_jobs() -> None:
        if manifest.jobs is None:
            raise HTTPException(status_code=500, detail="jobs config is not configured")
        if not manifest.jobs.applies_to_mode(active_mode):
            raise HTTPException(
                status_code=500,
                detail=f"jobs config is not configured for mode {active_mode}",
            )

    def load_current_state() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        refresh_observations(force=False, fail_silently=True)
        try:
            host_views, subscriptions = load_view_state(
                manifest=manifest,
                workspace_root=resolved_workspace_root,
                mode=active_mode,
            )
        except (ManifestError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        providers = [asdict(item) for item in describe_local_providers(manifest)]
        return host_views, subscriptions, providers

    def load_audits() -> list[dict[str, Any]]:
        if not jobs_enabled():
            return []
        return [
            _serialize_audit_record(item)
            for item in list_audit_records(manifest, resolved_workspace_root, active_mode)
        ]

    def load_worker_quotas() -> dict[str, Any]:
        if control_plane_read_client is None:
            raise HTTPException(status_code=404, detail="worker quota view is not configured")
        try:
            return control_plane_read_client.fetch_worker_quotas()
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

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

    @app.get("/api/worker-quotas")
    def api_worker_quotas() -> dict[str, Any]:
        return load_worker_quotas()

    @app.post("/api/observations/refresh")
    def api_refresh_observations() -> dict[str, Any]:
        if not observations_refresh_enabled():
            raise HTTPException(status_code=404, detail="observations refresh is not configured")
        result = refresh_observations(force=True, fail_silently=False)
        return {"refresh": _serialize_observation_refresh_result(result)}

    @app.get("/api/jobs")
    def api_jobs() -> dict[str, Any]:
        require_jobs()
        return {"jobs": load_audits()}

    @app.post("/api/jobs/plan")
    def api_plan_job(payload: dict[str, Any]) -> dict[str, Any]:
        require_jobs()
        job_kind = str(payload.get("job_kind", "")).strip()
        job_payload = payload.get("payload") or {}
        if not job_kind:
            raise HTTPException(status_code=422, detail="job_kind is required")
        if not isinstance(job_payload, dict):
            raise HTTPException(status_code=422, detail="payload must be an object")
        try:
            plan = plan_job(
                manifest=manifest,
                workspace_root=resolved_workspace_root,
                mode=active_mode,
                job_kind=job_kind,
                requested_by=str(payload.get("requested_by", "web")),
                payload=dict(job_payload),
            )
        except (JobConfigError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"plan": _serialize_job_plan(plan)}

    @app.post("/api/jobs/apply")
    def api_apply_job(payload: dict[str, Any]) -> dict[str, Any]:
        require_jobs()
        plan_value = payload.get("plan_path")
        if not plan_value:
            raise HTTPException(status_code=422, detail="plan_path is required")
        try:
            plan_path = resolve_job_plan_path(manifest, resolved_workspace_root, active_mode, str(plan_value))
        except (JobConfigError, JobPlanIntegrityError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not plan_path.exists():
            raise HTTPException(status_code=404, detail=f"unknown plan file: {plan_path}")
        try:
            plan = load_job_plan(plan_path)
        except JobPlanIntegrityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if plan.mode != active_mode:
            raise HTTPException(
                status_code=409,
                detail=f"plan mode {plan.mode} does not match active mode {active_mode}",
            )
        try:
            result = apply_job_plan(
                manifest=manifest,
                workspace_root=resolved_workspace_root,
                mode=active_mode,
                plan=plan,
                requested_by=str(payload.get("requested_by", "web")),
                confirm=bool(payload.get("confirm", False)),
            )
        except JobApplyUnsupportedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (JobConfigError, JobPlanIntegrityError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"result": _serialize_job_apply_result(result)}

    @app.get("/")
    def overview_page(request: Request):
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_overview_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=jobs_enabled(),
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="overview_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": jobs_enabled(),
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/hosts")
    def hosts_page(request: Request):
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_hosts_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=jobs_enabled(),
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="hosts_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": jobs_enabled(),
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/subscriptions")
    def subscriptions_page(request: Request):
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_subscriptions_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=jobs_enabled(),
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="subscriptions_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": jobs_enabled(),
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/providers")
    def providers_page(request: Request):
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_providers_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=jobs_enabled(),
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="providers_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": jobs_enabled(),
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/worker-quotas")
    def worker_quotas_page(request: Request):
        worker_quotas = load_worker_quotas()
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_worker_quotas_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=jobs_enabled(),
            worker_quotas=worker_quotas,
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="worker_quotas_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": jobs_enabled(),
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/jobs")
    def jobs_page(request: Request):
        if not jobs_enabled():
            raise HTTPException(status_code=404, detail="jobs page is not available for this mode")
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_jobs_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=True,
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="jobs_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": True,
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    @app.get("/audit")
    def audit_page(request: Request):
        if not jobs_enabled():
            raise HTTPException(status_code=404, detail="audit page is not available for this mode")
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
        context = build_audit_page_context(
            manifest_name=manifest.name,
            active_mode=active_mode,
            host_views=host_views,
            subscriptions=subscriptions,
            providers=providers,
            audits=audits,
            jobs_enabled=True,
            worker_quotas_enabled=worker_quotas_enabled(),
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="audit_page.html",
            context={
                "request": request,
                **context,
                "observations_refresh_enabled": observations_refresh_enabled(),
                "bootstrap_json": json.dumps(
                    {
                        "jobs_enabled": True,
                        "observations_refresh_enabled": observations_refresh_enabled(),
                        "worker_quotas_enabled": worker_quotas_enabled(),
                    },
                    ensure_ascii=False,
                ),
            },
        )

    return app


def run_web_console(
    manifest_path: str | Path,
    workspace_root: str | Path | None,
    mode: str | None,
    host: str,
    port: int,
    basic_auth_username: str | None = None,
    basic_auth_password: str | None = None,
    control_plane_read_client: ControlPlaneReadClient | None = None,
) -> None:
    import uvicorn

    app = create_app(
        manifest_path,
        workspace_root,
        mode=mode,
        basic_auth_username=basic_auth_username,
        basic_auth_password=basic_auth_password,
        control_plane_read_client=control_plane_read_client,
    )
    uvicorn.run(app, host=host, port=port)


def _serialize_job_plan(plan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["plan_path"] = str(plan.plan_path)
    return payload


def _serialize_job_apply_result(result) -> dict[str, Any]:
    payload = asdict(result)
    payload["plan_path"] = str(result.plan_path)
    payload["handoff_path"] = str(result.handoff_path) if result.handoff_path is not None else None
    return payload


def _serialize_observation_refresh_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {
        "observations_path": str(result.observations_path),
        "probed_hosts": result.probed_hosts,
        "healthy_hosts": result.healthy_hosts,
        "down_hosts": result.down_hosts,
        "source": result.source,
    }


def _serialize_audit_record(record) -> dict[str, Any]:
    return asdict(record)


def _is_basic_auth_authorized(
    *,
    authorization_header: str | None,
    expected_username: str,
    expected_password: str,
) -> bool:
    if not authorization_header:
        return False
    scheme, _, encoded = authorization_header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    username, separator, password = decoded.partition(":")
    if not separator:
        return False
    return secrets.compare_digest(username, expected_username) and secrets.compare_digest(
        password, expected_password
    )
