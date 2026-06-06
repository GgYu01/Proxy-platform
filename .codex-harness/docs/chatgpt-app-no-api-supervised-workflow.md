# ChatGPT App 无 API 监督协作方案

日期：2026-05-27
状态：可选方案；默认优先使用 Simprint 浏览器桥接的 ChatGPT Web 人工协作流程

## 结论

这个方案不是“从 ChatGPT Web 直接调用本地 Codex 干活”。

正确边界是：

```text
用户在 ChatGPT Web 里手动选择模型
  -> 用户在当前对话启用 ChatGPT App connector
  -> ChatGPT 通过 Apps SDK / MCP 调用我们写的受限后端工具
  -> 后端只保存任务包、候选 patch、报告和 receipt 查询结果
  -> 本地 Codex supervisor 独立读取候选产物、应用到隔离环境、跑测试并验收
  -> 本地 Codex 写 local_supervisor_receipt
  -> ChatGPT App 只能读取 receipt 并起草更易读的报告
```

用户不想使用 OpenAI API 时，MCP 后端不得调用 Responses API、Chat Completions API 或其他模型 API。模型推理发生在 ChatGPT Web 产品里，使用用户当前手动选择的模型和 ChatGPT 订阅额度。

如果只是想让本地 Codex supervisor 和 ChatGPT Web 协作，不需要 ChatGPT 直接调用本地工具，默认不要走本方案。优先使用 `docs/chatgpt-web-manual-assist-workflow.md` 中的 Simprint 浏览器桥接路线：

```text
Simprint Chrome 144 + ChatGPT Web GPT-5.5 Thinking
  -> Codex 通过本地 CDP 辅助打开/填入已脱敏 prompt
  -> 用户确认模型、内容和发送动作
  -> ChatGPT Web 返回候选 artifact
  -> 本地 Codex supervisor 验收
```

这条默认路线不需要公网 IP、HTTPS tunnel 或 ChatGPT Apps SDK connector。

## 详细实施计划

### 阶段 1：固定边界和安全策略

目标：保证这个方案不会退化成 API executor、浏览器自动化或本地 Codex remote control。

交付物：

- `docs/chatgpt-app-no-api-supervised-workflow.md`
- `docs/protocol-boundaries.md`
- `docs/project-capability-profile.md`

验收：

- 文档明确写出：ChatGPT Web 模型选择只作用于当前 ChatGPT 对话的大脑，不是 Apps SDK 的配置项。
- connector 明确禁止调用模型 API、启动 Codex、运行 shell、提交 git、部署、读取 secrets。
- 本地 Codex supervisor 是唯一验收方。

### 阶段 2：实现受限 connector artifact inbox

目标：让 ChatGPT Web 通过 Apps SDK / MCP 工具把尽可能多的草拟工作交给 ChatGPT 完成，并以结构化 artifact 交给本地。

交付物：

- `tools/chatgpt_app_no_api_common.py`
- `tools/chatgpt_app_no_api_connector.py`

验收：

- 创建 run 时强制 `api_model_calls_allowed: false`。
- 创建 run 时强制 `local_supervisor_required: true`。
- artifact 写入 `.tmp/chatgpt-app/<run_id>/incoming/`。
- manifest 记录 artifact path、type、producer、sha256。
- 明文 secret、cookie、token、session、private key 等字段或内容被拒绝。

### 阶段 3：实现本地 Codex supervisor

目标：Codex 不负责主要生成工作，只负责读取候选 artifact、运行本地检查、给出验收或返工反馈。

交付物：

- `tools/chatgpt_app_supervisor.py`

验收：

- 本地 check 通过时 receipt 为 `passed`。
- 本地 check 失败时 receipt 为 `failed`。
- 没有 check 时 receipt 为 `needs_manual_review`，不得伪装成通过。

### 阶段 4：接入 ChatGPT Web

