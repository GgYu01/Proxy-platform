# Codex-led Harness 开源生态调研

日期：2026-06-02
范围：开源 coding agent、多 agent 框架、评测 harness、协议/runtime 层
目标：判断当前 `Codex-led multi-agent harness` 是否已有相似开源实现，并给出可复用方案。

## 结论

目前没有看到一个开源项目完整覆盖本工作区 harness 的目标形态：本地 Codex supervisor 作为交付权威、稳定 `Harness Run Contract`、provider adapter registry、workspace 打包隔离、串并行调度、候选产物导入、本地验证 gate、receipt/trace/eval 沉淀、以及 ChatGPT Web / Cursor / Codex 等异构通道边界。

最接近的不是单个项目，而是四类项目的组合：

1. **代码执行型 agent**：OpenHands、SWE-agent / mini-SWE-agent、Cline、aider、Codex CLI、goose、opencode。它们能操作代码、终端、patch、测试或 IDE，但通常把自身产品当控制面，不提供 provider-neutral run contract 和本地 supervisor 交付 gate。
2. **多 agent 编排框架**：LangGraph、OpenAI Agents SDK、AutoGen / AG2、CrewAI、MetaGPT、ChatDev、CAMEL、AgentScope、Semantic Kernel / Microsoft Agent Framework。它们提供状态机、handoff、multi-agent conversation、human-in-the-loop、tracing 或 workflow graph，但不是面向真实仓库交付的完整 coding harness。
3. **评测和 benchmark harness**：SWE-bench、Terminal-Bench、OpenHands benchmarks、WebArena / BrowserGym、OSWorld、tau-bench / tau2-bench、OpenAI Evals、Inspect AI。它们最适合借鉴 golden tasks、Docker/VM sandbox、结果目录、trajectory、leaderboard、评分和失败样本沉淀。
4. **协议和 runtime 层**：ACP、MCP、A2A。它们分别解决 editor-agent、tool/context、agent-agent 通信，但都不应该替代 harness 自己的 run lifecycle 和 delivery gate。

建议路线：不要照搬 MetaGPT / ChatDev 的“虚拟软件公司”作为主架构，也不要把某个 coding agent 产品直接当 harness。更稳的方案是保留当前本地 supervisor + contract/gate 模型，把 OpenHands / Cline / SWE-agent / Codex CLI 视作可插拔 executor 参考，把 LangGraph / Agents SDK / AutoGen / CrewAI 的编排能力作为内部实现参考，把 SWE-bench / Terminal-Bench 的 evaluation harness 作为外部质量坐标。

## 当前 Harness 的对比维度

本报告按以下能力判断相似度：

| 编号 | 能力 | 本 harness 需要的含义 |
|---|---|---|
| H1 | 需求归一化 | 把自然语言目标转成 scope、acceptance criteria、risk、verification obligations。 |
| H2 | 架构与编排设计 | 产出架构、接口、dispatch graph、prompt assembly。 |
| H3 | 串并行执行 | 显式依赖、owned paths、merge order、rollback/rework 策略。 |
| H4 | Workspace 打包隔离 | dirty snapshot、context crop、source/debug bundle、redaction、artifact hash。 |
| H5 | Provider adapter | CodexSDK、Codex CLI、ChatGPT Web、Cursor 等只暴露能力和限制，不泄露协议状态。 |
| H6 | 代码执行 | 编辑、patch、shell、测试、日志、长进程监控。 |
| H7 | 验证 gate | schema/static/unit/integration/scenario/governance 分层，通过 receipt 证明。 |
| H8 | Observability | prompts、events、logs、artifact manifest、verification receipt、成本/耗时。 |
| H9 | Human gate | 对外上传、危险命令、untrusted patch、commit/push/deploy、弱验证交付。 |
| H10 | Evaluation | golden tasks、public benchmark 映射、失败样本、评分、对比报告。 |

## 最接近的代码执行型 Agent

### OpenHands

OpenHands 是当前最接近“完整 coding agent 平台”的开源项目之一。README 描述了 Software Agent SDK、CLI、Local GUI、REST API、cloud/enterprise 形态，并提到可在本地运行 agent、也可扩展到云端大量 agent；还关联 evaluation infrastructure。它对 H6、H8、H10 很强，对 H3/H4 也有可参考实现。

