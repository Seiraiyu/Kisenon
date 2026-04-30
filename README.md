# Kisenon

Branchable serverless Postgres. Cold endpoints wake on first connect, branches in seconds, pay storage only — idle compute is free.

**[kisenon.com](https://kisenon.com)** · alpha · invite-only · v0.9

This repository is the **public portal** for Kisenon. It tracks issues, hosts open-source examples and integration scripts, and is where you file bug reports or feature requests. The Kisenon platform itself runs as a managed service at kisenon.com; the platform source lives in a separate, private repository.

## Getting access

Kisenon is in invite-only alpha. Request access:

- Email **hello@kisenon.com** with the subject `Alpha access`
- Or click the **Request alpha access** pill on [kisenon.com](https://kisenon.com)

Once you have an invite, sign in at [kisenon.com](https://kisenon.com) → create a project → grab the connection string → connect with any Postgres 17 client.

```
psql "postgresql://app:•••••@kisenon.com/main?endpoint=ep_…"
```

## What lives here

This repo is intentionally lean. Right now:

- **Issues** — bug reports, feature requests, design discussions: [open an issue](https://github.com/Seiraiyu/Kisenon/issues)
- **Discussions** — questions, architecture chats, feedback: [start a discussion](https://github.com/Seiraiyu/Kisenon/discussions)

Coming soon:

- **`examples/`** — small, runnable apps using Kisenon (Next.js, Drizzle, Prisma, raw `pg`, …). Branch-per-PR-preview patterns, edge runtime, etc.
- **`scripts/`** — operational helpers: connection-string formatters, branch-cleanup utilities, CI integrations.
- **`plugins/`** — open-source extensions and templates contributed by the community.

If you want to ship one of the above, open a discussion first so we can sketch the shape together.

## Reporting Bugs

Use [GitHub issues](https://github.com/Seiraiyu/Kisenon/issues) for anything that's broken, surprising, or missing. When filing a bug:

- Include the **endpoint id** or **project slug** if it helps reproduce
- Paste the **error message** verbatim — we read every one
- Mention your **client** (psql, node-postgres, Drizzle, etc.) and version

For security issues, please email **security@kisenon.com** instead of opening a public issue.

## Connect

- [Discord](https://kisenon.com) (link coming soon)
- [@kisenondb](https://kisenon.com) on socials (placeholder)

## Status & support

- Service status: status.kisenon.com (coming soon)
- Public docs: [docs.kisenon.com](https://kisenon.com/docs)
- Email: **hello@kisenon.com**

## Data usage and privacy

When you use Kisenon, we store the data you put in your Postgres branches plus the metadata needed to operate the service (project + branch names, endpoint state, audit logs, request metrics).

We do not train models on your data. We do not share your data with third parties beyond the cloud regions you choose to run in. Full terms and privacy policy at [kisenon.com/legal](https://kisenon.com/legal) (coming soon).
