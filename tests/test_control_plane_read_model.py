from proxy_platform.control_plane_read_model import build_worker_quota_snapshot


def test_build_worker_quota_snapshot_accepts_accounts_without_latest_snapshot() -> None:
    accounts_payload = [
        {
            "account_id": "codex_group_a:fbdfb813bfca32bd",
            "worker_id": "vmrack1_codex_primary",
            "group_id": "codex_group_a",
            "auth_name": "codex-62843a39-DestineeConnellypaor@outlook.com-team.json",
            "provider": "codex",
            "status": "active",
            "email": "DestineeConnellypaor@outlook.com",
            "last_probe_status": "error",
            "probe_state": {
                "status": "error",
                "observed_at": "2026-04-20T02:16:56.276727+00:00",
                "has_fresh_failure": True,
                "message": "Latest refresh failed on the worker.",
            },
            "latest_snapshot": None,
        }
    ]
    overview_payload = {
        "captured_at": "2026-04-20T02:18:20.636539+00:00",
        "workers": [
            {
                "worker_id": "vmrack1_codex_primary",
                "status": "failed",
                "captured_at": "2026-04-20T02:18:20.636539+00:00",
            }
        ],
    }

    snapshot = build_worker_quota_snapshot(accounts_payload, overview_payload)

    assert snapshot["meta"]["worker_total"] == 1
    assert snapshot["meta"]["accounts_without_snapshot"] == 1
    assert snapshot["meta"]["fresh_probe_failures"] == 1
    assert snapshot["workers"][0]["accounts"][0]["latest_snapshot_present"] is False
    assert snapshot["workers"][0]["accounts"][0]["quota_summary"] == "无最新配额快照"
