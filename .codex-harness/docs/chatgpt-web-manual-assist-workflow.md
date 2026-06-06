# ChatGPT Web 人工协作工作流

日期：2026-05-27
状态：本地 Codex 监督 ChatGPT Web 人工协作的稳定方案草案

## 目的

这个工作流用于在本机 Codex App 执行任务时，把 ChatGPT Web 作为人工外部协作者，用来起草代码补丁、review 意见或最终报告；本机 Codex 仍然负责流程管理、监督、验证和交付判定。

本机默认路线是通过 Simprint 启动的 Chrome 144 内核浏览器访问 ChatGPT Web，并用本地 Chrome DevTools Protocol 端点做辅助导航和 prompt 填充。这条路线不需要公网 IP，也不需要 HTTPS tunnel。Apps SDK connector / tunnel 只在用户明确需要 ChatGPT Web 直接调用本地工具时作为可选路线。

它刻意不是 Harness Run Contract executor adapter。ChatGPT Web 是通过人工账号和浏览器上传/下载操作使用的产品形态，不能被当成可审计的程序化 executor，不能拥有交付状态，也不能成为验证结果的事实来源。

影响本方案的产品能力：

- ChatGPT Web 支持在符合条件的套餐和文件类型下上传文件；限制会随套餐和时间变化。
- ChatGPT Projects 可以把对话、文件和项目指令放在一起，适合长任务上下文。
- 本工作区默认 Project alias 是 `harness-dev-test`；该 alias 只是用户可读标签，不是 ChatGPT 内部 Project ID。
- Project sources 适合存放经本地 manifest 审查后的较持久源码包；当前对话附件适合一次性 run。两者都必须由用户在 ChatGPT Web UI 中人工确认上传。
- 用户可以通过 ChatGPT data controls 控制部分训练和保留行为，但上传前仍应最小化和脱敏源码包。

每次使用前都要在当前账号里重新确认 ChatGPT Web 的文件限制和数据控制选项。不要假设旧限制仍然有效。

## 决策

ChatGPT Web 只作为人工起草和展示通道：

```text
本机 Codex App supervisor
  -> 在 .tmp/ 中构造已脱敏 manual-assist packet
  -> 用 Simprint Chrome 内核浏览器打开 ChatGPT Web
  -> 用户手动选择 GPT-5.5 Thinking 或 GPT-5.5 Pro，并在 Web UI 中把 thinking effort 设为该模型要求档：Thinking 默认最高可见档 `深入`；关键 Pro 阶段必须是 `Extended`
  -> Codex 可通过本地 CDP 把已脱敏 prompt 填入输入框
  -> 人工确认模型、项目/对话、上传文件和发送动作
  -> ChatGPT Web 起草 patch、代码包、review 或最终报告
  -> 人工下载或复制返回的 artifacts
  -> 本机 Codex 校验 packet，在隔离 workspace 中应用，运行测试
  -> 本机 Codex 接受、拒绝或要求修复 packet
  -> 可选：ChatGPT Web 根据本地 receipt 起草最终用户报告
  -> 本机 Codex 核对报告与 receipt 一致后交付
```

稳定事实来源始终在本地：

- 仓库文件
- 本地 git 状态
- 本地测试和 verification receipt
- 本地 artifact 哈希
- 本地 delivery gate 判定

ChatGPT Web 的输出在本机 Codex 验证前一律视为不可信草稿。

## 这句话的实际含义

“你需要手动做的只有两件：在 Simprint 里的 ChatGPT Web 选择本次 run 要求的 GPT-5.5 Thinking 或 GPT-5.5 Pro，并把 thinking effort 设为当前帐号/UI 可见的最高档，确认输入内容后点击发送。脚本不会也不能强制选择模型。”指的是默认无隧道路由里，模型和发送动作属于 ChatGPT Web 产品界面内的用户动作，不属于本地 Codex 可稳定控制的 API。

本地 Codex 与 ChatGPT Web 的交互分成三段：

