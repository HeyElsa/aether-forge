from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


JSON_VALUE = Any
SECRET_LIKE_KEY = re.compile(r"(secret|token|private[-_]?key|seed[-_]?phrase|mnemonic|password|api[-_]?key)", re.IGNORECASE)

_PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMAS_ROOT = _PACKAGE_DIR / "schemas"
# Fallback for development: if schemas aren't bundled in the package, try repo root
if not SCHEMAS_ROOT.exists():
    SCHEMAS_ROOT = _PACKAGE_DIR.parents[1] / "schemas"


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    artifact_type: str | None = None
    artifact_path: str | None = None
    path: str | None = None


@dataclass(slots=True)
class LoadedArtifact:
    artifact_type: str
    file_name: str
    file_path: str
    schema_id: str
    data: dict[str, Any]


@dataclass(slots=True)
class ArtifactSetValidationResult:
    ok: bool
    issues: list[ValidationIssue]
    artifacts: list[LoadedArtifact]
    artifact_set_id: str | None = None


ARTIFACT_FILE_DEFINITIONS = [
    {
        "file_name": "agent-spec.json",
        "artifact_type": "agent-spec",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/agent-spec.schema.json",
        "required": True,
    },
    {
        "file_name": "capability-manifest.json",
        "artifact_type": "capability-manifest",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/capability-manifest.schema.json",
        "required": True,
    },
    {
        "file_name": "policy-bundle.json",
        "artifact_type": "policy-bundle",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/policy-bundle.schema.json",
        "required": True,
    },
    {
        "file_name": "scenario-pack.json",
        "artifact_type": "scenario-pack",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/scenario-pack.schema.json",
        "required": True,
    },
    {
        "file_name": "research-record.json",
        "artifact_type": "research-record",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/research-record.schema.json",
        "required": False,
    },
    {
        "file_name": "promotion-record.json",
        "artifact_type": "promotion-record",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/promotion-record.schema.json",
        "required": False,
    },
    {
        "file_name": "memory-record.json",
        "artifact_type": "memory-record",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/memory-record.schema.json",
        "required": False,
    },
    {
        "file_name": "scaffold.manifest.json",
        "artifact_type": "scaffold-manifest",
        "schema_id": "https://schemas.aether-forge.dev/artifacts/scaffold-manifest.schema.json",
        "required": True,
    },
]

SCHEMA_FILES = [
    "common/artifact-ref.schema.json",
    "common/compatibility.schema.json",
    "common/migration-contract.schema.json",
    "common/artifact-envelope.schema.json",
    "runtime/active-comparison-contract.schema.json",
    "runtime/policy-decision-record.schema.json",
    "runtime/runtime-step-ledger-entry.schema.json",
    "artifacts/agent-spec.schema.json",
    "artifacts/capability-manifest.schema.json",
    "artifacts/policy-bundle.schema.json",
    "artifacts/scenario-pack.schema.json",
    "artifacts/research-record.schema.json",
    "artifacts/promotion-record.schema.json",
    "artifacts/memory-record.schema.json",
    "artifacts/scaffold-manifest.schema.json",
]


def validate_artifact_directory(directory_path: str | Path) -> ArtifactSetValidationResult:
    directory = Path(directory_path)
    issues: list[ValidationIssue] = []
    artifacts: list[LoadedArtifact] = []
    store = _load_schema_store()

    for definition in ARTIFACT_FILE_DEFINITIONS:
        file_path = directory / definition["file_name"]

        if not file_path.exists():
            if definition["required"]:
                issues.append(
                    ValidationIssue(
                        code="artifact.missing",
                        severity="error",
                        artifact_type=definition["artifact_type"],
                        artifact_path=str(file_path),
                        message=f"Missing required artifact file {definition['file_name']}.",
                    )
                )
            continue

        parsed = _read_json_object(file_path, definition["artifact_type"], issues)
        if parsed is None:
            continue

        for error in _validate_against_schema(parsed, definition["schema_id"], store):
            issues.append(
                ValidationIssue(
                    code=f"schema.{error.validator}",
                    severity="error",
                    artifact_type=definition["artifact_type"],
                    artifact_path=str(file_path),
                    path=error.json_path if error.json_path != "$" else None,
                    message=f"Schema validation failed: {error.message}.",
                )
            )

        if parsed.get("artifactType") != definition["artifact_type"]:
            issues.append(
                ValidationIssue(
                    code="artifact.type.mismatch",
                    severity="error",
                    artifact_type=definition["artifact_type"],
                    artifact_path=str(file_path),
                    path="/artifactType",
                    message=(
                        f"Expected artifactType {definition['artifact_type']} "
                        f"but found {parsed.get('artifactType')}."
                    ),
                )
            )

        artifacts.append(
            LoadedArtifact(
                artifact_type=definition["artifact_type"],
                file_name=definition["file_name"],
                file_path=str(file_path),
                schema_id=definition["schema_id"],
                data=parsed,
            )
        )

    _cross_validate_artifacts(artifacts, issues)
    artifact_set_id = artifacts[0].data.get("artifactSetId") if artifacts else None

    return ArtifactSetValidationResult(
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        artifacts=artifacts,
        artifact_set_id=artifact_set_id if isinstance(artifact_set_id, str) else None,
    )