目标：让用户在 ChatGPT Web 中手动选择 GPT-5.5 Thinking，然后通过 connector 调用上面的工具。

注意：这是可选路线。只有当任务需要 ChatGPT Web 在网页里直接执行 connector tool call、把 artifact 写入 `.tmp/chatgpt-app/` 时，才需要 HTTPS tunnel。如果只是让 ChatGPT Web 起草 patch/report，由本地 Codex 监督验收，使用 Simprint 浏览器桥接路线即可，不需要 tunnel。

如果用户希望从 ChatGPT Web 作为任务起始入口，必须使用 workspace registry。ChatGPT Web 不能传入任意本地绝对路径；它只能先调用 `list_registered_workspaces`，选择一个用户预注册的 `workspace_id`，再用 `create_assist_run` 绑定该工作区。后续读取源码只能走 `list_workspace_files`、`read_workspace_file` 或 `create_workspace_bundle`，并受本地路径、大小、扩展名、忽略目录和敏感内容过滤约束。完整入口设计见 `docs/chatgpt-web-workload-and-entry-design.md`。

配置：

1. 本地启动 connector。
2. 用 HTTPS tunnel 暴露 `/mcp`。
3. 在 ChatGPT Web 的 Apps & Connectors 开发者设置里创建 connector。
4. 在新对话中添加 connector。
5. 在 ChatGPT Web 里手动选择 GPT-5.5 Thinking。
6. 让 ChatGPT 先调用 `create_assist_run`，再调用 `submit_candidate_artifact` 提交候选 patch/report。

验收：

- ChatGPT Web 中能看到 connector。
- ChatGPT Web 能提交 artifact。
- 本地 `.tmp/chatgpt-app/<run_id>/` 生成 request、incoming artifact 和 manifest。
- Codex supervisor 能生成 receipt。

### 阶段 5：闭环返工

目标：把 Codex 的审核、指出问题、验收反馈送回 ChatGPT Web，让 ChatGPT 继续承担修订工作。

流程：

1. Codex supervisor 生成 failed receipt 或 feedback。
2. ChatGPT Web 调用 `get_supervisor_receipt` 读取问题。
3. ChatGPT Web 按 feedback 修订，再调用 `submit_candidate_artifact` 覆盖或新增 artifact。
4. Codex supervisor 重新验收。

验收：

- 每次返工都有 revision request 或 supervisor feedback。
- 每次重新提交都有新的 artifact manifest hash。
- 最终只有 passed receipt 才能作为交付依据。

## 不是 API Executor

Apps SDK connector 只把工具暴露给 ChatGPT。它不等于 API executor，也不让本地 Codex 自动受 ChatGPT Web 控制。

无 API 模式下：

- 不配置 OpenAI API key。
- 不在 MCP 后端调用模型。
- 不在工具 schema 里提供 `model`、`reasoning_effort` 或类似 API 参数。
- 不把 ChatGPT 会话 ID、cookie、session、share link 当作项目资产。
- 不把 ChatGPT Web 输出当作已验收结果。

ChatGPT Web 当前用哪个模型，由用户在 ChatGPT 界面里手动选择。Apps SDK 不能强制 ChatGPT Web 使用某个模型。

## 模型选择到底怎么作用

Apps SDK / MCP connector 只定义工具：工具名、参数 schema、说明、返回值，以及可选的组件 UI。它不定义 ChatGPT Web 当前对话使用哪一个大模型，也不消耗本地 OpenAI API key。

实际工作时有两个平面：

