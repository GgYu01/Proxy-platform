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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
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
    if worker_connections_enabled:
        action_cards.append(
            {
                "href": "/worker-connections",
                "kicker": "Worker links",
                "title": "远端连接与余额",
                "description": "只看 worker 连通性和 oauth 剩余余额窗口，不再摊开旧 quota/probe 控制面细节。",
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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
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
    worker_connections_enabled: bool = False,
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
        worker_connections_enabled=worker_connections_enabled,
    )
    return {
        **context,
        **sections,
        "page_title": "proxy-platform audit",
        "page_heading": "作业审计",
        "page_description": "这里集中展示最近计划和 apply 事件，帮助复核刚才的动作到底有没有落到审计里。",
        "empty_audit_message": "当前还没有审计事件。",
    }


def build_worker_connections_page_context(
    *,
    manifest_name: str,
    active_mode: str,
    host_views: list[dict[str, Any]],
    subscriptions: dict[str, Any],
    providers: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    jobs_enabled: bool,
    worker_connections: dict[str, Any],
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
        active_page="worker-connections",
        worker_connections_enabled=True,
    )
    meta = worker_connections.get("meta") if isinstance(worker_connections.get("meta"), dict) else {}
    overview_status = str(meta.get("overview_status") or "available")
    overview_warning = str(meta.get("overview_warning") or "").strip() or None
    summary_cards = [
        {
            "label": "直连 worker",
            "value": meta.get("worker_live", 0),
            "help": "control-plane 当前还能实时连通并提供实时状态的 worker 数量。",
            "tone": "success",
        },
        {
            "label": "受限 worker",
            "value": meta.get("worker_degraded", 0) + meta.get("worker_disconnected", 0),
            "help": "处于 fallback 或 failed 的 worker，说明连接链仍有明显缺口。",
            "tone": "warn",
        },
        {
            "label": "已连通 oauth",
            "value": meta.get("account_connected", 0),
            "help": "最近探测成功、当前仍能证明连接正常的 oauth 文件数量。",
            "tone": "accent",
        },
        {
            "label": "可见余额",
            "value": meta.get("balance_authoritative_accounts", 0),
            "help": "拿到 authoritative quota 余额窗口的 oauth 文件数量。",
            "tone": "neutral",
        },
        {
            "label": "主窗口均值",
            "value": _display_percent(meta.get("primary_remaining_average")),
            "help": "所有带主窗口余额信号的 oauth 文件主窗口平均剩余百分比。",
            "tone": "accent",
        },
        {
            "label": "扩展窗口均值",
            "value": _display_percent(meta.get("secondary_remaining_average")),
            "help": "所有带扩展窗口余额信号的 oauth 文件次窗口平均剩余百分比。",
            "tone": "neutral",
        },
    ]
    return {
        **context,
        **sections,
        "page_title": "proxy-platform worker connections",
        "page_heading": "远端连接与剩余余额面板",
        "page_description": "这里只读消费 cliproxy-control-plane 的权威接口，但只投影两类信息：worker 连接状态，以及各 oauth 文件当前可见的剩余余额窗口。",
        "worker_connection_summary_cards": summary_cards,
        "worker_connection_meta": {
            "captured_at": meta.get("captured_at") or "未提供时间",
            "overview_status_label": _worker_connection_overview_status_label(overview_status),
            "overview_status_tone": _worker_connection_overview_status_tone(overview_status),
            "worker_live": meta.get("worker_live", 0),
            "worker_degraded": meta.get("worker_degraded", 0),
            "worker_disconnected": meta.get("worker_disconnected", 0),
            "worker_unknown": meta.get("worker_unknown", 0),
            "account_total": meta.get("account_total", 0),
            "balance_visible_accounts": meta.get("balance_visible_accounts", 0),
        },
        "worker_connection_overview_note": _worker_connection_overview_note(overview_status),
        "worker_connection_overview_warning": overview_warning,
        "worker_connection_workers": [
            _build_worker_connection_worker_row(item) for item in worker_connections.get("workers", [])
        ],
        "empty_worker_connection_message": "当前 authority 控制面还没有返回任何远端连接或余额数据。",
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
    """Compatibility wrapper for callers still using the previous naming."""
    return build_worker_connections_page_context(
        manifest_name=manifest_name,
        active_mode=active_mode,
        host_views=host_views,
        subscriptions=subscriptions,
        providers=providers,
        audits=audits,
        jobs_enabled=jobs_enabled,
        worker_connections=worker_quotas,
    )


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
            "help": "满足登记册策略且未被 72 小时可用性剔除的节点数量。",
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
        "subscription_excluded_rows": [
            _build_subscription_excluded_row(item) for item in subscriptions.get("excluded_availability", [])
        ],
        "provider_rows": [_build_provider_row(item) for item in providers],
        "audit_rows": [_build_audit_row(item) for item in audits[:10]],
    }


def _build_shell_context(
    *,
    manifest_name: str,
    active_mode: str,
    jobs_enabled: bool,
    active_page: str,
    worker_connections_enabled: bool,
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
    if worker_connections_enabled:
        nav_items.append(
            {
                "id": "worker-connections",
                "href": "/worker-connections",
                "kicker": "Worker links",
                "label": "连接 / 余额",
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


def _build_subscription_excluded_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name", "")),
        "alias": str(item.get("alias", "")),
        "unavailable_since": str(item.get("unavailable_since") or "未知"),
        "detail": str(item.get("detail") or "连续不可用已达 72 小时阈值"),
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


def _build_worker_connection_worker_row(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status", "unknown"))
    status_label, status_tone = _worker_status_meta(status)
    return {
        "worker_id": str(item.get("worker_id", "")),
        "status_label": status_label,
        "status_tone": status_tone,
        "status_detail": _worker_status_detail(status),
        "captured_at": str(item.get("captured_at") or "未提供时间"),
        "account_total": int(item.get("account_total", 0)),
        "connected_accounts": int(item.get("connected_accounts", 0)),
        "issue_accounts": int(item.get("issue_accounts", 0)),
        "balance_visible_accounts": int(item.get("balance_visible_accounts", 0)),
        "balance_authoritative_accounts": int(item.get("balance_authoritative_accounts", 0)),
        "primary_remaining_average": _display_percent(item.get("primary_remaining_average")),
        "secondary_remaining_average": _display_percent(item.get("secondary_remaining_average")),
        "accounts": [_build_worker_connection_account_row(account) for account in item.get("accounts", [])],
    }


def _build_worker_connection_account_row(item: dict[str, Any]) -> dict[str, Any]:
    connection_state = str(item.get("connection_state", "waiting"))
    connection_label, connection_tone = _connection_status_meta(connection_state)
    primary_percent = _percent_or_zero(item.get("primary_remaining_percent"))
    secondary_percent = _percent_or_zero(item.get("secondary_remaining_percent"))
    return {
        "auth_name": str(item.get("auth_name", "")),
        "email": str(item.get("email") or "未记录邮箱"),
        "group_id": str(item.get("group_id", "")),
        "provider": str(item.get("provider", "unknown")),
        "account_status": str(item.get("account_status", "unknown")),
        "connection_label": connection_label,
        "connection_tone": connection_tone,
        "connection_observed_at": str(item.get("connection_observed_at") or "未提供时间"),
        "balance_summary": str(item.get("balance_summary") or "当前无剩余余额信号"),
        "balance_reset_at": str(item.get("balance_reset_at") or "未提供 reset"),
        "balance_signal": _balance_signal_label(
            str(item.get("balance_capability_level", "unavailable")),
            bool(item.get("has_authoritative_balance")),
        ),
        "has_balance_snapshot": bool(item.get("has_balance_snapshot")),
        "primary_window_label": str(item.get("primary_window_label") or "P"),
        "primary_remaining_label": _display_percent(item.get("primary_remaining_percent")),
        "primary_bar_width": primary_percent,
        "primary_reset_at": str(item.get("primary_reset_at") or "未提供 reset"),
        "secondary_window_label": str(item.get("secondary_window_label") or "S"),
        "secondary_remaining_label": _display_percent(item.get("secondary_remaining_percent")),
        "secondary_bar_width": secondary_percent,
        "secondary_reset_at": str(item.get("secondary_reset_at") or "未提供 reset"),
    }


def _worker_status_meta(status: str) -> tuple[str, str]:
    if status == "realtime":
        return "直连中", "healthy"
    if status == "fallback":
        return "回退中", "accent"
    if status == "failed":
        return "失联", "danger"
    return "未知", "neutral"


def _worker_status_detail(status: str) -> str:
    if status == "realtime":
        return "authority 仍能从这个 worker 拿到实时连接态与余额窗口。"
    if status == "fallback":
        return "当前退回最近成功快照，连接链受限但仍保留可读余额信息。"
    if status == "failed":
        return "worker 当前未提供可用实时连接，余额面板只能显示缺口。"
    return "authority 没有给出稳定 worker 状态，需要继续在 control-plane 排障。"


def _connection_status_meta(status: str) -> tuple[str, str]:
    if status == "connected":
        return "已连通", "healthy"
    if status == "issue":
        return "连接异常", "danger"
    return "待刷新", "neutral"


def _balance_signal_label(capability_level: str, authoritative: bool) -> str:
    if authoritative:
        return "权威余额"
    if capability_level == "worker_usage_only":
        return "仅 worker usage"
    if capability_level == "account_state_only":
        return "仅账号状态"
    return "余额缺失"


def _display_percent(value: Any) -> str:
    if value is None or value == "":
        return "--"
    return f"{value}%"


def _percent_or_zero(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _publish_reason_text(reason: str) -> str:
    if reason == "enabled_in_registry":
        return "登记册允许进入订阅"
    if reason == "excluded_by_subscription_policy":
        return "订阅策略排除"
    if reason == "disabled_in_registry":
        return "登记册已停用"
    if reason == "auto_excluded_unavailable_72h":
        return "连续不可用 ≥72h，已自动剔除"
    if reason == "included_pending_availability":
        return "探测异常，暂仍发布（未达 72h）"
    return reason or "未说明"


def _worker_connection_overview_status_label(status: str) -> str:
    if status == "degraded":
        return "overview 降级"
    return "overview 已接入"


def _worker_connection_overview_status_tone(status: str) -> str:
    if status == "degraded":
        return "accent"
    return "healthy"


def _worker_connection_overview_note(status: str) -> str:
    if status == "degraded":
        return "当前 tactical overview 暂时不可用，worker 状态改由 accounts/latest-view 与余额快照推导，页面保持可读但会显式暴露降级。"
    return "当前以 accounts/latest-view 作为主事实源，tactical overview 只做增强，不再成为页面可用性的硬依赖。"
