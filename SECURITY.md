# Security Policy

## Supported versions

This project is under active development. Security fixes are applied to the `main`
branch. There is no long-term-support branch yet.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, use one of the following private channels:

- Open a private report via GitHub Security Advisories
  ("Report a vulnerability" in the repository's **Security** tab), or
- Email the maintainer at **bingweichenapply@gmail.com** with the subject line
  `[SECURITY] Requirement Workbench`.

Please include:

- a description of the issue and its impact,
- steps to reproduce (proof-of-concept if possible),
- affected version/commit, and
- any suggested remediation.

We aim to acknowledge reports within **5 business days** and to provide a remediation
timeline after triage. Please give us reasonable time to fix the issue before any
public disclosure.

## Handling secrets

- Never commit real credentials. `backend/.env.local` is git-ignored; only
  `backend/.env.local.example` (placeholders) is tracked.
- If you believe a credential was committed, report it privately as above so we can
  rotate it.