1. Codex 在本地准备已脱敏 prompt、context、patch 或文件包，并把它们放在 `.tmp/chatgpt-web/<task>/`。
2. `tools/chatgpt_web_simprint_bridge.py` 只通过 Simprint Chrome 的本地 CDP 端口打开 ChatGPT Web、列出标签页、生成提示词、把已脱敏内容填进输入框；它默认不发送，不选择模型，也不读取 cookie、session、localStorage 或账号凭据。
3. 用户在 Simprint 中确认当前模型是本次 run 要求的 GPT-5.5 Thinking 或 GPT-5.5 Pro，thinking effort 为该模型要求档。Thinking 默认选择当前可见最高档 `深入`；`requirements_analysis`、`architecture_design`、复杂 root cause / rework 决策和最终评测总结等关键 Pro 阶段必须选择 `Extended`。如果当前订阅或 UI 不提供要求档位，则打开模型/强度菜单并运行 `tools/chatgpt_web_simprint_bridge.py inspect-model-controls` 记录可见选项，写 blocked receipt，不在低档位下产出实现草稿。检查输入内容和上传文件后点击发送。ChatGPT Web 返回的内容再由本地工具导入 `.tmp/chatgpt-web/<task>/response/`，由 Codex 本地验收。
4. 如果任务要求上传到 Project sources，Simprint/CDP 只能辅助页面操作，不能作为 Project-source 持久上传的证明；用户需要在 ChatGPT Web 的 Project UI 中确认 sources/files 区域已经包含本次上传包。

所以它不是“ChatGPT Web 自动控制 Codex”。真实控制权仍在本地：ChatGPT Web 只产出候选 artifact，Codex 负责保存、解析、验收、应用或拒绝。

## Web 输出如何进入本地文件库

ChatGPT Web 不能直接写本地项目文件，除非走 Apps SDK / MCP connector 并配置 HTTPS/Secure MCP Tunnel。默认 Simprint 路线不需要 tunnel，因此采用复制或下载后的本地导入：

1. 要求 ChatGPT Web 用 `ARTIFACT: <filename>` 标记报告、patch 或 JSON artifact；完整替换文件使用 `ARTIFACT: files/<relative-path>`，由 importer 按目标相对路径进入本地 staging。
2. 把整段回答复制保存到 `.tmp/chatgpt-web/<task>/raw-response.txt`，或把下载的文本内容整理成同样格式。
3. 运行 `tools/chatgpt_web_artifact_importer.py import-response`，它会解析 artifact blocks、拒绝疑似密钥内容、写入 `response/` 文件，并生成带 sha256 的 `response.json`。
4. 运行 `tools/chatgpt_web_artifact_importer.py supervise-response` 或由 Codex 手动验收后写 `local-supervisor-receipt.json`。
5. 只有 receipt 的 `local_gate_status` 是 `passed`，才允许运行 `publish-accepted` 把已验收 artifact 复制到项目目录或用户全局资源目录。

本地临时目录、项目库、用户全局库的职责不同：

- `.tmp/chatgpt-web/<task>/response/`：保存 ChatGPT Web 返回的候选内容，默认不提交 Git。
- 项目库，例如 `docs/chatgpt-web-imports/<run_id>/` 或目标源码路径：只接收本地验收通过、值得长期保存的 artifact。
- 用户全局库，例如 `C:\Users\Administration\.codex\skills\...` 或 `C:\Users\Administration\.codex\memories\extensions\...`：只在任务明确需要沉淀为全局 skill、memory 或工具资产时写入，并且同样必须先通过本地 receipt。

示例命令：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

