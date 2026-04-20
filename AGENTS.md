# AGENTS.md: Harness Operating Notes

## Scope

- This file is for stable, cross-project harness guidance.
- Project-specific policy belongs in the nearest repo `AGENTS.md`, not here.
- Runtime switches such as hooks, models, permissions, and feature flags belong in harness config files, not in this document.

## Tooling

- Check relevant skills first.
- Prefer the smallest set of high-signal tools, MCPs, and existing repo scripts that can answer the task.
- Do not fan out all tools by default; add evidence sources only when they change decision quality.
- Routine, reversible tool calls can proceed without confirmation. Destructive or cross-project changes need extra care.

## Decomposition

- For multi-step work, keep a persistent plan and progress trail in the project workspace when appropriate.
- Use parallel tool calls for independent reads, checks, and lookups.
- Use multi-agent or sub-agent execution only when the current harness supports it and the task materially benefits from delegation.

## Recovery

- On failure, change the hypothesis, evidence source, or execution path before retrying.
- Keep status updates short, concrete, and tied to new evidence.

--- project-doc ---

# AGENTS.md: Harness Operating Notes

## Scope

- This file is for stable, cross-project harness guidance.
- Project-specific policy belongs in the nearest repo `AGENTS.md`, not here.
- Runtime switches such as hooks, models, permissions, and feature flags belong in harness config files, not in this document.

## Tooling

- Check relevant skills first.
- Prefer the smallest set of high-signal tools, MCPs, and existing repo scripts that can answer the task.
- Do not fan out all tools by default; add evidence sources only when they change decision quality.
- Routine, reversible tool calls can proceed without confirmation. Destructive or cross-project changes need extra care.

## Decomposition

- For multi-step work, keep a persistent plan and progress trail in the project workspace when appropriate.
- Use parallel tool calls for independent reads, checks, and lookups.
- Use multi-agent or sub-agent execution only when the current harness supports it and the task materially benefits from delegation.

## Recovery

- On failure, change the hypothesis, evidence source, or execution path before retrying.
- Keep status updates short, concrete, and tied to new evidence.

--- project-doc ---

# AGENTS.md

`proxy-platform` 是统一入口薄平台壳仓库，不是新的控制面内核，也不是私有 inventory/secrets 真相源。

## Scope

- 本仓库负责统一 CLI / 未来 Web 工作台 / 编排层 / manifest / 平台级文档治理。
- 本仓库负责平台状态模型：主机登记册、观测回报、订阅派生与后续 job schema 的统一定义。
- 本仓库可以引用下游仓库，但不应复制它们的业务内核与私有真相内容。
- 下游仓库各自的实现细节、私有 secrets、运行时状态仍以原仓库为准。
- `/workspaces/proxy-platform/repos/` 下的是权威工作树。
- `/workspaces/proxy-platform/archive/` 下的是分析副本、历史快照和临时材料，不是源码真相源。

## Hard Boundaries

- 不在本仓库提交 `Proxy_ops_private` 的真实 secrets、inventory、生成产物。
- 不在本仓库重写 `CliProxy-control-plane` 的 `/v1` 网关和 worker southbound 逻辑。
- 不在本仓库直接实现 destructive 远端写操作，除非先有 dry-run、审计日志和明确的 job schema。
- 不把订阅文本、页面列表或临时脚本输出当成原始真相；它们只能是派生结果。
- 远端 worker/oauth quota 的权威真相继续留在 `cliproxy-control-plane`；`proxy-platform` 只能做只读集成展示。
- `remote_browser` 在本阶段只作为可选 provider 插槽，不默认进入核心主链工作流。
- `webchat-openai-runtime` 只作为可选 provider runtime 纳管，不得被写成新的平台控制面、帐号池控制台或私有真相源。

## Delivery Workflow

- 先写计划，再写失败测试，再写最小实现。
- 新命令必须先有帮助文案与可验证输出，再扩展副作用。
- 任何平台级决策都要同步写入 `docs/adr/`。
- 任何新增 adapter 或 command 都必须补最小测试。
- 涉及仓库边界调整时，先做 ownership review，再决定代码落点。
- 新增或修改 `webchat-openai-runtime` 这种运行时仓库时，必须同步更新 manifest、ADR、README、agent governance、review checklist 和最小 acceptance 证据。

## Documentation Contract

- `README.md` 是用户入口。
- `docs/adr/` 记录架构决策。
- `docs/agent-governance/project/` 记录平台级 agent/harness 解释。
- `docs/review-checklists/` 记录人工与 agent 评审清单。

