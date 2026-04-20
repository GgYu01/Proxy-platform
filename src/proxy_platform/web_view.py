from __future__ import annotations

from typing import Any


HEALTH_META = {
    "healthy": {"label": "正常", "tone": "healthy"},
    "degraded": {"label": "降级", "tone": "degraded"},
    "down": {"label": "异常", "tone": "down"},
    "unknown": {"label": "未知", "tone": "unknown"},
}

AUDIT_TONE = {
    "planned": "accent",
    "applied": "success",
    "rejected": "danger",
    "failed": "danger",
}


def build_overview_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="overview",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    action_cards = [
        {
            "href": "/hosts",
            "kicker": "Hosts",
            "title": "主机现场清单",
            "description": "按主机看当前健康、拓扑、订阅归属和最近观测细节。",
            "tone": "neutral",
        },
        {
            "href": "/subscriptions",
            "kicker": "Subscriptions",
            "title": "订阅入口",
            "description": "集中查看多节点入口、单节点入口和复制按钮。",
            "tone": "accent",
        },
        {
            "href": "/providers",
            "kicker": "Providers",
            "title": "本地 provider 生命周期",
            "description": "核对本地 MCP/provider 的启动预算和请求预算。",
            "tone": "neutral",
        },
    ]
    if worker_quotas_enabled:
        action_cards.append(
            {
                "href": "/worker-quotas",
                "kicker": "Worker quotas",
                "title": "远端 worker 配额",
                "description": "按 worker 分组查看不同 oauth 文件的 quota、probe 和回退状态。",
                "tone": "accent",
            }
        )
    if jobs_enabled:
        action_cards.extend(
            [
                {
                    "href": "/jobs",
                    "kicker": "Jobs",
                    "title": "主机登记作业",
                    "description": "新增、删除、部署和摘除都在独立变更页里完成。",
                    "tone": "warn",
                },
                {
                    "href": "/audit",
                    "kicker": "Audit",
                    "title": "作业审计",
                    "description": "集中复核最近计划、apply 和 authority handoff 落地结果。",
                    "tone": "neutral",
                },
            ]
        )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform overview",
        "action_cards": action_cards,
        "host_preview_rows": sections["host_rows"][:4],
        "audit_preview_rows": sections["audit_rows"][:5],
        "audit_preview_empty_message": "当前还没有审计事件。" if jobs_enabled else "当前模式不提供作业审计预览。",
        "workspace_heading": "处理入口",
        "workspace_description": "这里负责把现场判断后的下一步入口分开，避免在总览页里直接堆满所有动作。",
    }


def build_hosts_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="hosts",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform hosts",
        "page_heading": "主机现场清单",
        "page_description": "这里看的是现场主机清单，不夹带作业表单，便于值守时先确认主机、状态和订阅归属。",
    }


def build_subscriptions_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="subscriptions",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform subscriptions",
        "page_heading": "订阅入口",
        "page_description": "这里展示的是订阅派生结果和导入入口。普通 HTTPS 订阅 URL 和 Hiddify Deep Link 会分开表达，避免把两种用法混在一起。",
    }


def build_providers_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="providers",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform providers",
        "page_heading": "本地 provider 生命周期",
        "page_description": "这里看 provider 的启动预算和请求预算，方便判断本地 MCP 或探针为什么会慢、会重试、会超时。",
        "empty_provider_message": "当前 manifest 没有配置本地 provider。",
    }


def build_jobs_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="jobs",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform jobs",
        "page_heading": "主机登记作业",
        "page_description": "新增、删除、部署和摘除都在这里完成。页面仍然只负责 plan、confirm、apply 和审计，不直接 SSH。",
        "jobs_empty_message": "当前 manifest 没有启用 jobs 配置，所以这里不会提供变更入口。",
    }


def build_audit_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas_enabled: bool = False,
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="audit",
        worker_quotas_enabled=worker_quotas_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform audit",
        "page_heading": "作业审计",
        "page_description": "这里集中展示最近计划和 apply 事件，帮助复核刚才的动作到底有没有落到审计里。",
        "empty_audit_message": "当前还没有审计事件。",
    }