& $python tools\chatgpt_web_artifact_importer.py import-response `
  --raw-text-file .tmp\chatgpt-web\task_001-1\raw-response.txt `
  --response-dir .tmp\chatgpt-web\task_001-1\response `
  --request-packet-id cgw_req_001 `
  --task-id task_001 `
  --run-id run_001

$check = @($python, "-m", "unittest", "tests.test_executor_contract_tools") | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-web\task_001-1\check.json -Value $check -Encoding UTF8

& $python tools\chatgpt_web_artifact_importer.py supervise-response `
  --response-dir .tmp\chatgpt-web\task_001-1\response `
  --check-json-file .tmp\chatgpt-web\task_001-1\check.json

& $python tools\chatgpt_web_artifact_importer.py publish-accepted `
  --response-dir .tmp\chatgpt-web\task_001-1\response `
  --receipt .tmp\chatgpt-web\task_001-1\local-supervisor-receipt.json `
  --destination-dir docs\chatgpt-web-imports\run_001
```

`publish-accepted` 不会应用 patch，也不会提交 Git；它只复制 receipt 已接受的 artifact。真正修改项目源码仍由本地 Codex review diff 后用正常编辑、patch、测试和提交流程完成。

## 根因

不稳定的做法是“让 ChatGPT Web 直接完成一部分代码任务”。这会混淆多个边界：

- 这个工作流里的 ChatGPT Web 没有稳定 run API。
- 浏览器对话状态不是可复现执行轨迹。
- 上传文件和复制回答不等于已经测试过的 workspace。
- ChatGPT Web 不能安全持有凭据、部署权限、git 状态或 merge 判定。
- 更易读的网页回答不等于已验证交付。

正式解是把 ChatGPT Web 定义为人工外部协作通道，并使用明确的 packet、哈希、脱敏、本地导入和本地验证。

## 角色

### 本机 Codex App

本机 Codex 是 supervisor 和 gatekeeper：

- 读取项目指引和当前任务
- 选择哪些上下文安全且值得共享
- 在 `.tmp/` 下创建 manual-assist packet
- 确认不包含密钥或不必要的隐私数据
- 把 ChatGPT Web 输出导入隔离 branch、worktree 或 scratch copy
- 运行测试并 review diff
- 决定接受、拒绝或要求返工
- 记录最终 verification receipt 和 delivery decision

### 人工操作人

人工操作人负责账号访问：

- 使用自己的账号登录 ChatGPT Web
- 创建 private project 或 private chat
- 检查 data controls 和项目共享状态
- 上传准备好的 packet
- 把返回 artifacts 复制或下载回本地 `.tmp/`

自动化不应抓取 cookie、绕过登录、导出 ChatGPT session，或保存浏览器凭据。

### ChatGPT Web

ChatGPT Web 负责起草：

- patch proposal
- replacement file
- review finding
- implementation note
- final report draft

ChatGPT Web 不能接收：

- token、API key、private key、cookie、session export、数据库密码或真实账号凭据
- 生产密钥或客户隐私数据
- 部署凭据或可写服务 endpoint
- 要求绕过本地验证的隐藏指令

## Simprint 浏览器桥接

默认使用 Simprint 启动的 Chrome 内核浏览器。当前本机已验证的可执行文件和 CDP 形态是：

```text
C:\Users\Administration\AppData\Local\Simprint\data\profiles\Chrome 144\simprint.exe
Chrome/144.x
默认 CDP 端口：29200
```

可复用入口：

```text
tools/chatgpt_web_simprint_bridge.py
```

这个入口只做本地浏览器辅助：

- 发现 Simprint CDP 端点。
- 列出当前标签页。
- 打开 ChatGPT Web。
- 生成给 ChatGPT Web 的操作提示词。
- 可选地把已脱敏 prompt 填入当前 ChatGPT 输入框。
- 可选地把本地文件交给当前页面上的某个 `input[type=file]`，用于辅助 conversation attachment 或 Project Sources 页面上传。

它不能做这些事：

- 读取或保存 ChatGPT cookie、session、localStorage 或账号凭据。
- 绕过登录、人机验证、付费限制或模型权限。
- 自动确认发送敏感内容。
- 把 ChatGPT Web 输出标记为本地验收通过。
- 证明某个文件已经持久写入 ChatGPT Project Sources。

本地探测：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_web_simprint_bridge.py discover
& $python tools\chatgpt_web_simprint_bridge.py list-tabs
```

