# ChatGPT Web 承担更多开发工作的入口设计

日期：2026-05-28
状态：可执行设计；配套工具已落地到 no-API connector

## 结论

要最大程度减少本地 agent 的生成工作，推荐采用“双入口、同一套本地门禁”的设计：

```text
入口 A：Codex-first，默认安全入口
  本地 Codex 选 workspace、脱敏、打包最小上下文
  -> ChatGPT Web 负责设计、读代码、写 patch/report
  -> 本地 Codex 只做导入、测试、验收、发布

入口 B：ChatGPT-Web-first，可选高交互入口
  用户先在 ChatGPT Web 提任务
  -> ChatGPT 通过 connector 查询本地预注册 workspace
  -> 只能读取白名单文本文件或生成待人工上传的 source bundle
  -> ChatGPT 产出候选 artifact
  -> 本地 Codex 验收
```

默认用入口 A。入口 B 只有在用户明确希望“从网页作为任务起始入口”时使用，并且必须通过本地 workspace registry 精确绑定工作区，不能让 ChatGPT Web 传入任意本地路径。

## ChatGPT Web 可以多承担哪些工作

可以交给 ChatGPT Web 的高价值工作：

- 需求拆解和方案比较：让它基于已上传的 README、设计文档、关键源码和测试说明，输出 implementation plan。
- 代码阅读和调用链梳理：让它分析有限源文件包，产出 dependency map、风险点和需要修改的文件清单。
- patch 起草：让它返回 `ARTIFACT: changes.patch` 或通过 connector 提交 `patch` artifact。
- 替换文件起草：让它为小文件生成完整 replacement file。
- 测试建议：让它起草测试用例和本地验证命令，但不能声称已在本地运行。
- 失败修复循环：Codex 把本地测试失败的脱敏摘要和 receipt 送回 ChatGPT Web，让它修 patch。
- 最终报告草稿：ChatGPT Web 起草用户可读报告，Codex 只核对报告与 receipt 是否一致。
- 文档整理：架构说明、ADR、runbook、变更摘要、review checklist。
- 多方案并行：同一个上下文包可以让 ChatGPT Web 生成 2-3 个候选 patch，Codex 只做 diff review 和验证。

不应该交给 ChatGPT Web 的工作：

- 读取或保存 secrets、cookie、session、token、SSH 私钥、生产数据。
- 直接运行本地 shell、git、部署、数据库写入或服务重启。
- 判定任务已经交付。
- 决定哪个本地目录是目标工作区。
- 长期保存未经审查的整仓源码快照。

## 为什么入口 A 仍是默认

Codex-first 的优势是 workspace 选择发生在本机：

1. Codex 知道当前 `cwd`、git 状态、AGENTS.md、忽略规则和本地测试入口。
2. Codex 可以先做脱敏、最小上下文选择和 manifest。
3. 用户上传到 ChatGPT Web 前能看到明确的文件清单和 hash。
4. Web 侧不会误拿到错误工作区，也不会被提示词诱导读取不该读的路径。

这条路线的本地工作量仍然很小：Codex 主要做选择上下文、导入输出、跑测试、写 receipt。真正耗脑的设计、阅读、patch 起草、报告整理都可以交给 ChatGPT Web。

## ChatGPT-Web-first 怎么准确获取本地工作区

如果从网页入口开始，不能让用户在 ChatGPT Web 里直接写：

```text
请读取 C:\Users\Administration\CodexWorkspaces\some-project
```

这不安全，也不可靠。正确做法是本地先维护一个 workspace registry：

```json
{
  "workspaces": [
    {
      "workspace_id": "harness_agent_approve",
      "display_name": "Codex harness architecture workspace",
      "root": "C:/Users/Administration/CodexWorkspaces/harness_agent_approve",
      "include_paths": [
        "AGENTS.md",
        "docs",
        "prompt_groups",
        "tools",
        "tests"
      ],
      "exclude_patterns": [
        ".tmp/**",
        ".git/**",
        ".env*",
        "node_modules/**",
        "secrets/**"
      ],
      "max_files": 240,
      "max_file_bytes": 300000,
      "max_total_bytes": 3000000
    }
  ]
}
```

