from __future__ import annotations

from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

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
from proxy_platform.inventory import load_host_registry
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

    def jobs_enabled() -> bool:
        return manifest.jobs is not None and manifest.jobs.applies_to_mode(active_mode)

    def require_jobs() -> None:
        if manifest.jobs is None:
            raise HTTPException(status_code=500, detail="jobs config is not configured")
        if not manifest.jobs.applies_to_mode(active_mode):
            raise HTTPException(
                status_code=500,
                detail=f"jobs config is not configured for mode {active_mode}",
            )

    def load_current_state() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        host_registry_source = require_host_registry()
        registry = load_host_registry(host_registry_source, resolved_workspace_root)
        host_views = [asdict(item) for item in build_host_views(registry)]
        subscriptions = asdict(build_subscription_projection(registry))
        providers = [asdict(item) for item in describe_local_providers(manifest)]
        return host_views, subscriptions, providers

    def load_audits() -> list[dict[str, Any]]:
        if not jobs_enabled():
            return []
        return [
            _serialize_audit_record(item)
            for item in list_audit_records(manifest, resolved_workspace_root, active_mode)
        ]

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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        host_views, subscriptions, providers = load_current_state()
        audits = load_audits()
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
        audit_rows = "".join(
            (
                "<li>"
                f"{escape(item['created_at'])}: event={escape(item['event'])} "
                f"job={escape(item['job_kind'])} status={escape(item['status'])} "
                f"summary={escape(item['summary'])}"
                "</li>"
            )
            for item in audits[:10]
        )
        job_section = ""
        if jobs_enabled():
            job_section = """
    <section>
      <h2>主机登记作业</h2>
      <form id="add-host-form">
        <label>主机名<input name="name" required /></label>
        <label>主机地址<input name="host" required /></label>
        <div class="inline">
          <label>SSH 端口<input name="ssh_port" type="number" value="22" required /></label>
          <label>基准端口<input name="base_port" type="number" value="10000" required /></label>
        </div>
        <label>订阅别名<input name="subscription_alias" required /></label>
        <div class="inline">
          <label>provider<input name="provider" required /></label>
          <label>change_policy
            <select name="change_policy">
              <option value="mutable">mutable</option>
              <option value="frozen">frozen</option>
            </select>
          </label>
        </div>
        <label><input name="enabled" type="checkbox" checked /> enabled</label>
        <label><input name="include_in_subscription" type="checkbox" checked /> include_in_subscription</label>
        <label><input name="infra_core_candidate" type="checkbox" checked /> infra_core_candidate</label>
        <button type="submit">先生成新增计划</button>
      </form>
      <form id="remove-host-form">
        <label>要移除的主机名<input name="name" required /></label>
        <button type="submit">先生成移除计划</button>
      </form>
      <form id="remote-plan-form">
        <label>远端 dry-run 主机名<input name="name" required /></label>
        <div class="inline">
          <button type="button" data-remote-kind="deploy_host">计划部署</button>
          <button type="button" data-remote-kind="decommission_host">计划摘除</button>
        </div>
      </form>
      <form id="apply-plan-form">
        <label>待 apply 的计划文件路径<input id="apply-plan-path" name="plan_path" required /></label>
        <button type="submit">明确确认后 apply</button>
      </form>
      <p id="job-status">这里会显示最近一次作业 plan / apply 结果。页面不会自动跳过 apply 审核步骤。</p>
    </section>
    <section>
      <h2>作业审计</h2>
      <ul>"""
            job_section += audit_rows or "<li>当前还没有审计事件。</li>"
            job_section += """</ul>
    </section>"""

        script = """
    <script>
      const statusNode = document.getElementById("job-status");
      const applyPlanPathInput = document.getElementById("apply-plan-path");

      async function copyText(text) {
        await navigator.clipboard.writeText(text);
      }

      async function createPlan(jobKind, payload) {
        const response = await fetch("/api/jobs/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_kind: jobKind, payload, requested_by: "operator-web" }),
        });
        const body = await response.json();
        if (!response.ok) {
          throw new Error(body.detail || "plan failed");
        }
        return body.plan;
      }

      async function applyPlan(planPath) {
        const response = await fetch("/api/jobs/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan_path: planPath, confirm: true, requested_by: "operator-web" }),
        });
        const body = await response.json();
        if (!response.ok) {
          throw new Error(body.detail || "apply failed");
        }
        return body.result;
      }

      function formatPlan(plan) {
        const lines = [
          `planned: ${plan.job_id}`,
          `kind: ${plan.job_kind}`,
          `executor: ${plan.executor}`,
          `apply_supported: ${plan.apply_supported}`,
          `plan_path: ${plan.plan_path}`,
        ];
        for (const step of plan.preview_steps) {
          lines.push(`preview: ${step}`);
        }
        for (const warning of plan.warnings) {
          lines.push(`warning: ${warning}`);
        }
        return lines.join("\\n");
      }

      function formatResult(result) {
        return [
          `applied: ${result.job_id}`,
          `status: ${result.status}`,
          `audit_id: ${result.audit_id}`,
          `effect: ${result.effect}`,
        ].join("\\n");
      }

      function rememberPlan(plan) {
        if (applyPlanPathInput && plan.apply_supported) {
          applyPlanPathInput.value = plan.plan_path;
        }
        statusNode.textContent = formatPlan(plan);
      }

      document.querySelectorAll("[data-copy]").forEach((button) => {
        button.addEventListener("click", async () => {
          await copyText(button.dataset.copy);
        });
      });

      if (document.getElementById("add-host-form")) {
        document.getElementById("add-host-form").addEventListener("submit", async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          const payload = {
            name: data.get("name"),
            host: data.get("host"),
            ssh_port: Number(data.get("ssh_port")),
            base_port: Number(data.get("base_port")),
            subscription_alias: data.get("subscription_alias"),
            enabled: data.get("enabled") === "on",
            include_in_subscription: data.get("include_in_subscription") === "on",
            infra_core_candidate: data.get("infra_core_candidate") === "on",
            change_policy: data.get("change_policy"),
            provider: data.get("provider"),
          };
          try {
            rememberPlan(await createPlan("add_host", payload));
          } catch (error) {
            statusNode.textContent = String(error);
          }
        });
      }

      if (document.getElementById("remove-host-form")) {
        document.getElementById("remove-host-form").addEventListener("submit", async (event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          try {
            rememberPlan(await createPlan("remove_host", { name: data.get("name") }));
          } catch (error) {
            statusNode.textContent = String(error);
          }
        });
      }

      document.querySelectorAll("[data-remote-kind]").forEach((button) => {
        button.addEventListener("click", async () => {
          const hostName = new FormData(document.getElementById("remote-plan-form")).get("name");
          try {
            rememberPlan(await createPlan(button.dataset.remoteKind, { name: hostName }));
          } catch (error) {
            statusNode.textContent = String(error);
          }
        });
      });

      if (document.getElementById("apply-plan-form")) {
        document.getElementById("apply-plan-form").addEventListener("submit", async (event) => {
          event.preventDefault();
          try {
            const result = await applyPlan(applyPlanPathInput.value);
            statusNode.textContent = `${statusNode.textContent}\\n\\n${formatResult(result)}`;
            window.location.reload();
          } catch (error) {
            statusNode.textContent = String(error);
          }
        });
      }
    </script>
"""
        if not jobs_enabled():
            script = ""
            job_section = """
    <section>
      <h2>主机登记作业</h2>
      <p>当前 manifest 没有启用 jobs 配置，所以这个页面只保留只读视图。</p>
    </section>
"""

        return f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>proxy-platform web console</title>
    <style>
      body {{
        font-family: "SF Pro Display", "PingFang SC", "Noto Sans SC", sans-serif;
        margin: 32px;
        line-height: 1.5;
      }}
      section {{
        margin-bottom: 32px;
      }}
      table {{
        border-collapse: collapse;
        width: 100%;
      }}
      th, td {{
        border: 1px solid #cbd5e1;
        padding: 8px 12px;
        text-align: left;
      }}
      form {{
        display: grid;
        gap: 8px;
        margin-bottom: 16px;
        max-width: 720px;
      }}
      label {{
        display: grid;
        gap: 4px;
      }}
      input, select, button {{
        font: inherit;
        padding: 8px 10px;
      }}
      .inline {{
        display: flex;
        gap: 12px;
        align-items: center;
      }}
      #job-status {{
        white-space: pre-wrap;
        padding: 12px;
        background: #f8fafc;
        border: 1px solid #cbd5e1;
      }}
    </style>
  </head>
  <body>
    <h1>proxy-platform web console</h1>
    <section>
      <h2>主机现场清单</h2>
      <table>
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
{job_section}
    <section>
      <h2>本地 provider 生命周期</h2>
      <ul>{provider_rows}</ul>
    </section>
{script}
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


def _serialize_job_plan(plan) -> dict[str, Any]:
    payload = asdict(plan)
    payload["plan_path"] = str(plan.plan_path)
    return payload


def _serialize_job_apply_result(result) -> dict[str, Any]:
    payload = asdict(result)
    payload["plan_path"] = str(result.plan_path)
    return payload


def _serialize_audit_record(record) -> dict[str, Any]:
    return asdict(record)
