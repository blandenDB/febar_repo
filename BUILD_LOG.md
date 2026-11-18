# Build Log

| Date | What I tried | What failed | What I changed and why |
|---|---|---|---|
| 2026-11-18 | Wrote FEBAR_CONTEXT.md, CLAUDE.md pointer and .gitignore; cloned the GitHub repo | My FEVM account had no active workspaces, and the old banking demo workspace has likely expired | Prepared a new AWS Stable Serverless FEVM request |
| 2026-11-18 | Checked whether the FEVM workspace can create a catalog | The workspace is admin only on the workspace, not on the regional metastore, so `CREATE CATALOG` will probably fail | Chose catalog `c360_bank` and schema `customer_lifetime_value`, and recorded it in DECISIONS.md |
| 2026-11-18 | Submitted FEVM workspace `febar-c360-bank` (AWS Stable Serverless, us-west-2, 30 days). Resource ID 01a1ef6a-e164-72d6-9837-24fc5ac81c54 | (none so far; state Pending) | Expires 2026-12-18; request an extension before then if needed |
