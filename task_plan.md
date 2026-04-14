# proxy-platform 当前任务计划

## 当前目标

围绕用户新需求完成两件事的正式设计与评审准备：

- Codex 本地重试、MCP 启动超时与本地 MCP 启动速度优化方案
- `proxy-platform` 的远端代理部署、主机发现、健康检查、动态订阅与 Web 管理台方案

本轮主体实现已经推进到第三阶段：authority adapter、authority handoff、部署边界 ADR 和 operator 文档都已落地；当前重点是把文档口径、planning 文件、最终 review 和验证全部收口。

## 当前范围边界

- 不把 `proxy-platform` 做成第二控制面。
- 不把 `CliProxy-control-plane` 的 northbound `/v1` 和 worker southbound 内核复制进来。
- 不把 `Proxy_ops_private` 的 secrets、inventory 真相源直接搬入本仓库。
- 可以新增平台级 manifest、adapter、job schema、ADR、runbook、Web/CLI 设计，但要明确哪些仍然委托给下游仓库执行。
- Codex 本地配置允许单独调整，但要和仓库内平台设计分开表述。

## 当前阶段

1. `completed` 读取技能、记忆、AGENTS 和现有规划文件
2. `completed` 盘点仓库现状，确认当前只具备 workspace/toolchain shell 能力
3. `completed` 盘点本地 Codex/MCP 配置与启动日志，确认 timeout 现状
4. `completed` 提炼问题定义与关键架构分歧，用户确认选择混合模式
5. `completed` 输出正式设计、ADR、测试和第一阶段实现
6. `completed` 收口 public/operator 边界，防止私有登记册被 public 模式隐式读取
7. `completed` 进入第二阶段：远端 job schema、dry-run、审计与受控 apply 入口
8. `completed` 补强 mutation job 合同：当前策略复核、执行器漂移拦截、已执行计划防重放
9. `completed` 对齐 operator 文档与维护口径：统一虚拟环境入口、补 operator 前提、声明 state 目录定位
10. `completed` 第三阶段主体实现：authority adapter / authority handoff / 部署边界 ADR 已落地；正式公网域名、认证入口和脱敏 public state source 仍属于后续部署阶段

## 已确认事实

- 当前仓库主线仍是 CLI-first 的薄平台壳；真正运行的最小 Web 控制台已经在 `src/proxy_platform/web_app.py`，但 `apps/web-console` 目录仍只是未来完整前端占位。
- 当前平台壳已经能做的是工作区仓库盘点、toolchain 体检、operator 主机/订阅只读视图、mutation job plan/apply/audit 和 authority handoff；不能做的是平台侧直接 SSH 部署、正式公网发布和脱敏 public projection。
- 当前本地 Codex 配置真实路径仍是 `~/.codex/config.toml`；本轮复核时，主要 MCP 已经收敛到 `startup_timeout_sec = 15.0`，并保留了手动 rollback 注释。
- 当前 workspace / toolchain 代码使用同步 `subprocess.run(...)`，还没有统一 retry/timeout budget 抽象。
- 当前 mutation job apply 已补齐三道合同闸门：
  - 当前 manifest 仍允许 apply
  - 当前 executor 与计划时一致
  - 同一 `job_id` 没有已经执行过的 `applied` 审计
- operator inventory 现在正式支持 `include_in_subscription`，页面表单、登记册模型和订阅派生规则已对齐。

## 当前风险

- 如果把“远端主机管理 + 代理部署 + 健康检查 + 订阅生成”直接堆进现有 CLI，会把平台壳从入口层推成新的控制面。
- 如果“主机自动出现”没有明确真相源，最终会出现页面、订阅和真实可用主机三份不一致数据。
- 如果 planning / runbook 还残留“远端只支持 dry-run”或“Web 已经上线”的旧口径，reviewer 会误判当前阶段边界。

## 2026-04-14 新任务：平台编排与代理可见性体系

### 目标

在不突破“薄平台壳”与 private/public 边界的前提下，补齐以下正式设计与后续实现入口：

- Codex 本地重试、超时和本地 MCP 启动预算治理；
- 平台级远端主机登记、健康检查与动态发现模型；
- 动态订阅生成与 Web 查看/复制入口；
- 远端主机的可审计增删改编排接口；
- 平台级文档、ADR、agent governance 持续维护规则。

### 当前阶段

1. `completed` 现状盘点：确认仓库当前只有 workspace/toolchain 壳能力，没有主机注册与订阅编排能力
2. `completed` 根因拆解：解释为什么当前需求不能直接塞进现有 doctor/init/sync
3. `completed` 候选架构：收敛主机登记册、探针、订阅视图、部署 job schema 的边界
4. `completed` 设计输出：形成评审可读的正式方案并完成第一阶段实现
5. `completed` 边界回收：把依赖 private registry 的视图正式收紧为 `operator` 模式
6. `completed` 第二阶段：定义远端 mutation job schema 与审计模型
7. `completed` review hardening：修复 apply 原子性、计划重放与坏计划文件错误处理
8. `completed` 文档 hardening：统一 `.venv` 入口，补 operator 前提与 state 目录说明
9. `completed` 第三阶段主体：真正的远端 authority adapter、部署边界 ADR 与 authority handoff 已经落地
10. `pending` 后续部署阶段：正式公网域名、认证入口、脱敏 public state source 与真正的远端发布 owner

### 本轮风险

- 若把远端运行时状态、secret、inventory 直接拉进本仓库，会破坏 `Proxy_ops_private` 真相源边界。
- 若把订阅生成和远端写操作直接混进 CLI 命令，会把平台壳做成新的控制面内核。
- 若未来远端正式上线前没有补齐 deployment owner、认证入口和 public/private 视图拆分，当前本地 operator 控制台会被误解成“已经可以公网运维”的正式站点。