缺口：OpenHands 的控制面是自己的 agent/server/GUI/enterprise 体系，不是 provider-neutral run contract。它不能天然表达“ChatGPT Web 只是 candidate artifact channel、本地 Codex supervisor 才能交付”的边界。若复用，适合把 OpenHands 看作 executor backend 或参考实现，而不是替代 harness supervisor。

参考：<https://github.com/All-Hands-AI/OpenHands>

### SWE-agent / mini-SWE-agent

SWE-agent 以真实 GitHub repository issue 修复为核心，README 明确说它让模型自主使用工具修复真实仓库问题，并指出当前更多开发转向 mini-SWE-agent。它和 SWE-bench 生态强绑定，适合作为“任务 -> 工具执行 -> patch -> benchmark”的执行/评测参考。

缺口：它更像单 agent 或小型 agent loop，不负责跨 provider adapter registry、候选产物导入、人工 gate、长生命周期 receipts。它适合借鉴工具接口、issue-to-patch loop、SWE-bench 适配，而不是作为总控框架。

参考：<https://github.com/SWE-agent/SWE-agent>、<https://github.com/SWE-agent/mini-swe-agent>

### Cline

Cline 是和本 harness 思路高度相关的项目。README 描述了 IDE 和 terminal coding agent、CLI、parallel agents、human-in-the-loop approval、Plan/Act mode、MCP、checkpoints、project-specific rules、SDK、Kanban、多 agent teams、scheduled agents。它对 H2、H3、H6、H8、H9 很有参考价值。

缺口：Cline 的强项是 IDE/CLI 用户体验和自身 agent core。它没有天然把多个异构 provider 的输出降级成 candidate artifacts，再由一个独立本地 supervisor 做 verification receipt 和 delivery gate。它的 multi-agent team 很接近“编排”，但仍需要在 harness 层补 run contract、provider-neutral artifacts、scope/owned paths、merge/gate 规则。

参考：<https://github.com/cline/cline>

### aider

aider 是成熟的 terminal pair-programming agent。README 强调自动 commit、git diff/undo、lint/test、测试失败自动修复、以及 web chat copy/paste 工作流。它对 H6 和局部 H7 很强，尤其值得借鉴 git ergonomic、lint/test loop、Web chat 辅助的上下文往返。

缺口：aider 主要是单会话 pair-programming 工具，不是多 agent scheduler，也不提供 provider registry、receipt schema、artifact relay、public benchmark integration。

参考：<https://github.com/Aider-AI/aider>

### Codex CLI

OpenAI `codex` 仓库 README 把 Codex CLI 定义为本地运行的 coding agent，并区分本地 CLI 与 cloud-based Codex Web。它与当前工作区目标非常贴近：适合作为本地 executor 或 dispatcher backend。

缺口：Codex CLI 本身不是跨 provider harness；它是强 executor，不是完整的多 provider governance layer。当前 harness 应继续把它放在 adapter 后面。

参考：<https://github.com/openai/codex>

### goose

goose 是本机运行的通用 AI agent，覆盖 desktop app、CLI、API，用于 code、workflow、automation、data analysis。它适合作为“本地可嵌入 agent runtime / API”的参考。

缺口：它不是专门围绕真实仓库的 run contract、merge gate、benchmark receipt 构建，和当前 harness 的代码交付闭环仍有距离。

参考：<https://github.com/block/goose>、<https://github.com/aaif-goose/goose>

### opencode

opencode 是 terminal AI coding agent，README 中有 `build`、`plan` 和 `general` subagent 的区分。它适合参考 CLI/TUI、人机交互、计划/执行 agent 分工。

缺口：它更像单产品 coding agent，不是跨 provider supervisor 和 artifact governance layer。

参考：<https://github.com/sst/opencode>

### Continue

Continue 的 README 描述了 PR 上运行 agents 作为 GitHub status checks，每个 agent 是 repo 内 `.continue/checks/` 的 markdown 文件，绿色/红色结果可带 suggested diff。它不是完整实现 harness，但非常适合借鉴“repo-local agent check definition + PR gate + suggested diff”的治理方式。

