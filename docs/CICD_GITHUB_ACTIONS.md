# CI/CD with GitHub Actions (beginner-friendly)

← Back to [README](../README.md) · deploy targets: [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) · [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)

This explains the project's automation — the **CI** (test + lint on every change) and the
**CD** (build + deploy) — for someone who has never set up GitHub Actions.

## Contents

- [What is GitHub Actions?](#what-is-github-actions)
- [CI — test & lint on every change](#ci--test--lint-on-every-change)
- [Run the same checks locally](#run-the-same-checks-locally)
- [CD — deploy the backend to AWS](#cd--deploy-the-backend-to-aws)
- [Deploy the frontend](#deploy-the-frontend)
- [Troubleshooting](#troubleshooting)

## What is GitHub Actions?

GitHub Actions runs commands **for you on GitHub's servers** whenever something happens in
your repo (a push, a pull request, a schedule). You describe the work in a YAML file under
[`.github/workflows/`](../.github/workflows/); GitHub spins up a fresh virtual machine
("runner"), checks out your code, and runs your steps. You watch the results in the repo's
**Actions** tab.

Two common uses, both set up here:

- **CI (Continuous Integration):** every change automatically runs the tests and linter, so a
  mistake is caught in minutes — before it reaches `master`.
- **CD (Continuous Deployment):** when `master` is updated, automatically build the app image
  and ship it to your server.

## CI — test & lint on every change

The CI workflow lives in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). It triggers
on pushes to `master` and on every pull request, and runs three jobs in parallel:

| Job | What it does | Python |
| --- | --- | --- |
| **Lint (ruff)** | `ruff check` (bugs/style) + `ruff format --check` (formatting) across the libraries, app, and backend. | 3.12 |
| **Library tests** | `pytest tests/` — the five libraries' ~1,200 tests, across a **version matrix**. | 3.11, 3.12, 3.13, 3.14 |
| **App + backend tests** | `pytest apps/streamlit/tests apps/backend` — the Streamlit app and FastAPI backend. | 3.12 |

Design choices worth knowing:

- **The library matrix skips `torch`.** The heavy `[rerank]` extra (torch via
  sentence-transformers) is omitted; the re-ranking tests inject fakes / simulate its absence,
  so the full core suite still runs — much faster, and avoids waiting on torch wheels for new
  Python versions.
- **3.14 is "informational."** It is the aspirational ceiling; because some compiled wheels lag
  a brand-new Python, that matrix entry uses `continue-on-error` so it reports status without
  failing the whole run. Remove that once the ecosystem catches up.
- **`cancel-in-progress`** stops an outdated run when you push again, saving CI minutes.
- **No secrets are needed** for CI — tests mock all HTTP and never download models, so they run
  offline and deterministically.

### Where to see results

Open your repo → **Actions** tab → click a run to see each job's logs. A ✅ or ❌ also appears
next to each commit and on every pull request, with a required-checks gate you can enable in
**Settings → Branches**.

## Run the same checks locally

CI runs exactly what you can run yourself — do this before pushing to avoid red builds:

```bash
# lint (exactly what the "Lint" job runs)
python -m ruff check src/ tests/ apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/ apps/backend
python -m ruff format --check src/ tests/ apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/ apps/backend

# tests
python -m pytest tests/                 # libraries
python -m pytest apps/streamlit/tests   # app
python -m pytest apps/backend           # backend
```

(The project also exposes `test-runner` and `code-reviewer` agent skills for this — see the
repo's `.github/skills/`.)

## CD — deploy the backend to AWS

The workflow [`.github/workflows/deploy-backend.yml`](../.github/workflows/deploy-backend.yml)
builds the FastAPI backend image, pushes it to **Amazon ECR**, and rolls out your **ECS**
service. It is **inert until you opt in**, so it never fails for people who haven't set up AWS.

First create the AWS resources (one time) following the [AWS runbook](AWS_DEPLOYMENT.md): an ECR
repository and an ECS cluster + service running the backend image.

Then connect GitHub to AWS **without long-lived keys**, using OIDC:

1. **Add GitHub as an identity provider** in AWS IAM → Identity providers → add
   `token.actions.githubusercontent.com` (OpenID Connect).
2. **Create an IAM role** the workflow assumes, trusted by *only* this repo, e.g.:
   ```json
   {
     "Effect": "Allow",
     "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {
       "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
       "StringLike": { "token.actions.githubusercontent.com:sub": "repo:prakosd/rag-playground:ref:refs/heads/master" }
     }
   }
   ```
   Grant the role least-privilege permission to push to ECR and update the ECS service.
3. **Tell the workflow about your setup** in the repo's **Settings**:
   - **Secrets → Actions:** `AWS_DEPLOY_ROLE_ARN` = the role's ARN.
   - **Variables → Actions:** `AWS_REGION`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, and
     finally `DEPLOY_BACKEND` = `true` to **arm** the workflow.
4. **Push to `master`** (or run it manually from the Actions tab). It builds, pushes
   `:<commit-sha>` and `:latest` to ECR, and forces a new ECS deployment that pulls `:latest`
   (point your ECS task definition at the `:latest` tag).

Until `DEPLOY_BACKEND` is `true`, the job is skipped — safe to merge immediately.

## Deploy the frontend

The Streamlit UI deploys the **easiest** way of all: **Streamlit Community Cloud auto-deploys
from GitHub.** There is no workflow to write — every push to the connected branch redeploys.

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub and pick this repo.
2. Set the entry point to `apps/streamlit/streamlit_app.py`.
3. Add secrets in the app's **Settings → Secrets** (`.streamlit/secrets.toml` format): any
   `AWS_*` / `OPENAI_API_KEY` you need, and — for the **Tier 2 split** — `BACKEND_MODE="http"`
   plus `BACKEND_URL="https://<your-aws-backend>"` so the hosted UI calls your AWS backend
   instead of running compute itself (see
   [AWS_DEPLOYMENT.md § Tier 2](AWS_DEPLOYMENT.md#tier-2--split-frontend-and-backend-scale-out)).

**Optional smoke test.** To get alerted if a deploy breaks, add a tiny scheduled workflow that
pings the health endpoint (see [HEALTH_CHECK.md](HEALTH_CHECK.md)); it stays inert until you set
a `HEALTHCHECK_URL` repo variable:

```yaml
# .github/workflows/smoke-test.yml
name: Smoke test
on:
  workflow_dispatch:
  schedule: [{ cron: "0 * * * *" }] # hourly
jobs:
  ping:
    runs-on: ubuntu-latest
    if: ${{ vars.HEALTHCHECK_URL != '' }}
    steps:
      - run: curl --fail --silent --show-error "${{ vars.HEALTHCHECK_URL }}"
```

## Troubleshooting

- **A job fails only on 3.14** → likely a missing compiled wheel for that brand-new Python;
  it is informational (see above). Confirm 3.11–3.13 are green.
- **"ruff format --check" fails** → run `python -m ruff format src/ tests/ apps/streamlit/streamlit_app.py apps/streamlit/app_pages/ apps/streamlit/src/ apps/streamlit/tests/ apps/backend`
  locally and commit the result.
- **Tests pass locally but fail in CI** → ensure you did not rely on a locally-installed model
  or network; CI is offline by design.