def build_worker_quotas_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_quotas: dict[str, Any],
) -> dict[str, Any]:
    sections = _build_console_sections(
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
    )
    context = _build_shell_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        jobs_enabled=jobs_enabled,
        active_page="worker-quotas",
        worker_quotas_enabled=True,
    )
    meta = worker_quotas.get("meta") if isinstance(worker_quotas.get("meta"), dict) else {}
    summary_cards = [
        {
            "label": "远端 worker",
            "value": meta.get("worker_total", 0),
            "help": "当前 authority 控制面返回给页面的 worker 总数。",
            "tone": "accent",
        },
        {
            "label": "oauth 文件",
            "value": meta.get("account_total", 0),
            "help": "按不同 auth_name 统计的账号文件行数。",
            "tone": "neutral",
        },
        {
            "label": "有最新配额快照",
            "value": meta.get("accounts_with_snapshot", 0),
            "help": "最近探测已经拿到 quota 快照的 oauth 文件数。",
            "tone": "success",
        },
        {
            "label": "最新探测失败",
            "value": meta.get("fresh_probe_failures", 0),
            "help": "最近刷新失败的 oauth 文件数，需要优先排查对应 worker。",
            "tone": "warn",
        },
    ]
    return {
        **context,
        **sections,
        "page_title": "proxy-platform worker quotas",
        "page_heading": "远端 worker / oauth 文件配额",
        "page_description": "这里只读消费 cliproxy-control-plane 的权威快照，不把 worker/oauth quota 真相复制回 proxy-platform。",
        "worker_quota_summary_cards": summary_cards,
        "worker_quota_meta": {
            "captured_at": meta.get("captured_at") or "未提供时间",
            "worker_realtime": meta.get("worker_realtime", 0),
            "worker_fallback": meta.get("worker_fallback", 0),
            "worker_failed": meta.get("worker_failed", 0),
            "accounts_without_snapshot": meta.get("accounts_without_snapshot", 0),
        },
        "worker_quota_workers": [
            _build_worker_quota_worker_row(item) for item in worker_quotas.get("workers", [])
        ],
        "empty_worker_quota_message": "当前 authority 控制面还没有返回任何 worker/oauth 配额数据。",
    }


def _build_console_sections(
    *,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
) -> dict[str, Any]:
    alias_by_name = {
        str(item.get("name")): str(item.get("alias"))
        for item in subscriptions.get("per_node", [])
        if isinstance(item, dict)
    }
    healthy_hosts = sum(1 for item in host_views if item.get("observed_health") == "healthy")
    publishable_hosts = sum(1 for item in host_views if bool(item.get("should_publish")))
    summary_cards = [
        {
            "label": "健康可用",
            "value": healthy_hosts,
            "help": "来自最近一次 TCP 探测的 healthy 主机数量；unknown 不会被算成 healthy。",
            "tone": "success",
            "featured": True,
        },
        {
            "label": "可发布节点",
            "value": publishable_hosts,
            "help": "同时满足 enabled 与 include_in_subscription 的节点数量。",
            "tone": "accent",
            "featured": False,
        },
        {
            "label": "现场主机",
            "value": len(host_views),
            "help": "当前现场清单里一共纳入了多少台主机。",
            "tone": "neutral",
            "featured": False,
        },
        {
            "label": "最近审计",
            "value": len(audits[:10]),
            "help": "当前页面可查看的最近审计事件条数。",
            "tone": "neutral",
            "featured": False,
        },
    ]
    return {
        "summary_cards": summary_cards,
        "host_rows": [_build_host_row(item, alias_by_name) for item in host_views],
        "subscription_profile_name": str(subscriptions.get("profile_name", "GG Proxy Nodes")),
        "subscription_multi_node_url": str(subscriptions.get("multi_node_url", "")),
        "subscription_multi_node_hiddify": str(subscriptions.get("multi_node_hiddify_import", "")),
        "subscription_remote_profile_url": str(subscriptions.get("remote_profile_url", "")),
        "subscription_rows": [_build_subscription_row(item) for item in subscriptions.get("per_node", [])],
        "provider_rows": [_build_provider_row(item) for item in providers],
        "audit_rows": [_build_audit_row(item) for item in audits[:10]],
    }