本地文件位置：

```text
.tmp/chatgpt-app/workspace-registry.json
```

ChatGPT Web 只能通过 connector 做这些动作：

1. `list_registered_workspaces`：列出用户预注册的 workspace alias。
2. `create_assist_run`：创建 run，并绑定 `workspace_id`。
3. `list_workspace_files`：列出允许读取的安全文本文件。
4. `read_workspace_file`：读取单个允许文件。
5. `create_workspace_bundle`：生成 `source-files.zip` 和 `source-files-manifest.json`，等待用户人工上传到 ChatGPT Project。
6. `submit_candidate_artifact`：提交候选 patch/report。
7. `get_supervisor_receipt`：读取本地 Codex 验收结果。
8. `request_revision`：记录返工请求。

关键点：ChatGPT Web 不传本地绝对路径，只传 `workspace_id` 和相对路径。本地 connector 用 registry 决定真实目录。

## 入口 B 的实际流程

先启动 connector：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\chatgpt_app_no_api_connector.py serve --host 127.0.0.1 --port 8787
```

如果要让 ChatGPT Web 直接调用 connector，需要 HTTPS tunnel 或 Secure MCP Tunnel。没有公网 IP 不影响，使用 tunnel 即可；不想配 tunnel 时，用 Simprint 手动上传下载路线。

ChatGPT Web 里的起始提示词可以是：

```text
你现在通过 Codex Harness Supervisor Inbox No API connector 协助本机 Codex supervisor。

请先调用 list_registered_workspaces，列出可选工作区。
我选择 workspace_id 为 harness_agent_approve。
然后调用 create_assist_run，绑定该 workspace_id。
接着调用 list_workspace_files，只读取和任务相关的文件。
你负责起草 patch/report，但不要声称你运行了本地测试。
最终请通过 submit_candidate_artifact 提交 changes.patch 和 report.md。
本地 Codex supervisor 会运行测试并写 local-supervisor-receipt.json。
```

如果 ChatGPT 需要更多上下文，让它调用 `create_workspace_bundle`。该工具只在本地生成 zip 和 manifest，仍需用户人工确认后上传到 ChatGPT Project。

## 最小安全策略

必须保留这些边界：

- registry 是唯一工作区来源。
- connector 拒绝绝对路径、`..`、隐藏敏感目录、密钥字段名、疑似 secret 文本和大文件。
- connector 不运行 shell，不启动 Codex，不应用 patch，不提交 git，不部署。
- ChatGPT Web 返回的一切都是候选 artifact。
- 本地 Codex 的 `local-supervisor-receipt.json` 是唯一验收依据。
- 只有 receipt passed 后才能把 artifact 发布到项目目录或用户全局库。

## 推荐落地顺序

1. 继续保留 Codex-first 作为默认入口。
2. 对常用项目建立 `.tmp/chatgpt-app/workspace-registry.json`。
3. 在 ChatGPT Web connector 中暴露 workspace registry 和只读上下文工具。
4. 首轮只允许读文本文件和生成 bundle，不允许直接写项目文件。
5. 把失败 receipt 回传给 ChatGPT Web，形成返工循环。
6. 等流程稳定后，再做“多候选 patch 并行生成”和“最终报告草稿由 Web 生成”。

这个设计已经把本地 Codex 压缩成 supervisor：它不承担主要开发推理，只承担上下文裁剪、边界执行、验收和交付判定。

## Web 主执行自动化闭环

当前已落地一个更接近目标形态的本地入口：

```text
tools/chatgpt_web_harness.py
```

它把本地 Codex 的职责压缩为五件事：

1. 从 workspace registry 找到目标工作区。
2. 生成 `source-files.zip`、`source-files-manifest.json`、`chatgpt-web-request.json`、`chatgpt-web-task-prompt.md`，并在 `upload/` 下复制一套带 `{run_id}--` 前缀的上传文件。
3. 导入 ChatGPT Web 返回的 `ARTIFACT:` blocks。
4. 校验 ChatGPT Web 返回的 `codex-execution-plan.json`，把其中的 serial / parallel work units 交给当前本地 Codex 主会话决定是否拉起 subagent、SDK agent 或人工串行执行。
5. 在目标 workspace 中应用 `changes.patch`，运行本地检查，写 `local-supervisor-receipt.json`。

## 当前闭环实现状态

用户期望的完整闭环可以拆成这些环节：

```text
source bundle
  -> analysis agent
  -> task decomposition, prompts, acceptance criteria
  -> execution agents
  -> local supervisor or reviewer approval
  -> accepted delivery
  -> failed evidence package back to analysis