- 推理平面：发生在 ChatGPT Web 产品里。你在 ChatGPT Web 里选择本次 run 要求的 GPT-5.5 Thinking 或 GPT-5.5 Pro，并把 thinking effort 设为该模型要求档。Thinking 默认选择当前可见最高档 `深入`；关键 Pro 阶段必须选择 `Extended`，且要有当前账号 UI probe receipt。若 UI 证据不包含 Extended，则记录可见选项并阻塞，不在低档位下生成 patch/report 草稿。那么当前对话里的 ChatGPT 就用这个产品侧模型来读提示词、决定是否调用 connector、生成候选产物。这个配额按你的 ChatGPT 产品账号和订阅规则走，不是本地 Codex 的 API 调用。
- 工具平面：发生在我们写的本地 connector 后端。ChatGPT Web 如果调用 `submit_candidate_artifact`，后端只把候选 artifact 写到 `.tmp/chatgpt-app/<run_id>/incoming/`，写 manifest/hash，或读取本地 supervisor receipt。后端不调用 Responses API、Chat Completions API 或任何模型 API。

因此“选择模型”的作用点在 ChatGPT Web 对话，不在 connector 配置。connector 里不应该提供 `model`、`reasoning_effort`、`api_key` 这类字段；否则就会把 no-API 协作误做成 API executor。

官方 Apps SDK 的定位也是把 MCP 工具和组件接入 ChatGPT 体验，而不是让本地程序稳定遥控 chatgpt.com 网页会话。需要 ChatGPT 直接调用本地工具时，ChatGPT 需要能访问 HTTPS MCP URL；本机没有公网 IP 时，应使用 Secure MCP Tunnel、Cloudflare Tunnel、ngrok 等隧道，而不是暴露真实内网地址。若不需要 ChatGPT 直接 tool call，优先使用 Simprint CDP 手动协作路线。

## 为什么还需要 Connector

纯手工流程需要复制、上传、下载文件，容易漏掉 artifact、hash、验收结果和限制说明。Connector 的价值是把这些动作结构化：

- ChatGPT 把候选 patch/report 通过 tool call 提交给后端。
- 后端给每个 artifact 写 manifest、路径、hash 和 producer。
- 本地 Codex supervisor 能读取同一份结构化 inbox。
- ChatGPT 可以查询本地 supervisor receipt，但不能伪造验收。

这个 connector 是“受限任务收件箱”和“artifact 中转站”，不是本地 shell，不是 Codex remote control。

## 组件划分

### ChatGPT Web

用户在 ChatGPT Web 中：

- 手动选择想用的模型，例如 GPT-5.5 Thinking。
- 在对话里启用本项目 connector。
- 要求 ChatGPT 生成或修订候选 patch/report。
- 确认必要的 tool call。

ChatGPT Web 不能：

- 直接访问本地 repo。
- 直接运行测试。
- 直接启动 Codex。
- 直接 merge、deploy 或标记交付完成。
- 读取或保存本地凭据。

### ChatGPT App Connector / MCP 后端

建议代码位置：

```text
tools/chatgpt_app_no_api_connector.py
tools/chatgpt_app_no_api_common.py
```

第一版只需要 MCP tools，不需要 iframe UI。当前已实现 tools：

| Tool | 写权限 | 作用 |
|---|---:|---|
| `create_assist_run` | 是 | 创建一次协作 run，写入目标、范围、限制和期望 artifact。 |
| `submit_candidate_artifact` | 是 | 提交候选 patch、report 或代码包，只写入 `.tmp/chatgpt-app/<run_id>/incoming/`。 |
| `list_candidate_artifacts` | 否 | 列出候选 artifact、hash、时间和 producer。 |
| `get_supervisor_receipt` | 否 | 读取本地 Codex supervisor 写入的 receipt。 |
| `request_revision` | 是 | 记录验收失败后的修订要求，供 ChatGPT 继续改。 |

禁止提供这些 tools：

- `run_shell`
- `run_codex`
- `apply_patch_to_repo`
- `git_commit`
- `deploy`
- `read_secret`
- `read_browser_session`

后端可以写入：

```text
.tmp/chatgpt-app/<run_id>/request.json
.tmp/chatgpt-app/<run_id>/incoming/<artifact>
.tmp/chatgpt-app/<run_id>/artifact-manifest.json
.tmp/chatgpt-app/<run_id>/revision-requests.jsonl
```