## Review Focus

- 是否保持薄平台壳边界，没有滑向“第二控制面”。
- 是否保护 private/public 边界。
- 是否把复杂性收敛到 manifest、adapter、job schema，而不是散落在 README 和人工步骤里。
- 是否把共享平台判断逻辑留在 `proxy-platform`，而不是散回 `remote_proxy` 或 `Proxy_ops_private`。
- 是否把 worker/oauth quota 真相继续留在 `cliproxy-control-plane`，而不是在 `proxy-platform` 里复制一套控制面逻辑。
- 是否把浏览器会话执行复杂性留在 `webchat-openai-runtime`，而不是回流到 `proxy-platform` 根仓。

## JavaScript REPL (Node)

- Use `js_repl` for Node-backed JavaScript with top-level await in a persistent kernel.
- `js_repl` is a freeform/custom tool. Direct `js_repl` calls must send raw JavaScript tool input (optionally with first-line `// codex-js-repl: timeout_ms=15000`). Do not wrap code in JSON (for example `{"code":"..."}`), quotes, or markdown code fences.
- Helpers: `codex.cwd`, `codex.homeDir`, `codex.tmpDir`, `codex.tool(name, args?)`, and `codex.emitImage(imageLike)`.
- `codex.tool` executes a normal tool call and resolves to the raw tool output object. Use it for shell and non-shell tools alike. Nested tool outputs stay inside JavaScript unless you emit them explicitly.
- `codex.emitImage(...)` adds one image to the outer `js_repl` function output each time you call it, so you can call it multiple times to emit multiple images. It accepts a data URL, a single `input_image` item, an object like `{ bytes, mimeType }`, or a raw tool response object with exactly one image and no text. It rejects mixed text-and-image content.
- `codex.tool(...)` and `codex.emitImage(...)` keep stable helper identities across cells. Saved references and persisted objects can reuse them in later cells, but async callbacks that fire after a cell finishes still fail because no exec is active.
- Request full-resolution image processing with `detail: "original"` only when the `view_image` tool schema includes a `detail` argument. The same availability applies to `codex.emitImage(...)`: if `view_image.detail` is present, you may also pass `detail: "original"` there. Use this when high-fidelity image perception or precise localization is needed, especially for CUA agents.
- Example of sharing an in-memory Playwright screenshot: `await codex.emitImage({ bytes: await page.screenshot({ type: "jpeg", quality: 85 }), mimeType: "image/jpeg", detail: "original" })`.
- Example of sharing a local image tool result: `await codex.emitImage(codex.tool("view_image", { path: "/absolute/path", detail: "original" }))`.
- When encoding an image to send with `codex.emitImage(...)` or `view_image`, prefer JPEG at about 85 quality when lossy compression is acceptable; use PNG when transparency or lossless detail matters. Smaller uploads are faster and less likely to hit size limits.
- Top-level bindings persist across cells. If a cell throws, prior bindings remain available and bindings that finished initializing before the throw often remain usable in later cells. For code you plan to reuse across cells, prefer declaring or assigning it in direct top-level statements before operations that might throw. If you hit `SyntaxError: Identifier 'x' has already been declared`, first reuse the existing binding, reassign a previously declared `let`, or pick a new descriptive name. Use `{ ... }` only for a short temporary block when you specifically need local scratch names; do not wrap an entire cell in block scope if you want those names reusable later. Reset the kernel with `js_repl_reset` only when you need a clean state.
- Top-level static import declarations (for example `import x from "./file.js"`) are currently unsupported in `js_repl`; use dynamic imports with `await import("pkg")`, `await import("./file.js")`, or `await import("/abs/path/file.mjs")` instead. Imported local files must be ESM `.js`/`.mjs` files and run in the same REPL VM context. Bare package imports always resolve from REPL-global search roots (`CODEX_JS_REPL_NODE_MODULE_DIRS`, then cwd), not relative to the imported file location. Local files may statically import only other local relative/absolute/`file://` `.js`/`.mjs` files; package and builtin imports from local files must stay dynamic. `import.meta.resolve()` returns importable strings such as `file://...`, bare package names, and `node:...` specifiers. Local file modules reload between execs, while top-level bindings persist until `js_repl_reset`.
- Avoid direct access to `process.stdout` / `process.stderr` / `process.stdin`; it can corrupt the JSON line protocol. Use `console.log`, `codex.tool(...)`, and `codex.emitImage(...)`.