缺口：Continue 更偏 CI/review/check，不覆盖完整需求分析、架构设计、执行修复、外部 assist 导入和本地交付 receipt。

参考：<https://github.com/continuedev/continue>

### Roo Code、Open Interpreter、GPT Engineer、smol developer、Mentat、AutoGPT

这些项目有局部参考价值：

- Roo Code：Cline 衍生生态，强调 MCP servers 和 custom modes，可参考模式/工具扩展。
- Open Interpreter：本地代码/终端执行和 computer interaction 思路有用，但不是仓库交付 harness。
- GPT Engineer / smol developer：更偏早期“从需求生成项目”或小型 developer agent，可作为历史形态。
- Mentat：代码编辑 agent 思路有参考价值，但生态热度和完整度弱于前面项目。
- AutoGPT：通用 autonomous agent 代表，适合参考长期任务和插件化，但不应作为 coding harness 主架构。

参考：<https://github.com/RooCodeInc/Roo-Code>、<https://github.com/OpenInterpreter/open-interpreter>、<https://github.com/gpt-engineer-org/gpt-engineer>、<https://github.com/smol-ai/developer>、<https://github.com/mentat-ai/mentat>、<https://github.com/Significant-Gravitas/AutoGPT>

## 多 Agent 编排框架

### LangGraph

LangGraph 是低层 stateful agent orchestration framework。README 明确强调 long-running stateful agents、durable execution、human-in-the-loop、memory、debugging/tracing、production deployment。它是当前 harness 状态机和 supervisor loop 的最佳通用框架参考之一。

缺口：LangGraph 不直接提供 coding-specific workspace packaging、patch merge、artifact manifest、verification receipt。它是内部实现框架候选，不是现成 coding harness。

参考：<https://github.com/langchain-ai/langgraph>

### OpenAI Agents SDK

OpenAI Agents SDK README 描述了 multi-agent workflows、agents configured with tools/guardrails/handoffs、sandbox agents、agents-as-tools、human-in-the-loop、sessions、tracing、MCP/hosted tools。它很适合实现 provider 内部编排、handoff、guardrail、trace。

缺口：它不是专门为真实代码仓库的多 executor merge/gate 设计；也不能替代本地 supervisor 对 ChatGPT Web / Cursor / Codex 的边界治理。

参考：<https://github.com/openai/openai-agents-python>、<https://github.com/openai/openai-agents-js>

### AutoGen / AG2 / Microsoft Agent Framework

AutoGen README 说明它用于创建可自主或与人协作的 multi-agent applications，并提示新用户迁移到 Microsoft Agent Framework；AG2 README 描述了多 agent cooperation、tool use、human-in-the-loop、group chat、nested chat、sequential chat、code execution。它们对 multi-agent conversation、role pattern、tool execution 很有参考价值。

缺口：这些框架默认抽象是 agent application，不是代码仓库交付系统。需要在 harness 层额外设计 workspace、merge、receipt、benchmark 和 provider authority。

参考：<https://github.com/microsoft/autogen>、<https://github.com/ag2ai/ag2>、<https://github.com/microsoft/semantic-kernel>、<https://github.com/microsoft/agent-framework>

### CrewAI

CrewAI README 定位为 multi-agent automation framework，强调 Crews、Flows、event-driven control、human review、tracing/observability、unified control plane。它适合参考 H2/H3/H8，尤其是“高层 Crew + 低层 Flow”的分层。

缺口：CrewAI 不专注于真实代码修改、测试、merge gate 和本地 repo receipt。它更像 workflow engine，不是 coding delivery authority。

参考：<https://github.com/crewAIInc/crewAI>

### MetaGPT

MetaGPT 是最像“需求 -> 产品经理/架构师/项目经理/工程师 -> 软件公司 SOP”的开源 multi-agent 软件开发框架之一。README 明确把 software company 作为 multi-agent system，角色包括 product managers、architects、project managers、engineers。

缺口：它的虚拟软件公司模型有启发，但容易把“角色聊天”误当工程控制。当前 harness 更需要 contract、workspace、verification 和 receipt，而不是继续堆角色。MetaGPT 可借鉴 SOP、文档产物、角色拆分，不宜作为主控。