后端只能读取：

```text
.tmp/chatgpt-app/<run_id>/local-supervisor-receipt.json
.tmp/chatgpt-app/<run_id>/public-report.md
```

### 本地 Codex Supervisor

建议代码位置：

```text
tools/chatgpt_app_supervisor.py
```

职责：

1. 读取 `.tmp/chatgpt-app/<run_id>/incoming/`。
2. 验证 manifest、hash、文件类型和敏感字段。
3. 在隔离 worktree 或 scratch copy 中应用候选 patch。
4. 运行项目指定测试、lint、schema validator 和必要的人工审查 gate。
5. 写入 `.tmp/chatgpt-app/<run_id>/local-supervisor-receipt.json`。
6. 失败时写入结构化 failure，供 `request_revision` 使用。

Codex supervisor 是唯一能把候选产物推进到“可交付”的组件。

## 本地命令

启动 connector：

```powershell
C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\chatgpt_app_no_api_connector.py serve --host 127.0.0.1 --port 8787
```

本地列出 tools：

```powershell
C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\chatgpt_app_no_api_connector.py list-tools
```

本地模拟创建 run：

```powershell
$payload = @{ run_id = "demo_run"; goal = "Draft a candidate patch for local Codex supervisor review."; redaction_confirmed = $true } | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-app-create.json -Value $payload -Encoding UTF8
C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\chatgpt_app_no_api_connector.py call-tool create_assist_run --arguments-json-file .tmp\chatgpt-app-create.json
```

本地模拟提交 artifact：

```powershell
$payload = @{ run_id = "demo_run"; artifact_type = "markdown_report"; filename = "report.md"; content = "# Report`n`nCandidate only." } | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-app-artifact.json -Value $payload -Encoding UTF8
C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\chatgpt_app_no_api_connector.py call-tool submit_candidate_artifact --arguments-json-file .tmp\chatgpt-app-artifact.json
```

运行 supervisor 的本地 smoke check：

```powershell
$run = "demo_run"
$code = "import pathlib; run = pathlib.Path('$run'); assert (run / 'request.json').exists(); assert (run / 'artifact-manifest.json').exists(); assert any((run / 'incoming').iterdir())"
$check = @("C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe", "-c", $code) | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-app-check.json -Value $check -Encoding UTF8
C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\chatgpt_app_supervisor.py $run --check-json-file .tmp\chatgpt-app-check.json
```

## 阶段 4 手把手接入 ChatGPT Web

这一阶段的目标是让 ChatGPT Web 里的模型承担生成、分析、改写和候选 patch/report 草拟工作；本地 Codex 只负责启动受限 connector、观察 artifact、运行本地验收和写 receipt。

### 必须手动完成的动作

这些动作不能由本地 Codex 安全代办：

1. 登录你的 ChatGPT Web 账号。
2. 在 ChatGPT Web 里手动选择你想用的模型，例如 GPT-5.5 Thinking。
3. 在 ChatGPT 设置里创建 connector。
4. 在每次写入类 tool call 前检查 ChatGPT 展示的 JSON payload，并确认是否允许调用。

不要把 ChatGPT cookie、session、share link、OAuth token 或任何账号凭据写入本仓库、`.tmp/` artifact、日志或 prompt。

### 第 1 步：启动本地 connector

在第一个 PowerShell 窗口中运行：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_app_no_api_connector.py serve --host 127.0.0.1 --port 8787
```

这个窗口要保持打开。此时本地地址是：

```text
http://127.0.0.1:8787/mcp
```

ChatGPT Web 不能直接访问这个 localhost 地址，后面必须通过 HTTPS tunnel 暴露。

在第二个 PowerShell 窗口里先做本地自检：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8787/health
& $python tools\chatgpt_app_no_api_connector.py list-tools
```

