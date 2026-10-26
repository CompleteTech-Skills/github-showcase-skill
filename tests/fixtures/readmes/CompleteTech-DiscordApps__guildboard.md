# Guildboard

An open-source, real-time moderated whiteboard Discord Activity with collaborative drawing, Discord role-based editing, persistent boards, secure moderation, and GoDaddy self-hosting.

**State: engineering roadmap and repository foundation. The application is not implemented or deployed.** There is no production website or Discord installation link yet.

- [Engineering & Delivery Project](https://github.com/users/CompleteDotTech/projects/7)
- [Canonical backlog](planning/guildboard-backlog.json)
- [Architecture boundaries](docs/architecture.md)
- [Development setup](docs/development.md)
- [Contribution process](CONTRIBUTING.md)
- [Security reporting](SECURITY.md)
- [Verified bootstrap report](planning/BOOTSTRAP-REPORT.md)
- [MVP acceptance traceability](planning/MVP-ACCEPTANCE.md)
- [Live audit artifacts](planning/audit/)

## Intended system

React/TypeScript Activity and Excalidraw adapter; Fastify HTTP/WebSocket backend; Discord bot; shared versioned contracts; MySQL/MariaDB operations, snapshots and metadata; private persistent asset storage. Production must run on a **GoDaddy Linux VPS** with Nginx HTTPS/WSS. Detailed dependency/version choices await the roadmap's evidence and ADR gates.

`apps/activity`, `apps/api`, `apps/bot`, `packages/contracts`, `packages/auth`, `packages/canvas`, `packages/collaboration`, `database`, `infra/godaddy`, `tests` and `docs` establish ownership boundaries. These directories contain design/runbook scaffolding, not a working product.

## Planning tooling

Python 3.11+ and GitHub CLI are required. Authenticate `gh` with repository, workflow and project permissions; credentials remain in the CLI keyring. Run `python3 scripts/github-bootstrap/validate.py` locally. Remote audit: `python3 scripts/github-bootstrap/audit.py`. Read the bootstrap guide before mutation.

## License

MIT for original repository content. Dependency, asset and redistribution licensing must be reviewed before adoption; an MIT repository license is not a compatibility determination for future dependencies.