def _build_shell_context(
    *,
    manifest_name: str,
    active_mode: str,
    jobs_enabled: bool,
    active_page: str,
    worker_quotas_enabled: bool,
) -> dict[str, Any]:
    if not jobs_enabled:
        readonly_hint = (
            "当前模式只保留只读视图。页面仍读取 operator 真相源，但不提供 mutation 作业。"
            if active_mode == "operator"
            else "当前是只读视角。页面只消费脱敏 public 快照，不读取 private 现场清单，也不开放 mutation 作业。"
        )
    else:
        readonly_hint = "所有变更都仍然走 plan -> 明确确认 -> apply -> audit。远端部署类 apply 只生成 authority handoff，不会直接 SSH。"
    hero_copy = (
        "统一查看现场、入口分流与 handoff 收口；不直接替代下游 authority 执行远端生命周期。"
        if jobs_enabled
        else readonly_hint
    )
    nav_items = [
        {
            "id": "overview",
            "href": "/",
            "kicker": "Overview",
            "label": "总览",
            "help": "摘要与分流",
        },
        {
            "id": "hosts",
            "href": "/hosts",
            "kicker": "Hosts",
            "label": "主机",
            "help": "主机现场",
        },
        {
            "id": "subscriptions",
            "href": "/subscriptions",
            "kicker": "Subscriptions",
            "label": "订阅",
            "help": "链接与入口",
        },
        {
            "id": "providers",
            "href": "/providers",
            "kicker": "Providers",
            "label": "Provider",
            "help": "本地预算",
        },
    ]
    if worker_quotas_enabled:
        nav_items.append(
            {
                "id": "worker-quotas",
                "href": "/worker-quotas",
                "kicker": "Worker quotas",
                "label": "配额",
                "help": "worker / oauth",
            }
        )
    if jobs_enabled:
        nav_items.extend(
            [
                {
                    "id": "jobs",
                    "href": "/jobs",
                    "kicker": "Jobs",
                    "label": "作业",
                    "help": "计划与确认",
                },
                {
                    "id": "audit",
                    "href": "/audit",
                    "kicker": "Audit",
                    "label": "审计",
                    "help": "结果回看",
                },
            ]
        )
    for item in nav_items:
        item["active"] = item["id"] == active_page
    return {
        "manifest_name": manifest_name,
        "active_mode": active_mode,
        "mode_label": "operator 真相源" if active_mode == "operator" else "public 脱敏快照",
        "truth_source_label": "private host registry" if active_mode == "operator" else "public snapshot files",
        "readonly_hint": readonly_hint,
        "hero_copy": hero_copy,
        "jobs_enabled": jobs_enabled,
        "active_page": active_page,
        "nav_items": nav_items,
    }


def _build_host_row(item: dict[str, Any], alias_by_name: dict[str, str]) -> dict[str, Any]:
    health_key = str(item.get("observed_health", "unknown"))
    health = HEALTH_META.get(health_key, HEALTH_META["unknown"])
    alias = alias_by_name.get(str(item.get("name")), "未进入订阅")
    host = item.get("host")
    ssh_port = item.get("ssh_port")
    endpoint = f"{host}:{ssh_port}" if host and ssh_port is not None else "public snapshot only"
    search_fields = [
        item.get("name"),
        item.get("provider"),
        alias,
        item.get("deployment_topology"),
        item.get("runtime_service"),
        health_key,
        item.get("publish_reason"),
    ]
    observed_at = item.get("observed_at") or "未上报时间"
    observed_detail = item.get("observed_detail") or "当前没有额外观测细节"
    return {
        "name": str(item.get("name", "")),
        "provider": str(item.get("provider", "")),
        "topology_service": f"{item.get('deployment_topology', 'unknown')} / {item.get('runtime_service', 'unknown')}",
        "health_key": health_key,
        "health_label": health["label"],
        "health_tone": health["tone"],
        "publish_label": "发布中" if bool(item.get("should_publish")) else "未发布",
        "publish_reason": _publish_reason_text(str(item.get("publish_reason", "unknown"))),
        "subscription_alias": alias,
        "observed_at": str(observed_at),
        "observed_detail": str(observed_detail),
        "endpoint": endpoint,
        "change_policy": str(item["change_policy"]) if item.get("change_policy") else None,
        "search_text": " ".join(str(value) for value in search_fields if value),
    }