参考：<https://github.com/geekan/MetaGPT>

### ChatDev

ChatDev 1.x 是 Virtual Software Company，README 描述 CEO、CTO、Programmer 等 agent 通过 specialized seminars 自动化软件生命周期，包括 design、coding、testing、documentation。它还提到 Human-Agent-Interaction、incremental development、DAG/MacNet、多 agent orchestration platform 等方向。

缺口：ChatDev 很接近概念验证，但它偏研究/演示和多 agent 对话拓扑，不提供本 harness 需要的 provider-neutral contract、真实仓库 dirty-state 治理、local supervisor delivery gate、public benchmark receipt。

参考：<https://github.com/OpenBMB/ChatDev>

### CAMEL、AgentScope

CAMEL 强调多 agent 大规模模拟、statefulness、环境交互、benchmark；AgentScope 2.0 强调 production-ready agent framework、MCP/A2A、message hub、多 agent orchestration、evaluation、OTel。它们适合参考大规模 agent coordination、message hub、observability 和 evaluation。

缺口：两者都不是专门为 code patch/merge/test/receipt 交付闭环设计。

参考：<https://github.com/camel-ai/camel>、<https://github.com/modelscope/agentscope>

## 评测与 Benchmark Harness

### SWE-bench

SWE-bench 是最应该接入的代码修复 benchmark。README 描述它用 GitHub 真实软件 issue 评估 LLM，使用 Docker 做 reproducible evaluations，提供 `swebench.harness.run_evaluation`，生成 build logs、evaluation logs 和 evaluation results。SWE-bench Verified 是由真实软件工程师确认可解的 500 问题子集。

对当前 harness 的启发：

- golden task 可用真实 issue + patch prediction 格式。
- evaluation receipt 应记录 dataset、instance id、image/build log、patch、test result、run id。
- 本地 harness 的 H7/H10 可用 SWE-bench 作为第一批 public benchmark 映射。

参考：<https://github.com/SWE-bench/SWE-bench>、<https://www.swebench.com/>

### Terminal-Bench

Terminal-Bench README 把项目定义为测试 AI agents 在真实 terminal environments 中处理端到端任务的 benchmark，并明确由 task dataset 和 execution harness 两部分组成。每个 task 包含 instruction、Docker environment、test script；harness 连接 language model 到 sandboxed terminal environment。

对当前 harness 的启发：

- 每个 harness eval task 应有明确 instruction、环境、验证脚本。
- debug bundle 应保留 terminal transcript、test output、artifact。
- 它适合验证“代码之外的终端运维任务”和长命令执行能力。

参考：<https://github.com/laude-institute/terminal-bench>、<https://www.tbench.ai/>

### OpenHands benchmarks

OpenHands 单独维护 benchmarks / evaluation infrastructure，适合调研 coding agent 如何规模化跑 SWE-bench 或其它工程任务。若后续要比较 Codex CLI、OpenHands、Cline、SWE-agent 同一批任务，OpenHands benchmarks 值得二次深入。

参考：<https://github.com/OpenHands/benchmarks>

### WebArena / BrowserGym

WebArena README 定义它为 self-hostable web environment for autonomous agents，并提供 end-to-end evaluation、trajectory、leaderboard、Docker/self-host environment。README 还提到 BrowserGym 支持 parallel experiments、集成多个 web navigation benchmarks、统一 leaderboard reporting。

对当前 harness 的启发：

- 如果 harness 未来包含浏览器操作、文档网页上传、Web UI 验证，WebArena / BrowserGym 的 environment reset、trajectory、parallel experiments 值得借鉴。
- 这些不是 coding harness 本体，但适合做 L3 scenario benchmark。

参考：<https://github.com/web-arena-x/webarena>、<https://github.com/ServiceNow/BrowserGym>

### OSWorld

OSWorld 是真实桌面/VM 环境的 multimodal agent benchmark。README 描述 VMware/VirtualBox/AWS 等环境、并行评估、results 中保存 screenshots、actions、video recordings、manual examination tool、public verified evaluation。它对 computer-use 类能力评估很有参考价值。