Files called AGENTS.md commonly appear in many places inside a container - at "/", in "~", deep within git repositories, or in any other directory; their location is not limited to version-controlled folders.

Their purpose is to pass along human guidance to you, the agent. Such guidance can include coding standards, explanations of the project layout, steps for building or testing, and even wording that must accompany a GitHub pull-request description produced by the agent; all of it is to be followed.

Each AGENTS.md governs the entire directory that contains it and every child directory beneath that point. Whenever you change a file, you have to comply with every AGENTS.md whose scope covers that file. Naming conventions, stylistic rules and similar directives are restricted to the code that falls inside that scope unless the document explicitly states otherwise.

When two AGENTS.md files disagree, the one located deeper in the directory structure overrides the higher-level file, while instructions given directly in the prompt by the system, developer, or user outrank any AGENTS.md content.

## JavaScript REPL (Node)

- Use `js_repl` for Node-backed JavaScript with top-level await in a persistent kernel.
- `js_repl` is a freeform/custom tool. Direct `js_repl` calls must send raw JavaScript tool input (optionally with first-line `// codex-js-repl: timeout_ms=15000`). Do not wrap code in JSON (for example `{"code":"..."}`), quotes, or markdown code fences.
- Helpers: `codex.cwd`, `codex.homeDir`, `codex.tmpDir`, `codex.tool(name, args?)`, and `codex.emitImage(imageLike)`.
- `codex.tool` executes a normal tool call and resolves to the raw tool output object. Use it for shell and non-shell tools alike. Nested tool outputs stay inside JavaScript unless you emit them explicitly.
- `codex.emitImage(...)` adds one image to the outer `js_repl` function output each time you call it, so you can call it multiple times to emit multiple images. It accepts a data URL, a single `input_image` item, an object like `{ bytes, mimeType }`, or a raw tool response object with exactly one image and no text. It rejects mixed text-and-image content.
- `codex.tool(...)` and `codex.emitImage(...)` keep stable helper identities across cells. Saved references and persisted objects can reuse them in later cells, but async callbacks that fire after a cell finishes still fail because no exec is active.
- Request full-resolution image processing with `detail: "original"` only when the `view_image` tool schema includes a `detail` argument. The same availability applies to `codex.emitImage(...)`: if `view_image.detail` is present, you may also pass `detail: "original"` there. Use this when high-fidelity image perception or precise localization is needed, especially for CUA agents.
- Example of sharing an in-memory Playwright screenshot: `await codex.emitImage({ bytes: await page.screenshot({ type: "jpeg", quality: 85 }), mimeType: "image/jpeg", detail: "original" })`.
- Example of sharing a local image tool result: `await codex.emitImage(codex.tool("view_image", { path: "/absolute/path", detail: "original" }))`.
- When encoding an image to send with `codex.emitImage(...)` or `view_image`, prefer JPEG at about 85 quality when lossy compression is acceptable; use PNG when transparency or lossless detail matters. Smaller uploads are faster and less likely to hit size limits.
- Top-level bindings persist across cells. If a cell throws, prior bindings remain available and bindings that finished initializing before the throw often remain usable in later cells. For code you plan to reuse across cells, prefer declaring or assigning it in direct top-level statements before operations that might throw. If you hit `SyntaxError: Identifier 'x' has already been declared`, first reuse the existing binding, reassign a previously declared `let`, or pick a new descriptive name. Use `{ ... }` only for a short temporary block when you specifically need local scratch names; do not wrap an entire cell in block scope if you want those names reusable later. Reset the kernel with `js_repl_reset` only when you need a clean state.
- Top-level static import declarations (for example `import x from "./file.js"`) are currently unsupported in `js_repl`; use dynamic imports with `await import("pkg")`, `await import("./file.js")`, or `await import("/abs/path/file.mjs")` instead. Imported local files must be ESM `.js`/`.mjs` files and run in the same REPL VM context. Bare package imports always resolve from REPL-global search roots (`CODEX_JS_REPL_NODE_MODULE_DIRS`, then cwd), not relative to the imported file location. Local files may statically import only other local relative/absolute/`file://` `.js`/`.mjs` files; package and builtin imports from local files must stay dynamic. `import.meta.resolve()` returns importable strings such as `file://...`, bare package names, and `node:...` specifiers. Local file modules reload between execs, while top-level bindings persist until `js_repl_reset`.
- Avoid direct access to `process.stdout` / `process.stderr` / `process.stdin`; it can corrupt the JSON line protocol. Use `console.log`, `codex.tool(...)`, and `codex.emitImage(...)`.
