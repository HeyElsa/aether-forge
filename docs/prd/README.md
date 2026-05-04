# PRD Versioning

This directory contains the canonical Product Requirements Documents for `Aether Forge`.

## Current PRD

- Current version: `v0.20.0`
- Canonical file: `docs/prd/aether-forge-prd-v0.20.0.md`
- Change log: `docs/prd/CHANGELOG.md`

Note: v0.13.0 changes (security hardening, x402 client, data layer, generated-router data layer wiring, real-money live mode validation) live in the changelog only — they were merged into v0.14.0 as inherited baseline rather than written as a standalone PRD file. v0.19.0 (real on-chain agent-to-agent USDC transfers, two-agent marketplace) also lives only in the changelog.

## Source Hierarchy

Use these files in this order:

1. `docs/prd/aether-forge-prd-v0.20.0.md` (most current — DX & extensibility: public Protocols, plugin discovery, generator batteries, conftest, ARCHITECTURE.md)
2. `docs/prd/aether-forge-prd-v0.18.0.md` (docs site, cloud LLM, branding, demo)
3. `docs/prd/CHANGELOG.md` (v0.17.0 + v0.18.0 + v0.19.0 + v0.20.0 entries)
4. `docs/prd/aether-forge-prd-v0.15.0.md`
4. `docs/prd/aether-forge-prd-v0.14.0.md`
4. `docs/prd/aether-forge-prd-v0.12.0.md`
4. `docs/prd/aether-forge-prd-v0.11.0.md`
5. `docs/prd/aether-forge-prd-v0.10.0.md`
6. `docs/prd/aether-forge-prd-v0.9.0.md`
7. `docs/prd/aether-forge-prd-v0.8.0.md`
8. `docs/prd/aether-forge-prd-v0.7.0.md`
9. `docs/prd/aether-forge-prd-v0.6.0.md`
10. `docs/prd/aether-forge-prd-v0.5.0.md`
11. `docs/prd/aether-forge-prd-v0.4.0.md`
12. `docs/prd/aether-forge-prd-v0.3.0.md`
13. `docs/prd/aether-forge-prd-v0.2.0.md`
14. `docs/prd/aether-forge-prd-v0.1.0.md`
15. `docs/prd/CHANGELOG.md`
16. `docs/plans/2026-04-06-aether-forge-research.md`
17. `docs/plans/2026-04-06-aether-forge-prd-autoresearch.md`
18. `docs/plans/2026-04-06-aether-forge-prd-exact-autoresearch.md`
19. `docs/plans/2026-04-06-aether-forge-design.md`

The files under `docs/plans/` are supporting research, ideation, and design drafts.
The files under `docs/prd/` are the canonical product documents.

## Versioning Rules

Use semantic versioning for PRD updates.

### Patch bump

Use a patch bump for:

- wording clarifications
- examples and readability improvements
- small requirement clarifications that do not change product intent
- metadata or formatting fixes

Example: `v0.1.0` -> `v0.1.1`

### Minor bump

Use a minor bump for:

- scope expansion or reduction
- new product modules or environments
- meaningful requirement changes
- roadmap or milestone changes
- new user types or new jobs-to-be-done

Example: `v0.1.0` -> `v0.2.0`

### Major bump

Use a major bump for:

- repositioning the product
- changing the core user
- changing the spec-first or safety-first model
- changing the core architecture or lifecycle in a fundamental way

Example: `v0.1.0` -> `v1.0.0`

## Update Checklist

Whenever the PRD changes:

1. Create a new versioned PRD file instead of overwriting history.
2. Update the version, date, and status in the new PRD file.
3. Add a summary entry to `docs/prd/CHANGELOG.md`.
4. Update the `Current version` and `Canonical file` lines in this file.
5. If the design draft is no longer the latest source, keep its superseded note accurate.
6. Update `AGENTS.md` if the working rules or non-negotiables changed.

## Naming Convention

Use this file pattern for future versions:

`docs/prd/aether-forge-prd-vX.Y.Z.md`

## Status Values

Recommended status values:

- `Draft`
- `Proposed`
- `Approved`
- `Superseded`

## Notes

- Do not delete older PRD versions.
- Do not rewrite history inside the changelog.
- If a change affects product behavior, capture the reasoning in the new PRD version, not only in a commit message.