对当前 harness 的启发：

- 对桌面/浏览器/IDE 类 executor，不能只看文本结果，要保存屏幕、动作、视频、环境配置。
- public eval 需要披露 agent implementation 或足够报告，不能只报分数。

参考：<https://github.com/xlang-ai/OSWorld>、<https://os-world.github.io/>

### tau-bench / tau2-bench

tau-bench 模拟 user-agent-tool 互动，关注 domain-specific APIs 和 policy guidelines。README 还提到 fault assignment，用来判断 user、agent、environment 谁负责失败。当前仓库 README 指出旧任务已过时，应迁移到 tau2/tau3-bench。

对当前 harness 的启发：

- 测试失败不应只记 `failed`，还应分类：需求不清、agent 错、环境错、工具错、验证错。
- 适合借鉴多轮交互、工具调用和失败归因，不是代码修复主 benchmark。

参考：<https://github.com/sierra-research/tau-bench>、<https://github.com/sierra-research/tau2-bench>

### OpenAI Evals、Inspect AI

OpenAI Evals 和 Inspect AI 是通用评测框架。OpenAI Evals README 强调可评估 LLM 或 LLM-built systems，并可写 custom evals；Inspect AI README 强调 prompt engineering、tool usage、multi-turn dialog、model-graded evaluations、200+ pre-built evals。

对当前 harness 的启发：

- harness 内部可以用轻量 custom eval 评估需求分析质量、设计质量、receipt 完整度。
- 但 coding 交付成败仍应优先用真实测试、schema、SWE-bench/Terminal-Bench，而不是模型打分。

参考：<https://github.com/openai/evals>、<https://github.com/UKGovernmentBEIS/inspect_ai>

## 协议与 Runtime 层

### ACP

Agent Client Protocol README 明确它标准化 code editors 和 coding agents 之间的通信，当前 stable protocol version 为 `1`，wire compatibility 由 initialize 时交换的 `protocolVersion` 决定。

对当前 harness 的结论：ACP 适合作为 Cursor/Zed/IDE agent adapter 内部协议，但不应该成为 harness 的 run lifecycle。它解决 editor-client 会话，不解决 provider-neutral task contract、artifact receipt、delivery gate。

参考：<https://github.com/zed-industries/agent-client-protocol>、<https://agentclientprotocol.com/>

### MCP

MCP reference servers README 说明这些 server 展示如何给 LLM 安全、受控访问工具和数据源，并明确很多 reference server 是 educational examples，不是 production-ready solutions。

对当前 harness 的结论：MCP 是工具/context 协议，不是 executor lifecycle。它可以挂 Git、filesystem、browser、issue tracker、CI、document store，但不能替代 `RunRequest`、`RunEvent`、`VerificationReceipt`、`RunResult`。

参考：<https://github.com/modelcontextprotocol/servers>、<https://modelcontextprotocol.io/>

### A2A

A2A README 定义它为让 opaque agentic applications 通信和互操作的开放协议，可发现能力、安全协作长任务，并且不暴露内部状态、memory、tools。它还说明可和 MCP 互补，用于不同框架的 agent 协作。

对当前 harness 的结论：A2A 适合未来外部 agent 服务互操作，但它不应该替代本地 supervisor 的 gate。若未来有远程 executor，可以把 A2A 放进 adapter internals。

参考：<https://github.com/google/A2A>、<https://a2a-protocol.org/>

## 覆盖矩阵

