from pathlib import Path

from proxy_platform.manifest import load_manifest
from proxy_platform.providers import describe_local_providers


def test_describe_local_providers_reads_retry_and_timeout_policies(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
  local_providers:
    - id: local_mcp_pool
      display_name: Local MCP pool
      kind: mcp
      startup_timeout_seconds: 15
      request_timeout_seconds: 45
      startup_max_attempts: 3
      request_max_attempts: 2
commands: {}
""",
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    providers = describe_local_providers(manifest)

    assert len(providers) == 1
    assert providers[0].provider_id == "local_mcp_pool"
    assert providers[0].startup_timeout_seconds == 15
    assert providers[0].request_max_attempts == 2

