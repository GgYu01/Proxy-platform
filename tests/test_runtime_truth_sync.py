from pathlib import Path

from proxy_platform.runtime_truth_sync import refresh_runtime_truth_from_seed


def _write_truth_seed(seed_root: Path, *, node_name: str) -> None:
    (seed_root / "operator").mkdir(parents=True, exist_ok=True)
    (seed_root / "operator" / "nodes.yaml").write_text(
        f"nodes:\n  - name: {node_name}\n",
        encoding="utf-8",
    )
    (seed_root / "operator" / "subscriptions.yaml").write_text(
        f"profile_name: {node_name}\n",
        encoding="utf-8",
    )


def test_refresh_runtime_truth_updates_workspace_when_it_still_matches_previous_seed(tmp_path: Path) -> None:
    previous_seed_root = tmp_path / "previous-seed"
    current_seed_root = tmp_path / "current-seed"
    workspace_root = tmp_path / "workspace"
    _write_truth_seed(previous_seed_root, node_name="akilecloud")
    _write_truth_seed(current_seed_root, node_name="dedirock")

    workspace_nodes = workspace_root / "repos" / "proxy_ops_private" / "inventory" / "nodes.yaml"
    workspace_nodes.parent.mkdir(parents=True, exist_ok=True)
    workspace_nodes.write_text(
        (previous_seed_root / "operator" / "nodes.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    workspace_subscriptions = workspace_root / "repos" / "proxy_ops_private" / "inventory" / "subscriptions.yaml"
    workspace_subscriptions.write_text(
        (previous_seed_root / "operator" / "subscriptions.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = refresh_runtime_truth_from_seed(
        previous_seed_root=previous_seed_root,
        current_seed_root=current_seed_root,
        workspace_root=workspace_root,
    )

    assert workspace_nodes.read_text(encoding="utf-8") == "nodes:\n  - name: dedirock\n"
    assert workspace_subscriptions.read_text(encoding="utf-8") == "profile_name: dedirock\n"
    assert "repos/proxy_ops_private/inventory/nodes.yaml" in result.refreshed_files
    assert "repos/proxy_ops_private/inventory/subscriptions.yaml" in result.refreshed_files


def test_refresh_runtime_truth_preserves_workspace_when_runtime_has_local_edits(tmp_path: Path) -> None:
    previous_seed_root = tmp_path / "previous-seed"
    current_seed_root = tmp_path / "current-seed"
    workspace_root = tmp_path / "workspace"
    _write_truth_seed(previous_seed_root, node_name="akilecloud")
    _write_truth_seed(current_seed_root, node_name="dedirock")

    workspace_nodes = workspace_root / "repos" / "proxy_ops_private" / "inventory" / "nodes.yaml"
    workspace_nodes.parent.mkdir(parents=True, exist_ok=True)
    workspace_nodes.write_text("nodes:\n  - name: runtime-edited\n", encoding="utf-8")
    workspace_subscriptions = workspace_root / "repos" / "proxy_ops_private" / "inventory" / "subscriptions.yaml"
    workspace_subscriptions.write_text("profile_name: runtime-edited\n", encoding="utf-8")

    result = refresh_runtime_truth_from_seed(
        previous_seed_root=previous_seed_root,
        current_seed_root=current_seed_root,
        workspace_root=workspace_root,
    )

    assert workspace_nodes.read_text(encoding="utf-8") == "nodes:\n  - name: runtime-edited\n"
    assert workspace_subscriptions.read_text(encoding="utf-8") == "profile_name: runtime-edited\n"
    assert "repos/proxy_ops_private/inventory/nodes.yaml" in result.preserved_files
    assert "repos/proxy_ops_private/inventory/subscriptions.yaml" in result.preserved_files


def test_refresh_runtime_truth_seeds_missing_workspace_files(tmp_path: Path) -> None:
    previous_seed_root = tmp_path / "previous-seed"
    current_seed_root = tmp_path / "current-seed"
    workspace_root = tmp_path / "workspace"
    previous_seed_root.mkdir(parents=True, exist_ok=True)
    _write_truth_seed(current_seed_root, node_name="vmrack1")

    result = refresh_runtime_truth_from_seed(
        previous_seed_root=previous_seed_root,
        current_seed_root=current_seed_root,
        workspace_root=workspace_root,
    )

    assert (
        workspace_root / "repos" / "proxy_ops_private" / "inventory" / "nodes.yaml"
    ).read_text(encoding="utf-8") == "nodes:\n  - name: vmrack1\n"
    assert "repos/proxy_ops_private/inventory/nodes.yaml" in result.seeded_files


def test_refresh_runtime_truth_requires_current_seed_files(tmp_path: Path) -> None:
    current_seed_root = tmp_path / "current-seed"
    current_seed_root.mkdir(parents=True, exist_ok=True)

    try:
        refresh_runtime_truth_from_seed(
            previous_seed_root=tmp_path / "previous-seed",
            current_seed_root=current_seed_root,
            workspace_root=tmp_path / "workspace",
        )
    except ValueError as exc:
        assert "missing current runtime truth seed file" in str(exc)
    else:
        raise AssertionError("expected refresh_runtime_truth_from_seed to reject incomplete seed")