| 项目/类别 | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 | H9 | H10 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| OpenHands | M | M | M | M | L | H | M | M | M | H | 最接近完整 coding agent 平台，可作 executor/backend 参考。 |
| Cline | M | H | H | M | M | H | M | H | H | L | 最接近 IDE/CLI 多 agent 操作体验和人工审批。 |
| SWE-agent / mini | L | M | L | M | L | H | H | M | L | H | 最适合 issue-to-patch 和 SWE-bench loop。 |
| aider | L | M | L | L | L | H | M | L | M | L | 最适合 terminal edit/test/git ergonomics。 |
| Codex CLI | M | M | L | M | L | H | M | M | M | L | 当前最自然本地 executor，但不是总控 harness。 |
| LangGraph | M | H | H | L | M | L | M | H | H | M | 可作 supervisor 状态机/持久执行参考。 |
| OpenAI Agents SDK | M | H | M | M | M | M | M | H | H | L | 可作 provider 内部 orchestration/handoff/tracing 参考。 |
| AutoGen / AG2 | M | H | M | M | M | M | M | M | H | M | 多 agent 对话和工具执行参考。 |
| CrewAI | M | H | H | L | M | L | M | H | M | M | workflow/flows/control-plane 参考。 |
| MetaGPT | H | H | M | L | L | M | M | M | L | L | SOP/角色拆分参考，不能替代工程 gate。 |
| ChatDev | H | H | M | L | L | M | M | M | M | L | 虚拟软件公司概念参考，生产治理不足。 |
| SWE-bench | L | L | L | H | L | M | H | H | L | H | 代码修复公开评测主基准。 |
| Terminal-Bench | L | L | L | H | L | M | H | H | L | H | 真实终端任务和 sandbox harness 参考。 |
| WebArena / BrowserGym | L | L | M | H | L | M | H | H | L | H | 浏览器/网页场景 eval 参考。 |
| OSWorld | L | L | M | H | L | M | H | H | M | H | 桌面/VM/computer-use eval 参考。 |
| ACP | L | L | L | L | H | M | L | L | L | L | editor-agent adapter protocol。 |
| MCP | L | L | L | L | H | M | L | L | L | L | tool/context protocol。 |
| A2A | L | M | M | L | H | L | L | M | M | L | future agent-agent interoperability。 |

标记：H = 高度覆盖，M = 部分覆盖，L = 低覆盖或只间接相关。

## 可复用架构方案

### 方案 A：现有 Harness 主控 + Codex CLI / SDK Executor

这是当前最稳路线。Supervisor 继续负责 `RunRequest`、workspace、dispatch、verification、receipt；Codex CLI / SDK 只作为 executor adapter。优点是边界最清晰，最容易在本工作区验证。缺点是短期多 provider 覆盖少。

适合当前阶段。

### 方案 B：引入 OpenHands 作为重型 Executor Backend

把 OpenHands 当可选 executor，用它的 agent server/SDK/CLI 执行某些 work unit，再由本地 supervisor 验证产物。优点是开源生态成熟，接近 cloud/local agent 平台。缺点是集成成本高，容易引入第二个控制面。

适合后续专项实验，不适合作为第一版核心。

### 方案 C：用 LangGraph / Agents SDK 实现 Supervisor 内部状态机

把 harness supervisor loop 建成显式 graph：prepare -> analyze -> design -> dispatch -> verify -> gate -> receipt。优点是 durable execution、human-in-loop、tracing 能力强。缺点是会把项目从脚本/validator 形态推进到框架依赖，当前可能过早。

适合当现有脚本状态机开始膨胀时引入。

### 方案 D：MetaGPT / ChatDev 风格角色流水线

需求分析、架构、项目经理、工程师、测试员角色分工与用户的五段流程表面非常像。优点是 prompt 和 SOP 容易写。缺点是若没有 contract/gate，会退化成角色聊天和生成文档，难以证明交付。

只建议借鉴角色和 SOP，不建议作为主控架构。

### 方案 E：Evaluation-first Harness

先把 SWE-bench Lite / Verified、Terminal-Bench、自定义 golden tasks 接入 receipt。优点是能快速形成客观质量坐标，避免自动修复 loop 空转。缺点是不能直接提升执行能力。

建议作为当前阶段的并行建设方向：先记录失败样本和评分，不做自动修复。

## 对 CursorSDK / ChatGPT Web / CodexSDK 的判断

- **CodexSDK / Codex CLI**：应作为第一批真实 executor 验证路径。Codex CLI 已有官方开源仓库可参考；SDK 能力需要以官方文档和本地 probe 为准。
- **ChatGPT Web**：只能是 candidate-artifact assist channel。它可以分析上传包、草拟设计、patch、测试建议，但不能直接 claim 本地验证或交付。
- **CursorSDK / Cursor CLI**：没有真实 Cursor 账号认证前，不应写成 verified executor。复用本机 Codex 的 OpenAI-compatible URL/key 最多能证明 generic model connectivity，不能证明 Cursor agent execution、Cursor UI/ACP/CLI 行为或账号授权。

