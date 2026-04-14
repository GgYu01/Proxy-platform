from __future__ import annotations

from proxy_platform.manifest import LocalProviderSpec, PlatformManifest


def describe_local_providers(manifest: PlatformManifest) -> list[LocalProviderSpec]:
    return list(manifest.local_providers)
