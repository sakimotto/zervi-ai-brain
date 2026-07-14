# Saki AI Release Workflow

The single source of truth for Saki AI release management lives in the `odoo-local` repository:

**→ [sakimotto/odoo-local/blob/main/RELEASE_WORKFLOW.md](../odoo-local/blob/main/RELEASE_WORKFLOW.md)**

This repo (`zervi-ai-brain`) follows the same branch strategy:

- `develop` — integration branch.
- `main` — production branch.
- Feature/fix branches from `develop`.
- PR checks: Python compile + pytest.
- Production deploy: manual `workflow_dispatch` of `.github/workflows/deploy-prod.yml` on `main`.

When releasing a brain change to production, remember to update the `ai_brain` submodule pointer in `odoo-local` afterwards so the released Odoo module is pinned to a known brain commit.

## Known Issues

- The `deploy-stage.yml` GitHub Action is currently failing because the repository secret `ELESTIO_STAGE_SSH_KEY` is empty. Stage deploys must be done manually via SSH to the Elestio VM until the secret is configured.
