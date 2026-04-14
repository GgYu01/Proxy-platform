# Mutation Job Flow Review Checklist

- 是否先定义了 `job_kind`、payload、preview、audit，再接 Web/CLI 按钮
- 是否把 apply 明确限制在允许的 executor 上，而不是默认所有 job 都能执行
- 是否只有 `inventory_only` 类变更可以在当前阶段 apply
- 是否把 `deploy_host` / `decommission_host` 保持为 dry-run，避免页面直接连 SSH
- 是否把真正的远端 authority 继续留在 `remote_proxy` 或其他下游真相源
- 是否为每个新 job 补了最小测试，至少覆盖 plan、apply gate、audit
- 是否校验了 plan 文件只能来自受管目录，且 apply 前会验证计划内容没有被替换
- 是否为每个可 apply 的 job 明确了当前回退方式
- 是否把新边界同步写进 ADR 和 runbook，而不是只落在实现里
- 是否保持 `operator` / `public` 分层，没有让 public 入口穿透 private registry
- 是否避免把 secrets、inventory 真相、生成物提交进 `proxy-platform`
