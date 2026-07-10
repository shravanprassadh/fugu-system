# Branch protection contract

The workflow in `.github/workflows/ci.yml` reports objective validation status only. Repository merge enforcement must be configured separately in GitHub branch protection or repository rulesets.

## Protected branch

Apply the ruleset to:

- `main`

Feature branches are temporary and must not receive separate long-lived protection rules.

## Required status check

Require this stable aggregate check before merge:

- `Infrastructure Continuous Integration Gate / Required CI Gate`

The aggregate gate fails unless all of these jobs complete successfully:

- `Security & Secret Auditing`
- `Backend Lint, Type Check, Tests & Audit`
- `Frontend Lint, Tests, Build & Audit`
- `Production Container & Runtime Validation`

## Required repository settings

Enable:

- Require a pull request before merging
- Require status checks to pass before merging
- Require branches to be up to date before merging
- Require conversation resolution before merging
- Do not allow bypassing the above settings
- Block force pushes
- Block branch deletion

Keep deployment checks separate from this CI contract until deployment validation is added to the required gate.

## Security thresholds

- Python: `pip-audit` fails on any known vulnerability in the resolved requirements graph.
- npm: `npm audit` fails on `high` or `critical` vulnerabilities.
- Secrets: verified TruffleHog findings fail the workflow. Tracked environment files, private-key files, and known credential prefixes are rejected independently by the repository policy scan.

## Action and runtime pinning

Third-party and GitHub-maintained actions are referenced by immutable commit SHA. Runtime versions and audit-tool versions are explicit in the workflow. Updates must be reviewed as code changes rather than inherited automatically from floating action tags.
