# Findings

## 当前决定

- 当前权威仓库位置：`/workspaces/proxy-platform`
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

- 正式公网 Web 工作台
- 真实 job runner
- 平台侧真实远端 apply/publish 写操作
- 自动安装或切换系统级运行时
- 自动远端 SSH 检查与修复

## 2026-04-14 新任务发现

- 在任务起点盘点时，这个仓库在项目语言里更像“工作区仓库盘点结果 + 宿主机依赖体检入口”，还不是完整的“远端代理编排与动态订阅平台”。
- 在任务起点盘点时，`apps/web-console/README.md` 仍明确是占位目录，这也是为什么当时先从最小 Web 控制台而不是完整前端落手。
- `src/proxy_platform/cli.py`、`src/proxy_platform/workspace.py`、`src/proxy_platform/toolchain.py` 目前都没有统一的 timeout/retry policy 抽象。
- `workspace.py` 和 `toolchain.py` 直接用同步 `subprocess.run(..., capture_output=True, text=True)`，没有每类动作独立的超时预算，也没有结构化重试策略。
- 当前本地 Codex 配置真实路径是 `~/.codex/config.toml`；本轮复核时，主要 MCP 的 `startup_timeout_sec` 已经收敛到 `15.0`，并保留了手动 rollback 注释。
- 从现有 `context-engine` 启动日志看，服务本身能在秒级启动；说明当前主要矛盾不是“默认 120 秒不够”，而是缺少更细粒度的启动性能治理和分层 timeout。
- 按现有 ADR 边界，`proxy-platform` 可以新增 adapter / job schema / manifest / UI，但不应复制 `CliProxy-control-plane` northbound 内核，也不应替代 `remote_proxy` 的宿主机生命周期脚本。
- 用户这次的核心新需求不是单一代理节点，而是“远端主机登记 -> 部署代理 -> 健康检查 -> 动态订阅 -> Web 可视化管理”的完整闭环；在任务开始时，这个闭环在项目里还不存在。
- 设计上的第一关键分歧是：远端主机“自动出现”到底靠平台侧登记，还是靠远端 agent/self-register 反向注册；这会决定平台的数据真相源和故障模式。

## 2026-04-14 新发现

- 在第一轮盘点时，`proxy-platform` 已有的平台壳能力只有三类：
  - 工作区仓库盘点与同步
  - manifest/.gitmodules 一致性校验
  - 宿主机 toolchain 诊断
- 在第一轮盘点时，仓库内还没有“远端主机登记册”“健康探针”“订阅视图”“Web 管理台”“远端部署 job schema”的正式模型。
- 现有 `doctor toolchain` 只做单机本地只读检查，不含重试预算、超时治理、MCP 启动时序或 provider 级健康状态。
- `apps/web-console` 目录仍不是正式前端源码根；当前已存在最小 Web 控制台实现，但仓库仍要求未来完整前端复用下游能力，不应在这里重写控制面业务内核。
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

## 2026-04-14 合同硬化结果

- mutation job apply 仅校验“计划没被替换”还不够，还必须校验“当前平台规则仍允许执行”：
  - 如果 manifest 后来把某类 job 改成 dry-run，旧计划不能继续 apply
  - 如果 executor 语义变了，旧计划也必须重新评审再生成
- 同一个 `job_id` 不能通过把 `status` 改回 `planned` 来重放：
  - 现在只要审计里已经有 `applied` 事件，就会拒绝再次执行
- 受管目录内的坏计划文件也要走合同错误，而不是回退成 traceback/500：
  - 缺失计划文件会返回 `unknown plan file`
  - 损坏 JSON 会返回 `failed to load plan file`
- operator inventory 模型和文档原先有一个真实错位：
  - 文档说订阅由 `enabled` 和 `include_in_subscription` 共同决定
  - 但实现只支持 `enabled`
  - 现在已经把 `include_in_subscription` 接回登记册模型、页面表单和订阅派生逻辑
- 当前 inventory 写回已经恢复成 YAML，而不是把 YAML 真相文件写成 JSON 文本；这更符合 private inventory 的维护方式。

## 2026-04-14 文档与维护口径结果

- README、operator runbook、mutation job runbook 现在统一改成以仓库本地 `.venv/bin/python` 为基准命令入口。
- 文档现在明确区分两类启动：
  - public 壳能力
  - 依赖 `repos/proxy_ops_private/` 的 operator 能力
- `state/` 目录现在被明确标成：
  - 本地运行态和审计痕迹
  - 不是 inventory 真相源
  - 不提交到 Git
- Web runbook 现在补了一个明确的“上线决策门”：
  - 远端正式部署前，必须先补 deployment ADR，明确落地拓扑、发布仓库和认证入口责任归属

## 2026-04-14 第三阶段主体完成后的复核

- `deploy_host` / `decommission_host` 现在已经不是“只能 dry-run”的旧入口，而是“可以 apply 生成 authority handoff 移交单”的正式平台合同。
- 这意味着当前平台层已经能回答三个关键问题：
  - 这台主机属于哪种部署拓扑
  - 这类动作应该移交给哪个下游 owner
  - 回退 owner 和 rollback hint 是什么
- 当前仍然没有完成的是“正式公网发布”而不是“平台合同本身”：
  - 还没有正式公网域名
  - 还没有最终认证入口
  - 还没有脱敏后的 public state source
- 因此，当前正确口径应该是：
  - 平台合同、移交单、Web 本地控制台已完成当前阶段目标
  - 远端正式上线仍是后续 deployment 阶段
