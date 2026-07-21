<p align="center">
  <img src="frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

# Security Policy

## Current support boundary

Academic Roundtable is a local, single-user learning MVP. It is not hardened for internet-facing, shared, clinical, legal, or other high-stakes production use.

## Reporting a vulnerability

For a GitHub-hosted repository, use GitHub's private vulnerability-reporting or security-advisory channel when enabled. Do not publish credentials, private transcripts, uploaded source content, or exploit details in a public issue. If no private channel is configured, contact the repository owner privately before disclosing details.

## Credential handling

- Store real credentials only in `.env.local` or another ignored local secret store.
- Never commit `.env.local`, `.env`, logs, databases, exported sessions, or uploaded sources.
- Use `.env.example` only for empty placeholders and non-secret defaults.
- Revoke and replace any credential that may have entered a commit, build artifact, screenshot, log, or issue.
- Before publishing, scan the entire Git history, not only the current working tree.

## Deployment warning

Before any shared deployment, add authentication, authorization, per-user isolation, HTTPS, deployment secret management, request and upload controls, malware scanning, durable migrations, security headers, audit logging, retention controls, and tested backup/recovery procedures.
