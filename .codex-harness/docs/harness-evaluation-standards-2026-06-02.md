# Harness 评测标准引入方案

日期：2026-06-02
状态：Active evaluation registry baseline
机器可读来源：`configs/harness-evaluation-registry.json`
校验入口：`tools/validate_harness_evaluation_registry.py`

## 结论

当前阶段先尽可能广地引入公开评测标准，但只引入为 **evaluation registry、benchmark mapping、golden task、scenario eval、metric framework、safety eval、watchlist**。这些资产只负责记录评测标准、指标、来源、适配理由和后续映射优先级，不安装第三方 benchmark runner，不接入 executor dispatch，也不触发自动修复。

评测结果只能进入 `VerificationReceipt`、`evaluation_run_receipt.json`、failure sample、comparison report 或 rework request。它不能绕过本地 Codex supervisor，也不能把 benchmark 分数直接当成交付通过。

本轮 registry 已覆盖 76 个公开标准或框架，分布在 23 个类别中：

- `adopt_now`：SWE-bench Verified / Lite、Terminal-Bench、EvalPlus HumanEval+ / MBPP+、OpenAI Evals、Inspect AI。
- `adopt_next`：SWE-bench Full / Multimodal、Multi-SWE-bench、SWE-bench Multilingual、SWE-PolyBench、MLE-bench、LiveCodeBench、BigCodeBench、MultiPL-E、GAIA、AgentBench、BrowseComp、BFCL、tau-bench、tau2/tau3-bench、AppWorld、AgentDojo、WebArena / VisualWebArena / BrowserGym、OSWorld、promptfoo、DeepEval agent metrics、OpenTelemetry GenAI semantic conventions、AgentHarm。
- `watch`：SWE-rebench、TerminalWorld、aider Polyglot、RepoBench、CrossCodeEval、CRUXEval、DS-1000、ToolBench、API-Bank、ToolSandbox、ToolEmu、AgentIF、WorkArena、Mind2Web 系列、WebVoyager、MiniWoB++、WebShop、WebLINX、Browserbase Harness、ClawBench、OSWorld-Verified、OSWorld-MCP、Windows Agent Arena、AndroidWorld、AndroidControl、MobileAgentBench、Mobile-Bench、SeeClick、ScreenSpot-Pro、Ragas、Phoenix、TruLens、Giskard、Braintrust、LM Evaluation Harness、NIST AI RMF、OWASP LLM Top 10、MITRE ATLAS、MLCommons AILuminate、CyberSecEval、Cybench、METR time horizon。

## 引入原则

- `adopt_now` 代表可以先登记并准备本地映射，不代表已经在当前 Windows 工作区跑通。
- `adopt_next` 代表适合作为下一批 benchmark mapping 或 scenario eval，但需要先准备环境、adapter、dataset 或评分约束。
- `watch` 代表需要继续跟踪，先不进入核心评分面板或本地交付门禁。
- 所有评测必须记录 `run_id`、dataset/task id、executor/provider、prompt/config digest、artifact hash、trace/log、score、blocked/skipped reason。
- 模型打分只能作为辅助信号。代码交付优先看真实测试、schema、static checks、SWE-bench/Terminal-Bench 这类可复现 verifier。
- 自动修复保持关闭。失败只进入 `run.rework_required`、failure sample、repair request 或 comparison report。

## 分层评测面板

### E0: Harness Contract 和 Receipt 质量

目标：验证主控流程是否诚实、可复盘、可比较。

引入：

- OpenAI Evals：需求分析、设计、receipt 完整度的 custom eval。
- Inspect AI：多轮工具使用、model-graded rubric、trace 记录。
- promptfoo：prompt group 和 provider 配置回归测试。
- DeepEval agent metrics：plan quality、plan adherence、tool correctness、step efficiency。
- OpenTelemetry GenAI semantic conventions：为 token、tool call、trace/span 建立可比较的记录语义。
- Phoenix、TruLens、Giskard、Braintrust、Ragas：作为观察名单，用于后续 context packaging、RAG 或实验管理评测。

映射层级：`R0`、`D0`、`L0`、`G0`。
通过条件：rubric、deterministic assertions、schema validator 和人工抽样一致，而不是“模型觉得好”。

### E1: 代码生成和轻量回归

目标：低成本发现 executor 的基本代码能力回归。

引入：

- EvalPlus HumanEval+ / MBPP+：立即作为 smoke/regression。
- LiveCodeBench：较新的代码题，降低污染风险。
- BigCodeBench：复杂 instruction 和函数调用。
- MultiPL-E：多语言函数级覆盖。
- DS-1000：数据科学代码任务，先观察。
- CRUXEval：代码执行推理和输入/输出预测，先观察。

映射层级：`L1`、`L2`、`G0`。
限制：这些不是仓库级交付证明，不能证明 merge、workspace packaging、debug bundle、receipt gate。

### E2: 仓库级软件工程

目标：评估真实 issue-to-patch、repo navigation、test-driven repair 能力。

引入：

- SWE-bench Lite：第一批低成本映射。
- SWE-bench Verified：第一批主评测。
- SWE-bench Full：稳定后扩展。
- SWE-bench Multimodal：涉及 UI/screenshot 时引入。
- Multi-SWE-bench、SWE-bench Multilingual、SWE-PolyBench：多语言仓库覆盖。
- SWE-rebench：作为去污染和新鲜 issue 方向观察。
- aider Polyglot Benchmark：观察 edit-focused 多语言 coding-agent 对比信号。
- RepoBench、CrossCodeEval：观察 context preparation 和跨文件代码理解能力。

