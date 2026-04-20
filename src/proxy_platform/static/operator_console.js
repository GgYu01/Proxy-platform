function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(kind, message) {
  const region = document.getElementById("toast-region");
  if (!region) {
    return;
  }
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.dataset.kind = kind;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 3200);
}

async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const fallback = document.createElement("textarea");
  fallback.value = text;
  fallback.setAttribute("readonly", "true");
  fallback.style.position = "fixed";
  fallback.style.opacity = "0";
  document.body.appendChild(fallback);
  fallback.select();
  const ok = document.execCommand("copy");
  fallback.remove();
  if (!ok) {
    throw new Error("clipboard not available");
  }
}

function successMessageForCopy(button) {
  const copyKind = String(button.dataset.copyKind || "plain");
  if (copyKind === "hiddify-deep-link") {
    return "Hiddify Deep Link 已复制，请在 Hiddify 中使用“打开导入链接”或“从剪贴板导入”，不要粘贴到手动订阅 URL。";
  }
  if (copyKind === "subscription-url") {
    return `${button.dataset.copyLabel || "订阅 URL"} 已复制，可直接粘贴到客户端的手动订阅地址。`;
  }
  return `${button.dataset.copyLabel || "链接"} 已复制`;
}

function renderList(title, rows) {
  const listHtml = rows.map((item) => `<li>${item}</li>`).join("");
  return `<h3>${escapeHtml(title)}</h3><ul>${listHtml}</ul>`;
}

function auditTone(status) {
  const value = String(status || "").toLowerCase();
  if (value === "applied") {
    return "success";
  }
  if (value === "planned") {
    return "accent";
  }
  if (value === "failed" || value === "rejected") {
    return "danger";
  }
  return "neutral";
}

function renderPlan(plan) {
  const rows = [
    `job_id: ${escapeHtml(plan.job_id)}`,
    `job_kind: ${escapeHtml(plan.job_kind)}`,
    `executor: ${escapeHtml(plan.executor)}`,
    `plan_path: ${escapeHtml(plan.plan_path)}`,
  ];
  if (plan.authority_adapter_id) {
    rows.push(`authority_adapter: ${escapeHtml(plan.authority_adapter_id)}`);
  }
  if (plan.authority_topology) {
    rows.push(`authority_topology: ${escapeHtml(plan.authority_topology)}`);
  }
  if (plan.handoff_action) {
    rows.push(`handoff_action: ${escapeHtml(plan.handoff_action)}`);
  }
  for (const preview of plan.preview_steps || []) {
    rows.push(`preview: ${escapeHtml(preview)}`);
  }
  for (const warning of plan.warnings || []) {
    rows.push(`warning: ${escapeHtml(warning)}`);
  }
  return renderList("最近计划", rows);
}

function renderResult(result) {
  const rows = [
    `job_id: ${escapeHtml(result.job_id)}`,
    `status: ${escapeHtml(result.status)}`,
    `executor: ${escapeHtml(result.executor)}`,
    `audit_id: ${escapeHtml(result.audit_id)}`,
    `effect: ${escapeHtml(result.effect)}`,
    `handoff_path: ${escapeHtml(result.handoff_path || "none")}`,
  ];
  if (result.authority_adapter_id) {
    rows.push(`authority_adapter: ${escapeHtml(result.authority_adapter_id)}`);
  }
  return renderList("最近执行结果", rows);
}

function renderError(title, error) {
  return `<h3>${escapeHtml(title)}</h3><p>${escapeHtml(String(error))}</p>`;
}

function renderAudits(jobs) {
  const auditListNode = document.getElementById("audit-list");
  if (!auditListNode) {
    return;
  }
  if (!jobs.length) {
    auditListNode.innerHTML = '<li class="audit-item audit-empty">当前还没有审计事件。</li>';
    return;
  }
  auditListNode.innerHTML = jobs.slice(0, 10).map((item) => (
    `<li class="audit-item" data-tone="${escapeHtml(auditTone(item.status))}">
      <div class="audit-topline">
        <strong>${escapeHtml(item.job_kind)}</strong>
        <span class="status-badge" data-health="${escapeHtml(auditTone(item.status))}">${escapeHtml(item.status || "unknown")}</span>
      </div>
      <div class="cell-meta">${escapeHtml(item.created_at)} / event=${escapeHtml(item.event)}</div>
      <div>${escapeHtml(item.summary)}</div>
    </li>`
  )).join("");
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

async function refreshAudits() {
  const response = await fetch("/api/jobs");
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || "load jobs failed");
  }
  renderAudits(body.jobs || []);
}

