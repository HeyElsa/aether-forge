"""Credential resolution for crypto capabilities."""

from __future__ import annotations

from typing import Any, Protocol

from .types import CredentialLease


class CredentialResolver(Protocol):
    def resolve(self, handle_id: str, environment: str, capability_manifest: dict[str, Any]) -> CredentialLease: ...


class ManifestCredentialResolver:
    def resolve(self, handle_id: str, environment: str, capability_manifest: dict[str, Any]) -> CredentialLease:
        for handle in capability_manifest.get("credentialHandles", []):
            if handle.get("handleId") != handle_id:
                continue

            if environment not in set(handle.get("allowedEnvironments", [])):
                raise ValueError(f"credential handle {handle_id} is not allowed in environment {environment}")

            return CredentialLease(
                handle_id=handle_id,
                environment=environment,
                maximum_access_scope=dict(handle.get("maximumAccessScope", {})),
                metadata={
                    "kind": handle.get("kind"),
                    "rotationExpectation": handle.get("rotationExpectation"),
                    "ttlPolicy": handle.get("ttlPolicy"),
                },
            )

        raise ValueError(f"credential handle {handle_id} was not found in capability manifest")
