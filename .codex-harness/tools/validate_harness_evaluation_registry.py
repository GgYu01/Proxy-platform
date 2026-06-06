#!/usr/bin/env python3
"""Validate the Codex-led harness evaluation registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_ADOPTION = {"adopt_now", "adopt_next", "watch", "defer"}
ALLOWED_MODES = {
    "public_benchmark_mapping",
    "local_golden_task",
    "scenario_eval",
    "metric_framework",
    "safety_eval",
    "watchlist",
}
ALLOWED_LEVELS = {"R0", "D0", "L0", "L1", "L2", "L3", "L4", "L5", "L6", "G0"}
REQUIRED_KEYS = {"id", "name", "category", "adoption", "mode", "levels", "metrics", "sources", "fit"}
REQUIRED_CATEGORY_PREFIXES = (
    "software_engineering",
    "code_",
    "repository_",
    "terminal_",
    "tool_",
    "web_browser_",
    "desktop_",
    "mobile_",
    "evaluation_framework",
    "safety_",
)


class RegistryError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _validate_url(value: str, benchmark_id: str) -> None:
    parsed = urlparse(value)
    _require(parsed.scheme in {"https", "http"}, f"{benchmark_id}: source is not a URL: {value}")
    _require(bool(parsed.netloc), f"{benchmark_id}: source URL missing host: {value}")


def validate_registry(path: str | Path) -> dict[str, int]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    _require(data.get("registry_type") == "harness_evaluation_registry", "registry_type mismatch")
    policy = data.get("policy")
    _require(isinstance(policy, dict), "policy must be an object")
    _require(policy.get("delivery_authority") == "local_codex_supervisor", "delivery authority must stay local")
    _require(policy.get("auto_repair_enabled") is False, "auto repair must remain disabled")

    adoption_levels = set(data.get("adoption_levels", []))
    integration_modes = set(data.get("integration_modes", []))
    _require(adoption_levels == ALLOWED_ADOPTION, "adoption_levels must match allowed set")
    _require(integration_modes == ALLOWED_MODES, "integration_modes must match allowed set")

    benchmarks = data.get("benchmarks")
    _require(isinstance(benchmarks, list), "benchmarks must be a list")
    _require(bool(benchmarks), "benchmarks must not be empty")

    seen_ids: set[str] = set()
    adoption_counts = {key: 0 for key in ALLOWED_ADOPTION}
    mode_counts = {key: 0 for key in ALLOWED_MODES}
    categories: set[str] = set()

    for index, benchmark in enumerate(benchmarks):
        _require(isinstance(benchmark, dict), f"benchmark[{index}] must be an object")
        missing = REQUIRED_KEYS - set(benchmark)
        _require(not missing, f"benchmark[{index}] missing keys: {sorted(missing)}")

        benchmark_id = benchmark["id"]
        _require(isinstance(benchmark_id, str) and benchmark_id, f"benchmark[{index}] id must be non-empty")
        _require(benchmark_id not in seen_ids, f"duplicate benchmark id: {benchmark_id}")
        seen_ids.add(benchmark_id)

        adoption = benchmark["adoption"]
        mode = benchmark["mode"]
        _require(adoption in ALLOWED_ADOPTION, f"{benchmark_id}: invalid adoption {adoption}")
        _require(mode in ALLOWED_MODES, f"{benchmark_id}: invalid mode {mode}")
        adoption_counts[adoption] += 1
        mode_counts[mode] += 1

        for field in ("name", "category", "fit"):
            _require(isinstance(benchmark[field], str) and benchmark[field].strip(), f"{benchmark_id}: {field} required")
        categories.add(benchmark["category"])

        levels = benchmark["levels"]
        metrics = benchmark["metrics"]
        sources = benchmark["sources"]
        _require(isinstance(levels, list) and levels, f"{benchmark_id}: levels must be a non-empty list")
        _require(all(level in ALLOWED_LEVELS for level in levels), f"{benchmark_id}: invalid levels {levels}")
        _require(isinstance(metrics, list) and metrics, f"{benchmark_id}: metrics must be a non-empty list")
        _require(all(isinstance(metric, str) and metric for metric in metrics), f"{benchmark_id}: metrics invalid")
        _require(isinstance(sources, list) and sources, f"{benchmark_id}: sources must be a non-empty list")
        for source in sources:
            _require(isinstance(source, str) and source, f"{benchmark_id}: source must be non-empty string")
            _validate_url(source, benchmark_id)

    _require(adoption_counts["adopt_now"] >= 3, "registry should contain at least three adopt_now benchmarks")
    _require(mode_counts["public_benchmark_mapping"] >= 3, "registry should contain public benchmark mappings")
    _require(mode_counts["metric_framework"] >= 2, "registry should contain metric frameworks")
    _require(mode_counts["safety_eval"] >= 1, "registry should contain safety evaluations")
    for prefix in REQUIRED_CATEGORY_PREFIXES:
        _require(
            any(category.startswith(prefix) for category in categories),
            f"registry should contain category prefix {prefix}",
        )

    return {
        "benchmarks": len(benchmarks),
        "adopt_now": adoption_counts["adopt_now"],
        "adopt_next": adoption_counts["adopt_next"],
        "watch": adoption_counts["watch"],
        "defer": adoption_counts["defer"],
        "categories": len(categories),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    args = parser.parse_args(argv)

    try:
        summary = validate_registry(args.registry)
    except (json.JSONDecodeError, OSError, RegistryError) as exc:
        print(f"invalid: harness_evaluation_registry: {exc}", file=sys.stderr)
        return 1

    print(
        "valid: harness_evaluation_registry "
        f"benchmarks={summary['benchmarks']} "
        f"adopt_now={summary['adopt_now']} "
        f"adopt_next={summary['adopt_next']} "
        f"watch={summary['watch']} "
        f"defer={summary['defer']} "
        f"categories={summary['categories']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
