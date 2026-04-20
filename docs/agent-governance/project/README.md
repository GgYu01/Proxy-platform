# 平台级 Agent Governance

本目录记录 `proxy-platform` 对 OpenAI Codex / Anthropic Claude Code / Meta-Harness 类 agent / harness 规范的项目化解释。

一句话结论：在这个仓库里，agent 可以扩展合同、文档和适配层，但不能把仓库做成新的远端控制面。

## 当前硬约束

- 分层 `AGENTS.md`
- 子代理只做边界清晰的 side work
- destructive 动作必须先 dry-run 或 authority handoff
- 平台级架构决策必须进入 ADR
- 平台状态必须区分“登记册真相、观测回报、派生视图”
- agent 修改仓库边界时，必须先做 ownership matrix review
- 依赖 private registry 的入口必须显式声明 `operator` 模式，不允许 public 模式隐式穿透
- public 模式只能消费脱敏 snapshot，不允许再用“只读例外”穿透 private truth
- `.runtime-workspace` 回写 private truth 时必须走 reviewed sync plan，不能手工 copy 覆盖
- 浏览器驱动型 provider runtime 必须继续作为下游运行时仓库治理，不能借机把 `proxy-platform` 写成第二控制面
- 远端 worker/oauth quota 必须继续以 `cliproxy-control-plane` 为权威真相源；`proxy-platform` 只能做只读消费和展示

## 第三阶段新增约束

### 1. 远端部署类动作必须先进入 authority handoff

agent 不能因为页面上已经有按钮，就把 `deploy_host` / `decommission_host` 直接接成 SSH 或宿主机脚本执行。

当前允许的做法是：

- 生成 reviewed plan
- 生成 audit
- 生成 authority handoff artifact
- 把真实宿主机执行继续留在下游 authority

### 2. adapter 是平台合同，不是脚本备忘录

只要新增或修改 authority adapter，agent 就必须同步维护：

- manifest schema
- 最小测试
- ADR
- runbook
- review checklist

### 3. `standalone_vps` 与 `infra_core_sidecar` 必须分开表达

agent 不能把这两种拓扑混成一个“统一安装脚本问题”。

- `standalone_vps`
  当前 authority 在 `remote_proxy`
- `infra_core_sidecar`
  当前 compose 生命周期 authority 在 `infra_core`

### 4. operator Web 不得被误写成“已上线”

如果没有正式部署 ADR、认证入口和发布 owner，agent 不得把当前 Web 控制台表述成正式公网站点。

### 5. 文档维护和代码维护同等重要

在这个仓库里，agent 不能只改代码不改文档。

只要边界、入口、拓扑、回退 owner 发生变化，就必须同步更新：

- `README.md`
- `docs/adr/`
- `docs/runbooks/`
- `docs/review-checklists/`

### 6. 正式部署不允许把运行态数据和发布物混在一起

如果 agent 触达正式部署链路，必须同时保护三层东西：

- 固定发布物 `/app`
- 部署 seed `.runtime-seed`
- 运行时工作区 `.runtime-workspace`

agent 不得为了“部署方便”在 redeploy 时覆盖 `.runtime-workspace`，因为这里保存的是线上 operator 站点正在使用的主机登记册副本、计划、审计和移交单。
但 agent 也不能把它理解成“永远不能刷新”的冻土层。
如果远端主机登记册副本仍然等于上一版 `.runtime-seed` 镜像，说明现场没有继续编辑，允许在 redeploy 时自动刷新到新的 seed；只有当运行态副本已经偏离上一版 seed 时，才必须保留并暴露漂移。

### 7. 远端 operator 站点必须继续遵守 authority handoff 边界

即使站点已经在 Ubuntu.online 上线，agent 也不能把它升级成直接 SSH 执行器。

当前允许上线的是：

- 带认证的 operator 页面
- 只读状态查看
- `add_host` / `remove_host` 的登记册变更
- `deploy_host` / `decommission_host` 的 authority handoff 生成

当前不允许 agent 擅自加入的是：

- 平台直接远端安装
- 平台直接远端摘除
- 平台绕过 `remote_proxy` / `infra_core` owner 的宿主机生命周期动作

### 8. 正式部署链必须保护认证与现场配置

agent 在重发 `proxy-platform-operator` 模块时，必须同时满足三件事：

- 缺少 Basic Auth 用户名或密码时直接拒绝启动
- 保留远端 `.env`，不把真实站点配置重置回示例值
- 只保留 operator 现场清单，不把 authority review surface 长期冻在旧版本
- 如果远端现场清单还只是上一版 seed 镜像，允许自动刷新；如果已经偏离上一版 seed，必须保留并暴露漂移

### 9. public snapshot 必须继续保持脱敏

agent 如果修改 public snapshot 导出或消费逻辑，必须同时保证三件事：

- public 只读入口继续只读 `state/public/*.json`
- 快照里不带 `host`、`ssh_port`、`base_port`、`change_policy` 这类 private 维护字段
- 快照结构错误时，CLI 和 Web 都以受控错误返回，而不是静默兜底或直接 traceback

### 10. private truth sync 只能是 reviewed bridge，不能是假控制面

agent 如果修改 `.runtime-workspace` -> `repos/proxy_ops_private` 的回写链路，必须保持：

- 先 plan，后 apply
- digest 校验 source/target 漂移
- 显式确认 `--confirm`
- 只覆盖 inventory 文件，不顺手带上 secrets、生成物或 Git push

### 11. browser-backed runtime 必须继续留在下游仓库

如果 agent 新增或修改 `webchat-openai-runtime` 这类浏览器驱动运行时，必须同时保持四条边界：

- `proxy-platform` 只负责 repo 注册、平台文档治理和评审入口，不直接吸收浏览器执行内核
- OpenAI-compatible 协议面、provider adapter、浏览器 profile、slot 状态和 challenge 处理继续留在 runtime 仓库
- 如果新增 Qwen 这类网页登录工作台，session manager、截图/输入接口和登录态回写也继续留在 runtime 仓库，不上提到根仓
- 默认关闭 hosted tool execution，只有明确开关和审计面到位后才允许启用
- 帐号池、租户、计费、渠道治理继续留给 `new-api`、`CLIProxyAPIPlus` 或其他上层系统，不回流到 runtime 或根仓

## 当前推荐做法

- 先把问题翻译成项目语言，再谈代码
- 先解释 owner boundary，再解释实现细节
- 先补失败测试，再补最小实现
- 对 deploy/decommission，优先回答“移交给谁、为什么不是平台自己执行”
- 对 public snapshot / private truth sync，优先回答“现在桥接的是哪两层真相、为什么不能直接穿透或自动推送”
