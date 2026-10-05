# Contributing and team roles

## Team ownership

This is the team's responsibility and handover allocation. Ownership is not proof
of who originally authored an existing change. Git author/committer metadata alone,
including rewritten history, does not establish meaningful individual contribution.
Use actual work, PR discussions, reviews and demonstrations as evidence.

| Member | Responsibility | Deliverables and scope | Cross-review |
|---|---|---|---|
| Trinh Duc Duong | Project lead, core architecture, biometric service and ML lifecycle | Maintain product scope and core Face/Voice verification, tenant isolation, data contracts, drift decision rules, template lifecycle, threshold calibration, independent MLflow policies and simulation design; integrate and review changes | Review ML/security behavior and final integration |
| Do Quang Hiep | Quality assurance, evaluation validation and reproducibility | Own unit/integration regression checks, held-out evaluation validation, customer/employee flows, monitoring verification, test evidence and reproducible local checks; maintain test matrix and investigate failures | Review Hai's deployment changes and Duc's technical evidence |
| To Thanh Hai | Platform, CI/CD and runtime operations | Own Docker/Compose, WSL-to-Windows runner bridge, exact-SHA staging, health/warmup handling, deployment preflight, operational recovery and platform/portal integration fixes | Review Hiep's automation and deployment-related documentation |
| Ngo Anh Duc | Report, presentation, architecture diagrams and documentation | Own PROJECT_REPORT.md, DEMO_PRESENTATION.md, architecture diagrams, integration/business narrative, evidence index and submission consistency; explain current design and limits with review from implementation owners | Review user guides and coordinate report/presentation review with Duong |

Every member must demonstrate their area and explain the full request-to-decision
and drift-to-rollout flow. Hiep owns technical verification rather than leaving that
work to Duc; Hai owns platform recovery so Duc can focus on report, slides and diagrams.

Each task/PR should identify its owner, acceptance criteria, changed files, actual
validation and reviewer. For final handover, link those PRs and reports from the team
report; distinguish planned ownership from completed, verified work. Do not present
synthetic simulation metrics as real-user accuracy.

## Branches, commits and review

The team repository is https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring.
The following example uses a remote named `fsb`; a fresh clone normally calls it
`origin`, so inspect `git remote -v` and use the remote that points to the team repo.

```bash
git fetch fsb
git switch -c docs/update-lifecycle-guide fsb/main
# Make and inspect your own changes, then stage specific files.
git diff --check
git add README.md
git commit -m "docs: clarify first-install readiness requirements"
git push -u fsb docs/update-lifecycle-guide
```

Use `feat/<topic>`, `fix/<topic>`, `test/<topic>` or `docs/<topic>` branches and PRs
into `main`; require passing applicable CI and at least one reviewer from another
area. This is the team process, not a claim that GitHub branch protection is enabled.
Messages should describe the concrete change, for example
`fix: preserve champion routing after a failed canary gate`.

Configure your own Git name/email, use an email linked to your GitHub account,
and make small, meaningful commits representing work you actually performed.
Do not rewrite other members' history as part of ordinary contribution. After the
team history rewrite, start from current `fsb/main`; do not merge the old pre-rewrite
branch back into it. The personal repository has separate history and is not the
target for team branch pushes.

## Development checks

Use Python 3.11 and the dependency profiles in [README.md](README.md). After installing
`requirements.txt` and `requirements-dev.txt`, run from the repository root:

```bash
python -m ruff check api pipeline monitoring tests legacy_demo
python -m compileall -q api pipeline monitoring airflow/dags ui legacy_demo
python -m pytest -q
docker compose config --quiet
git diff --check
```

For documentation-only changes, validate referenced paths/links, commands against
their CLI implementation and Mermaid diagrams; a runtime test is not needed just
to change prose. If dashboards change, regenerate with
`python pipeline/build_dashboard.py` and `python pipeline/build_simulation_dashboard.py`, then inspect both generated JSON files. For presentation changes, update `docs/presentation/deck-content.json` and regenerate the speaker script; do not describe archived binary exports as synchronized current artifacts. Use [the documentation index](docs/README.md) to find each canonical guide.

CI in [.github/workflows/ci.yml](.github/workflows/ci.yml) is authoritative for
the coverage scope and threshold (80%). The Ubuntu quality job can skip Windows-only
deployment tests; `deployment-preflight` on Windows runs those tests separately and
rejects skips. Container builds wait for both jobs. Only eligible trusted `main`
runs deploy through the approved self-hosted runner. Markdown-only pushes to `main`
are excluded by the workflow path filter; PRs still trigger CI.

Include validation results, data/schema and rollback impact, and screenshots when
changing dashboards/UI. Review security/performance gates on both Face and Voice;
do not bypass them to obtain a green demo. Simulation evidence must identify the
scenario, modality, run, synthetic data and isolated registry.

## Data and secrets

Never commit `.env`, API keys, biometric media, weights, generated private reports,
database volumes or backups. Keep `docs/architecture/` local artifacts out of commits
unless explicitly reviewed for publication. Publish only sanitized evidence selected
for the submission. Preserve existing runtime data; do not use `docker compose down -v`
as a troubleshooting or simulation reset command.
