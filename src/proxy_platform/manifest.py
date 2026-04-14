from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

import yaml


class ManifestError(ValueError):
    """Raised when the platform manifest is invalid."""


@dataclass(frozen=True)
class RepoSpec:
    repo_id: str
    display_name: str
    role: str
    required_modes: list[str]
    optional: bool
    visibility: str
    default_url: str
    default_path: Path
    local_override_path: Path | None

    def applies_to_mode(self, mode: str) -> bool:
        return mode in self.required_modes

    @property
    def required(self) -> bool:
        return not self.optional


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str


@dataclass(frozen=True)
class HostRegistrySource:
    inventory_path: Path
    subscriptions_path: Path
    observations_path: Path | None = None
    required_modes: list[str] | None = None

    def applies_to_mode(self, mode: str) -> bool:
        required_modes = self.required_modes or []
        return mode in required_modes


@dataclass(frozen=True)
class LocalProviderSpec:
    provider_id: str
    display_name: str
    kind: str
    owner_repo_id: str | None
    startup_timeout_seconds: int
    request_timeout_seconds: int
    startup_max_attempts: int
    request_max_attempts: int


@dataclass(frozen=True)
class StateSourceSpec:
    source_id: str
    display_name: str
    description: str
    kind: str
    repo_id: str
    path: Path
    ownership: str
    required_modes: list[str]

    def applies_to_mode(self, mode: str) -> bool:
        return mode in self.required_modes


@dataclass(frozen=True)
class ProjectionSpec:
    projection_id: str
    display_name: str
    description: str
    kind: str
    source_ids: list[str]
    required_modes: list[str]
    rules: dict[str, object]

    def applies_to_mode(self, mode: str) -> bool:
        return mode in self.required_modes


@dataclass(frozen=True)
class PythonRequirement:
    min_version: str
    candidates: list[str]
    env_hint: str | None


@dataclass(frozen=True)
class ToolchainCommandSpec:
    command_id: str
    display_name: str
    argv: list[str]
    fallback_argvs: list[list[str]]


@dataclass(frozen=True)
class ToolchainProfile:
    profile_id: str
    display_name: str
    description: str
    required_modes: list[str]
    repo_ids: list[str]
    python: PythonRequirement
    commands: list[ToolchainCommandSpec]

    def applies_to_mode(self, mode: str) -> bool:
        return mode in self.required_modes


@dataclass(frozen=True)
class PlatformManifest:
    name: str
    version: str
    default_mode: str
    supported_modes: list[str]
    repos: list[RepoSpec]
    host_registry_source: HostRegistrySource | None
    local_providers: tuple[LocalProviderSpec, ...]
    state_sources: dict[str, StateSourceSpec]
    projections: dict[str, ProjectionSpec]
    toolchains: dict[str, ToolchainProfile]
    commands: dict[str, CommandSpec]
    source_path: Path

    @property
    def host_registry(self) -> HostRegistrySource | None:
        return self.host_registry_source

    def repos_for_mode(self, mode: str) -> list[RepoSpec]:
        return [repo for repo in self.repos if repo.applies_to_mode(mode)]

    def state_sources_for_mode(self, mode: str) -> list[StateSourceSpec]:
        return [source for source in self.state_sources.values() if source.applies_to_mode(mode)]

    def projections_for_mode(self, mode: str) -> list[ProjectionSpec]:
        return [projection for projection in self.projections.values() if projection.applies_to_mode(mode)]

    def toolchains_for_mode(self, mode: str) -> list[ToolchainProfile]:
        return [profile for profile in self.toolchains.values() if profile.applies_to_mode(mode)]


