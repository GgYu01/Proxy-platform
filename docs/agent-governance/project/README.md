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

## 当前推荐做法

- 先把问题翻译成项目语言，再谈代码
- 先解释 owner boundary，再解释实现细节
- 先补失败测试，再补最小实现
- 对 deploy/decommission，优先回答“移交给谁、为什么不是平台自己执行”
