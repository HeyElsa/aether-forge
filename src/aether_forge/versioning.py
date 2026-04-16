"""Artifact versioning and compatibility utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import validate_artifact_directory


@dataclass(frozen=True, order=True, slots=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        parts = value.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid semantic version: {value}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(slots=True)
class ArtifactCompatibilityAssessment:
    artifact_type: str
    artifact_id: str
    previous_version: str
    current_version: str
    declared_status: str
    recommended_status: str
    migration_required: bool
    migration_present: bool
    ok: bool
    issues: list[str]


@dataclass(slots=True)
class ArtifactSetCompatibilityResult:
    ok: bool
    assessments: list[ArtifactCompatibilityAssessment]
    issues: list[str]


@dataclass(slots=True)
class ArtifactMigrationPlan:
    artifact_type: str
    artifact_id: str
    previous_version: str
    current_version: str
    contract: dict[str, Any]


def assess_artifact_set_compatibility(
    previous_directory: str | Path,
    current_directory: str | Path,
) -> ArtifactSetCompatibilityResult:
    previous = validate_artifact_directory(previous_directory)
    current = validate_artifact_directory(current_directory)

    issues: list[str] = []
    assessments: list[ArtifactCompatibilityAssessment] = []

    if not previous.ok:
        issues.append("Previous artifact directory failed validation.")
        issues.extend(_format_validation_issues(previous.issues))
    if not current.ok:
        issues.append("Current artifact directory failed validation.")
        issues.extend(_format_validation_issues(current.issues))
    if issues:
        return ArtifactSetCompatibilityResult(ok=False, assessments=[], issues=issues)

    previous_by_type = {artifact.artifact_type: artifact.data for artifact in previous.artifacts}
    current_by_type = {artifact.artifact_type: artifact.data for artifact in current.artifacts}
    shared_types = sorted(set(previous_by_type) & set(current_by_type))

    for artifact_type in shared_types:
        assessment = assess_artifact_compatibility(previous_by_type[artifact_type], current_by_type[artifact_type])
        assessments.append(assessment)
        if not assessment.ok:
            issues.extend(f"{artifact_type}: {issue}" for issue in assessment.issues)

    for artifact_type in sorted(set(previous_by_type) - set(current_by_type)):
        issues.append(f"Current artifact set is missing artifact type {artifact_type}.")
    for artifact_type in sorted(set(current_by_type) - set(previous_by_type)):
        issues.append(f"Current artifact set adds new artifact type {artifact_type}; compatibility should be reviewed.")

    return ArtifactSetCompatibilityResult(
        ok=len(issues) == 0,
        assessments=assessments,
        issues=issues,
    )


def assess_artifact_compatibility(previous: dict[str, Any], current: dict[str, Any]) -> ArtifactCompatibilityAssessment:
    issues: list[str] = []
    previous_type = str(previous.get("artifactType", "unknown"))
    current_type = str(current.get("artifactType", "unknown"))
    previous_id = str(previous.get("artifactId", "unknown"))
    current_id = str(current.get("artifactId", "unknown"))
    previous_version = str(previous.get("artifactVersion", "0.0.0"))
    current_version = str(current.get("artifactVersion", "0.0.0"))

    if previous_type != current_type:
        issues.append(f"artifact type changed from {previous_type} to {current_type}")
    if previous_id != current_id:
        issues.append(f"artifact id changed from {previous_id} to {current_id}")

    previous_semver = SemanticVersion.parse(previous_version)
    current_semver = SemanticVersion.parse(current_version)

    declared_status = str(compatibility.get("status", "unknown")) if isinstance((compatibility := current.get("compatibility", {})), dict) else "unknown"
    previous_declared = compatibility.get("previousArtifactVersion") if isinstance(compatibility, dict) else None
    migration_present = isinstance(compatibility.get("migrationRef"), dict) if isinstance(compatibility, dict) else False

    if current_semver == previous_semver:
        if current != previous:
            issues.append("artifact content changed without an artifactVersion bump")
        return ArtifactCompatibilityAssessment(
            artifact_type=current_type,
            artifact_id=current_id,
            previous_version=previous_version,
            current_version=current_version,
            declared_status=declared_status,
            recommended_status=declared_status,
            migration_required=False,
            migration_present=migration_present,
            ok=len(issues) == 0,
            issues=issues,
        )

    if current_semver < previous_semver:
        issues.append("current artifact version must be greater than the previous artifact version")

    if previous_declared != previous_version:
        issues.append(
            f"compatibility.previousArtifactVersion should point to {previous_version}, found {previous_declared}"
        )

    recommended_status = _recommended_compatibility_status(previous_semver, current_semver)
    migration_required = recommended_status == "breaking"

    if declared_status != recommended_status:
        issues.append(
            f"declared compatibility status {declared_status} does not match recommended status {recommended_status}"
        )
    if migration_required and not migration_present:
        issues.append("breaking version changes should provide a migrationRef")

    return ArtifactCompatibilityAssessment(
        artifact_type=current_type,
        artifact_id=current_id,
        previous_version=previous_version,
        current_version=current_version,
        declared_status=declared_status,
        recommended_status=recommended_status,
        migration_required=migration_required,
        migration_present=migration_present,
        ok=len(issues) == 0,
        issues=issues,
    )


def format_compatibility_result(result: ArtifactSetCompatibilityResult) -> str:
    lines: list[str] = []
    for assessment in result.assessments:
        lines.append(
            f"{assessment.artifact_type}: {assessment.previous_version} -> {assessment.current_version} "
            f"declared={assessment.declared_status} recommended={assessment.recommended_status} ok={assessment.ok}"
        )
        for issue in assessment.issues:
            lines.append(f"  - {issue}")
    for issue in result.issues:
        if not issue.startswith(tuple(artifact.artifact_type for artifact in result.assessments)):
            lines.append(f"- {issue}")
    return "\n".join(lines) if lines else "No compatibility issues found."


def build_artifact_migration_plan(
    previous_directory: str | Path,
    current_directory: str | Path,
    artifact_type: str,
) -> ArtifactMigrationPlan:
    previous = validate_artifact_directory(previous_directory)
    current = validate_artifact_directory(current_directory)

    if not previous.ok or not _only_has_ignorable_migration_issues(current, artifact_type):
        issues: list[str] = []
        if not previous.ok:
            issues.extend(_format_validation_issues(previous.issues))
        if not _only_has_ignorable_migration_issues(current, artifact_type):
            issues.extend(_format_validation_issues(current.issues))
        raise ValueError("Cannot build a migration plan from invalid artifact directories:\n" + "\n".join(issues))

    previous_artifact = next((artifact.data for artifact in previous.artifacts if artifact.artifact_type == artifact_type), None)
    current_artifact = next((artifact.data for artifact in current.artifacts if artifact.artifact_type == artifact_type), None)

    if previous_artifact is None:
        raise ValueError(f"Previous artifact directory does not contain artifact type {artifact_type}")
    if current_artifact is None:
        raise ValueError(f"Current artifact directory does not contain artifact type {artifact_type}")

    previous_version = str(previous_artifact.get("artifactVersion", "0.0.0"))
    current_version = str(current_artifact.get("artifactVersion", "0.0.0"))
    differences = diff_artifact_content(previous_artifact, current_artifact)

    transform_steps = [
        f"review changed field {path}" for path in sorted(differences["changed_paths"])
    ] + [
        f"map removed field {path} into a new location or archive decision" for path in sorted(differences["removed_paths"])
    ] + [
        f"initialize new field {path} with safe defaults or derived values" for path in sorted(differences["added_paths"])
    ]

    if not transform_steps:
        transform_steps.append("no semantic changes detected; migration may be unnecessary")

    validation_checks = [
        f"validate artifact type remains {artifact_type}",
        f"validate artifactVersion migrated from {previous_version} to {current_version}",
    ]
    if differences["removed_paths"]:
        validation_checks.append("validate all lossy field removals are intentional")
    if differences["changed_paths"]:
        validation_checks.append("validate changed fields preserve behavioral intent")

    contract = {
        "fromVersion": previous_version,
        "toVersion": current_version,
        "transformSteps": transform_steps,
        "lossyFields": sorted(differences["removed_paths"]),
        "validationChecks": validation_checks,
    }

    return ArtifactMigrationPlan(
        artifact_type=artifact_type,
        artifact_id=str(current_artifact.get("artifactId", "unknown")),
        previous_version=previous_version,
        current_version=current_version,
        contract=contract,
    )


def diff_artifact_content(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, set[str]]:
    added_paths: set[str] = set()
    removed_paths: set[str] = set()
    changed_paths: set[str] = set()
    ignored_root_fields = {"artifactVersion", "compatibility", "generator", "provenance"}

    def walk(previous_value: Any, current_value: Any, path: str) -> None:
        if isinstance(previous_value, dict) and isinstance(current_value, dict):
            previous_keys = set(previous_value)
            current_keys = set(current_value)

            for key in sorted(previous_keys - current_keys):
                removed_paths.add(f"{path}/{key}" if path else f"/{key}")
            for key in sorted(current_keys - previous_keys):
                added_paths.add(f"{path}/{key}" if path else f"/{key}")
            for key in sorted(previous_keys & current_keys):
                walk(previous_value[key], current_value[key], f"{path}/{key}" if path else f"/{key}")
            return

        if isinstance(previous_value, list) and isinstance(current_value, list):
            if previous_value != current_value:
                changed_paths.add(path or "/")
            return

        if previous_value != current_value:
            changed_paths.add(path or "/")

    filtered_previous = {key: value for key, value in previous.items() if key not in ignored_root_fields}
    filtered_current = {key: value for key, value in current.items() if key not in ignored_root_fields}
    walk(filtered_previous, filtered_current, "")

    return {
        "added_paths": added_paths,
        "removed_paths": removed_paths,
        "changed_paths": changed_paths,
    }


def _format_validation_issues(issues: list[Any]) -> list[str]:
    formatted: list[str] = []
    for issue in issues:
        location = f" {issue.path}" if getattr(issue, "path", None) else ""
        formatted.append(f"{issue.code}:{location} {issue.message}")
    return formatted


def _only_has_ignorable_migration_issues(result: Any, artifact_type: str) -> bool:
    if result.ok:
        return True

    for issue in result.issues:
        if getattr(issue, "artifact_type", None) != artifact_type:
            return False

        issue_path = getattr(issue, "path", "") or ""
        if issue.code == "compatibility.migration.missing" and issue_path == "/compatibility/migrationRef":
            continue
        if issue.code == "schema.type" and "compatibility.migrationRef" in issue_path:
            continue
        return False

    return True


def _recommended_compatibility_status(previous: SemanticVersion, current: SemanticVersion) -> str:
    if current.major != previous.major:
        return "breaking"
    return "backward-compatible"
