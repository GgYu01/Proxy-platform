# Mutation Job Flow Review Checklist

- 是否先定义了 `job_kind`、payload、preview、audit，再接 Web/CLI 按钮
- 是否把 apply 明确限制在允许的 executor 上，而不是默认所有 job 都能执行
- 是否让 `inventory_only` 和 `authority_handoff` 两类 executor 的边界清楚可见
- 是否把 `authority_handoff` 明确定义成“生成移交单”，而不是“平台直接 SSH 执行”
- 是否把真正的远端 authority 继续留在 `remote_proxy`、`infra_core` 或其他下游真相源
- 是否把 `standalone_vps` 和 `infra_core_sidecar` 拓扑分开处理，没有混用脚本
- 是否为每个 authority adapter 写清楚 downstream owner、entrypoint、本地 review prerequisite、downstream execution prerequisite、rollback owner
- 是否为每个新 job 补了最小测试，至少覆盖 plan、apply gate、audit 和 handoff artifact
- 是否校验了 plan 文件只能来自受管目录，且 apply 前会验证计划内容没有被替换
- 是否校验了当前 manifest policy、executor、authority adapter 没有在 planning 之后发生漂移
- 是否为每个可 apply 的 job 明确了当前回退方式或回退 owner
- 是否把新边界同步写进 ADR、runbook 和 reviewer 文档，而不是只落在实现里
- 是否保持 `operator` / `public` 分层，没有让 public 入口穿透 private registry
- 是否避免把 secrets、inventory 真相、生成物提交进 `proxy-platform`
