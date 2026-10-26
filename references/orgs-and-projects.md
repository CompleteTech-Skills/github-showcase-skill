# Organizations and GitHub Projects

Decision 23 extends this skill to organizations and GitHub Projects. The skill itself stays read-only toward GitHub: it generates the art and text, checks it, and prints the commands; the orchestrator's single writer queue (and the browser, for UI-only settings) applies them. This page holds the rules; the commands are in [org.md](org.md) (`showcase.py org`) and [projects.md](projects.md) (`showcase.py project`). Profile README structure is in [profile-readmes.md](profile-readmes.md); the org identity table (name, description, eyebrow) is in [estate-standard.md](estate-standard.md).

## Org About fields

Values come only from the org identity table; agents never compose an org name or description.

| Field | T1 | T2 product | T2-R (romgenie) |
|---|---|---|---|
| `name` | identity table | identity table | identity table |
| `description` (≤ 160 characters) | identity table | identity table | identity table |
| `blog` | `https://www.complete.tech` | jevplay-games `https://jevplay.games`; TouchedByAnAgent `https://touchedbyanagent.com`; others unchanged | unchanged |
| `location` | `Cincinnati, OH` | `Cincinnati, OH` (TouchedByAnAgent unchanged) | `Cincinnati, OH` |
| `email` | `Timothy.Gregg@complete.tech` once the user approves it; until then unchanged | same | same |
| `twitter_username` | `CompleteTechLLC` | unchanged | unchanged |

```bash
# `showcase.py org about ORG` prints this as a writer job (phase 1.2); the skill never runs it (needs admin:org)
gh api -X PATCH orgs/ORG -f name="…" -f description="…" -f blog="…" -f location="Cincinnati, OH"
```

The verified-domain badge needs DNS records the user adds; social accounts, avatars, pins and org default labels are set in the browser.

## Org checks (definition of done)