```

当前状态如下：

| 环节 | 当前状态 | 已有证据 / 缺口 |
| --- | --- | --- |
| 初始子 agent 打包代码给分析 agent | 已实现 | `prepare-run` 生成 `source-files.zip`、`source-files-manifest.json`、`chatgpt-web-request.json`、`chatgpt-web-task-prompt.md` 和 `upload-manifest.json`，由用户上传给 ChatGPT Web。 |
| ChatGPT Web 继续已有会话做多轮分析 | 已实现主干 | 本地记录 `chatgpt_conversation_alias` 和 `chatgpt-web-conversation-index.json`，防止不同 run 混用同一 alias；`prepare-followup` 会复用上一轮 conversation alias，把本地 receipt、日志 tail、diff 等失败证据打包给同一 Web 会话继续追问。真实 conversation URL/ID 可在用户显式 opt-in 后保存到 `.tmp` 下的本地私有 adapter state；但它不会进入上传包、run contract、receipt 或 tracked assets。 |
| 使用不同分析 agent 或 Web 模型做任务拆分 | 部分实现 | `codex-execution-plan.json` 支持 Web 侧输出 `execution_units`、`dispatch_mode`、`depends_on`、`owned_paths` 和 `acceptance_checks`；provider selection 仍是计划/registry 级约束，真实 Web 模型选择由用户在 ChatGPT Web UI 确认。 |
| 生成提示词文件和验收标准 | 已实现 | dispatcher 会为 `codex-cli` backend 的每个 unit 写 `.tmp/chatgpt-web/<run_id>/agents/<unit_id>/prompt.md`；`acceptance_checks` 被校验并写入 dispatch context。 |
| 原始用户需求传给执行 agent，防止拆分后漂移 | 已实现 | execution unit 可带 `raw_user_requirements`，dispatcher 会把它写入 Codex agent prompt 的 `Original User Request Context` 段落。 |
| 串行 / 并行执行 | 已实现 | dispatcher 校验依赖图并生成 `dispatch_batches`；`manual` backend 只写 receipt，`codex-cli` backend 会按 serial batch 串行、parallel batch 并行启动本地 Codex CLI units。 |
| 执行 agent 完成后的审批 | 部分实现 | 本地 supervisor receipt 和 schema 的 review verdict 能表达 `accepted` / `rework_required` / `blocked`；但当前没有自动拉起独立 reviewer subagent 做二次审批的统一命令。 |
| 合格后反馈主控 agent | 已实现 | `local-supervisor-receipt.json` 是主控验收依据；只有 `local_gate_status = passed` 才能 publish / commit / push 相关 accepted artifacts。 |
| 不合格时打包日志、源码重新进入分析流程 | 已实现主干 | failed receipt、stdout/stderr tail、agent prompt、last-message 和 rollback 信息会落盘；`prepare-followup` 可读取 failed `local-supervisor-receipt.json`、日志和 diff，生成下一轮给同一 ChatGPT Web 会话的上传包和 prompt。 |
| ChatGPT Web 生成多个可下载文件 | 已实现文本导入 | 响应文本中的多个 `ARTIFACT: filename` blocks 会被拆成多个文件并写 `response.json`；`ARTIFACT: files/<relative-path>` 支持完整文件按目标相对路径进入 staging。对网页直接下载目录或 zip 的 manifest 校验入口仍是后续增强。 |

所以，当前已经具备“打包 -> Web 分析/拆分 -> 本地调度 -> 本地验收 -> 失败证据回流 -> receipt gate”的主干。剩余缺口主要是网页直接下载目录或 zip artifact 的结构化导入，而不是主控流程本身。

## 面向 GPT-5.5 Pro Web 多轮分析的优化方向

为了让 ChatGPT Web 高能力模型承担更多真实分析工作，同时保持本地主控可验证，下一阶段应把 Web output contract 扩展为一个 round-based packet：

```text
analysis-round/
  codex-execution-plan.json
  agent-prompts/<unit_id>.md
  acceptance-criteria.json
  changes.patch
  testing-guide.md
  report.md
  repair-notes.md
  response-manifest.json
