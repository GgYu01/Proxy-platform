from __future__ import annotations

import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "repos" / "proxy_ops_private"
SCRIPT_PATH = PRIVATE_ROOT / "scripts" / "render_artifacts.py"

OPENAI_PROXY_DOMAIN_RULES = [
    "DOMAIN-SUFFIX,openai.com,PROXY",
    "DOMAIN-SUFFIX,chatgpt.com,PROXY",
    "DOMAIN-SUFFIX,oaistatic.com,PROXY",
    "DOMAIN-SUFFIX,oaiusercontent.com,PROXY",
    "DOMAIN-SUFFIX,oaistatsig.com,PROXY",
    "DOMAIN-SUFFIX,auth.openai.com,PROXY",
    "DOMAIN-SUFFIX,auth0.openai.com,PROXY",
    "DOMAIN-SUFFIX,cdn.openaimerge.com,PROXY",
]

OPENAI_APP_PROCESS_DIRECT_RULES = [
    r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\OpenAI\Codex\bin\*\codex.exe,DIRECT",
    r"PROCESS-PATH-WILDCARD,C:\Program Files\WindowsApps\OpenAI.Codex_*\app\*,DIRECT",
    r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT\*,DIRECT",
    r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT\*,DIRECT",
    r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT Atlas\*,DIRECT",
    r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT Atlas\*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Applications/ChatGPT.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Applications/ChatGPT Atlas.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Applications/Codex.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Users/*/Applications/ChatGPT.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Users/*/Applications/ChatGPT Atlas.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/Users/*/Applications/Codex.app/Contents/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/opt/chatgpt/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/usr/bin/chatgpt*,DIRECT",
    "PROCESS-PATH-WILDCARD,/opt/chatgpt-atlas/*,DIRECT",
    "PROCESS-PATH-WILDCARD,/usr/bin/chatgpt-atlas*,DIRECT",
    "PROCESS-PATH-WILDCARD,/usr/bin/chatgptatlas*,DIRECT",
    "PROCESS-PATH-WILDCARD,/opt/codex/*,DIRECT",
    "PROCESS-PATH,/usr/bin/codex,DIRECT",
]

FORBIDDEN_OPENAI_KEYWORD_RULES = [
    "DOMAIN-KEYWORD,openai",
    "DOMAIN-KEYWORD,codex",
    "DOMAIN-KEYWORD,openaiapi",
]


def load_render_artifacts_module():
    spec = importlib.util.spec_from_file_location("render_artifacts", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_private_fixture(tmp_path: Path, *, healthy_names: tuple[str, ...] = ("us_sea_bgp_01", "vmrack1", "dedirock")) -> Path:
    fixture_root = tmp_path / "proxy_ops_private"
    shutil.copytree(PRIVATE_ROOT / "inventory", fixture_root / "inventory")
    shutil.copytree(PRIVATE_ROOT / "secrets", fixture_root / "secrets")
    (fixture_root / "state").mkdir(parents=True)
    (fixture_root / "state" / "node_availability.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-06-23T00:00:00Z",
                "nodes": {
                    name: {
                        "last_probe_at": "2026-06-23T00:00:00Z",
                        "last_health": "healthy",
                        "unavailable_since": None,
                        "last_success_at": "2026-06-23T00:00:00Z",
                        "detail": "fixture real proxy probe passed",
                    }
                    for name in healthy_names
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return fixture_root


def test_mihomo_universal_config_uses_mainland_split_without_ai_proxy_group(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    config_text = render_artifacts.render_mihomo_config(fixture_root, platform="universal")
    config = yaml.safe_load(config_text)
    rule_text = "\n".join(config["rules"])
    proxy_groups = {group["name"]: group for group in config["proxy-groups"]}

    assert "AI-PROXY" not in config_text
    assert "DOMAIN-SUFFIX,qwen.ai" not in rule_text
    assert "DOMAIN-SUFFIX,qwenlm.ai" not in rule_text
    assert "PROXY" in proxy_groups
    assert proxy_groups["PROXY"]["proxies"][:2] == ["GG-US-SEA-BGP-01", "Auto"]
    assert "AI-PROXY" not in proxy_groups
    assert config["rule-providers"]["proxy"]["proxy"] == "PROXY"
    assert "RULE-SET,privateip,DIRECT,no-resolve" in rule_text
    assert "RULE-SET,apple-cn,DIRECT" in rule_text
    assert "RULE-SET,microsoft-cn,DIRECT" in rule_text
    assert "RULE-SET,google-cn,DIRECT" in rule_text
    assert "RULE-SET,cn,DIRECT" in rule_text
    assert "RULE-SET,cnip,DIRECT,no-resolve" in rule_text
    assert "RULE-SET,telegramip,PROXY,no-resolve" in rule_text
    assert "RULE-SET,proxy,PROXY" in rule_text
    assert "RULE-SET,gfw,PROXY" in rule_text
    assert "RULE-SET,tld-proxy,PROXY" in rule_text
    assert config["rules"][-1] == "MATCH,PROXY"


def test_mihomo_universal_config_directs_cursor_domains_before_process_rules(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="universal"))
    rules = config["rules"]

    expected_cursor_rules = [
        "DOMAIN-KEYWORD,cursor,DIRECT",
        "DOMAIN-SUFFIX,cursor.sh,DIRECT",
        "DOMAIN-SUFFIX,cursor.com,DIRECT",
        "DOMAIN-SUFFIX,cursorapi.com,DIRECT",
        "DOMAIN-SUFFIX,cursor-cdn.com,DIRECT",
        "DOMAIN-SUFFIX,anysphere.co,DIRECT",
        "DOMAIN-SUFFIX,anysphere.inc,DIRECT",
    ]
    assert rules[: len(expected_cursor_rules)] == expected_cursor_rules
    openai_start = len(expected_cursor_rules)
    assert rules[openai_start : openai_start + len(OPENAI_PROXY_DOMAIN_RULES)] == OPENAI_PROXY_DOMAIN_RULES
    expected_wps_domain_rules = [
        "DOMAIN-KEYWORD,kingsoft,DIRECT",
        "DOMAIN-SUFFIX,kingsoft.com,DIRECT",
        "DOMAIN-SUFFIX,kingsoft-office-service.com,DIRECT",
        "DOMAIN-SUFFIX,wps.cn,DIRECT",
        "DOMAIN-SUFFIX,wpscdn.cn,DIRECT",
        "DOMAIN-SUFFIX,wpscdn.com,DIRECT",
        "DOMAIN-SUFFIX,kdocs.cn,DIRECT",
        "DOMAIN-SUFFIX,kdocs.com,DIRECT",
        "DOMAIN-SUFFIX,ksosoft.com,DIRECT",
        "DOMAIN-SUFFIX,ksord.com,DIRECT",
        "DOMAIN-SUFFIX,wpsplus.com,DIRECT",
    ]
    wps_start = len(expected_cursor_rules) + len(OPENAI_PROXY_DOMAIN_RULES)
    assert rules[wps_start : wps_start + len(expected_wps_domain_rules)] == expected_wps_domain_rules
    first_process_rule = next(i for i, rule in enumerate(rules) if rule.startswith("PROCESS-"))
    first_process_proxy_rule = next(i for i, rule in enumerate(rules) if rule.startswith("PROCESS-") and rule.endswith(",PROXY"))
    first_proxy_ruleset = rules.index("RULE-SET,proxy,PROXY")
    assert all(rules.index(rule) < first_process_rule for rule in expected_cursor_rules)
    assert all(rules.index(rule) < first_process_rule for rule in OPENAI_PROXY_DOMAIN_RULES)
    assert all(rules.index(rule) < first_process_rule for rule in expected_wps_domain_rules)
    assert all(rules.index(rule) < first_process_proxy_rule for rule in expected_cursor_rules)
    assert all(rules.index(rule) < first_process_proxy_rule for rule in OPENAI_PROXY_DOMAIN_RULES)
    assert all(rules.index(rule) < first_process_proxy_rule for rule in expected_wps_domain_rules)
    assert all(rules.index(rule) < first_proxy_ruleset for rule in expected_cursor_rules)
    assert all(rules.index(rule) < first_proxy_ruleset for rule in OPENAI_PROXY_DOMAIN_RULES)
    assert all(rules.index(rule) < first_proxy_ruleset for rule in expected_wps_domain_rules)
    assert not any(any(rule.startswith(forbidden) for forbidden in FORBIDDEN_OPENAI_KEYWORD_RULES) for rule in rules)


def test_mihomo_config_uses_dustinwin_tun_and_direct_process_protections(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="windows"))

    assert config["mode"] == "rule"
    assert config["find-process-mode"] == "always"
    assert config["external-ui"] == "ui"
    assert config["geodata-mode"] is False
    assert config["tun"]["enable"] is True
    assert config["tun"]["auto-route"] is True
    assert "any:53" in config["tun"]["dns-hijack"]
    assert "cn" in config["rule-providers"]
    assert config["rule-providers"]["cn"]["url"].endswith("/mihomo-ruleset/cn.mrs")
    assert config["rule-providers"]["cn"]["format"] == "mrs"
    assert config["rule-providers"]["cn"]["proxy"] == "PROXY"
    assert config["rule-providers"]["proxy"]["url"].endswith("/mihomo-ruleset/proxy.mrs")
    assert config["rule-providers"]["cnip"]["behavior"] == "ipcidr"
    assert not any(rule.startswith("GEOIP,") for rule in config["rules"])
    assert config["dns"]["fallback-filter"]["geoip"] is False

    rule_text = "\n".join(config["rules"])
    assert "PROCESS-NAME,QQ.exe,DIRECT" in rule_text
    assert "PROCESS-NAME,WeChat.exe,DIRECT" in rule_text
    assert "PROCESS-NAME,Cursor.exe,DIRECT" in rule_text
    assert "PROCESS-NAME,wps.exe,DIRECT" in rule_text
    assert "PROCESS-NAME,wpscloudsvr.exe,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Kingsoft\WPS Office\*,DIRECT" in rule_text
    assert "DOMAIN-SUFFIX,wps.cn,DIRECT" in rule_text
    assert "DOMAIN-KEYWORD,kingsoft,DIRECT" in rule_text
    assert r"PROCESS-PATH,C:\Program Files\Microsoft\Edge Beta\Application\msedge.exe,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\Cursor\*,DIRECT" in rule_text
    assert "PROCESS-NAME,simprint.exe,DIRECT" not in rule_text
    assert "PROCESS-NAME,simprint-runtime.exe,DIRECT" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\Simprint\webview-fixed\*\msedgewebview2.exe,PROXY" not in rule_text
    assert (
        r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe,PROXY"
        in rule_text
    )
    assert (
        r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe,PROXY"
        in rule_text
    )
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\Google\Antigravity\*,PROXY" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\Google\Antigravity*\*,PROXY" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\Antigravity\*,PROXY" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\OpenAI\Codex\bin\*\codex.exe,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\WindowsApps\OpenAI.Codex_*\app\*,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT\*,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT\*,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT Atlas\*,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT Atlas\*,DIRECT" in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\OpenAI\Codex\bin\*\codex.exe,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\WindowsApps\OpenAI.Codex_*\app\*,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT\*,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT\*,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files\OpenAI\ChatGPT Atlas\*,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Programs\ChatGPT Atlas\*,PROXY" not in rule_text
    for rule in OPENAI_PROXY_DOMAIN_RULES:
        assert rule in config["rules"]
        assert config["rules"].index(rule) < config["rules"].index(
            r"PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\OpenAI\Codex\bin\*\codex.exe,DIRECT"
        )
    assert "PROCESS-NAME,simprint.exe,PROXY" not in rule_text
    assert "PROCESS-NAME,simprint-runtime.exe,PROXY" not in rule_text
    assert "PROCESS-NAME,msedgewebview2.exe,PROXY" not in rule_text
    assert "PROCESS-NAME,node.exe,PROXY" not in rule_text
    assert "PROCESS-NAME,python.exe,PROXY" not in rule_text
    assert r"PROCESS-PATH-WILDCARD,C:\Program Files (x86)\Microsoft\EdgeWebView\*\msedgewebview2.exe,PROXY" not in rule_text
    assert not any(rule.startswith("PROCESS-NAME,") and rule.endswith(",PROXY") for rule in config["rules"])
    allowed_process_proxy_fragments = (
        "Simprint",
        "Antigravity",
    )
    bad_process_proxy_rules = [
        rule
        for rule in config["rules"]
        if rule.startswith(("PROCESS-PATH,", "PROCESS-PATH-WILDCARD,")) and rule.endswith(",PROXY")
        and not any(fragment in rule for fragment in allowed_process_proxy_fragments)
    ]
    assert bad_process_proxy_rules == []
    assert rule_text.index("RULE-SET,cn,DIRECT") < rule_text.index("RULE-SET,proxy,PROXY")


def test_openai_family_routing_is_domain_proxy_with_process_direct_fallback(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="universal"))
    rules = config["rules"]
    rule_text = "\n".join(rules)

    for rule in OPENAI_PROXY_DOMAIN_RULES:
        assert rule in rules
    assert not any(any(rule.startswith(forbidden) for forbidden in FORBIDDEN_OPENAI_KEYWORD_RULES) for rule in rules)

    first_openai_rule = min(rules.index(rule) for rule in OPENAI_PROXY_DOMAIN_RULES)
    first_direct_app_rule = min(index for index, rule in enumerate(rules) if rule in OPENAI_APP_PROCESS_DIRECT_RULES)
    first_proxy_process_rule = min(index for index, rule in enumerate(rules) if rule.startswith("PROCESS-") and rule.endswith(",PROXY"))
    assert first_openai_rule < first_direct_app_rule < first_proxy_process_rule

    for rule in OPENAI_APP_PROCESS_DIRECT_RULES:
        assert rule in rules
        assert f"{rule.removesuffix(',DIRECT')},PROXY" not in rules

    assert "openaiapi" not in rule_text.lower()
    assert "api.openai-relay.example" not in rule_text


def test_mihomo_universal_config_marks_direct_process_rules_as_user_editable(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    rendered = render_artifacts.render_mihomo_config(fixture_root, platform="universal")
    config = yaml.safe_load(rendered)

    assert "# === USER-EDITABLE PROCESS DIRECT PROTECTIONS ===" in rendered
    assert "# To stop protecting one DIRECT process" in rendered
    assert "# === USER-EDITABLE PROCESS PROXY OVERRIDES ===" in rendered
    assert "# Comment individual lines out to route that app by destination" in rendered
    assert "# === END USER-EDITABLE PROCESS DIRECT PROTECTIONS ===" in rendered
    assert rendered.index("# === USER-EDITABLE PROCESS DIRECT PROTECTIONS ===") < rendered.index(
        "- PROCESS-NAME,QQ.exe,DIRECT"
    )
    assert rendered.index("- PROCESS-NAME,QQ.exe,DIRECT") < rendered.index(
        "# === END USER-EDITABLE PROCESS DIRECT PROTECTIONS ==="
    )
    assert rendered.index("# === END USER-EDITABLE PROCESS DIRECT PROTECTIONS ===") < rendered.index(
        "# === USER-EDITABLE PROCESS PROXY OVERRIDES ==="
    )
    assert rendered.index("# === USER-EDITABLE PROCESS PROXY OVERRIDES ===") < rendered.index(
        r"- PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe,PROXY"
    )
    assert config["rules"][-1] == "MATCH,PROXY"


def test_mihomo_process_notes_describe_mainland_split_policy() -> None:
    render_artifacts = load_render_artifacts_module()

    notes = render_artifacts.render_mihomo_process_routing_notes(PRIVATE_ROOT)

    assert "AI-PROXY" not in notes
    assert "Qwen" not in notes
    assert "Simprint Chrome profile" in notes
    assert "not `C:\\Users\\...\\Simprint\\simprint.exe`" in notes
    assert "final fallback is `MATCH,PROXY`" in notes
    assert "non-mainland destinations are proxied" in notes
    assert "Cursor domain rules are the highest-priority DIRECT rules" in notes
    assert "cursor.sh" in notes
    assert "cursorapi.com" in notes
    assert "Official OpenAI / ChatGPT / Codex domains are high-priority `PROXY` rules" in notes
    assert "OpenAI-family desktop app paths are `DIRECT` fallbacks" in notes
    assert "Antigravity and Simprint Chrome profile paths are default process-level `PROXY` overrides" in notes
    assert "DOMAIN-KEYWORD,openai" not in notes
    assert "DOMAIN-KEYWORD,codex" not in notes
    assert "WPS / Kingsoft domain DIRECT rules" in notes


def test_windows_verify_script_checks_mainland_split_without_ai_proxy() -> None:
    verify_script = ROOT / "scripts" / "windows" / "verify-mihomo-windows.ps1"
    script_text = verify_script.read_text(encoding="utf-8")

    assert "AI-PROXY" not in script_text
    assert "qwen_domain" not in script_text
    assert "proxy egress:" not in script_text
    assert "direct egress:" not in script_text
    assert "policy probe summary:" in script_text
    assert "qwen_no_ai_proxy" in script_text
    assert "https://chat.qwen.ai/" in script_text
    assert "qwen_domain" not in script_text
    assert "runtime_ai_proxy_count" in script_text
    assert "file_ai_proxy_count" in script_text
    assert "current mihomo log summary:" in script_text
    assert "Get-MihomoProcessStartTime" in script_text
    assert "Sort-Object StartTime" not in script_text
    assert "current_log_unavailable_reason=start_time_unavailable" in script_text
    assert "Get-Content 'C:\\ProgramData\\mihomo\\mihomo-current.out.log' -Tail 80" not in script_text
    assert "https://www.google.com/" in script_text
    assert "https://www.baidu.com/" in script_text
    assert "https://im.qq.com/" in script_text
    assert "https://weixin.qq.com/" in script_text
    assert "wps_update" in script_text
    assert "wps_drive" in script_text
    assert "verification_verdict=PASS" in script_text
    assert "Test-AllowedProcessProxyRule" in script_text
    assert "PROCESS-(NAME|PATH)" in script_text
    assert "Assert-OpenAIDomainProxyGuardrails" in script_text
    assert "openai_domain_proxy_count" in script_text
    assert "forbidden_openai_keyword_count" in script_text
    assert r"C:\Users\*\Simprint\webview-fixed\*\msedgewebview2.exe" not in script_text
    assert "PROCESS-NAME,simprint.exe,PROXY" not in script_text
    assert "PROCESS-NAME,msedgewebview2.exe,PROXY" not in script_text
    assert "C:\\Users\\*\\AppData\\Local\\OpenAI\\Codex\\bin\\*\\codex.exe',\n" not in script_text
    assert "C:\\Program Files\\WindowsApps\\OpenAI.Codex_*\\app\\*',\n" not in script_text
    assert "C:\\Program Files\\OpenAI\\ChatGPT\\*',\n" not in script_text


def test_windows_admin_scripts_allow_only_simprint_browser_proxy_rules() -> None:
    script_paths = [
        ROOT / "scripts" / "windows" / "refresh-mihomo-tun-config.ps1",
        ROOT / "scripts" / "windows" / "apply-simprint-routing-admin.ps1",
        ROOT / "scripts" / "windows" / "apply-mihomo-routing-policy-admin.ps1",
        ROOT / "scripts" / "windows" / "install-mihomo-tun.ps1",
    ]

    for script_path in script_paths:
        script_text = script_path.read_text(encoding="utf-8")
        assert "Test-AllowedProcessProxyRule" in script_text
        assert "PROCESS-(NAME|PATH)" in script_text
        assert "runtime_disallowed_process_proxy_count" in script_text
        assert r"C:\Users\*\Simprint\webview-fixed\*\msedgewebview2.exe" not in script_text
        assert "PROCESS-NAME,simprint.exe,PROXY" not in script_text
        assert "PROCESS-NAME,msedgewebview2.exe,PROXY" not in script_text
        assert "Assert-OpenAIDomainProxyGuardrails" in script_text
        assert "forbidden_openai_keyword_count" in script_text
        assert r"C:\Program Files\WindowsApps\OpenAI.Codex_*\app\*" not in script_text
        assert r"C:\Program Files\OpenAI\ChatGPT\*" not in script_text
        assert r"C:\Program Files\Google\Antigravity\*" in script_text
        assert "/Applications/Codex.app/Contents/*" not in script_text
        assert "/usr/bin/codex" not in script_text


def test_simprint_diagnostic_scripts_keep_qwen_out_and_show_route_details() -> None:
    apply_script = (ROOT / "scripts" / "windows" / "apply-simprint-routing-admin.ps1").read_text(
        encoding="utf-8"
    )
    watch_script = (ROOT / "scripts" / "windows" / "watch-simprint-routing.ps1").read_text(encoding="utf-8")

    assert "qwen" not in apply_script.lower()
    assert "qwen" not in watch_script.lower()
    assert "RulePayload" in watch_script
    assert "Chains" in watch_script
    assert "Sort-Object Time, Source, Process, Host, Remote -Unique |\n        Format-List" in watch_script


def test_simprint_cdp_probe_targets_only_launched_chrome_profile_browser() -> None:
    script = (ROOT / "scripts" / "windows" / "debug-simprint-chrome-proxy.ps1").read_text(
        encoding="utf-8"
    )

    assert "Chrome DevTools Protocol" in script
    assert "/json/new?" in script
    assert "https://chat.qwen.ai/?codex_simprint_proxy_probe=" in script
    assert r"$env:LOCALAPPDATA\Simprint\data\profiles\Chrome *\simprint.exe" in script
    assert r"C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe" in script
    assert r"C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe" in script
    assert r"C:\Users\...\Simprint\simprint.exe" in script
    assert "simprint-runtime.exe" in script
    assert "msedgewebview2.exe,PROXY" not in script
    assert "PROCESS-NAME,simprint.exe,PROXY" not in script
    assert "result=PASS" in script
    assert "ProcessPathWildcard PROXY rule" in script


def test_windows_scripts_keep_system_mihomo_as_only_tun_runtime() -> None:
    install_script = (ROOT / "scripts" / "windows" / "install-mihomo-tun.ps1").read_text(encoding="utf-8")
    apply_script = (ROOT / "scripts" / "windows" / "apply-mihomo-routing-policy-admin.ps1").read_text(
        encoding="utf-8"
    )

    for script_text in (install_script, apply_script):
        assert "Set-ClashVergeTunDisabled" in script_text
        assert "Write-ClashCoreProfile" in script_text
        assert "Update-ClashRuntimeConfig" in script_text
        assert "enable_tun_mode: true" not in script_text
        assert "enable_system_proxy: true" not in script_text
        assert "tun_tray_icon: true" not in script_text
        assert "tun:" in script_text
        assert "enable: false" in script_text
        assert "external-controller: 127.0.0.1:9097" in script_text
        assert "'clash-verge.yaml') -Force" not in script_text


def test_windows_mihomo_startup_tasks_are_unlimited_runtime() -> None:
    script_paths = [
        ROOT / "scripts" / "windows" / "install-mihomo-tun.ps1",
        ROOT / "scripts" / "windows" / "refresh-mihomo-tun-config.ps1",
    ]

    for script_path in script_paths:
        script_text = script_path.read_text(encoding="utf-8")
        assert "-ExecutionTimeLimit (New-TimeSpan -Seconds 0)" in script_text, script_path


def test_mihomo_macos_and_linux_configs_keep_direct_protections_only(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    macos = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="macos"))
    linux = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="linux"))

    macos_rules = "\n".join(macos["rules"])
    linux_rules = "\n".join(linux["rules"])

    assert "PROCESS-NAME,Cursor Helper,DIRECT" in macos_rules
    assert "PROCESS-NAME,cursor-agent,DIRECT" in linux_rules
    assert "PROCESS-NAME,ChatGPT Atlas,PROXY" not in macos_rules
    assert "PROCESS-NAME,Antigravity Helper,PROXY" not in macos_rules
    assert "PROCESS-NAME,antigravity,PROXY" not in linux_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/Microsoft Edge.app/Contents/*,PROXY" not in macos_rules
    assert "PROCESS-PATH-WILDCARD,/opt/microsoft/msedge/*,PROXY" not in linux_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/ChatGPT.app/Contents/*,DIRECT" in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/ChatGPT Atlas.app/Contents/*,DIRECT" in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/Codex.app/Contents/*,DIRECT" in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/ChatGPT.app/Contents/*,PROXY" not in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/ChatGPT Atlas.app/Contents/*,PROXY" not in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/Codex.app/Contents/*,PROXY" not in macos_rules
    assert "PROCESS-PATH-WILDCARD,/Applications/Antigravity.app/Contents/*,PROXY" in macos_rules
    assert "PROCESS-PATH-WILDCARD,/opt/antigravity/*,PROXY" in linux_rules
    assert "PROCESS-PATH-WILDCARD,/opt/chatgpt/*,DIRECT" in linux_rules
    assert "PROCESS-PATH-WILDCARD,/opt/codex/*,DIRECT" in linux_rules
    assert "PROCESS-PATH-WILDCARD,/opt/chatgpt/*,PROXY" not in linux_rules
    assert "PROCESS-PATH-WILDCARD,/opt/codex/*,PROXY" not in linux_rules
    assert "PROCESS-NAME,node,PROXY" not in linux_rules
    assert "PROCESS-NAME,python,PROXY" not in linux_rules
    assert macos["rules"][-1] == "MATCH,PROXY"
    assert linux["rules"][-1] == "MATCH,PROXY"


def test_mihomo_config_maps_enabled_nodes_to_vless_reality_proxies(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="macos"))

    proxy_by_name = {proxy["name"]: proxy for proxy in config["proxies"]}
    assert "GG-Vmrack1" in proxy_by_name
    vmrack = proxy_by_name["GG-Vmrack1"]
    assert vmrack["type"] == "vless"
    assert vmrack["port"] == 10003
    assert vmrack["network"] == "tcp"
    assert vmrack["tls"] is True
    assert vmrack["flow"] == "xtls-rprx-vision"
    assert vmrack["client-fingerprint"] == "chrome"
    assert "public-key" in vmrack["reality-opts"]
    assert "short-id" in vmrack["reality-opts"]


def test_subscription_landing_page_links_mihomo_configs(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    html = render_artifacts.render_subscription_landing_page(fixture_root)

    assert "mihomo-universal.yaml" in html
    assert "mihomo-windows.yaml" not in html
    assert "mihomo-macos.yaml" not in html
    assert "mihomo-linux.yaml" not in html
    assert "DustinWin/ruleset_geodata" in html
    assert "places AI app process rules before China direct rules" not in html
    assert "keeps mainland China/private traffic direct" in html


def test_mihomo_process_notes_include_wps_domains(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)

    notes = render_artifacts.render_mihomo_process_routing_notes(fixture_root)

    assert "WPS / Kingsoft domain DIRECT rules" in notes
    assert "wps.cn" in notes
    assert "wpscloudsvr.exe" in notes
    assert "DOMAIN-KEYWORD,kingsoft,DIRECT" in notes


def test_runbook_documents_wps_and_dual_mihomo_monitoring() -> None:
    runbook = (ROOT / "docs" / "runbooks" / "proxy-subscription-client-deployment-requirements.md").read_text(
        encoding="utf-8"
    )

    assert "wpscloudsvr.exe" in runbook
    assert "DOMAIN-SUFFIX,wps.cn,DIRECT" in runbook
    assert "127.0.0.1:9090" in runbook
    assert "watch-wps-routing.ps1" in runbook
    assert "accept-mihomo-windows.ps1" in runbook
    assert "file_allowed_process_proxy_count=29" in runbook
    assert "update.wps.cn" in runbook


def test_watch_wps_routing_script_structure() -> None:
    watch_script = (ROOT / "scripts" / "windows" / "watch-wps-routing.ps1").read_text(encoding="utf-8")

    assert "qwen" not in watch_script.lower()
    assert "RulePayload" in watch_script
    assert "Chains" in watch_script
    assert "9090" in watch_script


def test_verify_script_includes_wps_policy_probes() -> None:
    verify_script = (ROOT / "scripts" / "windows" / "verify-mihomo-windows.ps1").read_text(encoding="utf-8")

    assert "wps_update" in verify_script
    assert "wps_drive" in verify_script
    assert "wps_account" in verify_script
    assert "verification_verdict=PASS" in verify_script
    assert "verification_verdict=FAIL" in verify_script


def test_generated_mihomo_universal_matches_render() -> None:
    render_artifacts = load_render_artifacts_module()

    generated_path = PRIVATE_ROOT / "generated" / "subscriptions" / "mihomo-universal.yaml"
    rendered = render_artifacts.render_mihomo_config(PRIVATE_ROOT, platform="universal")
    assert generated_path.read_text(encoding="utf-8") == rendered


def test_allowed_process_proxy_rule_lists_stay_in_sync(tmp_path: Path) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)
    verify_script = (ROOT / "scripts" / "windows" / "verify-mihomo-windows.ps1").read_text(encoding="utf-8")

    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="universal"))
    expected_payloads = {
        rule.split(",", 2)[1]
        for rule in config["rules"]
        if rule.startswith(("PROCESS-PATH,", "PROCESS-PATH-WILDCARD,")) and rule.endswith(",PROXY")
    }

    import re

    allowed_payloads = set(re.findall(r"'((?:[^'\\]|\\.)*)'", verify_script.split("allowedPayloads = @(", 1)[1].split(")", 1)[0]))
    assert expected_payloads == allowed_payloads


def test_public_base_url_override_rewrites_mihomo_links_and_direct_host(tmp_path: Path, monkeypatch) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = copy_private_fixture(tmp_path)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://subs.sea.prod.gglohh.top/subscriptions")

    html = render_artifacts.render_subscription_landing_page(fixture_root)
    config = yaml.safe_load(render_artifacts.render_mihomo_config(fixture_root, platform="windows"))

    assert "https://subs.sea.prod.gglohh.top/subscriptions/mihomo-universal.yaml" in html
    assert "DOMAIN,subs.sea.prod.gglohh.top,DIRECT" in config["rules"]
    assert "DOMAIN-SUFFIX,subs.sea.prod.gglohh.top,DIRECT" in config["rules"]


def test_subscriptions_inventory_uses_sea_gateway_authoritative_base_url() -> None:
    subscriptions = yaml.safe_load((PRIVATE_ROOT / "inventory" / "subscriptions.yaml").read_text(encoding="utf-8"))
    assert subscriptions["subscription_base_url"] == "https://subs.sea.prod.gglohh.top/subscriptions"
    assert subscriptions["publish"]["verify_url"] == "https://subs.sea.prod.gglohh.top/subscriptions/v2ray_nodes.txt"
    assert subscriptions["publish"]["node"] == "us_sea_bgp_01"
    legacy_subscription_port = ":180" + "80"
    assert legacy_subscription_port not in subscriptions["subscription_base_url"]
    assert ":27111" not in subscriptions["subscription_base_url"]
    assert "systemd_unit" not in subscriptions["publish"]
    assert "publish_port" not in subscriptions["publish"]
    old_subscription_port = "180" + "80"
    assert old_subscription_port not in json.dumps(subscriptions["publish"], sort_keys=True)


def test_generated_subscriptions_do_not_use_deprecated_27111_urls() -> None:
    subscriptions_dir = PRIVATE_ROOT / "generated" / "subscriptions"
    for path in subscriptions_dir.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert ":27111" not in text, f"deprecated URL found in {path.name}"


def test_infra_core_sidecar_scripts_removed() -> None:
    removed = [
        PRIVATE_ROOT / "scripts" / "apply_infra_core_sidecar.sh",
        PRIVATE_ROOT / "scripts" / "check_infra_core_egress_ip.sh",
        PRIVATE_ROOT / "scripts" / "check_infra_core_sidecar.sh",
        PRIVATE_ROOT / "scripts" / "deploy_infra_core_failover_controller.sh",
        PRIVATE_ROOT / "scripts" / "reconcile_infra_core_failover.py",
    ]
    for path in removed:
        assert not path.exists(), f"expected removed: {path}"


def test_runbook_documents_sea_bgp_primary_subscription_url() -> None:
    runbook = (ROOT / "docs" / "runbooks" / "proxy-subscription-client-deployment-requirements.md").read_text(
        encoding="utf-8"
    )
    assert "https://subs.sea.prod.gglohh.top/subscriptions" in runbook
    assert "publish_subscriptions_to_sea_host.sh" in runbook
    assert "27111" in runbook
    legacy_subscription_ip_port = "69.5.53.82:" + ("180" + "80")
    assert legacy_subscription_ip_port not in runbook
    legacy_subscription_unit = "gg-proxy-subscriptions-" + "http.service"
    assert legacy_subscription_unit not in runbook
    assert "不要恢复 IP+HTTP 端口" in runbook


def test_runbook_documents_native_sea_gateway_https_cutover_gate() -> None:
    runbook = (ROOT / "docs" / "runbooks" / "proxy-subscription-client-deployment-requirements.md").read_text(
        encoding="utf-8"
    )

    assert "native Podman `sea-gateway`" in runbook
    assert "https://subs.sea.prod.gglohh.top/subscriptions" in runbook
    assert "sea-gateway` production" in runbook
    assert "`80/443`" in runbook
    assert "本地 Codex / mihomo 订阅配置切到域名 `443`" in runbook
    assert "k0s Traefik" not in runbook


def test_sea_bgp_ssh_scripts_require_env_password_without_literal_fallback() -> None:
    script_paths = sorted((ROOT / "scripts" / "windows").glob("ssh-sea-bgp-*.mjs"))
    assert script_paths

    for script_path in script_paths:
        script_text = script_path.read_text(encoding="utf-8")
        assert "process.env.SEA_PASSWORD ||" not in script_text
        assert "SEA_PASSWORD_required" in script_text


def test_active_sea_subscription_paths_do_not_publish_legacy_http_ip_port() -> None:
    checked_paths = [
        ROOT / "docs" / "runbooks" / "proxy-subscription-client-deployment-requirements.md",
        PRIVATE_ROOT / "docs" / "client-subscription-quickstart.md",
        ROOT / "scripts" / "windows" / "ssh-sea-bgp-probe.mjs",
        ROOT / "scripts" / "windows" / "ssh-sea-bgp-deep-audit.mjs",
        ROOT / "scripts" / "windows" / "ssh-sea-bgp-chatgpt-stability.mjs",
    ]

    for path in checked_paths:
        text = path.read_text(encoding="utf-8")
        old_subscription_port = "180" + "80"
        legacy_subscription_ip_port = "69.5.53.82:" + old_subscription_port
        legacy_local_subscription_url = "127.0.0.1:" + old_subscription_port
        legacy_subscription_unit = "gg-proxy-subscriptions-" + "http.service"
        assert legacy_subscription_ip_port not in text, path
        assert legacy_local_subscription_url not in text, path
        assert legacy_subscription_unit not in text, path


def test_render_v2ray_subscription_honors_availability_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    render_artifacts = load_render_artifacts_module()
    fixture_root = tmp_path / "repo"
    shutil.copytree(PRIVATE_ROOT / "inventory", fixture_root / "inventory")
    shutil.copytree(PRIVATE_ROOT / "state", fixture_root / "state")
    if (PRIVATE_ROOT / "secrets").exists():
        shutil.copytree(PRIVATE_ROOT / "secrets", fixture_root / "secrets")
    inventory = yaml.safe_load((fixture_root / "inventory" / "nodes.yaml").read_text(encoding="utf-8"))
    node_name = next(
        str(node["name"])
        for node in inventory["nodes"]
        if node.get("enabled") and node.get("include_in_subscription", True)
    )
    healthy_node_name = next(
        str(node["name"])
        for node in inventory["nodes"]
        if node.get("enabled") and node.get("include_in_subscription", True) and str(node["name"]) != node_name
    )
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    (fixture_root / "state" / "node_availability.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-06-07T00:00:00Z",
                "nodes": {
                    node_name: {
                        "last_health": "down",
                        "unavailable_since": four_days_ago,
                        "detail": "tcp failed",
                    },
                    healthy_node_name: {
                        "last_health": "healthy",
                        "unavailable_since": None,
                        "detail": "tcp succeeded",
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SKIP_AVAILABILITY_PROBE", "1")
    all_nodes = render_artifacts.render_v2ray_subscription(fixture_root)
    excluded_single = render_artifacts.render_v2ray_subscription(fixture_root, node_name=node_name)

    excluded_host = next(
        str(node.get("proxy_domain") or node["host"])
        for node in inventory["nodes"]
        if str(node["name"]) == node_name
    )
    assert f"@{excluded_host}:" not in all_nodes
    assert excluded_single == ""
    assert render_artifacts.subscription_publishable_nodes(fixture_root)