## 建议的下一步

1. 保留当前 `Harness Run Contract` 和 provider registry，先不要换成任何外部框架的原生 task schema。
2. 选 3 个 executor 参考方向做最小 probe：`codex_cli`、OpenHands、SWE-agent / mini-SWE-agent。每个 probe 只验证一个小任务、一个 artifact manifest、一个 verification receipt。
3. 先做 evaluation 目录结构：`golden_tasks/`、`evaluation_runs/`、`failure_samples/`、`benchmark_mappings/`。第一批映射 SWE-bench Lite / Verified 和 Terminal-Bench。
4. 把 Cline 的 Plan/Act、approval、checkpoints、multi-agent teams、scheduled agents 作为 UX/control reference，但不要让 Cline 的产品状态进入 harness contract。
5. 如果 supervisor 状态机继续复杂化，再评估 LangGraph 或 OpenAI Agents SDK 作为内部实现层；不要在第一版为了“看起来多 agent”引入重框架。

## 调研证据与限制

本次调研读取了当前工作区 active harness 文档，并抓取/查阅了以下项目 README 或官方入口。GitHub 匿名 API 在中途触发 rate limit，所以星标等元数据不作为主证据；核心判断来自项目 README、官方文档入口和本工作区 contract 文档。

主要来源：

- OpenAI Codex CLI：<https://github.com/openai/codex>
- OpenAI Agents SDK Python：<https://github.com/openai/openai-agents-python>
- OpenAI Agents SDK JS：<https://github.com/openai/openai-agents-js>
- OpenHands：<https://github.com/All-Hands-AI/OpenHands>
- OpenHands Software Agent SDK：<https://github.com/OpenHands/software-agent-sdk>
- OpenHands benchmarks：<https://github.com/OpenHands/benchmarks>
- SWE-agent：<https://github.com/SWE-agent/SWE-agent>
- mini-SWE-agent：<https://github.com/SWE-agent/mini-swe-agent>
- aider：<https://github.com/Aider-AI/aider>
- Cline：<https://github.com/cline/cline>
- Roo Code：<https://github.com/RooCodeInc/Roo-Code>
- goose：<https://github.com/block/goose>
- opencode：<https://github.com/sst/opencode>
- Continue：<https://github.com/continuedev/continue>
- AutoGen：<https://github.com/microsoft/autogen>
- AG2：<https://github.com/ag2ai/ag2>
- CrewAI：<https://github.com/crewAIInc/crewAI>
- LangGraph：<https://github.com/langchain-ai/langgraph>
- MetaGPT：<https://github.com/geekan/MetaGPT>
- ChatDev：<https://github.com/OpenBMB/ChatDev>
- CAMEL：<https://github.com/camel-ai/camel>
- AgentScope：<https://github.com/modelscope/agentscope>
- Semantic Kernel：<https://github.com/microsoft/semantic-kernel>
- Microsoft Agent Framework：<https://github.com/microsoft/agent-framework>
- SWE-bench：<https://github.com/SWE-bench/SWE-bench>
- Terminal-Bench：<https://github.com/laude-institute/terminal-bench>
- WebArena：<https://github.com/web-arena-x/webarena>
- BrowserGym：<https://github.com/ServiceNow/BrowserGym>
- OSWorld：<https://github.com/xlang-ai/OSWorld>
- tau-bench：<https://github.com/sierra-research/tau-bench>
- tau2/tau3-bench：<https://github.com/sierra-research/tau2-bench>
- OpenAI Evals：<https://github.com/openai/evals>
- Inspect AI：<https://github.com/UKGovernmentBEIS/inspect_ai>
- ACP：<https://github.com/zed-industries/agent-client-protocol>
- MCP reference servers：<https://github.com/modelcontextprotocol/servers>
- A2A：<https://github.com/google/A2A>

本报告没有本地安装或执行这些第三方项目，因此不能证明它们在当前 Windows 工作区可运行。若后续进入实现阶段，需要对候选 executor 做独立 local probe，并把结果写成 blocked/passed receipt。