def _build_subscription_row(item: dict[str, Any]) -> dict[str, Any]:
    health_key = str(item.get("observed_health", "unknown"))
    health = HEALTH_META.get(health_key, HEALTH_META["unknown"])
    return {
        "name": str(item.get("name", "")),
        "alias": str(item.get("alias", "")),
        "health_label": health["label"],
        "health_tone": health["tone"],
        "v2ray_url": str(item.get("v2ray_url", "")),
        "hiddify_import_url": str(item.get("hiddify_import_url", "")),
    }


def _build_provider_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": str(item.get("provider_id", "")),
        "kind": str(item.get("kind", "")),
        "startup_budget": f"{item.get('startup_timeout_seconds', 0)}s x {item.get('startup_max_attempts', 0)}",
        "request_budget": f"{item.get('request_timeout_seconds', 0)}s x {item.get('request_max_attempts', 0)}",
        "owner_repo_id": str(item.get("owner_repo_id") or "platform local"),
    }


def _build_audit_row(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status", "planned"))
    return {
        "created_at": str(item.get("created_at", "")),
        "event": str(item.get("event", "")),
        "job_kind": str(item.get("job_kind", "")),
        "status": status,
        "summary": str(item.get("summary", "")),
        "tone": AUDIT_TONE.get(status, "neutral"),
    }


def _build_worker_quota_worker_row(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status", "unknown"))
    status_label, status_tone = _worker_status_meta(status)
    return {
        "worker_id": str(item.get("worker_id", "")),
        "status_label": status_label,
        "status_tone": status_tone,
        "captured_at": str(item.get("captured_at") or "未提供时间"),
        "group_ids": item.get("group_ids", []),
        "account_total": int(item.get("account_total", 0)),
        "accounts_with_snapshot": int(item.get("accounts_with_snapshot", 0)),
        "accounts_without_snapshot": int(item.get("accounts_without_snapshot", 0)),
        "fresh_probe_failures": int(item.get("fresh_probe_failures", 0)),
        "accounts": [_build_worker_quota_account_row(account) for account in item.get("accounts", [])],
    }


def _build_worker_quota_account_row(item: dict[str, Any]) -> dict[str, Any]:
    probe_status = str(item.get("probe_status", "unknown"))
    probe_label, probe_tone = _probe_status_meta(probe_status)
    return {
        "auth_name": str(item.get("auth_name", "")),
        "email": str(item.get("email") or "未记录邮箱"),
        "group_id": str(item.get("group_id", "")),
        "provider": str(item.get("provider", "unknown")),
        "account_status": str(item.get("account_status", "unknown")),
        "probe_label": probe_label,
        "probe_tone": probe_tone,
        "probe_message": str(item.get("probe_message") or "未提供探测说明"),
        "probe_observed_at": str(item.get("probe_observed_at") or "未提供时间"),
        "quota_summary": str(item.get("quota_summary") or "无最新配额快照"),
        "reset_at": str(item.get("reset_at") or "未提供 reset"),
        "capability_level": str(item.get("capability_level") or "unknown"),
        "source_endpoint": str(item.get("source_endpoint") or "未提供来源接口"),
        "latest_snapshot_present": bool(item.get("latest_snapshot_present")),
    }


def _worker_status_meta(status: str) -> tuple[str, str]:
    if status == "realtime":
        return "实时", "healthy"
    if status == "fallback":
        return "回退", "accent"
    if status == "failed":
        return "失败", "danger"
    return "未知", "neutral"


def _probe_status_meta(status: str) -> tuple[str, str]:
    if status == "ok":
        return "探测成功", "healthy"
    if status == "error":
        return "探测失败", "danger"
    return "探测未知", "neutral"


def _publish_reason_text(reason: str) -> str:
    if reason == "enabled_in_registry":
        return "登记册允许进入订阅"
    if reason == "excluded_by_subscription_policy":
        return "订阅策略排除"
    if reason == "disabled_in_registry":
        return "登记册已停用"
    return reason or "未说明"
