# 项目内 Harness 打包与安装

日期：2026-06-04
状态：Active project-local install path

## 结论

当前 harness 支持被打包成一个可移动 zip，并安装到任意目标项目的 `.codex-harness/` 目录下。安装是项目内的，不写入全局 Codex 配置，不要求全局启用，也不会把目标项目变成当前源仓库的副本。

目标项目根目录只会新增或更新一个受管理的 `AGENTS.md` 入口块，用来告诉 Codex 在该项目中读取 `.codex-harness/AGENTS.md`、工具清单和验证命令。实际 harness 资产、配置、prompt、schema、工具、receipt 都保存在 `.codex-harness/`。

## 打包

在 harness 源工作区运行：

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\package_harness.py pack --source . --output-dir dist
```

输出：

- `dist/codex-project-harness.zip`
- JSON stdout，包含 `package_path` 和 `package_sha256`

包内包含：

- `harness-package.json`
- `AGENTS.md`
- `configs/`
- `docs/`
- `prompt_groups/codex_harness/`
- `schemas/`
- `tools/`

包内不包含：

- `.git/`
- `.tmp/`
- `repos/`
- 缓存、日志、环境文件、凭据、全局 Codex 配置

## 安装到目标项目

在任意目标项目路径运行：

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python C:\Users\Administration\CodexWorkspaces\harness_agent_approve\tools\package_harness.py install `
  --package C:\Users\Administration\CodexWorkspaces\harness_agent_approve\dist\codex-project-harness.zip `
  --target C:\Path\To\TargetProject
```

安装结果：

- `C:\Path\To\TargetProject\.codex-harness\`
- `C:\Path\To\TargetProject\.codex-harness\receipts\install-receipt.json`
- `C:\Path\To\TargetProject\AGENTS.md` 中的 `codex-harness:start` 管理块

如果目标项目已有非本工具管理的 `.codex-harness/`，安装会拒绝覆盖。确认要替换时才使用 `--force`。

重新安装时，installer 只移除 manifest 管理的旧文件；目标项目中现有的 `.codex-harness/.tmp/`、自定义 runtime receipt 和其它非包内管理状态会保留，避免覆盖本地 ChatGPT Web / App 协作证据。

## 本地 Secret Companion

如果目标项目需要复用本机已有的 GitHub token env companion，只能通过显式命令复制到目标项目的 ignored `state/` 目录，并写 redacted receipt。receipt 只记录键名，不记录值、长度或 hash：

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python C:\Users\Administration\CodexWorkspaces\harness_agent_approve\tools\package_harness.py copy-local-secret-env `
  --source C:\Users\Administration\CodexWorkspaces\proxy-platform\state\github\github.env `
  --target C:\Path\To\TargetProject\state\github\github.env `
  --target-root C:\Path\To\TargetProject
```

`state/github/github.env` 必须被目标项目 `.gitignore` 忽略；不要把该文件放进 zip、Git commit、prompt、receipt 明文或日志输出。

## 验证目标项目安装

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python C:\Path\To\TargetProject\.codex-harness\tools\package_harness.py verify --target C:\Path\To\TargetProject
```

验证会检查：

- 安装 manifest 和 install receipt。
- 包内资产 sha256。
- 目标项目 `AGENTS.md` 是否包含受管理入口块。
- provider registry validator。
- evaluation registry validator。
- active harness alignment validator。

验证 receipt 写入：

```text
C:\Path\To\TargetProject\.codex-harness\receipts\verify-receipt.json
```

## 使用边界

- 这是项目内安装，不是全局安装。
- 目标项目的 Codex 线程读取根目录 `AGENTS.md` 后，会看到 `.codex-harness/` 入口。
- ChatGPT Web / ChatGPT App no-API 仍然只是 candidate-artifact assist channel。
- Cursor SDK / CLI 仍然需要真实 Cursor authentication；没有认证时只能记录 blocked receipt 或 capability probe。
- 评测 registry 只登记标准和映射，不触发自动修复。

## 当前不做

- 不安装为系统服务。
- 不修改全局 `$CODEX_HOME`、全局 skills 或全局 MCP 配置。
- 不自动把目标项目提交到 Git。
- 不把第三方 benchmark runner 接进 dispatch。
