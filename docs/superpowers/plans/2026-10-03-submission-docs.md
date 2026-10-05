> HISTORICAL PLAN / SPEC: retained for design history, not current runtime status.
> See [current documentation](../../README.md) for implementation, commands and evidence.

# Submission Documentation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline. Documentation only; no runtime changes.

**Goal:** Complete required submission documentation against the existing implementation.

**Architecture:** Preserve the application and describe its existing service, policy lifecycle and isolated simulation. Keep the modality lifecycle document as the detailed reference.

**Tech Stack:** Markdown, Mermaid, Docker Compose, GitHub Actions.

**Spec:** User-required README, architecture, contribution roles, dependencies, containers and CI/CD documentation.

## Constraints

- Preserve secrets, runtime data and untracked `docs/architecture/`.
- Work from the rewritten FSB history; do not alter personal remote history.
- Do not claim clean-install production readiness, encoder training or real-user benchmark evidence.

## Tasks

- [x] Update README with fresh-install prerequisites, safe environment setup, dependency profiles, service startup, usage, verification and initial champion limitations.
- [x] Replace placeholder contribution roles with named responsibilities and review/delivery expectations; distinguish ownership from historical authorship evidence.
- [x] Update architecture and overview diagrams for independent policy lifecycle, persistence, template updates, simulation and deployment boundaries.
- [x] Align deployment and operations instructions with lifecycle rollback, current runner and CI jobs.
- [x] Validate relative documentation links, referenced paths, Mermaid diagrams where tooling is available, configuration consistency and `git diff --check`; record limits without modifying runtime.

## Verification

- All 42 relative links and linked Markdown heading anchors resolve across the six updated documents.
- Mermaid CLI 11.12.0 rendered both architecture diagrams and the overview diagram successfully using headless Chrome. Generated files stay under gitignored `reports/submission-docs/`.
- `docker compose --env-file .env.example config --quiet` and `git diff --check` pass.
- Compared commands, endpoints, DAG schedules/task counts, lifecycle thresholds and rollout descriptions with source/configuration.
- No application changes or new runtime tests. Did not start a fresh installation, send alerts, deploy or re-run biometric validation.
- Documented two existing limits: initial evaluated production champion setup is not automated, and the current modality candidate endpoint does not enforce the legacy fairness flag.
