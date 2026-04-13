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
class PlatformManifest:
    name: str
    version: str
    default_mode: str
    supported_modes: list[str]
    repos: list[RepoSpec]
    commands: dict[str, CommandSpec]
    source_path: Path

    def repos_for_mode(self, mode: str) -> list[RepoSpec]:
        return [repo for repo in self.repos if repo.applies_to_mode(mode)]


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

    _validate_gitmodules_alignment(manifest)


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
