from pathlib import Path

import pytest

from proxy_platform.state import build_host_views
from proxy_platform.state import load_host_observations
from proxy_platform.state import load_host_registry
from proxy_platform.state import project_subscription
from proxy_platform.state import StateFileError


def test_build_host_views_preserves_registry_as_expected_state(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: lisahost
    display_name: Lisahost
    endpoint: https://lisa.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
    tags: [prod]
  - host_id: vmrack2
    display_name: VMrack2
    endpoint: https://vmrack2.example.com/sub
    provider: cliproxy_plus
    enabled: false
    include_in_subscription: true
    tags: [standby]
""",
        encoding="utf-8",
    )
    observations_path = tmp_path / "observations.yaml"
    observations_path.write_text(
        """
observations:
  - host_id: lisahost
    status: degraded
    source: probe
    observed_at: "2026-04-14T10:00:00Z"
""",
        encoding="utf-8",
    )

    views = build_host_views(
        load_host_registry(registry_path),
        load_host_observations(observations_path),
    )

    assert [view.host_id for view in views] == ["lisahost", "vmrack2"]
    assert views[0].desired_state == "enabled"
    assert views[0].observed_status == "degraded"
    assert views[0].subscription_included is True
    assert views[1].desired_state == "disabled"
    assert views[1].observed_status == "unknown"
    assert views[1].subscription_included is False


def test_project_subscription_includes_hosts_even_when_observation_is_down(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: lisahost
    display_name: Lisahost
    endpoint: https://lisa.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
  - host_id: edge-temp
    display_name: Edge Temp
    endpoint: https://edge.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: false
""",
        encoding="utf-8",
    )
    observations_path = tmp_path / "observations.yaml"
    observations_path.write_text(
        """
observations:
  - host_id: lisahost
    status: down
    source: agent
    observed_at: "2026-04-14T10:10:00Z"
  - host_id: stray-host
    status: healthy
    source: probe
""",
        encoding="utf-8",
    )

    projection = project_subscription(
        load_host_registry(registry_path),
        load_host_observations(observations_path),
    )

    assert [member.host_id for member in projection.members] == ["lisahost"]
    assert projection.members[0].observed_status == "down"
    assert projection.excluded_host_ids == ("edge-temp",)
    assert projection.unknown_observation_host_ids == ("stray-host",)


def test_load_host_registry_rejects_duplicate_host_ids(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: duplicated
    display_name: One
    endpoint: https://one.example.com/sub
    provider: cliproxy_plus
  - host_id: duplicated
    display_name: Two
    endpoint: https://two.example.com/sub
    provider: cliproxy_plus
""",
        encoding="utf-8",
    )

    with pytest.raises(StateFileError):
        load_host_registry(registry_path)


def test_load_host_observations_rejects_unknown_status(tmp_path: Path) -> None:
    observations_path = tmp_path / "observations.yaml"
    observations_path.write_text(
        """
observations:
  - host_id: lisahost
    status: broken
    source: probe
""",
        encoding="utf-8",
    )

    with pytest.raises(StateFileError):
        load_host_observations(observations_path)
