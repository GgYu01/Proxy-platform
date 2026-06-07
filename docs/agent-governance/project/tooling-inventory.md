# Agent Tooling Inventory

生成日期：2026-05-30

## 目的

- 记录当前项目可直接调用的 harness tool / MCP / skills / CLI。
- 给后续 agent 一个稳定入口，减少重复摸索和上下文爆炸。
- 详细长文档放这里；根 `AGENTS.md` 只保留边界和入口。

## 本项目当前推荐优先级

1. 先用 `using-superpowers` 思路检查流程类 skills，再选最小可用技能集。
2. 代码和架构任务优先看 `planning-with-files`、`writing-plans`、`test-driven-development`、`verification-before-completion`。
3. 本仓运行时/浏览器/多 provider 相关调查优先看 `gstack`、`agent-browser`、`playwriter`、`context7`、`deepwiki`、`exa`、`sirchmunk`、`openspace`。
4. 大改动前优先找现有 repo-local skills 和 helper scripts，不先扩散到根仓逻辑。

## Harness Core Tools

- `apply_patch`
- `close_agent`
- `exec_command`
- `followup_task`
- `js_repl`
- `js_repl_reset`
- `list_agents`
- `list_mcp_resource_templates`
- `list_mcp_resources`
- `read_mcp_resource`
- `request_user_input`
- `send_message`
- `spawn_agent`
- `spawn_agents_on_csv`
- `update_plan`
- `view_image`
- `wait_agent`
- `write_stdin`

## MCP / Tool Namespaces

### `chrome_devtools`

- `mcp__chrome_devtools__click`
- `mcp__chrome_devtools__close_page`
- `mcp__chrome_devtools__drag`
- `mcp__chrome_devtools__emulate`
- `mcp__chrome_devtools__evaluate_script`
- `mcp__chrome_devtools__fill`
- `mcp__chrome_devtools__fill_form`
- `mcp__chrome_devtools__get_console_message`
- `mcp__chrome_devtools__get_network_request`
- `mcp__chrome_devtools__handle_dialog`
- `mcp__chrome_devtools__hover`
- `mcp__chrome_devtools__lighthouse_audit`
- `mcp__chrome_devtools__list_console_messages`
- `mcp__chrome_devtools__list_network_requests`
- `mcp__chrome_devtools__list_pages`
- `mcp__chrome_devtools__navigate_page`
- `mcp__chrome_devtools__new_page`
- `mcp__chrome_devtools__performance_analyze_insight`
- `mcp__chrome_devtools__performance_start_trace`
- `mcp__chrome_devtools__performance_stop_trace`
- `mcp__chrome_devtools__press_key`
- `mcp__chrome_devtools__resize_page`
- `mcp__chrome_devtools__select_page`
- `mcp__chrome_devtools__take_memory_snapshot`
- `mcp__chrome_devtools__take_screenshot`
- `mcp__chrome_devtools__take_snapshot`
- `mcp__chrome_devtools__type_text`
- `mcp__chrome_devtools__upload_file`
- `mcp__chrome_devtools__wait_for`

### `context7`

- `mcp__context7__query_docs`
- `mcp__context7__resolve_library_id`

### `context_engine`

- `mcp__context_engine__analyze_project`
- `mcp__context_engine__clear_cache`
- `mcp__context_engine__edit_multiple_files`
- `mcp__context_engine__get_file_relationships`
- `mcp__context_engine__get_project_context`
- `mcp__context_engine__get_project_stats`
- `mcp__context_engine__search_project`

### `deepwiki`

- `mcp__deepwiki__ask_question`
- `mcp__deepwiki__read_wiki_contents`
- `mcp__deepwiki__read_wiki_structure`

### `exa`

- `mcp__exa__web_fetch_exa`
- `mcp__exa__web_search_exa`

### `excel`

- `mcp__excel__excel_copy_sheet`
- `mcp__excel__excel_create_table`
- `mcp__excel__excel_describe_sheets`
- `mcp__excel__excel_format_range`
- `mcp__excel__excel_read_sheet`
- `mcp__excel__excel_write_to_sheet`

### `filesystem`

- `mcp__filesystem__create_directory`
- `mcp__filesystem__directory_tree`
- `mcp__filesystem__edit_file`
- `mcp__filesystem__get_file_info`
- `mcp__filesystem__list_allowed_directories`
- `mcp__filesystem__list_directory`
- `mcp__filesystem__list_directory_with_sizes`
- `mcp__filesystem__move_file`
- `mcp__filesystem__read_file`
- `mcp__filesystem__read_media_file`
- `mcp__filesystem__read_multiple_files`
- `mcp__filesystem__read_text_file`
- `mcp__filesystem__search_files`
- `mcp__filesystem__write_file`

### `openspace`

- `mcp__openspace__execute_task`
- `mcp__openspace__fix_skill`
- `mcp__openspace__search_skills`
- `mcp__openspace__upload_skill`

### `planning`

- `mcp__planning__sequentialthinking`

### `sequential_thinking`

- `mcp__sequential_thinking__sequentialthinking`

### `sirchmunk`

- `mcp__sirchmunk__sirchmunk_search`

### `strategic_thinking`

- `mcp__strategic_thinking__sequentialthinking`

## Global Skills

### `/home/devops/.codex/skills`

- 总数：`0`
- 技能：`(none discovered)`