def load_manifest(path: str | Path) -> PlatformManifest:
    manifest_path = Path(path).resolve()
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        platform = payload["platform"]
    except (OSError, KeyError, yaml.YAMLError) as exc:
        raise ManifestError(f"failed to load manifest {manifest_path}: {exc}") from exc
    repos = [
        RepoSpec(
            repo_id=item["id"],
            display_name=item["display_name"],
            role=item["role"],
            required_modes=list(item["required_modes"]),
            optional=bool(item["optional"]),
            visibility=item["visibility"],
            default_url=item["default_url"],
            default_path=Path(item["default_path"]),
            local_override_path=Path(item["local_override_path"]) if item.get("local_override_path") else None,
        )
        for item in payload.get("repos", [])
    ]
    state_source_items = payload.get("state_sources", [])
    state_source_ids = [item["id"] for item in state_source_items]
    if len(set(state_source_ids)) != len(state_source_ids):
        raise ManifestError("duplicate state source ids are not allowed")
    state_sources = {
        item["id"]: StateSourceSpec(
            source_id=item["id"],
            display_name=item["display_name"],
            description=item["description"],
            kind=item["kind"],
            repo_id=item["repo_id"],
            path=Path(item["path"]),
            ownership=item["ownership"],
            required_modes=list(item["required_modes"]),
        )
        for item in state_source_items
    }
    projection_items = payload.get("projections", [])
    projection_ids = [item["id"] for item in projection_items]
    if len(set(projection_ids)) != len(projection_ids):
        raise ManifestError("duplicate projection ids are not allowed")
    projections = {
        item["id"]: ProjectionSpec(
            projection_id=item["id"],
            display_name=item["display_name"],
            description=item["description"],
            kind=item["kind"],
            source_ids=list(item["source_ids"]),
            required_modes=list(item["required_modes"]),
            rules=dict(item.get("rules", {})),
        )
        for item in projection_items
    }
    state_payload = payload.get("state") or {}
    host_registry_payload = state_payload.get("host_registry")
    host_registry_source = None
    if host_registry_payload:
        host_registry_source = HostRegistrySource(
            inventory_path=Path(host_registry_payload["inventory_path"]),
            subscriptions_path=Path(host_registry_payload["subscriptions_path"]),
            observations_path=(
                Path(host_registry_payload["observations_path"])
                if host_registry_payload.get("observations_path")
                else None
            ),
            required_modes=list(host_registry_payload.get("required_modes", platform["supported_modes"])),
        )
    local_providers = tuple(
        LocalProviderSpec(
            provider_id=item["id"],
            display_name=item["display_name"],
            kind=item["kind"],
            owner_repo_id=item.get("owner_repo_id") or ("cliproxy_control_plane" if item["kind"] == "mcp" else None),
            startup_timeout_seconds=int(item["startup_timeout_seconds"]),
            request_timeout_seconds=int(item["request_timeout_seconds"]),
            startup_max_attempts=int(item["startup_max_attempts"]),
            request_max_attempts=int(item["request_max_attempts"]),
        )
        for item in state_payload.get("local_providers", [])
    )
    toolchain_items = payload.get("toolchains", [])
    toolchain_ids = [item["id"] for item in toolchain_items]
    if len(set(toolchain_ids)) != len(toolchain_ids):
        raise ManifestError("duplicate toolchain ids are not allowed")
    toolchains = {
        item["id"]: ToolchainProfile(
            profile_id=item["id"],
            display_name=item["display_name"],
            description=item["description"],
            required_modes=list(item["required_modes"]),
            repo_ids=list(item["repo_ids"]),
            python=PythonRequirement(
                min_version=str(item["python"]["min_version"]),
                candidates=[str(candidate) for candidate in item["python"]["candidates"]],
                env_hint=item["python"].get("env_hint"),
            ),
            commands=[
                ToolchainCommandSpec(
                    command_id=command["id"],
                    display_name=command["display_name"],
                    argv=[str(value) for value in command["argv"]],
                    fallback_argvs=[
                        [str(value) for value in argv]
                        for argv in command.get("fallback_argvs", [])
                    ],
                )
                for command in item.get("commands", [])
            ],
        )
        for item in toolchain_items
    }
    commands = {
        name: CommandSpec(name=name, description=data["description"])
        for name, data in (payload.get("commands") or {}).items()
    }
    manifest = PlatformManifest(
        name=platform["name"],
        version=str(platform["version"]),
        default_mode=platform["default_mode"],
        supported_modes=list(platform["supported_modes"]),
        repos=repos,
        host_registry_source=host_registry_source,
        local_providers=local_providers,
        state_sources=state_sources,
        projections=projections,
        toolchains=toolchains,
        commands=commands,
        source_path=manifest_path,
    )
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: PlatformManifest) -> None:
    if manifest.default_mode not in manifest.supported_modes:
        raise ManifestError(
            f"default_mode {manifest.default_mode!r} is not in supported_modes {manifest.supported_modes!r}"
        )

    repo_ids = [repo.repo_id for repo in manifest.repos]
    if len(set(repo_ids)) != len(repo_ids):
        raise ManifestError("duplicate repo ids are not allowed")

    unsupported = [
        (repo.repo_id, mode)
        for repo in manifest.repos
        for mode in repo.required_modes
        if mode not in manifest.supported_modes
    ]
    if unsupported:
        repo_id, mode = unsupported[0]
        raise ManifestError(f"repo {repo_id} uses unsupported mode {mode}")

    unknown_toolchain_modes = [
        (profile.profile_id, mode)
        for profile in manifest.toolchains.values()
        for mode in profile.required_modes
        if mode not in manifest.supported_modes
    ]
    if unknown_toolchain_modes:
        profile_id, mode = unknown_toolchain_modes[0]
        raise ManifestError(f"toolchain profile {profile_id} uses unsupported mode {mode}")

    repo_id_set = {repo.repo_id for repo in manifest.repos}
    valid_source_repo_ids = set(repo_id_set)
    valid_source_repo_ids.add(manifest.name)
    unknown_state_source_modes = [
        (source.source_id, mode)
        for source in manifest.state_sources.values()
        for mode in source.required_modes
        if mode not in manifest.supported_modes
    ]
    if unknown_state_source_modes:
        source_id, mode = unknown_state_source_modes[0]
        raise ManifestError(f"state source {source_id} uses unsupported mode {mode}")

    unknown_state_source_repos = [
        (source.source_id, source.repo_id)
        for source in manifest.state_sources.values()
        if source.repo_id not in valid_source_repo_ids
    ]
    if unknown_state_source_repos:
        source_id, repo_id = unknown_state_source_repos[0]
        raise ManifestError(f"state source {source_id} references unknown repo {repo_id}")

    unknown_projection_modes = [
        (projection.projection_id, mode)
        for projection in manifest.projections.values()
        for mode in projection.required_modes
        if mode not in manifest.supported_modes
    ]
    if unknown_projection_modes:
        projection_id, mode = unknown_projection_modes[0]
        raise ManifestError(f"projection {projection_id} uses unsupported mode {mode}")

    state_source_id_set = set(manifest.state_sources)
    unknown_projection_sources = [
        (projection.projection_id, source_id)
        for projection in manifest.projections.values()
        for source_id in projection.source_ids
        if source_id not in state_source_id_set
    ]
    if unknown_projection_sources:
        projection_id, source_id = unknown_projection_sources[0]
        raise ManifestError(f"projection {projection_id} references unknown state source {source_id}")

    unknown_toolchain_repo_ids = [
        (profile.profile_id, repo_id)
        for profile in manifest.toolchains.values()
        for repo_id in profile.repo_ids
        if repo_id not in repo_id_set
    ]
    if unknown_toolchain_repo_ids:
        profile_id, repo_id = unknown_toolchain_repo_ids[0]
        raise ManifestError(f"toolchain profile {profile_id} references unknown repo {repo_id}")

    _validate_host_registry_alignment(manifest)
    _validate_projection_mode_coverage(manifest)
    _validate_gitmodules_alignment(manifest)


