# Documentation audit - 2026-10-05

Scope: repository documentation, Markdown guides, plans/specs, presentation sources
and exports, generators, local architecture drafts and references. Runtime data,
secrets, model weights, original assignment files and vendor attribution are not
documentation cleanup targets. Existing simulation changes are preserved.

## Decisions

| Component | Finding | Resolution |
|---|---|---|
| Root navigation | No single current/history map | Add `docs/README.md` with canonical owners and source precedence |
| PROJECT_REPORT / RUBRIC_MAPPING | Fixed champion, old run/counts, direct promotion, Windows runner, legacy 20% gate | Rewrite against independent policy lifecycle and scoped evidence |
| PROJECT_REQUIREMENTS / SCALABILITY_COST | Legacy gate and ambiguous session/request capacity | Distinguish CV selection from rollout budgets; size by concurrent captures |
| MONITORING_MAPPING / OPERATIONS | Seven old dashboard groups and outdated runner instructions | Document ten-panel overview plus ten-panel simulation; Explore and authenticated reports separately |
| DEPLOYMENT | Claims private overlay disables all simulation; changing tenant env enables customer training | State actual legacy flag scope and code restriction to demo tenant |
| RESPONSIBLE_AI | Claims fairness flag blocks new lifecycle and full appeal/retention coverage | Record enforcement gap, actual observations, human labels and unimplemented controls |
| Architecture / lifecycle / continuous MLOps | Stale links and overbroad panel/aging claims | Match current datasources, method heuristic, defaults and 100+100 observation requirement |
| DEMO_HANDOVER_GUIDE | Long duplicate of obsolete monitoring/runbook | Replace with short service map and links to canonical operation/demo guides |
| PROJECT_STATE | Historic continuation notes presented at root | Move to `docs/archive/PROJECT_STATE_2026-09-29.md`, mark historical and repair links |
| Plans/specs | Completed/intermediate designs read as current instructions | Keep paths and content; prepend historical status and current index link |
| Presentation | Source says 15+13+10 minutes but script says 10 minutes/no demo; binary order/export differs | Regenerate 38-minute script from source, fix source references, update demo monitoring instructions |
| PPTX/PDF | Export snapshots contain deleted references and manual slide edits | Preserve binary contents unchanged in `docs/archive/presentation-2026-10-04/`; explicitly label historical |
| Old 12-slide generator | Recreates a removed, stale deck alongside current builder | Remove `pipeline/build_presentation.py`; retain single classroom JSON/builder path |
| Current generators | Hard-coded update dates / obsolete output location | Read presentation date from source; report PDF goes to ignored `reports/` with source footer |
| Evidence | Deleted VERIFICATION.md linked as current proof | Add `docs/EVIDENCE.md`, preserving run dates and scope; no claim of a new execution |
| Local `docs/architecture/` | Pre-existing untracked HLD has old lifecycle and local figures | Preserve draft contents/assets, add status notice; current design is ARCHITECTURE + ARCHITECTURE_OVERVIEW |
| Assignment / vendor / dependency manifests | Required originals, attribution or runtime inputs | Preserve; no removal based on age |

## Verification for this documentation change

Completed local checks: 39 Markdown files, 281 relative links/heading anchors with
zero unresolved targets, presentation source paths and the 15/13/10-minute schedule
across 33 slides. Source checks confirm seven model DAG tasks with no schedule and
ten Prometheus panels in each dashboard. The speaker script was regenerated from
JSON; syntax, Ruff and `git diff --check` passed for the documentation changes.
SHA-256 comparisons against Git HEAD confirm all three archived PPTX/PDF files
are byte-for-byte unchanged. Local results are saved in the ignored
`reports/documentation-audit-20261005.json` (not available on a fresh clone).

External links and runtime health are not established by local path checks. No new
CI deployment, human benchmark, simulation traffic, Telegram message or retrain is
required for this documentation audit. Historical exports are not re-rendered or
presented as newly verified artifacts. Before distributing a new PPTX/PDF, build
from current sources and visually review the resulting pages/slides.

Current facts were checked against `pipeline/lifecycle_config.json`, the three
DAGs, `.github/workflows/ci.yml`, Compose/private overlay, drift/observation/lifecycle
code, collectors and dashboard JSON. Evidence provenance remains separate in
[EVIDENCE](EVIDENCE.md). See [index](README.md) for the maintained guides.