`list-tools` 应该至少能看到这些工具：

- `list_registered_workspaces`
- `create_assist_run`
- `list_workspace_files`
- `read_workspace_file`
- `create_workspace_bundle`
- `submit_candidate_artifact`
- `list_candidate_artifacts`
- `get_supervisor_receipt`
- `request_revision`

### 第 2 步：按需给 tunnel 命令走 Hiddify 代理

如果本机直接访问 ChatGPT 或 tunnel 服务不稳定，先确认 Hiddify mixed port：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_app_proxy.py probe
```

返回 `ok: true` 表示 `127.0.0.1:12334` 可用。需要让某条 tunnel 或诊断命令走代理时，用：

```powershell
& $python tools\chatgpt_app_proxy.py run -- <需要走代理的命令>
```

也可以写出 `.env` 风格代理文件，供需要读取环境变量的工具使用：

```powershell
& $python tools\chatgpt_app_proxy.py write-env .tmp\chatgpt-app-proxy.env
```

该文件只包含本地代理地址，不包含账号、token 或密码。

### 第 3 步：创建 HTTPS tunnel

ChatGPT Web 创建 connector 时需要一个可访问的 HTTPS `/mcp` URL。优先级如下。

方式 A：Secure MCP Tunnel。

OpenAI 官方建议本地、内网或受防火墙保护的 MCP server 使用 Secure MCP Tunnel。这个方式不需要把本地 MCP server 直接暴露到公网，但需要在 OpenAI Platform tunnel settings 中创建 tunnel，并给 `tunnel-client` 配置 runtime API key、`tunnel_id` 和本地 MCP server 地址。

关键边界：

- `tunnel-client` 的 API key 只用于连接 OpenAI tunnel control plane，不允许写入本仓库、`.tmp/`、日志或 artifact。
- 本项目 connector 仍然不得调用 Responses API、Chat Completions API 或其他模型 API。
- 如果你只是想快速 smoke test，Cloudflare Tunnel 或 ngrok 更直接；如果你想长期保留私有边界，优先 Secure MCP Tunnel。

按官方页面下载 `tunnel-client` 后，先运行：

```powershell
tunnel-client help quickstart
```

本项目当前是 HTTP MCP server，本地地址是：

```text
http://127.0.0.1:8787/mcp
```

因此配置 tunnel-client 时应使用官方文档中的 HTTP MCP server URL 路线，而不是 stdio sample。连接 ChatGPT 时，在 connector 创建页选择 Tunnel，再选择可用 tunnel 或粘贴有效 `tunnel_id`。

方式 B：Cloudflare Tunnel 临时开发 URL。

如果未安装 `cloudflared`，先安装：

```powershell
winget install --id Cloudflare.cloudflared
```

启动 tunnel：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_app_proxy.py run -- cloudflared tunnel --url http://127.0.0.1:8787
```

命令输出里会出现类似：

```text
https://example.trycloudflare.com
```

在 ChatGPT connector 里填写：

```text
https://example.trycloudflare.com/mcp
```

方式 C：ngrok 临时开发 URL。

如果未安装 `ngrok`，先安装：

```powershell
winget install --id Ngrok.Ngrok
```

如果 ngrok 要求 authtoken，在用户级配置里设置，不要写入本仓库：

```powershell
ngrok config add-authtoken <你的-ngrok-token>
```

启动 tunnel：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_app_proxy.py run -- ngrok http 8787
```

ngrok 输出里会出现类似：

```text
https://example.ngrok-free.app
```

在 ChatGPT connector 里填写：

```text
https://example.ngrok-free.app/mcp
```

### 第 4 步：在 ChatGPT Web 创建 connector

在 ChatGPT Web 中执行：

1. 打开 Settings -> Apps & Connectors -> Advanced settings。
2. 启用 Developer mode。
3. 打开 Settings -> Connectors -> Create。
4. 填写 connector 信息。
5. 点击 Scan Tools，确认工具列表。
6. 点击 Create。

建议第一版开发配置：

```text
Connector name:
Codex Harness Supervisor Inbox No API

