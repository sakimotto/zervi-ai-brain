# Saki AI Release Workflow

The single source of truth for Saki AI release management lives in the `odoo-local` repository:

**→ [sakimotto/odoo-local/blob/main/RELEASE_WORKFLOW.md](../odoo-local/blob/main/RELEASE_WORKFLOW.md)**

This repo (`zervi-ai-brain`) follows the same branch strategy:

- `develop` — integration branch.
- `main` — production branch.
- Feature/fix branches from `develop`.
- PR checks: Python compile + pytest.
- Stage deploy: auto on every `develop` push via `.github/workflows/deploy-stage.yml`.
- Production deploy: manual `workflow_dispatch` of `.github/workflows/deploy-prod.yml` on `main`.

When releasing a brain change to production, remember to update the `ai_brain` submodule pointer in `odoo-local` afterwards so the released Odoo module is pinned to a known brain commit.
