<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

# GitHub Release Checklist

## Required before the first push

- [ ] Decide whether the repository is private or public.
- [ ] Choose and add an explicit license if distribution or contribution is intended.
- [ ] Initialize Git in the GitHub-ready copy, not in a folder containing unrelated work.
- [ ] Confirm `.env.local` is ignored and absent from `git status` and `git ls-files`.
- [ ] Scan the full candidate commit and history for secrets.
- [ ] Confirm `data/`, uploads, exports, logs, dependencies, caches, and build artifacts are untracked.
- [ ] Run 24 backend tests and the frontend production build from the clean copy.
- [ ] Review README limitations and security warnings.
- [ ] Configure private vulnerability reporting before inviting outside users.

## Suggested repository settings

- Protect the default branch and require the CI workflow.
- Require pull requests for changes to the default branch.
- Enable secret scanning and push protection when available.
- Disable unnecessary workflow write permissions.
- Keep Actions permissions read-only by default.

## Local credential retained in the prepared copy

The prepared development copy may contain a local `.env.local` so it can be tested immediately. That file is intentionally excluded by `.gitignore` and the CI safety job rejects tracked local environment files. Before any push, verify its ignored status again; ignore rules do not remove a secret that was previously committed.