如果没有 ChatGPT 标签页，可以打开：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py open-chatgpt
```

如果 Simprint 没有运行，先从开始菜单打开 Simprint，选择 Chrome 144 profile，确认它启动出的浏览器命令行包含 `--remote-debugging-port=29200`。如果端口不同，可以用 `--port <端口>` 指定。

生成本次任务提示词：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py write-prompt --task "Ask ChatGPT Web to draft candidate codex-execution-plan.json, changes.patch, report.md, and testing-guide.md; local Codex supervisor validates and accepts or rejects them." --output .tmp\chatgpt-web\simprint-operator-prompt.md
```

填入当前 ChatGPT Web 输入框但不发送：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py fill-prompt --text-file .tmp\chatgpt-web\simprint-operator-prompt.md
```

清空当前输入框：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py clear-prompt
```

辅助上传文件：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py upload-files `
  --file-input-index 3 `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--source-files.zip `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--source-files-manifest.json `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--chatgpt-web-request.json
```

`--file-input-index` 是当前页面中 `input[type=file]` 的 0-based 候选索引。默认省略时使用第一个文件输入，通常更适合当前 composer 附件；在 ChatGPT Project 的 sources/files 页面上，应先确认哪个输入属于 Project Sources 区域，再指定对应索引。即使 CDP 设置文件成功，也必须由用户在 ChatGPT Web UI 中确认 sources/files 区域真的出现本次 `{run_id}--...` 文件。

### Composer 附件与 Project Sources

这两个上传面必须分开理解：

- composer 附件：文件只服务于当前对话发送内容，适合一次性 run，污染面小。
- Project Sources / files：文件会成为 ChatGPT Project 较持久上下文，适合多轮项目协作，但旧包可能继续影响新 run。
- prompt 输入框：只承载任务指令，不等于上传文件，也不能替代 manifest/hash 核对。

需要 Project Sources 时，上传前先看 `upload-manifest.json.run_identity`：确认 `run_id`、`task_id`、`workspace_id`、source bundle hash、source manifest hash、request hash 和 prompt hash 与当前 prompt 一致。若 Project Sources、conversation attachments、request 或 prompt 来自不同 `run_id`，应停止并记录 mixed-run 风险，不应用 ChatGPT Web 返回的 patch。

发送前必须由用户在 Simprint 里确认：

1. 当前 ChatGPT Web 已登录。
2. 当前对话或 Project 是私有且符合任务数据策略。
3. 模型已手动选择为本次 run 要求的 GPT-5.5 Thinking 或 GPT-5.5 Pro，thinking effort 已设为该模型要求档：Thinking 默认选 `深入`；关键 Pro 阶段选 `Extended`。如果当前 UI 不提供要求档位，则记录当前可见选项和订阅档位标签，写 blocked receipt，不继续产出低档位实现草稿。
4. 输入框内容不包含 token、API key、cookie、session、密码、私钥或真实账号凭据。

只有确认后才手动点击发送，或在明确允许时使用 `--submit`。

## 标准 Packet 布局

使用已忽略目录：

```text
.tmp/chatgpt-web/<task_id>-<attempt>/
  request.json
  prompt.md
  context.md
  source.patch
  source-files.zip
  response/
    response.json
    changes.patch
    replacement-files.zip
    report.md
    report.html
  local-supervisor-receipt.json
