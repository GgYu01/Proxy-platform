# Progress

## 2026-04-13

- 初始化 `proxy-platform` 仓库。
- 确认第一波实现目标为平台壳最小闭环，而非全量平台。
- 写入平台级 `AGENTS.md`、`README.md`、`platform.manifest.yaml` 与 5 份 ADR。
- 写入 `.gitmodules`，并补 manifest 与 gitmodules 的一致性校验。
- 先写测试，再实现 `manifest validate`、`repos list`、`doctor`、`init`、`sync`。
- 新增 manifest 驱动的 host toolchain profile，并暴露 `doctor toolchain --profile <id>`。
- `init` / `sync` 现在支持三类物化路径：
  - 现有 Git 仓库执行 `git fetch --all --tags`
  - 有 `local_override_path` 时建立本地符号链接
  - 两者都没有时按 `default_url` 做 clone
- `git clone` 失败时会回收半残目录，避免后续运行被误判成“已有工作区”。
- 本地验证结果：
  - `. .venv/bin/activate && pytest -q` -> `32 passed`
  - `. .venv/bin/activate && python -m proxy_platform manifest validate` -> `manifest: ok`
  - `. .venv/bin/activate && python -m proxy_platform repos list ...` -> 输出 public 模式 repo 状态
  - `. .venv/bin/activate && python -m proxy_platform doctor ...` -> 正确报告未初始化 submodule 工作区缺失 required repos
  - `. .venv/bin/activate && python -m proxy_platform init --mode operator --dry-run ...` -> 正确输出基于 local override 的初始化计划
  - 临时 workspace smoke：真实执行 `init` 后，`doctor` 从 `ok=false` 变为 `ok=true`
  - 临时 workspace smoke：`init` 在无 override 且 `default_url` 指向本地 Git 仓库时会成功 clone
  - 临时 workspace smoke：`init` 在不可达远端上返回 `EXIT_CODE=2`，输出 `failed to clone ...`，且失败目录被清理
  - 临时 workspace smoke：`sync` 在已有 Git 仓库远端不可达时返回 `EXIT_CODE=2`，输出 `failed to fetch ...`
  - `. .venv/bin/activate && python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone` -> 当前主机 Python/curl/jq/systemd 满足，但 `podman` 缺失，返回 `EXIT_CODE=2`
  - `. .venv/bin/activate && python -m proxy_platform doctor toolchain --profile control_plane_compose` -> 当前主机 Python 满足，但 `docker` / `docker-compose` 缺失，返回 `EXIT_CODE=2`
  - 非法 manifest smoke：`default_mode=broken` 时 `manifest validate` 返回 `EXIT_CODE=2`
  - `.gitmodules` 与 `platform.manifest.yaml` 的 path / url 一致性已纳入测试与运行时校验
  - manifest 现在也会拒绝重复 `toolchain profile id`，避免 schema 被静默覆盖
- 尝试追加只读 reviewer 子代理，但未在超时窗口内返回有效评审结论；本轮质量结论以本地 TDD、smoke 和 fresh verification 为准。

## 2026-04-14

- 读取并遵循了当前仓库 `AGENTS.md`、技能说明和现有 planning 文件。
- 重新盘点仓库现状：
  - 当前 CLI 只覆盖 `manifest validate`、`repos list`、`doctor`、`init`、`sync`
  - 当前 Web 控制台仍是占位，不存在远端主机管理界面
  - 当前平台壳没有远端部署、主机发现、健康检查、订阅聚合相关对象模型
- 重新盘点本地 Codex 配置：
  - 真实配置路径为 `~/.codex/config.toml`
  - 多数本地 MCP `startup_timeout_sec = 120.0`
  - 尚未按用户要求做 `15s` 启动预算分级
- 重新盘点本地 MCP 启动日志：
  - `context-engine-mcp` 日志显示服务能在秒级启动
  - 当前问题更像“缺少启动性能治理和分类 timeout”，不是简单“把 timeout 再调大”
- 更新本轮计划文件，准备进入单点澄清与正式设计阶段。

## 2026-04-14

- 接收新任务：把“Codex 本地稳定性治理 + 本地 MCP 启动优化 + 远端代理部署/发现/健康检查/Web 可视化”收敛成正式平台方案。
- 重新核对仓库边界：
  - `proxy-platform` 仍是薄平台壳
  - `Proxy_ops_private` 仍是 private inventory/secrets/generated artifacts 真相源
  - 当前仓库不能直接滑向新的控制面内核
- 盘点现有实现后确认：
  - 已有 CLI 只覆盖 `manifest validate / repos list / doctor / init / sync`
  - 已有 toolchain 诊断只覆盖本地宿主机命令检查
  - `apps/web-console` 仍为占位目录