`showcase.py org doctor ORG --snapshot FILE` computes O1, O2, O3, O4 and O6 (plus O9, the org banner, and O11, the verified badge, from STANDARD §1.4); O5, O7 and O8 stay with the orchestrator, and O10 (the org's Workstreams project) is `project lint`.

| # | Check |
|---|---|
| O1 | Custom avatar from the one avatar system (decision 11). Fetch `owner.avatar_url` plus `&s=420`; it passes when, quantized to 8 colours, more than 2 colours each cover at least 1% of pixels, and it is not the default identicon. |
| O2 | Profile fields equal the table above. |
| O3 | Public `ORG/.github` with `profile/README.md` listing every public, non-fork, non-archived repository, with no GitHub link whose `full_name` differs. |
| O4 | The default community files below are present. |
| O5 | `labels.yml` in `.github` (not romgenie); org default labels set in the browser. |
| O6 | Pins: up to 6 public and up to 6 members-only per org, chosen in the registry (decision 14); set from each repository page's Edit Pins menu. |
| O7 | X account `CompleteTechLLC` on T1 orgs and on CompleteDotTech. |
| O8 | The CompleteDotTech profile lists the org. |

## Org `.github` repository

It must be public. In an existing `.github`, add only missing files; existing files get only brand-spelling fixes, the SECURITY scope line, absolute links, label rewrites in kept issue forms and link rewrites. AI-Ascension's `.github` gets no new files; TouchedByAnAgent gets no copied prose until the user decides. Never create `.github-private`.

| Path | T1 and T2 product orgs | romgenie orgs |
|---|---|---|
| `README.md` | Variant J | Variant J |
| `LICENSE` | MIT (covers the templates only) | MIT |
| `profile/README.md` | yes | yes |
| `profile/assets/banner.jpg` | generated orgs only (1600×400) | romgenie-following |
| `profile/assets/avatar-500.png`, `avatar-1024.png` | for avatars produced in the run | same |
| `profile/assets/PROMPTS.md` | when generated art exists | same |
| `CONTRIBUTING.md`, `SUPPORT.md` | if missing (master text from `CompleteTech-LLC/.github`) | no |
| `SECURITY.md` | if missing: private vulnerability reporting plus email | the romgenie text |
| `CODE_OF_CONDUCT.md` | if missing: Contributor Covenant 2.1, contact `Timothy.Gregg@complete.tech` | no |
| `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `config.yml` | only if the folder holds no forms | no |
| `.github/PULL_REQUEST_TEMPLATE.md` | if missing | no |
| `labels.yml` | yes, except AI-Ascension ([labels.md](labels.md)) | no |

A repository-level file of the same type overrides the org default; a repository-level issue-template folder overrides the defaults entirely. That is why `completetech-repo-template` ships no issue templates, PR template, SECURITY, SUPPORT or CODE_OF_CONDUCT.

Default issue forms label new issues `["type:bug", "status:needs-triage"]` and `["type:feature", "status:needs-triage"]`; the labels must exist before a form that references them is pushed.

## Org profile README

New profiles follow the section order in [profile-readmes.md](profile-readmes.md). Existing profiles (AI-Ascension, CompleteTech-LLC, AI-Research, Jev-Engineering, jevplay-games, LibreEvolve, TouchedByAnAgent, both romgenie orgs) get only known fixes and missing public-repository rows in their existing format; a full re-template needs approval. T2 contact line: `[BLOG HOST](BLOG) · [All CompleteTech organizations](https://github.com/CompleteDotTech)`; T2 footer line `Steward: CompleteTech LLC` in place of `A CompleteTech LLC organization`.

The repository list is a Markdown table (Repository, What it is, License) in flagship order: public, non-fork, non-archived repositories other than `.github`, sorted by stars descending, then the last default-branch commit descending, then name. Public forks go under `### Forks`, public archived repositories under `### Archived`. Private repositories are never listed.

## CompleteDotTech personal profile (last, decision 20)

An "Organizations" table lists the 17 T1 and 7 T2 orgs (T3 only after sign-off; never HOLD or EXCLUDED), grouped in family order and alphabetical by display name within a family: a 32 px avatar, the linked display name, and the org description without its closing "A CompleteTech LLC organization." or "Steward: CompleteTech LLC." sentence. The kit's avatar grid goes above it; the table moves into `<details>` as a text index. The personal About fields follow review q92: the browser by default; `PATCH user` only as a writer job under an approved `user-about` row (Phase 8 capstone, decisions 9 and 20).

## GitHub Projects (decision 23)

The full procedure, with every command, is in [projects.md](projects.md); the standard is STANDARD §13.

**Golden board.** The user's org project https://github.com/orgs/Pick-Your-AI/projects/1, worked through its "Workstream Overview" view. Pick-Your-AI is co-owned (T3): reading the project is allowed; changing, marking or linking anything on it is not. Wherever the captured board has a field, option, view or setting, its names and settings win.

**Template.** `TEMPLATE — Workstream Portfolio`, owned by CompleteTech-LLC (templates must be org-owned, and a T3 org cannot host one), copied from the captured board and marked as a template last. Org boards are copied from it; a direct copy of Pick-Your-AI/1 is only the logged fallback. `gh project copy` alone drops option colours, so the copy is always followed by the stage 2 plan (`project copy-plan --copied`), which restores the full option lists with their ids, the missing fields and views, the text and the links.

**Per org (approved `create-project` items only).** Title `{display name} — Workstreams`; short description `{display name} workstreams: what is in flight, what is next and what has shipped, updated weekly.`; the README from the §13.7 template; the org's own Workstream options coloured by kind; private unless a `project-visibility` item is approved.

**Estate.** A private cross-org `CompleteTech — Estate` board on CompleteDotTech, only if the user approves it (`project estate-plan`).

**Text.** The short description follows the description checks (one sentence ending with a period, at most 120 characters, no emoji, exact brand strings). The README follows the README shared rules (no emoji, no placeholders, brand strings, facts only) and names the org by its identity-table name.

**Never.** Never pass `--drafts`, never copy items, never delete a project, field, option, item, view or workflow (the orchestrator's guard enforces this). Project visibility changes only from an approved list. Nothing on a T3 project changes without co-owner sign-off.