Description:
Use this connector only to create assist runs and submit candidate artifacts for local Codex supervisor review. It cannot run shell, apply patches, read secrets, call model APIs, or verify locally.

Connector URL:
<你的 HTTPS tunnel URL>/mcp

Authentication:
No Authentication
```

`No Authentication` 只适合本地开发和短期 tunnel smoke test。生产或多人使用时必须增加访问控制、审计和最小权限配置。

如果页面没有 Developer mode、Create 或 Scan Tools 按钮，通常是账号计划、工作区管理员权限、组织设置或功能灰度问题。以 ChatGPT Web 当前 UI 为准。

### 第 5 步：在新对话中启用 connector 并选择模型

在 ChatGPT Web 中：

1. 新开一个对话。
2. 手动选择目标模型，例如 GPT-5.5 Thinking。
3. 点击输入框旁边的 `+`。
4. 选择 More。
5. 添加 `Codex Harness Supervisor Inbox No API` connector。

模型选择发生在 ChatGPT Web 当前对话里。Apps SDK connector 不能规定模型，也不会把 `model` 参数传给本地后端。本地后端只接收 ChatGPT 通过 tool call 交来的结构化 artifact。

### 第 6 步：首次 smoke test 提示词

把下面这段发给 ChatGPT Web。若重复测试，修改 `run_id` 后缀，避免重复创建同名 run。

```text
请只使用 “Codex Harness Supervisor Inbox No API” connector，不要使用内置浏览、代码解释器或其他工具。

第一步，请调用 create_assist_run，参数如下：
{
  "task_id": "stage4_smoke",
  "run_id": "stage4_smoke_20260528_001",
  "goal": "Smoke test the no-API ChatGPT App connector by submitting a candidate markdown report for local Codex supervisor review.",
  "scope": [
    "connector tool call only",
    "no local shell",
    "no repository writes"
  ],
  "constraints": [
    "Do not include secrets, tokens, cookies, sessions, passwords, or private keys.",
    "Do not claim that ChatGPT ran local tests.",
    "Local Codex supervisor is the only verifier."
  ],
  "expected_artifacts": [
    "report.md"
  ],
  "verification_commands": [
    "local Codex supervisor smoke check"
  ],
  "redaction_confirmed": true,
  "redaction_confirmed_by": "user"
}

第二步，create_assist_run 成功后，请调用 submit_candidate_artifact，参数如下：
{
  "run_id": "stage4_smoke_20260528_001",
  "artifact_type": "markdown_report",
  "filename": "report.md",
  "content": "# Stage 4 Smoke Report\n\nThis is a candidate artifact submitted from ChatGPT Web through the no-API connector.\n\n## Boundaries\n\n- ChatGPT Web drafted this report.\n- The connector did not call OpenAI APIs.\n- The connector did not run shell commands.\n- Local Codex supervisor must verify this artifact before delivery.\n"
}

