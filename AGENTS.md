# Project documentation

- [Project plan](docs/plans/technology-graph-plan.md)
- [Data reference](docs/data-reference.md): the terms (breakthrough, milestone, link…) and every data field, where it is written and where it is used
- [Atlas core design](docs/plans/2026-11-09-atlas-core-design.md): the record kinds and `atlas/core/` files that are the source of truth
- [Site design](docs/plans/2026-11-11-site-design.md): pages, reading rules and look of the v1 website
- [Field onboarding runbook](docs/runbooks/Field_Onboarding_Runbook.md)
- [Publishing runbook](docs/runbooks/Publishing_Runbook.md): pre-publish prep (secret scan, history clean-up, license), Cloudflare Pages deploy, contributor guide and CI drafts
- [Ingestion pipeline](ingestion/README.md)
- [Detailed ingestion status and recovery report](docs/ingestion-status-2026-11-01.md)
- [Technology Atlas v1 — run and test](atlas/README.md)

# Code style

- Python: one statement per line, lines up to 100 characters, single quotes. Run `ruff format atlas ingestion` before committing (config in `ruff.toml`).
- Prompts, SQL and schemas are data: wrapping a long string must not change its value.
- Tests: `python3 -m unittest discover -s atlas/tests`; ingestion tests need `jsonschema` (`/opt/homebrew/Caskroom/miniforge/base/bin/python -m unittest discover -s ingestion/tests`).