function attachHostSearch() {
  const input = document.getElementById("host-search");
  const rows = Array.from(document.querySelectorAll("#host-table-body tr"));
  if (!input || !rows.length) {
    return;
  }
  input.addEventListener("input", () => {
    const query = String(input.value || "").trim().toLowerCase();
    rows.forEach((row) => {
      const haystack = String(row.dataset.search || "").toLowerCase();
      row.hidden = query !== "" && !haystack.includes(query);
    });
  });
}

function attachCopyButtons() {
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await copyText(button.dataset.copy || "");
        showToast("success", successMessageForCopy(button));
      } catch (error) {
        showToast("error", `${button.dataset.copyLabel || "链接"} 复制失败: ${String(error)}`);
      }
    });
  });
}

async function refreshObservations() {
  const response = await fetch("/api/observations/refresh", {
    method: "POST",
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || "refresh observations failed");
  }
  return body.refresh || {};
}

function attachObservationRefresh(bootstrap) {
  if (!bootstrap.observations_refresh_enabled) {
    return;
  }
  document.querySelectorAll("[data-observation-refresh]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const refresh = await refreshObservations();
        showToast(
          "success",
          `观测已刷新：探测 ${refresh.probed_hosts || 0} 台，healthy ${refresh.healthy_hosts || 0} 台，down ${refresh.down_hosts || 0} 台。`
        );
        window.setTimeout(() => {
          window.location.reload();
        }, 500);
      } catch (error) {
        button.disabled = false;
        showToast("error", `刷新观测失败: ${String(error)}`);
      }
    });
  });
}

function setCardHtml(id, html) {
  const node = document.getElementById(id);
  if (node) {
    node.innerHTML = html;
  }
}

function attachJobForms(bootstrap) {
  if (!bootstrap.jobs_enabled) {
    return;
  }

  const applyPlanPathInput = document.getElementById("apply-plan-path");

  function rememberPlan(plan) {
    if (applyPlanPathInput && plan.apply_supported) {
      applyPlanPathInput.value = plan.plan_path;
    }
    setCardHtml("recent-plan-card", renderPlan(plan));
  }

  const addForm = document.getElementById("add-host-form");
  if (addForm) {
    addForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(addForm);
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
        deployment_topology: data.get("deployment_topology"),
        runtime_service: data.get("runtime_service"),
      };
      try {
        rememberPlan(await createPlan("add_host", payload));
        showToast("success", "新增主机计划已生成");
      } catch (error) {
        setCardHtml("recent-plan-card", renderError("最近计划", error));
        showToast("error", `新增主机计划失败: ${String(error)}`);
      }
    });
  }

  const removeForm = document.getElementById("remove-host-form");
  if (removeForm) {
    removeForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(removeForm);
      try {
        rememberPlan(await createPlan("remove_host", { name: data.get("name") }));
        showToast("success", "移除主机计划已生成");
      } catch (error) {
        setCardHtml("recent-plan-card", renderError("最近计划", error));
        showToast("error", `移除主机计划失败: ${String(error)}`);
      }
    });
  }

  document.querySelectorAll("[data-remote-kind]").forEach((button) => {
    button.addEventListener("click", async () => {
      const remoteForm = document.getElementById("remote-plan-form");
      const hostName = new FormData(remoteForm).get("name");
      try {
        rememberPlan(await createPlan(button.dataset.remoteKind, { name: hostName }));
        showToast("success", "远端移交计划已生成");
      } catch (error) {
        setCardHtml("recent-plan-card", renderError("最近计划", error));
        showToast("error", `远端移交计划失败: ${String(error)}`);
      }
    });
  });

  const applyForm = document.getElementById("apply-plan-form");
  if (applyForm && applyPlanPathInput) {
    applyForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const result = await applyPlan(applyPlanPathInput.value);
        setCardHtml("recent-result-card", renderResult(result));
        showToast("success", "apply 已执行并写入审计");
        await refreshAudits();
      } catch (error) {
        setCardHtml("recent-result-card", renderError("最近执行结果", error));
        showToast("error", `apply 失败: ${String(error)}`);
      }
    });
  }
}

function main() {
  const bootstrapNode = document.getElementById("console-bootstrap");
  const bootstrap = bootstrapNode ? JSON.parse(bootstrapNode.textContent || "{}") : {};
  attachHostSearch();
  attachCopyButtons();
  attachObservationRefresh(bootstrap);
  attachJobForms(bootstrap);
}

window.addEventListener("DOMContentLoaded", main);
