# Changelog

All notable changes to `github-showcase-skill` are recorded here. Versions follow [Semantic Versioning](https://semver.org/): a new major version changes a generated surface, a command's contract or the standard version (`ct-std-v1`); a minor version adds a command or option; a patch fixes output without changing the contract. The template's workflow pins a release tag by its commit SHA, so every entry below names one tag.

## 1.0.0 — 2026-10-26

First public release, for the CompleteTech GitHub estate standard `ct-std-v1`.

### Added

- Repository surfaces: README hero banner (1280×360 and 2560×720), repo card SVG, social preview (1280×640), repo icon (1024×1024), the estate footer and README marker blocks for every README variant.
- Checks: `describe`, `topics`, `labels --plan`, `readme` scaffold and upgrade, `lint` (SVG, banner, PNG, README, public leak) and `doctor` (R1 to R11 plus the art columns).
- Command groups: `org` (profile README, About, pins, labels, health, doctor), `project` (capture, normalize, lint, copy plan, README, Estate board), `enterprise` (discover, snapshot, plans, doctor) and `content` (sidebar, links, images, art direction).
- `meta --from-gh` records `last_substantive_commit` (CQ-16) and takes `--allow-t3` after co-owner sign-off.
- The composite Action (`action.yml`) that the repository template runs to bootstrap and refresh its own README and images.

### Security

- Read-only toward GitHub: every write is printed as a `gh` argv or a writer job for the estate's writer to run.
