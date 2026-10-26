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
- `org profile` lists an estate-owned favorite (placeholder, merge-source and excluded owners included), or any favorite whose metadata was captured, only when it passes the public-slice test, and its leak check covers every captured repository whose metadata is not public, whoever the owner.
- `labels --plan` and `adopt` hold a rename (`label-rewrite-first`) while an issue form's or `dependabot.yml`'s `labels:` entry still assigns the old label, so no rename leaves a form naming a missing label.
- A label rename is never planned without its reference check: with no checkout (`labels --plan` without `--repo-dir`, `adopt`, `org labels`), it is planned only when the captured file tree, recorded whole (`files_complete: true`: `meta --from-gh` keeps GitHub's `truncated` answer), proves no issue form, `dependabot.yml`, workflow, `release.yml`, `labeler.yml` or `renovate.json` exists; otherwise it is held as `needs-input:label-references` with the files to check.
- The label reference check also reads the owner's `.github` default issue forms for a repository without forms of its own (`org labels` from `--meta-dir`; `labels` and `adopt` take `--org-defaults` with a checkout or its metadata JSON), and parses forms, front matter and `dependabot.yml` as YAML, so multi-line values, quoted keys, aliases and a byte order mark are recognised and a file that does not parse holds the rename.
- `org pins` adds to the public star List only the favorites the public slice may name: private, HOLD, excluded-owner and exposure favorites are dropped (`favorite-dropped:private-or-unknown`, unnamed) and unknown visibility leaves the plan `incomplete`.
- `content icon` refuses a family on hold unless `--allow-hold` is passed, as `banner` and `card` do.

### Fixed

- `project copy-plan`: a view filter on a quoted Workstream value (`workstream:"Research"`) now follows the option rename, renames apply in one pass, and the template and the Estate never get the public-visibility job even with an approval row.
- `topics`: the CVE-check vendor topic and the TouchedByAnAgent domain vocabulary match the owner through the shared resolver (CQ-03), so an approved org rename (`CompleTetech-Security` to `CompleteTech-Security`) no longer proposes removing a checker's vendor topic or logs `needs-input:domain-topic` and `topics-short`.