### `/home/devops/.codex/superpowers/skills`

- 总数：`0`
- 技能：`(none discovered)`

### `/home/devops/.agents/skills`

- 总数：`0`
- 技能：`(none discovered)`

## Project-local Skills

### `C:\Users\Administration\CodexWorkspaces\proxy-platform\.agents\skills`

- 总数：`2`
- 技能：`cliproxyapi-usagekeeper-deployment-harness`, `project-tooling-governance`

### `C:\Users\Administration\CodexWorkspaces\proxy-platform\repos\webchat-openai-runtime\.agents\skills`

- 总数：`1`
- 技能：`public-codex-qwen-acceptance`

## Project Helper Scripts

### `repos\cliproxy-control-plane\scripts`

- `repos\cliproxy-control-plane\scripts\refresh_agent_governance_sources.sh`

### `repos\proxy_ops_private\scripts`

- `repos\proxy_ops_private\scripts\apply_infra_core_sidecar.sh`
- `repos\proxy_ops_private\scripts\apply_standalone_node.sh`
- `repos\proxy_ops_private\scripts\check_infra_core_egress_ip.sh`
- `repos\proxy_ops_private\scripts\check_infra_core_sidecar.sh`
- `repos\proxy_ops_private\scripts\check_standalone_node.sh`
- `repos\proxy_ops_private\scripts\deploy_infra_core_failover_controller.sh`
- `repos\proxy_ops_private\scripts\lib\standalone_node_common.sh`
- `repos\proxy_ops_private\scripts\publish_subscriptions_to_sea_host.sh`
- `repos\proxy_ops_private\scripts\reconcile_subscription_node_availability.py`
- `repos\proxy_ops_private\scripts\render_artifacts.py`
- `repos\proxy_ops_private\scripts\subscription_node_availability.py`

### `repos\remote_proxy\scripts`

- `repos\remote_proxy\scripts\audit_project.py`
- `repos\remote_proxy\scripts\cleanup.sh`
- `repos\remote_proxy\scripts\cliproxy_api_standalone_rollout.sh`
- `repos\remote_proxy\scripts\deploy.sh`
- `repos\remote_proxy\scripts\gen_config.py`
- `repos\remote_proxy\scripts\gen_keys.sh`
- `repos\remote_proxy\scripts\lib\common.sh`
- `repos\remote_proxy\scripts\lib\runtime_compat.sh`
- `repos\remote_proxy\scripts\manage_swap.sh`
- `repos\remote_proxy\scripts\service.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\audit_usage_accounting.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\deploy.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\diagnose_usage_pipeline.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\gen_config.py`
- `repos\remote_proxy\scripts\services\cliproxy_plus\install.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\install_combo.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\state_snapshot.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\switch_version.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\usage_backup.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\usage_restore.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\verify.sh`
- `repos\remote_proxy\scripts\services\cliproxy_plus\verify_combo.sh`
- `repos\remote_proxy\scripts\services\cpa_usage_keeper\deploy.sh`
- `repos\remote_proxy\scripts\services\cpa_usage_keeper\verify.sh`
- `repos\remote_proxy\scripts\setup_env.sh`
- `repos\remote_proxy\scripts\show_info.sh`
- `repos\remote_proxy\scripts\verify.sh`

### `repos\webchat-openai-runtime\scripts`

- `repos\webchat-openai-runtime\scripts\public_codex_tui_acceptance.sh`
- `repos\webchat-openai-runtime\scripts\public_codex_tui_launch.sh`
- `repos\webchat-openai-runtime\scripts\public_runtime_preflight.sh`

### `scripts`

- `scripts\probe_responses_chain.py`
- `scripts\refresh_agent_tooling_inventory.py`
- `scripts\responses_http_sse_compat_proxy.py`

## CLI Discovery

- `codex` -> `C:\Program Files\WindowsApps\OpenAI.Codex_26.527.3686.0_x64__2p2nqsd0c76g0\app\resources\codex.EXE`
- `python3` -> `C:\Users\Administration\AppData\Local\Microsoft\WindowsApps\python3.EXE`
- `pnpm` -> `C:\Users\Administration\AppData\Local\Programs\nodejs\node-v24.15.0\pnpm.CMD`
- `node` -> `C:\Users\Administration\AppData\Local\Programs\nodejs\node-v24.15.0\node.EXE`
- `git` -> `C:\Program Files\Git\cmd\git.EXE`
- `rg` -> `C:\Users\Administration\AppData\Local\OpenAI\Codex\bin\ada252862d154cdd\rg.EXE`
- `uv` -> `missing`
- `jq` -> `missing`
- `yq` -> `missing`
- `tmux` -> `missing`
- `curl` -> `C:\WINDOWS\system32\curl.EXE`
- `gh` -> `missing`

## Governance Sources

- OpenAI / Anthropic / Meta-Harness 来源索引：`docs/agent-governance/project/harness-sources.md`
- 项目治理说明：`docs/agent-governance/project/README.md`

## Refresh

- 刷新文档：`python3 scripts/refresh_agent_tooling_inventory.py`
- 当前脚本会实时扫描全局 skills、本项目 repo-local skills、repo helper scripts 和本机 CLI 路径。
- MCP / harness tool 列表来自 `tooling-inventory.snapshot.json` 的受控快照；当 harness tool 面变化时，需要用当前会话重新生成该快照，再运行本脚本。