映射层级：`L2`、`L3`、`G0`。
必须记录：instance id、base commit、patch hash、test command、Docker/build log、resolved status、cost、elapsed time、失败归因。

### E3: 终端、长任务和机器学习工程

目标：评估 shell、环境配置、长命令、实验流程和真实 verifier script 的执行能力。

引入：

- Terminal-Bench：立即登记为主基准。
- TerminalWorld：观察补充。
- TheAgentCompany：下一批 scenario eval，覆盖浏览器、代码、程序运行和同事沟通式工作流。
- MLE-bench：下一批 scenario eval，用于机器学习工程、实验执行和提交质量。
- METR time horizon：观察长期任务能力曲线方法。

映射层级：`L3`、`G0`。
必须记录：terminal transcript、command tail、environment image、test script、timeout、manual intervention、cost、elapsed time。

### E4: Tool Use、协议和用户交互

目标：评估 adapter/tool call 的正确性、约束遵守、状态变更和失败归因。

引入：

- BFCL：function calling / arguments。
- ToolBench、API-Bank、ToolSandbox：工具选择、多步 API 调用、状态追踪，先观察。
- AppWorld：下一批 scenario eval，适合 deterministic 多 app/API 工作流。
- tau-bench、tau2/tau3-bench：tool-agent-user 动态交互和 fault assignment。
- AgentIF：instruction following 和约束维度，先观察。

映射层级：`R0`、`D0`、`L2`、`L3`、`G0`。
这类评测尤其适合当前 harness 的 `Provider Adapter Registry`、`RunRequest` unknown-field 约束和工具调用 trace 质量。

### E5: Browser、Desktop、Mobile 和 Computer Use

目标：当 harness 涉及 ChatGPT Web、浏览器上传、GUI、IDE 或桌面操作时，评估真实 UI 行为。

引入：

- WebArena、VisualWebArena、BrowserGym / AgentLab：下一批 browser scenario eval。
- WorkArena、Mind2Web、Online-Mind2Web、Mind2Web 2、WebVoyager、MiniWoB++、WebShop、WebLINX、Browserbase Harness、ClawBench：观察名单。
- OSWorld：下一批 desktop scenario eval。
- OSWorld-Verified、OSWorld-MCP、Windows Agent Arena：观察名单。
- AndroidWorld、AndroidControl、MobileAgentBench、Mobile-Bench：移动端观察名单。
- SeeClick、ScreenSpot-Pro：GUI grounding 观察名单，用于屏幕定位能力。

映射层级：`L3`、`G0`。
必须记录：screenshot、action trace、video 或 trace artifact、environment reset、浏览器/OS 版本、credential boundary。Web/desktop/mobile 结果不能替代本地 repo 验证。

### E6: Safety、Security 和治理标准

目标：避免 agent 在工具执行、代码修改、网络/系统操作中跨过安全边界。

引入：

- AgentHarm：下一批 safety eval。
- AgentDojo：下一批 tool-use safety eval，覆盖 prompt injection 和 utility/security tradeoff。
- ToolEmu：观察 unsafe tool call 和工具风险判断。
- CyberSecEval、Cybench：观察安全能力和风险边界。
- NIST AI RMF、OWASP LLM Top 10、MITRE ATLAS、MLCommons AILuminate：治理和风险分类标准，作为评测映射参考，不直接作为本地交付证明。

映射层级：`R0`、`D0`、`L2`、`L3`、`G0`。
必须记录：拒绝是否正确、是否调用危险工具、是否泄露 secret、是否绕过 approval policy、残余风险是否记录。

## Registry 使用规则

`configs/harness-evaluation-registry.json` 是当前评测标准的事实来源。每个条目必须包含：

- `id`：稳定 snake_case id。
- `name`：公开名称。
- `category`：分组。
- `adoption`：`adopt_now`、`adopt_next`、`watch` 或 `defer`。
- `mode`：`public_benchmark_mapping`、`local_golden_task`、`scenario_eval`、`metric_framework`、`safety_eval` 或 `watchlist`。
- `levels`：映射到 `VerificationReceipt` 的 `R0/D0/L*/G0`。
- `metrics`：至少一个可记录指标。
- `sources`：公开来源 URL。
- `fit`：为什么适合当前 harness。

校验命令：

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\validate_harness_evaluation_registry.py configs\harness-evaluation-registry.json
```

## 当前不做的事

- 不安装或运行第三方 benchmark。
- 不把 benchmark runner 接进 executor dispatch。
- 不做自动修复。
- 不把模型打分当成交付通过。
- 不把 browser/desktop/mobile benchmark 当成当前 repo 代码交付证明。

## 下一步

1. 为 `adopt_now` 生成本地 `benchmark_mappings/` 和 `golden_tasks/` 目录结构。
2. 先接 EvalPlus smoke、SWE-bench Lite/Verified mapping、Terminal-Bench mapping。
3. 为每次 benchmark run 写 `evaluation_run_receipt.json`，字段对齐 `VerificationReceipt`。
4. 将失败样本落到 `failure_samples/`，只记录，不自动修复。
5. 后续再决定是否接入真实 benchmark runner。
