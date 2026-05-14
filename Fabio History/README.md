# Fabio History

This folder holds **archival and reference material** for the Fabio / ORBit bot project: educational PDFs, non-sensitive snapshots, and other files you deliberately keep in Git for context.

## What belongs here

- Public-safe educational or policy PDFs.
- Redacted or synthetic examples (not live account data).

## What must **not** be committed

Follow the repo-wide rules in [`portal/docs/CONFIDENTIAL_DATA_AUDIT.md`](../portal/docs/CONFIDENTIAL_DATA_AUDIT.md): no `.env`, credentials, live logs, broker snapshots, or proprietary backtest outputs. Large generated CSVs, `*.log`, and runtime JSONL belong in `.gitignore`, not here.

## Paths with spaces

This directory name contains a space. In shells use quotes, for example:

```bash
cd "Fabio History"
```