完成后，请回复 run_id、提交的 artifact 文件名，以及你看到的 tool call 返回结果摘要。不要声称本地验收已通过。
```

ChatGPT 触发写入类 tool call 时，界面会要求确认。确认前检查 JSON payload，确保没有 secrets、cookie、token、session、密码或私钥。

如果从 ChatGPT Web 入口开始，并且需要让 Web 侧自己发现本地上下文，可以使用下面这段更完整的提示词：

```text
请只使用 “Codex Harness Supervisor Inbox No API” connector。
第一步调用 list_registered_workspaces，列出可选 workspace。
我选择 workspace_id 为 harness_agent_approve。
第二步调用 create_assist_run，并传入 workspace_id。
第三步调用 list_workspace_files，只读取和当前任务相关的文件；需要单个文件时调用 read_workspace_file。
如果需要较完整上下文，请调用 create_workspace_bundle，但不要声称你已经上传或运行了本地测试。
最后用 submit_candidate_artifact 提交 changes.patch 和 report.md。
本地 Codex supervisor 会验证 artifact 并写 local-supervisor-receipt.json。
```

### 第 7 步：本地确认 artifact 已生成

ChatGPT tool call 成功后，在本地第二个 PowerShell 窗口执行：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$run = "stage4_smoke_20260528_001"
Get-ChildItem -Force ".tmp\chatgpt-app\$run"
Get-ChildItem -Force ".tmp\chatgpt-app\$run\incoming"
Get-Content -LiteralPath ".tmp\chatgpt-app\$run\request.json" -Raw
Get-Content -LiteralPath ".tmp\chatgpt-app\$run\artifact-manifest.json" -Raw
```

最低应看到：

```text
.tmp/chatgpt-app/<run_id>/request.json
.tmp/chatgpt-app/<run_id>/incoming/report.md
.tmp/chatgpt-app/<run_id>/artifact-manifest.json
```

### 第 8 步：运行本地 Codex supervisor

先跑最小 smoke check：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$run = "stage4_smoke_20260528_001"
$code = "import pathlib; run = pathlib.Path('$run'); assert (run / 'request.json').exists(); assert (run / 'artifact-manifest.json').exists(); assert any((run / 'incoming').iterdir())"
$check = @($python, "-c", $code) | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-app-check.json -Value $check -Encoding UTF8
& $python tools\chatgpt_app_supervisor.py $run --check-json-file .tmp\chatgpt-app-check.json --json
Get-Content -LiteralPath ".tmp\chatgpt-app\$run\local-supervisor-receipt.json" -Raw
```

如果 receipt 中 `status` 是 `passed`，说明阶段 4 smoke test 通过。真实工程任务还要把 check command 换成项目的 unit test、lint、schema validator、patch apply 或人工 review gate。

### 第 9 步：把 Codex 反馈送回 ChatGPT Web

如果本地 supervisor 生成了 `failed` 或 `needs_manual_review` receipt，在 ChatGPT Web 里继续提示：

```text
请调用 get_supervisor_receipt，run_id 为 "stage4_smoke_20260528_001"。
读取本地 Codex supervisor 的反馈后，重新提交一个修订版 report.md。
提交时仍然只使用 submit_candidate_artifact，不要声称你运行了本地测试。
```

如果需要显式记录返工要求，可以让 ChatGPT 调用 `request_revision`，然后再提交新的 artifact。最终只有本地 Codex supervisor 写出的 `passed` receipt 可以作为交付依据。

### 常见故障

- ChatGPT Scan Tools 失败：确认本地 connector 窗口仍在运行，HTTPS URL 末尾是 `/mcp`，tunnel 没有断开，本地 `Invoke-WebRequest http://127.0.0.1:8787/health` 正常。
- ChatGPT 只能看到旧工具：在 Settings -> Connectors 里打开该 connector，点击 Refresh，再新开对话测试。
- ChatGPT 不调用指定工具：在 prompt 里明确写“只使用这个 connector”，并点名 `create_assist_run` 和 `submit_candidate_artifact`。
- 写入类调用一直要求确认：这是正常安全行为。确认前检查 JSON payload。
- tunnel 命令访问失败：先启动 Hiddify，再用 `tools\chatgpt_app_proxy.py run -- <tunnel 命令>` 包裹。
- `.tmp/chatgpt-app/<run_id>/` 没有生成：说明 ChatGPT 没有成功调用写入工具，回到 ChatGPT UI 查看 tool call 返回和错误。
- ChatGPT Web 没有 Developer mode 或 Create：检查账号计划、工作区管理员设置和功能灰度；本地代码无法绕过这个产品权限。

### 官方依据