```

推荐规则：

- `codex-execution-plan.json` 继续作为本地 dispatcher 的唯一任务编排输入。
- `agent-prompts/*.md` 保存 Web 为每个执行 agent 生成的完整 prompt；dispatcher 可以在校验后选择直接采用、合并或覆盖。
- `acceptance-criteria.json` 保存可机器校验的验收标准，避免只在自然语言报告里描述。
- `response-manifest.json` 记录每个下载文件的路径、sha256、类型、用途和是否 required。
- `repair-notes.md` 只在返工轮次中使用，引用本地 failed receipt、失败命令、日志 tail、被拒绝 artifact hash 和 rollback 状态。
- 同一个 `chatgpt_conversation_alias` 可以表达“继续同一 Web 会话”。如果用户想让本地 operator 直接复用真实 Web 会话，可以显式 opt-in，把真实 conversation URL/ID 保存为 `.tmp` 下的本地私有 adapter state；该 handle 不得写入上传包、response artifact、receipt、tracked docs 或模型可见 prompt。
- 本地已新增 `prepare-followup` 命令：读取 failed `local-supervisor-receipt.json`、日志和 diff，沿用同一个 `chatgpt_conversation_alias` 生成下一轮给 Web 的上传包和 prompt。
- 本地 importer 已支持 `ARTIFACT: files/<relative-path>` 完整文件产物。后续仍可新增 `import-response-dir` 或 `import-response-zip` 命令：接收 ChatGPT Web 下载的多文件目录或 zip，校验 `response-manifest.json`，再落到 `.tmp/chatgpt-web/<run_id>/response/`。

准备任务包：

```powershell
cd C:\Users\Administration\CodexWorkspaces\harness_agent_approve
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

& $python tools\chatgpt_web_harness.py prepare-run `
  --workspace-id harness_agent_approve `
  --run-id web_primary_task_001 `
  --chatgpt-project-alias harness-dev-test `
  --chatgpt-conversation-alias web-primary-task-001 `
  --objective "让 ChatGPT Web 作为主执行者，基于上传源码包起草 patch 和报告。" `
  --user-instruction-file .tmp\chatgpt-app-user-instructions\web_primary_task_001.md `
  --path docs/chatgpt-web-workload-and-entry-design.md `
  --path tools/chatgpt_web_harness.py
```

该命令会生成：

```text
.tmp/chatgpt-app/<run_id>/source-files.zip
.tmp/chatgpt-app/<run_id>/source-files-manifest.json
.tmp/chatgpt-app/<run_id>/chatgpt-web-request.json
.tmp/chatgpt-app/<run_id>/chatgpt-web-task-prompt.md
.tmp/chatgpt-app/<run_id>/upload-manifest.json
.tmp/chatgpt-app/<run_id>/upload/<run_id>--source-files.zip
.tmp/chatgpt-app/<run_id>/upload/<run_id>--source-files-manifest.json
.tmp/chatgpt-app/<run_id>/upload/<run_id>--chatgpt-web-request.json
```

`source-files.zip` 不是新建或伪造的 Git 仓库，也不是把目录名拼出来的假项目结构。它使用真实工作区相对路径保存允许上传的文件，并读取当前 dirty worktree 内容；`.git/`、历史对象、reflog、branch refs 和远程凭据不会上传。为了让 ChatGPT Web 了解本地基线，zip 会额外包含：

- `.chatgpt-harness/git-context.json`：当前工作区是否是 git worktree、当前分支、原始最新 `HEAD` commit、commit subject、dirty 状态，以及 `history_policy = metadata_only_no_git_directory`、`snapshot_commit_policy = metadata_only_preserve_original_head_reference`。它只提供上下文，不提供可执行 Git 仓库。
- `.chatgpt-harness/directory-structure.json`：允许打包范围内的真实相对目录关系清单。没有普通文件的空目录会以 zip directory entry 保留，便于 Web 容器按同一目录树解压。它不宣称包含完整仓库树，只描述本次被允许上传的裁剪子集。

ChatGPT Web 可以基于上传文件手写 unified diff，返回 `ARTIFACT: changes.patch`；也可以用 `ARTIFACT: files/<relative-path>` 返回完整替换文件。它不能把上传包当作 Git remote，也不能声称 Web 容器里的任何 Git 操作等价于本地提交；本地是否接受仍由 Codex 的 path/hash/secret 校验、`git apply --check`、测试和 `local-supervisor-receipt.json` 决定。

真实上传时只上传 `upload-manifest.json` 中列出的 `upload_files`。这些文件名带 `run_id` 前缀，用来降低 Project Sources 中旧包和新包混在一起的风险。ChatGPT Project sources 只是 ChatGPT 产品侧的持久文件上下文，不会自动同步本地 repo，也不会保存为可 push/pull 的代码库。

从 2026-05-30 起，harness 运行过程中的 prompt、request、manifest、receipt 和 execution plan 默认使用英文。只有用户显式传入的 `objective` / `user_instruction` 原文会保留原语言，避免本地 harness 擅自改写用户需求；最终给用户看的说明文档和汇报仍可用简体中文。

ChatGPT Web 必须返回 `codex-execution-plan.json`。该文件不是本地已执行结果，而是 Web 端模型给本地 Codex supervisor 的工作分解建议，典型字段包括：

- `dispatch_strategy`：例如 `serial_then_parallel`。
- `execution_units[]`：每个单元包含 `id`、`title`、`dispatch_mode`、`prompt`、`owned_paths`、`depends_on` 和 `expected_artifacts`。
- `acceptance_checks`：建议本地 Codex 在整合后执行的命令 argv。

本地可用以下入口校验 execution plan，并选择本地 dispatch backend。默认 backend 是 `manual`：

```powershell
& $python tools\chatgpt_web_execution_dispatcher.py `
  --workspace-root <target-workspace> `
  --response-dir <target-workspace>\.tmp\chatgpt-web\<run_id>\response `
  --run-id <run_id> `
  --backend manual
```

`manual` backend 只把 `execution_units` 校验为 dependency-safe 的 `serial` / `parallel` batches，并写 `codex-dispatch-receipt.json`。它不会启动模型、不会修改文件，也不会应用 patch；当前 Codex 主会话可以按 receipt 决定是否使用内置 subagent、SDK agent 或人工串行执行。

如果希望把 ChatGPT Web 给出的 execution plan 直接交给本地 Codex CLI unit 执行，可显式使用 `codex-cli` backend：

```powershell
& $python tools\chatgpt_web_execution_dispatcher.py `
  --workspace-root <target-workspace> `
  --response-dir <target-workspace>\.tmp\chatgpt-web\<run_id>\response `
  --run-id <run_id> `
  --backend codex-cli `
  --sandbox workspace-write
```

`codex-cli` backend 会按 dispatch batches 启动本地 `codex exec`：串行 batch 逐个执行；同一 parallel batch 中的 units 并发启动。每个 unit 都会写入：

- `.tmp/chatgpt-web/<run_id>/agents/<unit_id>/prompt.md`
- `.tmp/chatgpt-web/<run_id>/agents/<unit_id>/stdout.jsonl`
- `.tmp/chatgpt-web/<run_id>/agents/<unit_id>/stderr.txt`
- `.tmp/chatgpt-web/<run_id>/agents/<unit_id>/last-message.md`

`codex-dispatch-receipt.json` 会记录每个 unit 的 backend、exit code、命令、输出路径和 stdout/stderr tail；只要有 unit 失败，dispatch receipt 的 `local_gate_status` 会是 `failed`。这仍然不是交付验收：它只证明本地 backend 已按 Web execution plan 尝试执行，真实合入、测试、merge 和 push 仍必须等本地 Codex supervisor 完成 `git apply --check`、本地检查和 `local-supervisor-receipt.json` 后再执行。

`--upload-target` 默认是 `project_sources`，有两个值：

- `project_sources`：把 `upload-manifest.json` 中的 `project_sources_files` 手动上传到 ChatGPT Project sources / files。适合长期任务和多轮对话复用同一批安全上下文，默认 Project alias 是 `harness-dev-test`。
- `conversation`：把 `conversation_attachment_files` 只作为当前对话附件上传。适合一次性任务，避免污染 Project sources。

`--user-instruction` 和 `--user-instruction-file` 用来让 harness 获取用户对 ChatGPT Web 的附加指引。该指引会写入 `chatgpt-web-request.json`、`upload-manifest.json` 和 `chatgpt-web-task-prompt.md`，但仍会被本地敏感文本检查拒绝；不要在其中放 token、cookie、session、密码、私钥或真实账号凭据。

无论哪种模式，上传包和本地可追踪 artifact 只记录 `chatgpt_project_alias` 和 `chatgpt_conversation_alias` 这类用户可读标签，不记录真实 ChatGPT Project ID、conversation ID、share link、cookie、session 或 OAuth token。

为落实“一次本地 run 对应一个 ChatGPT Web conversation”，`prepare-run` 会在 storage root 写入 `chatgpt-web-conversation-index.json`。同一个 conversation alias 只能绑定同一个 `run_id`；不同 `run_id` 复用同一 alias 会被拒绝。该索引仍只保存用户可读 alias 和本地 run 信息，不保存 ChatGPT 内部 ID 或 URL。

如果要复用真实 ChatGPT Web 会话上下文，可以额外提供本地 handle 文件并显式 opt-in：

```powershell
Set-Content -LiteralPath .tmp\chatgpt-web\conversation-handle.txt -Value "https://chatgpt.com/c/<conversation-id>" -Encoding UTF8

& $python tools\chatgpt_web_harness.py prepare-run `
  --workspace-id harness_agent_approve `
  --objective "Continue the previous Web analysis round." `
  --chatgpt-conversation-alias web-primary-task-001 `
  --chatgpt-conversation-handle-file .tmp\chatgpt-web\conversation-handle.txt `
  --allow-private-conversation-handle `
  --private-conversation-handle-ttl-days 14
```

这个 handle 只会写到 `.tmp/chatgpt-app/private/chatgpt-web-conversation-handles.json` 这类本地未跟踪 adapter state，并带 `expires_at`。它的作用是帮本地 operator 打开/定位已有 Web 会话，不是交付证据，不会上传给 ChatGPT Web，也不会进入 `chatgpt-web-request.json`、`upload-manifest.json`、`local-supervisor-receipt.json` 或 Git 提交。

如果使用 Simprint ChatGPT Web，可以让本地桥接辅助上传和填 prompt：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py upload-files `
  --file-input-index 3 `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--source-files.zip `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--source-files-manifest.json `
  .tmp\chatgpt-app\<run_id>\upload\<run_id>--chatgpt-web-request.json

& $python tools\chatgpt_web_simprint_bridge.py fill-prompt `
  --text-file .tmp\chatgpt-app\<run_id>\chatgpt-web-task-prompt.md
```

用户仍需在网页里确认模型、文件和发送动作。ChatGPT Web 可以使用自己的文件分析/容器能力处理上传包，但不能声称本地测试已经通过。

注意：`tools/chatgpt_web_simprint_bridge.py upload-files` 只能辅助当前 ChatGPT 页面上的文件输入。默认不传 `--file-input-index` 时会使用第一个文件输入，通常更接近当前 composer 附件；在 Project Sources 页面上，应先确认目标输入框索引，再用 `--file-input-index <n>` 指向 sources/files 区域。它仍不能可靠证明文件已经持久进入 Project sources，也不能验证当前页面属于哪个 Project alias。需要 Project-source 持久上下文时，以 `upload-manifest.json` 的人工步骤为准，由用户在 ChatGPT Web UI 中确认 sources 区域已经包含本次 `{run_id}--source-files.zip`、manifest 和 request。

### Project Sources stale / mixed-run 停止规则

Project Sources 是较持久上下文，不会因为本地 run 结束而自动清理。每次上传前都要检查：

- `upload_files` 的文件名必须全部以当前 `{run_id}--` 开头。
- `upload-manifest.json.run_identity`、`chatgpt-web-task-prompt.md` 顶部的 run identity、`chatgpt-web-request.json` 和 `source-files-manifest.json` 中的 run/task/workspace/hash 必须一致。
- Project Sources 里如果仍有旧 run 的 `source-files.zip`、manifest 或 request，应先删除、忽略或明确不使用；不能把旧 sources 与当前 prompt 混合。
- 如果 ChatGPT Web 看到的 Project Sources、conversation attachments、request 或 prompt 属于不同 `run_id`，应停止起草 patch，只返回 `report.md` 和 `LIMITATIONS` 说明 mixed-run 输入。

上传前可离线验证 request 和上传清单：

```powershell
& $python tools\validate_chatgpt_web_manual_assist.py .tmp\chatgpt-app\<run_id>\chatgpt-web-request.json
& $python tools\validate_chatgpt_web_manual_assist.py .tmp\chatgpt-app\<run_id>\upload-manifest.json
```

ChatGPT Web 完成后，优先用桥接抽取最新回复：

```powershell
& $python tools\chatgpt_web_simprint_bridge.py extract-latest-response `
  --output .tmp\chatgpt-app\<run_id>\raw-response.txt
```

导入回复：

```powershell
& $python tools\chatgpt_web_harness.py import-web-artifacts `
  --run-id <run_id> `
  --raw-text-file .tmp\chatgpt-app\<run_id>\raw-response.txt
```

如果 ChatGPT Web 返回了 `codex-execution-plan.json`，先让本地 Codex supervisor 校验并记录 dispatch 分组：

```powershell
& $python tools\chatgpt_web_execution_dispatcher.py `
  --workspace-root <target-workspace> `
  --response-dir <target-workspace>\.tmp\chatgpt-web\<run_id>\response `
  --run-id <run_id> `
  --backend manual
```

如果要让本地 Codex CLI 自动承接这些 work units，把 `--backend manual` 改为 `--backend codex-cli`。dispatcher 会按 receipt 中的 `serial` / `parallel` batch 运行 Codex CLI units，并保存每个 unit 的 prompt、stdout、stderr 和 last message。无论使用哪种 backend，`codex-dispatch-receipt.json` 都不代表 merge/push 已发生，也不代表任务通过本地验收；它之后仍要执行 patch 应用、本地检查和 supervisor receipt gate。

应用 patch 并验收：

```powershell
$check = @($python, "-m", "unittest", "tests.test_executor_contract_tools") | ConvertTo-Json -Compress
Set-Content -LiteralPath .tmp\chatgpt-app\<run_id>\check.json -Value $check -Encoding UTF8

& $python tools\chatgpt_web_harness.py apply-and-verify `
  --run-id <run_id> `
  --check-json-file .tmp\chatgpt-app\<run_id>\check.json
```

`apply-and-verify` 会先 `git apply --check`，通过后才应用 patch；如果后续本地检查失败，默认会 `git apply -R` 回滚，并写 failed receipt。只有 receipt passed 才算符合预期。

如果 receipt 已通过，并且需要把这次 Web+Codex 协作结果落成真实 Git 提交或推送，使用本地 delivery gate，而不是直接 `git add .`：

```powershell
& $python tools\chatgpt_web_artifact_importer.py `
  --workspace-root <target-workspace> `
  commit-accepted `
  --receipt <target-workspace>\.tmp\chatgpt-web\<run_id>\local-supervisor-receipt.json `
  --message "Accept ChatGPT Web supervised changes"
```

`commit-accepted` 只会 stage `local-supervisor-receipt.json.accepted_worktree_paths` 中的真实 worktree 路径；`.tmp/` 证据目录不会被提交。若工作区还有未被 receipt 接受的脏文件，默认会拒绝提交；确实要保留这些无关脏改但不提交它们时，显式加 `--allow-dirty-unaccepted`。需要推送时，在 receipt 通过且本地 commit 成功后再加：

如果目标仓库没有配置 Git identity，`git commit` 会失败并停在提交前；在该目标仓库内配置 `git config user.name ...` 和 `git config user.email ...` 后重试即可，不要把账号 token、cookie 或私钥写进仓库。

```powershell
& $python tools\chatgpt_web_artifact_importer.py `
  --workspace-root <target-workspace> `
  commit-accepted `
  --receipt <target-workspace>\.tmp\chatgpt-web\<run_id>\local-supervisor-receipt.json `
  --message "Accept ChatGPT Web supervised changes" `
  --push `
  --remote origin `
  --branch <branch-name>
```

这条命令仍然只是本地 Git delivery gate：ChatGPT Project 不是 Git remote，ChatGPT Web 容器里的 `git commit` 也不是本地仓库提交。真正可合入、可推送的对象只能来自本地 receipt 通过后的 accepted worktree paths。

## Codex 会话 / ChatGPT Project / Web 对话关系

更完整的可运行 demo 见 `docs/chatgpt-web-project-conversation-demo.md` 和 `tools/chatgpt_web_project_conversation_demo.py`。

本项目把三者明确分层：

- Codex 本地会话：本地 supervisor 和最终验收方，负责打包、导入、应用 patch、运行测试和写 `local-supervisor-receipt.json`。
- ChatGPT Project：ChatGPT 产品侧的长期上下文容器，可以保存用户手动上传的文件、项目指令和相关对话，但不是本地 Git 仓库，也不是本地执行权限。
- ChatGPT Web conversation：单次 run/attempt 的工作面，用户在这里手动选择模型、确认上传和发送，ChatGPT Web 只产出候选 artifact。
- Project sources 与 conversation attachment 的差异：Project sources 是 ChatGPT 产品侧更持久的项目上下文；conversation attachment 只服务于当前对话。本 harness 可以生成两种上传清单，但不能代替用户完成或验证 ChatGPT Web 产品内的持久上传。

本地可追踪的 `relationship-map.json` 只允许保存这些安全字段：

- `run_id`、`attempt_id`、`workspace_id`。
- `codex_thread_ref`、`chatgpt_project_alias`、`chatgpt_conversation_alias` 等用户可读 label。
- 上传包、manifest、prompt、response、receipt 的本地路径和状态。
- `upload_target`、source bundle hash、文件数、总字节数，以及 stale Project-source bundle 的手动删除提醒。
- 本地 supervisor 的验收摘要。

这些可追踪 artifacts 禁止保存：

- ChatGPT cookie、session、localStorage、OAuth token、share link。
- 真实 ChatGPT Project ID、conversation ID、session ID 或可恢复控制柄。
- OpenAI API key、SSH private key、数据库密码、生产凭据。
- 会把 no-API workflow 误导成 API executor 的 `model`、`reasoning_effort`、`api_key` 字段。

这意味着“把本地代码传到 ChatGPT Project”应理解为“上传一个经脱敏和 manifest 约束的源代码包供当前 Web 产品分析”，而不是把 ChatGPT Project 当作项目库或远程执行器。

例外是用户显式 opt-in 的本地私有 adapter state：它可以在 `.tmp/` 下保存真实 conversation URL/ID，用于继续同一 Web 会话，但必须满足本地未跟踪、带 TTL、不上传、不进入 receipt、不进入 tracked docs、不包含 cookie/token/localStorage/share link。
