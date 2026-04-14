# proxy-platform 当前任务计划

## 当前目标

围绕用户新需求完成两件事的正式设计与评审准备：

- Codex 本地重试、MCP 启动超时与本地 MCP 启动速度优化方案
- `proxy-platform` 的远端代理部署、主机发现、健康检查、动态订阅与 Web 管理台方案

本轮已完成第一阶段实现与一轮边界回收；当前重点转为把模式边界、仓库职责和后续作业流继续收紧成正式方案。

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
6. `in_progress` 收口 public/operator 边界，防止私有登记册被 public 模式隐式读取
7. `pending` 进入第二阶段：远端 job schema、dry-run、审计与受控 apply 入口

## 已确认事实

- 当前 `proxy-platform` 仍是 CLI-first 的薄平台壳，`apps/web-console` 只是占位。
- 当前平台壳能做的是工作区仓库盘点、toolchain 体检、init/sync；不能做远端主机注册、部署执行、健康巡检或订阅聚合。
- 当前 `~/.codex/config.toml` 中多数 MCP `startup_timeout_sec` 仍为 `120.0`，未体现用户要求的 `15` 秒启动预算。
- 当前 workspace / toolchain 代码使用同步 `subprocess.run(...)`，还没有统一 retry/timeout budget 抽象。

## 当前风险

- 如果把“远端主机管理 + 代理部署 + 健康检查 + 订阅生成”直接堆进现有 CLI，会把平台壳从入口层推成新的控制面。
- 如果“主机自动出现”没有明确真相源，最终会出现页面、订阅和真实可用主机三份不一致数据。
- 如果只调大 Codex timeout 而不治理 MCP 冷启动路径，本地体验只会变成“更慢地等待失败”。

## 2026-04-14 新任务：平台编排与代理可见性体系

### 目标

在不突破“薄平台壳”与 private/public 边界的前提下，补齐以下正式设计与后续实现入口：

- Codex 本地重试、超时和本地 MCP 启动预算治理；
- 平台级远端主机登记、健康检查与动态发现模型；
- 动态订阅生成与 Web 查看/复制入口；
- 远端主机的可审计增删改编排接口；
- 平台级文档、ADR、agent governance 持续维护规则。

### 当前阶段

1. `in_progress` 现状盘点：确认仓库当前只有 workspace/toolchain 壳能力，没有主机注册与订阅编排能力
2. `pending` 根因拆解：解释为什么当前需求不能直接塞进现有 doctor/init/sync
3. `pending` 候选架构：收敛主机登记册、探针、订阅视图、部署 job schema 的边界
4. `completed` 设计输出：形成评审可读的正式方案并完成第一阶段实现
5. `in_progress` 边界回收：把依赖 private registry 的视图正式收紧为 `operator` 模式
6. `pending` 第二阶段：定义远端 mutation job schema 与审计模型

### 本轮风险

- 若把远端运行时状态、secret、inventory 直接拉进本仓库，会破坏 `Proxy_ops_private` 真相源边界。
- 若把订阅生成和远端写操作直接混进 CLI 命令，会把平台壳做成新的控制面内核。
- 若本地 MCP 启动优化没有独立的超时/重试/健康模型，后续 Web 和编排层会继续复制同类逻辑。