```

小型和中型任务优先使用 `source.patch`。只有 patch 上下文不足时才使用 `source-files.zip`。zip 必须只包含必要文件，默认不要打包整个仓库。

用下面命令校验可机器检查的控制文件：

```powershell
python tools\validate_chatgpt_web_manual_assist.py .tmp\chatgpt-web\<task>\request.json
python tools\validate_chatgpt_web_manual_assist.py .tmp\chatgpt-web\<task>\response\response.json
python tools\validate_chatgpt_web_manual_assist.py .tmp\chatgpt-web\<task>\local-supervisor-receipt.json
```

## Request Packet Contract

request packet 描述准备发送给 ChatGPT Web 的内容。

```json
{
  "packet_type": "chatgpt_web_request",
  "packet_id": "cgw_req_20260527_001",
  "task_id": "task_001",
  "run_id": "run_001",
  "channel": "chatgpt_web_manual",
  "purpose": "implementation_draft",
  "created_at": "2026-05-27T10:00:00+08:00",
  "redaction": {
    "status": "confirmed",
    "excluded": ["secrets", "cookies", "session files", "private customer data"]
  },
  "inputs": [
    {
      "name": "context",
      "path": ".tmp/chatgpt-web/task_001-1/context.md",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_class": "task_context",
      "contains_secrets": false
    }
  ],
  "output_contract": {
    "required_artifacts": ["changes.patch", "report.md", "verification_notes"],
    "forbidden_outputs": ["plaintext secrets", "claims without evidence"]
  },
  "verification": {
    "local_supervisor_required": true,
    "commands": ["python -m unittest"]
  },
  "operator_actions": [
    "Create or open a private ChatGPT Project for this task. The default local alias is harness-dev-test.",
    "Confirm the project is not shared beyond intended collaborators.",
    "Upload only the listed inputs."
  ]
}
```

## Response Packet Contract

response packet 描述 ChatGPT Web 返回了什么。它不是工作正确性的证明。

```json
{
  "packet_type": "chatgpt_web_response",
  "packet_id": "cgw_resp_20260527_001",
  "request_packet_id": "cgw_req_20260527_001",
  "task_id": "task_001",
  "run_id": "run_001",
  "channel": "chatgpt_web_manual",
  "producer": "chatgpt_web",
  "artifacts": [
    {
      "name": "changes",
      "path": ".tmp/chatgpt-web/task_001-1/response/changes.patch",
      "sha256": "<LOCAL_SUPERVISOR_TO_FILL>",
      "type": "patch"
    }
  ],
  "self_reported_verification": [
    "Reviewed requirements against provided context."
  ],
  "limitations": [
    "No local tests were run inside ChatGPT Web."
  ]
}
```

## Local Supervisor Receipt Contract

本机 Codex 必须在使用输出前生成 supervisor receipt。

```json
{
  "packet_type": "local_supervisor_receipt",
  "packet_id": "cgw_receipt_20260527_001",
  "request_packet_id": "cgw_req_20260527_001",
  "response_packet_id": "cgw_resp_20260527_001",
  "task_id": "task_001",
  "run_id": "run_001",
  "local_gate_status": "passed",
  "checks": [
    {
      "name": "unit tests",
      "level": "L1",
      "status": "passed",
      "command": "python -m unittest",
      "exit_code": 0
    }
  ],
  "accepted_artifacts": [
    ".tmp/chatgpt-web/task_001-1/response/changes.patch"
  ],
  "known_risks": []
}
```

只有所有 check 都通过且 `exit_code == 0` 时，`local_gate_status == "passed"` 才有效。

## 操作流程

### 1. 判断是否使用 ChatGPT Web

适合使用的情况：

- 需要第二个模型视角来改进设计或 patch
- 用户明确希望最终报告由 ChatGPT Web 起草，便于阅读
- 任务适合在浏览器 project 中放文件和说明
- 没有可用或合适的 API executor

不适合使用的情况：

- 必须处理凭据、隐私数据或生产环境专属状态
- 任务必须完全自动化、可取消、可恢复、可审计
- 用户期望本地 Codex supervisor / reviewer 的 Harness Run Contract 语义
- 本机 supervisor 不能独立验证结果

### 2. 构造最小上下文

只准备 ChatGPT Web 真正需要的内容：

- task objective
- in-scope 和 out-of-scope path
- 相关文件或 diff
- coding style constraints
- expected output artifacts
- local verification commands
- known blocked checks

默认不要上传完整仓库。优先上传 patch、选定文件或小型源码包。

如果用户要求“从 ChatGPT Web 作为任务入口”，不要让网页直接指定 `C:\...` 本地路径。改用 Apps SDK / MCP connector 的 workspace registry 路线：ChatGPT Web 先调用 `list_registered_workspaces` 选择本地已登记的 `workspace_id`，再通过 `list_workspace_files`、`read_workspace_file` 或 `create_workspace_bundle` 获取受限上下文。完整设计见 `docs/chatgpt-web-workload-and-entry-design.md`。这条路线仍然只提供候选上下文和候选 artifact，本地 Codex supervisor 仍是唯一验收方。

### 3. 脱敏并校验

上传前：

- 排除 `.env`、secret、token、cookie、session directory、private key、本地浏览器 profile 和生产数据
- 用 `<REDACTED_SECRET>` 之类占位符替代敏感值
- 校验 `request.json`
- 把 packet 放在 `.tmp/` 下，避免被提交

如果无法确认脱敏完成，停止，不上传。

### 4. 要求 ChatGPT Web 返回结构化输出

把 `prompt_groups/codex_harness/chatgpt_web_manual_assist.md` 作为稳定 project instruction 或首条消息。它要求 ChatGPT Web 返回 patch/report artifacts、limitations 和 response manifest。

### 5. 导入本地

把输出放回 `.tmp/chatgpt-web/<task>/response/`。校验 `response.json`。只在隔离 branch、worktree 或 scratch copy 中应用 patch。不要未经 review 直接应用到生产 workspace。

### 6. 本地验证

运行 request packet 中列出的命令以及项目专项检查。review diff 时检查：

- 需求覆盖
- 安全回归
- 意外密钥包含
- 无关重写
- generated/vendor 文件噪音
- 没有证据支持的声明

写入 `local-supervisor-receipt.json`。

### 7. 修复循环

如果本地验证失败，生成 repair packet，包含：

- 失败 check 名称和命令
- 已脱敏的错误摘录
- 被拒绝 artifact 的 hash
- 请求修复的边界

如果原始日志包含密钥或隐私数据，不要上传。

### 8. 通过 ChatGPT Web 起草最终报告

如果用户希望最终报告由 ChatGPT Web 起草，只上传：

- 已脱敏任务摘要
- 已接受 diff 摘要
- local supervisor receipt
- verification result
- known risks
- output format requirements

ChatGPT Web 可以起草 `report.md` 和 `report.html`。本机 Codex 必须核对报告与已接受 artifact 和 receipt 一致后才能交付。如果报告包含无证据声明，应本地修正或要求重新起草。

## 稳定提示词

ChatGPT Web 使用的提示词文件是：

```text
prompt_groups/codex_harness/chatgpt_web_manual_assist.md
```

可以把它放进 private ChatGPT Project instruction，或作为 ChatGPT Web thread 的首条消息。

## 失败模式

| 失败 | 本地 supervisor 动作 |
|---|---|
| 上传限制或文件类型不支持 | 缩小 packet，从 zip 切到 patch，或拆成更小 attempt。 |
| ChatGPT Web 只返回 prose | 再次要求 response packet 和具体 artifact 文件。 |
| Patch 无法应用 | 要求 rebase/repair packet，或手动抽取有用变更到本地 branch。 |
| 测试失败 | 返回包含已脱敏失败证据的 repair packet。 |
| 输出包含密钥 | 删除本地副本，不提交；如有真实泄露则轮换密钥并记录 incident。 |
| 报告与 receipt 冲突 | 拒绝报告，并从本地 receipt 重新生成。 |

## 治理

这个工作流是可复用 harness 资产。`AGENTS.md` 保持轻量；详细流程放在本文档，并通过 tooling inventory 暴露。未来如果增加真正的 ChatGPT API-backed executor，必须作为单独 adapter 使用 Harness Run Contract。不要把这个人工流程变成隐藏的程序化浏览器自动化路径。

## 参考

- OpenAI Help Center, File Uploads FAQ: https://help.openai.com/en/articles/8555545-file-uploads-faq
- OpenAI Help Center, Projects in ChatGPT: https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt
- OpenAI privacy controls overview: https://openai.com/index/how-chatgpt-protects-privacy/