def _validate_host_registry_alignment(manifest: PlatformManifest) -> None:
    host_registry = manifest.host_registry
    if host_registry is None:
        return

    invalid_modes = [mode for mode in host_registry.required_modes or [] if mode not in manifest.supported_modes]
    if invalid_modes:
        raise ManifestError(f"host registry source uses unsupported mode {invalid_modes[0]}")

    state_host_registry = manifest.state_sources.get("host_registry")
    if state_host_registry and sorted(state_host_registry.required_modes) != sorted(host_registry.required_modes or []):
        raise ManifestError(
            "state.host_registry.required_modes must match state_sources.host_registry.required_modes"
        )


def _validate_projection_mode_coverage(manifest: PlatformManifest) -> None:
    state_sources = manifest.state_sources
    for projection in manifest.projections.values():
        for mode in projection.required_modes:
            missing_sources = [
                source_id
                for source_id in projection.source_ids
                if not state_sources[source_id].applies_to_mode(mode)
            ]
            if missing_sources:
                raise ManifestError(
                    f"projection {projection.projection_id} uses mode {mode} but sources "
                    f"{', '.join(missing_sources)} do not support that mode"
                )


def _validate_gitmodules_alignment(manifest: PlatformManifest) -> None:
    gitmodules_path = manifest.source_path.parent / ".gitmodules"
    if not gitmodules_path.exists():
        return

    parser = configparser.ConfigParser()
    parser.read(gitmodules_path, encoding="utf-8")
    section_by_name: dict[str, configparser.SectionProxy] = {}
    for section_name in parser.sections():
        if not section_name.startswith('submodule "'):
            continue
        name = section_name[len('submodule "') : -1]
        section_by_name[name] = parser[section_name]

    for repo in manifest.repos:
        section = section_by_name.get(repo.repo_id)
        if section is None:
            continue
        submodule_path = section.get("path")
        submodule_url = section.get("url")
        if submodule_path and Path(submodule_path) != repo.default_path:
            raise ManifestError(
                f".gitmodules path mismatch for {repo.repo_id}: {submodule_path!r} != {str(repo.default_path)!r}"
            )
        if submodule_url and submodule_url != repo.default_url:
            raise ManifestError(
                f".gitmodules url mismatch for {repo.repo_id}: {submodule_url!r} != {repo.default_url!r}"
            )