- 复用历史代理订阅经验作为边界证据：
  - 平台壳适合承接统一入口、登记、探针、订阅视图、编排 schema
  - 私有订阅生成物与 secrets 不应回流到本仓库
- 已把本轮任务拆成“现状盘点 -> 根因拆解 -> 候选架构 -> 正式设计输出”四步，避免直接跳进实现。

## 2026-04-14

- 对已落地的第一阶段实现做了一轮设计回收：
  - 发现 `hosts/subscriptions/web` 已经依赖 `Proxy_ops_private` 私有登记册，但 manifest/projection 文档仍把这组视图表述成 `public` 也可直接使用
  - 这不是测试层面的偶然问题，而是 private/public 边界表达不严谨
- 已补 schema 与命令边界：
  - `state.host_registry.required_modes = [operator]`
  - `host_console` / `subscription_nodes` projection 现在只声明 `operator`
  - `hosts list` / `subscriptions list` / `web` 新增 `--mode`，默认跟随 manifest；若当前模式没有私有登记册访问权，会明确报错
- 已补一致性校验：
  - projection 的 `required_modes` 现在必须是其输入 source mode 的子集
  - `state.host_registry.required_modes` 必须与 `state_sources.host_registry.required_modes` 对齐
- 已同步入口文档：
  - `README.md` 现在明确说明 manifest 驱动的主机/订阅/Web 入口当前只在 `operator` 模式开放
  - `apps/web-console/README.md` 说明当前已有最小 Web 控制台实现，未来完整前端仍是后续工作
- 本轮 fresh verification：
  - `.venv_fix/bin/python -m pytest tests/test_manifest.py tests/test_cli.py tests/test_web_app.py -q` -> `34 passed`

## 2026-04-14

- 继续完成第二阶段 mutation job 合同硬化，而不是只停留在第一版可运行实现：
  - 先补失败测试，再修改实现
  - 目标是收紧 apply 安全边界和 operator 文档可执行性
- 新增失败测试覆盖四类问题：
  - manifest policy 漂移后旧计划不应继续 apply
  - executor 漂移后旧计划不应继续 apply
  - 已执行计划不能通过修改 `status` 重放
  - CLI / Web 对受管目录内坏计划文件要返回受控错误
- 修复了 mutation job 合同的三个结构性漏洞：
  - apply 前重新读取当前 manifest policy，禁止旧计划越过新边界
  - 审计中已有 `applied` 记录时拒绝 replay
  - `load_job_plan()` 把缺失/损坏计划文件统一收敛为 `JobPlanIntegrityError`
- 修复了 operator inventory 与订阅派生错位：
  - `include_in_subscription` 现在正式进入 `inventory.HostRecord`
  - 页面新增主机表单已支持 `include_in_subscription`
  - 主机展示和订阅派生现在共同以 `enabled && include_in_subscription` 为准
  - inventory 写回已恢复为 YAML 格式
- 修复了 operator 文档的三类维护缺口：
  - README / runbook 统一以 `.venv/bin/python` 作为示例入口
  - README 单独补了 operator 前提，不再把 public bootstrap 和 operator 命令混写成一步
  - `state/` 目录已被写入 workspace 布局和 `.gitignore`
  - Web runbook 新增“真正上线前的决策门”说明
- 使用多层 review 做交叉复核：
  - 两个只读子代理分别审查代码合同和部署/文档口径
  - OpenSpace 做了一轮只读外部审查，未发现新的严重 correctness bug
  - OpenSpace 自动捕获了一个本地 review fallback skill，但当前未上传，因为它属于本轮本地工作流收敛产物
- 本轮 fresh verification：
  - `.venv_fix/bin/python -m pytest tests/test_jobs.py tests/test_cli.py tests/test_web_app.py -q` -> `40 passed`
  - `.venv_fix/bin/python -m pytest -q` -> `73 passed`
  - `.venv_fix/bin/python -m proxy_platform manifest validate --manifest platform.manifest.yaml` -> `manifest: ok (proxy-platform 0.1.0)`
  - `.venv_fix/bin/python -m proxy_platform jobs -h` -> 新增 `plan-add-host / plan-remove-host / plan-deploy-host / plan-decommission-host / apply / audit-list`
  - 本地真实进程 smoke：
    - `.venv_fix/bin/python -m proxy_platform web --mode operator --host 127.0.0.1 --port 8765`
    - `curl -fsS http://127.0.0.1:8765/ | rg -n "主机登记作业|明确确认后 apply|include_in_subscription"` 命中预期页面元素
