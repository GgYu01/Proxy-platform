# Findings

## 当前决定

- 新仓库位置：`/workspaces/proxy_own/proxy-platform`
- 先做 CLI-first 的薄平台壳
- `git submodule + platform.manifest.yaml` 共同表达依赖与语义
- 本阶段用 doctor / init / sync / toolchain profiles 建立最小闭环

## 第一波实现对象

- CLI 命令面
- manifest schema
- host toolchain profiles
- `.gitmodules` 与 manifest 一致性校验
- repo status 检测
- 基于 local override 的本地工作区物化
- 基于 `default_url` 的 clone / fetch 失败收敛
- 基于 manifest profile 的宿主机兼容诊断
- 平台级治理文档
- ADR 文档

## 暂不实现

- 真实 Web 工作台
- 真实 job runner
- 真实远端 apply/publish 写操作
- 自动安装或切换系统级运行时
- 自动远端 SSH 检查与修复

## 2026-04-14 新任务发现

- 当前仓库在项目语言里更像“工作区仓库盘点结果 + 宿主机依赖体检入口”，不是“远端代理编排与动态订阅平台”。
- `apps/web-console/README.md` 仍明确是占位目录，说明 Web 管理台尚未开始正式实现。
- `src/proxy_platform/cli.py`、`src/proxy_platform/workspace.py`、`src/proxy_platform/toolchain.py` 目前都没有统一的 timeout/retry policy 抽象。
- `workspace.py` 和 `toolchain.py` 直接用同步 `subprocess.run(..., capture_output=True, text=True)`，没有每类动作独立的超时预算，也没有结构化重试策略。
- 当前本地 Codex 配置真实路径是 `~/.codex/config.toml`，大多数本地 MCP 的 `startup_timeout_sec` 还是 `120.0`。
- 从现有 `context-engine` 启动日志看，服务本身能在秒级启动；说明当前主要矛盾不是“默认 120 秒不够”，而是缺少更细粒度的启动性能治理和分层 timeout。
- 按现有 ADR 边界，`proxy-platform` 可以新增 adapter / job schema / manifest / UI，但不应复制 `CliProxy-control-plane` northbound 内核，也不应替代 `remote_proxy` 的宿主机生命周期脚本。
- 用户这次的核心新需求不是单一代理节点，而是“远端主机登记 -> 部署代理 -> 健康检查 -> 动态订阅 -> Web 可视化管理”的完整闭环；这个闭环当前项目完全不存在。
- 设计上的第一关键分歧是：远端主机“自动出现”到底靠平台侧登记，还是靠远端 agent/self-register 反向注册；这会决定平台的数据真相源和故障模式。

## 2026-04-14 新发现

- 当前 `proxy-platform` 已有的平台壳能力只有三类：
  - 工作区仓库盘点与同步
  - manifest/.gitmodules 一致性校验
  - 宿主机 toolchain 诊断
- 当前仓库内没有“远端主机登记册”“健康探针”“订阅视图”“Web 管理台”“远端部署 job schema”的正式模型。
- 现有 `doctor toolchain` 只做单机本地只读检查，不含重试预算、超时治理、MCP 启动时序或 provider 级健康状态。
- 现有 `apps/web-console` 仍是占位目录，仓库明确要求未来 Web 复用下游能力，不应在这里重写控制面业务内核。
- 历史代理订阅经验表明，稳定的边界是：
  - `remote_proxy` 保留公开运行基线与客户端文档
  - `Proxy_ops_private` 保留 inventory、secrets、生成物与发布脚本真相源
  - 平台壳适合承接“登记、编排、诊断、可见性”，不适合承接私有事实和实时控制面内核

## 2026-04-14 边界回收结果

- 当前第一阶段实现里真正需要回收的不是“功能做错了”，而是“模式边界表达不够严谨”：
  - `hosts list` / `subscriptions list` / `web` 实际依赖 `Proxy_ops_private` 的私有登记册
  - 因此前述入口现在正式收紧为 `operator` 模式，不再让 `public` 模式隐式穿透 private 边界
- 新增的 manifest 校验会阻止一类长期漂移：
  - 如果 projection 声称支持某个 mode，但其 source 并不支持，manifest 直接判错
- 这意味着后续若要做公开页面或公开订阅入口，必须先补“脱敏派生状态源”，而不是继续复用私有登记册