def format_issues(issues: list[ValidationIssue]) -> str:
    if not issues:
        return "No validation issues found."

    lines: list[str] = []
    for issue in issues:
        location = f" {issue.path}" if issue.path else ""
        lines.append(f"[{issue.severity}] {issue.code}: {issue.message}{location}")
    return "\n".join(lines)


def _load_schema_store() -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for relative_path in SCHEMA_FILES:
        schema_path = SCHEMAS_ROOT / relative_path
        schema = json.loads(schema_path.read_text(encoding="utf8"))
        store[schema["$id"]] = schema
    return store


def _validate_against_schema(data: dict[str, Any], schema_id: str, store: dict[str, dict[str, Any]]):
    schema = store[schema_id]
    registry = Registry()
    for resource_id, resource_schema in store.items():
        registry = registry.with_resource(resource_id, Resource.from_contents(resource_schema))
    validator = Draft202012Validator(schema, registry=registry)
    return sorted(validator.iter_errors(data), key=lambda error: str(error.json_path))


def _read_json_object(file_path: Path, artifact_type: str, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    try:
        parsed = json.loads(file_path.read_text(encoding="utf8"))
    except json.JSONDecodeError as error:
        issues.append(
            ValidationIssue(
                code="artifact.invalid-json",
                severity="error",
                artifact_type=artifact_type,
                artifact_path=str(file_path),
                message=f"Failed to parse JSON: {error.msg}.",
            )
        )
        return None

    if not isinstance(parsed, dict):
        issues.append(
            ValidationIssue(
                code="artifact.invalid-json-shape",
                severity="error",
                artifact_type=artifact_type,
                artifact_path=str(file_path),
                message="Artifact root must be a JSON object.",
            )
        )
        return None

    return parsed


def _cross_validate_artifacts(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    if not artifacts:
        return

    _validate_artifact_set_consistency(artifacts, issues)
    _validate_compatibility_contracts(artifacts, issues)
    _validate_agent_spec(artifacts, issues)
    _validate_policy_bundle(artifacts, issues)
    _validate_capability_manifest(artifacts, issues)
    _validate_promotion_record(artifacts, issues)


def _validate_artifact_set_consistency(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    artifact_set_ids: set[str] = set()
    seen_keys: set[str] = set()

    for artifact in artifacts:
        artifact_set_id = _read_string(artifact.data, "artifactSetId")
        if artifact_set_id:
            artifact_set_ids.add(artifact_set_id)

        artifact_id = _read_string(artifact.data, "artifactId")
        artifact_version = _read_string(artifact.data, "artifactVersion")
        if artifact_id and artifact_version:
            key = f"{artifact.artifact_type}:{artifact_id}:{artifact_version}"
            if key in seen_keys:
                issues.append(
                    ValidationIssue(
                        code="artifact.duplicate-id",
                        severity="error",
                        artifact_type=artifact.artifact_type,
                        artifact_path=artifact.file_path,
                        message=f"Duplicate artifact identity {key}.",
                    )
                )
            seen_keys.add(key)

    if len(artifact_set_ids) > 1:
        issues.append(
            ValidationIssue(
                code="artifact-set.id.mismatch",
                severity="error",
                message=(
                    "All artifacts must share the same artifactSetId, "
                    f"found {', '.join(sorted(artifact_set_ids))}."
                ),
            )
        )


def _validate_compatibility_contracts(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    for artifact in artifacts:
        compatibility = _read_object(artifact.data, "compatibility")
        if compatibility is None:
            continue

        status = _read_string(compatibility, "status")
        migration_ref = compatibility.get("migrationRef")
        if status in {"breaking", "incompatible"} and not isinstance(migration_ref, dict):
            issues.append(
                ValidationIssue(
                    code="compatibility.migration.missing",
                    severity="error",
                    artifact_type=artifact.artifact_type,
                    artifact_path=artifact.file_path,
                    path="/compatibility/migrationRef",
                    message="Breaking or incompatible artifacts must include a migrationRef.",
                )
            )


def _validate_agent_spec(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    agent_spec = _find_artifact(artifacts, "agent-spec")
    if agent_spec is None:
        return

    for secret_path in _find_secret_like_paths(agent_spec.data):
        issues.append(
            ValidationIssue(
                code="agent-spec.secret-like-key",
                severity="error",
                artifact_type=agent_spec.artifact_type,
                artifact_path=agent_spec.file_path,
                path=secret_path,
                message="Agent Spec must not embed secret-like keys or raw credential material.",
            )
        )

    manifest = _find_artifact(artifacts, "capability-manifest")
    capability_ids: set[str] = set()
    if manifest is not None:
        for capability in _read_array(manifest.data.get("capabilities")):
            if isinstance(capability, dict):
                capability_id = _read_string(capability, "capabilityId")
                if capability_id:
                    capability_ids.add(capability_id)

    for capability_ref in _read_array(agent_spec.data.get("capabilityRefs")):
        if isinstance(capability_ref, str):
            if capability_ref not in capability_ids:
                issues.append(
                    ValidationIssue(
                        code="agent-spec.capability-ref.missing",
                        severity="error",
                        artifact_type=agent_spec.artifact_type,
                        artifact_path=agent_spec.file_path,
                        path="/capabilityRefs",
                        message=f"Capability reference {capability_ref} does not exist in capability-manifest.json.",
                    )
                )
        elif isinstance(capability_ref, dict) and _resolve_artifact_ref(capability_ref, artifacts) is None:
            issues.append(
                ValidationIssue(
                    code="agent-spec.capability-ref.unresolved",
                    severity="error",
                    artifact_type=agent_spec.artifact_type,
                    artifact_path=agent_spec.file_path,
                    path="/capabilityRefs",
                    message=f"Artifact capability reference {_stringify_artifact_ref(capability_ref)} could not be resolved.",
                )
            )

    evaluation = _read_object(agent_spec.data, "evaluation")
    scenario_pack_ref = _read_object(evaluation, "scenarioPackRef")
    if scenario_pack_ref and _resolve_artifact_ref(scenario_pack_ref, artifacts) is None:
        issues.append(
            ValidationIssue(
                code="agent-spec.scenario-pack-ref.missing",
                severity="error",
                artifact_type=agent_spec.artifact_type,
                artifact_path=agent_spec.file_path,
                path="/evaluation/scenarioPackRef",
                message=f"Scenario pack reference {_stringify_artifact_ref(scenario_pack_ref)} could not be resolved.",
            )
        )

    policy_bundle = _find_artifact(artifacts, "policy-bundle")
    policy_bundle_id = _read_string(policy_bundle.data, "artifactId") if policy_bundle else None
    for policy_ref in _read_array(agent_spec.data.get("policyRefs")):
        if isinstance(policy_ref, str) and policy_bundle_id and policy_ref != policy_bundle_id:
            issues.append(
                ValidationIssue(
                    code="agent-spec.policy-ref.mismatch",
                    severity="error",
                    artifact_type=agent_spec.artifact_type,
                    artifact_path=agent_spec.file_path,
                    path="/policyRefs",
                    message=f"Policy reference {policy_ref} does not match policy-bundle artifact ID {policy_bundle_id}.",
                )
            )


def _validate_policy_bundle(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    bundle = _find_artifact(artifacts, "policy-bundle")
    if bundle is None:
        return

    rules = _read_object(bundle.data, "rules")
    max_notional = rules.get("maxNotionalUsd") if rules else None
    if max_notional is not None and not isinstance(max_notional, (int, float)):
        issues.append(
            ValidationIssue(
                code="policy-bundle.max-notional.invalid",
                severity="error",
                artifact_type=bundle.artifact_type,
                artifact_path=bundle.file_path,
                path="/rules/maxNotionalUsd",
                message="Policy bundle maxNotionalUsd must be numeric when present.",
            )
        )


def _validate_capability_manifest(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    manifest = _find_artifact(artifacts, "capability-manifest")
    if manifest is None:
        return

    handle_ids: set[str] = set()
    for handle in _read_array(manifest.data.get("credentialHandles")):
        if isinstance(handle, dict):
            handle_id = _read_string(handle, "handleId")
            if handle_id:
                handle_ids.add(handle_id)

    for capability in _read_array(manifest.data.get("capabilities")):
        if not isinstance(capability, dict):
            continue

        capability_id = _read_string(capability, "capabilityId") or "<unknown>"
        credential_handle_id = _read_string(capability, "credentialHandleId")
        if credential_handle_id and credential_handle_id not in handle_ids:
            issues.append(
                ValidationIssue(
                    code="capability-manifest.credential-handle.missing",
                    severity="error",
                    artifact_type=manifest.artifact_type,
                    artifact_path=manifest.file_path,
                    path=f"/capabilities/{capability_id}/credentialHandleId",
                    message=(
                        f"Capability {capability_id} references missing credential handle {credential_handle_id}."
                    ),
                )
            )

        kind = _read_string(capability, "kind")
        if kind in {"wallet-action", "exchange-action", "onchain-action"} and not isinstance(capability.get("effectSemantics"), dict):
            issues.append(
                ValidationIssue(
                    code="capability-manifest.effect-semantics.missing",
                    severity="error",
                    artifact_type=manifest.artifact_type,
                    artifact_path=manifest.file_path,
                    path=f"/capabilities/{capability_id}/effectSemantics",
                    message=f"Capability {capability_id} must declare effectSemantics.",
                )
            )


def _validate_promotion_record(artifacts: list[LoadedArtifact], issues: list[ValidationIssue]) -> None:
    promotion_record = _find_artifact(artifacts, "promotion-record")
    if promotion_record is None:
        return

    for artifact_ref in _read_array(promotion_record.data.get("artifactRefs")):
        if isinstance(artifact_ref, dict) and _resolve_artifact_ref(artifact_ref, artifacts) is None:
            issues.append(
                ValidationIssue(
                    code="promotion-record.artifact-ref.missing",
                    severity="error",
                    artifact_type=promotion_record.artifact_type,
                    artifact_path=promotion_record.file_path,
                    path="/artifactRefs",
                    message=f"Promotion artifact reference {_stringify_artifact_ref(artifact_ref)} could not be resolved.",
                )
            )


def _find_artifact(artifacts: list[LoadedArtifact], artifact_type: str) -> LoadedArtifact | None:
    for artifact in artifacts:
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def _resolve_artifact_ref(ref: dict[str, Any], artifacts: list[LoadedArtifact]) -> LoadedArtifact | None:
    artifact_type = _read_string(ref, "artifactType")
    artifact_id = _read_string(ref, "artifactId")
    artifact_version = _read_string(ref, "artifactVersion")

    if not artifact_type or not artifact_id or not artifact_version:
        return None

    for artifact in artifacts:
        if (
            artifact.artifact_type == artifact_type
            and _read_string(artifact.data, "artifactId") == artifact_id
            and _read_string(artifact.data, "artifactVersion") == artifact_version
        ):
            return artifact
    return None


def _find_secret_like_paths(value: JSON_VALUE, prefix: str = "") -> list[str]:
    if isinstance(value, list):
        matches: list[str] = []
        for index, entry in enumerate(value):
            matches.extend(_find_secret_like_paths(entry, f"{prefix}/{index}"))
        return matches

    if not isinstance(value, dict):
        return []

    matches: list[str] = []
    for key, nested_value in value.items():
        next_prefix = f"{prefix}/{key}"
        if SECRET_LIKE_KEY.search(key):
            matches.append(next_prefix)
        matches.extend(_find_secret_like_paths(nested_value, next_prefix))
    return matches


def _stringify_artifact_ref(ref: dict[str, Any]) -> str:
    artifact_type = _read_string(ref, "artifactType") or "unknown-type"
    artifact_id = _read_string(ref, "artifactId") or "unknown-id"
    artifact_version = _read_string(ref, "artifactVersion") or "unknown-version"
    return f"{artifact_type}:{artifact_id}:{artifact_version}"


def _read_string(source: dict[str, Any] | None, key: str) -> str | None:
    if source is None:
        return None
    value = source.get(key)
    return value if isinstance(value, str) else None


def _read_object(source: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if source is None:
        return None
    value = source.get(key)
    return value if isinstance(value, dict) else None


def _read_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