- OpenAI Apps SDK Connect from ChatGPT: https://developers.openai.com/apps-sdk/deploy/connect-chatgpt
- OpenAI ChatGPT Developer mode: https://developers.openai.com/api/docs/guides/developer-mode
- OpenAI Help Center Developer mode and MCP apps: https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt

## 生产配置要求

生产阶段：

- MCP 后端必须有 HTTPS、访问控制、审计日志和错误监控。
- 写工具默认需要人工确认。
- 所有输入都要服务端校验。
- 不把 token、cookie、session、API key、private key 或数据库密码写入 artifact、日志或 tool response。

## 配额和费用

无 API 模式下：

- ChatGPT 的推理消耗用户 ChatGPT 产品订阅内的消息/使用限制。
- 本项目 MCP 后端不消耗 OpenAI API token。
- 只有当后端主动调用 OpenAI API、第三方 API 或云服务时，才会产生对应 API/云服务费用。

因此第一版应该明确禁止 MCP 后端调用模型 API，避免把用户的 ChatGPT 订阅路径误变成 API 计费路径。

## 最小验收标准

一个 run 只有同时满足以下条件，才算可交付：

1. ChatGPT App connector 已提交候选 artifact manifest。
2. 本地 Codex supervisor 已验证 artifact hash 和敏感字段。
3. 候选 patch 已在隔离环境应用成功。
4. 指定测试和检查命令已运行并通过，或有明确不可运行原因。
5. `local-supervisor-receipt.json` 存在，且 `status` 为 `passed`。
6. 最终报告与 receipt 一致，没有声称 ChatGPT Web 自己运行了本地测试。

## 和现有人工流程的关系

`docs/chatgpt-web-manual-assist-workflow.md` 是纯人工上传/下载流程。

本文是 Apps SDK connector 辅助流程。它减少手工搬运，但仍然是外部协作通道，不是 Harness Run Contract adapter。未来如果要做真正自动 executor，应另建 API-backed adapter，并继续通过 Harness Run Contract 接入。

## Project / Conversation 持久化边界

如果把 ChatGPT Project 作为任务入口，Project 只能被视为 ChatGPT 产品侧的长期上下文容器；当前 Web conversation 只能被视为本次 run/attempt 的工作面。connector 后端和本地 Codex supervisor 只保存用户可读 alias，例如 `chatgpt_project_alias`、`chatgpt_conversation_alias`、`run_id`、`attempt_id` 和 artifact/receipt 路径。

当前默认 ChatGPT Project alias 是：

```text
harness-dev-test
```

这个 alias 只用于让用户和本地 manifest 对齐，不是 ChatGPT Project ID，也不是可恢复控制柄。

源码上传分两种：

- `project_sources`：用户把 `source-files.zip`、`source-files-manifest.json` 和 request 手动上传到 ChatGPT Project sources / files。适合希望 ChatGPT Web 在同一 Project 内跨多轮使用这批安全上下文的任务。旧包过期后需要用户手动从 Project sources 删除。
- `conversation`：用户只把文件作为当前 Web conversation 附件上传。适合一次性 run，默认更不容易污染长期 Project 上下文。

connector 可以生成 bundle 和 manifest，但不能证明 ChatGPT Web 里已经完成 Project-source 上传；写入 Project sources、选择模型和发送消息都必须由用户在 Web UI 中确认。

禁止把以下内容写入 `.tmp/`、项目文档、manifest、prompt、artifact 或 harness task payload：

- ChatGPT cookie、session、localStorage、OAuth token、share link。
- 真实 ChatGPT Project ID、conversation ID、session ID。
- 可以恢复网页登录态或绕过用户确认的任何控制柄。
- `model`、`reasoning_effort`、`api_key` 等会把 no-API connector 误导成 API executor 的字段。

可运行 demo 见 `tools/chatgpt_web_project_conversation_demo.py`，中文说明见 `docs/chatgpt-web-project-conversation-demo.md`。
