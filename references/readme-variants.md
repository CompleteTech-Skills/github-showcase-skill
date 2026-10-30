# README variants

Condensed from `ct-std-v1` §7 with decisions 13, 18 and 21 applied: every README opens with the hero banner (one dark PNG, a plain `<img>`), and ends with the CompleteTech LLC footer. `showcase.py readme` scaffolds or upgrades a README to its variant; `showcase.py lint readme` checks it. The machine-readable H2 order, renames, license rows and disclaimers are in `references/standard/readme-variants.yaml`.

## Order of a README

hero banner → nav line → centred H1, badges and bold tagline → `---` → H2 sections in the variant's order → `## Notes` (optional) → `## License` or `## Licensing` → the footer, always last. This is review q57 `nav`'s default, "Banner first, then nav line"; only if the user answers "Nav line first" does `readme.nav_first: true` in `brand.yaml` move the nav line above the banner (nothing else changes). `readme --mode header` (what the Action runs) swaps a README's two leading marker blocks into the configured order.

Only Variant A keeps an untitled intro paragraph after `---`; every other variant puts that text in `## About`.

## Header block (decision 13; variants A, B, C, D, E and I)

Each generated block sits between marker comments, so `readme --mode header` and the composite Action replace only that block on every run:

```markdown
<!-- showcase:banner:start -->
<p align="center">
  <img src="docs/images/banner.png" alt="REPO-SLUG by COMPANY" width="100%">
</p>
<!-- showcase:banner:end -->

<!-- showcase:nav:start -->
**NAV NAME** · [All repositories](https://github.com/ORG) · [Contributing](CONTRIBUTING-URL) · [Security](SECURITY-URL)
<!-- showcase:nav:end -->

<div align="center">

# PRODUCT NAME

<!-- showcase:badges:start -->
BADGE 1 BADGE 2 [BADGE 3] [BADGE 4]
<!-- showcase:badges:end -->

<!-- showcase:tagline:start -->
**GITHUB DESCRIPTION, VERBATIM**
<!-- showcase:tagline:end -->

</div>

---
```

- The banner is the first image and a plain `<img>`, never `<picture>` (decision 21). `COMPANY` is `CompleteTech LLC` for T1 and the org display name for T2.
- **Variant F** (security checks) uses its own exact header (below), with no H1; it is the golden and already the layout of the 48 security repositories.
- A preserve-list README that already opens with a banner `<img>` or `<picture>` keeps it directly under the new header: the hero banner goes above it (review q57 `pres` default, "Banner above the existing content"; logged `preserve-banner:kept-below-hero`). Only if the user answers "Leave them unchanged" (`readme.preserve_banner: unchanged`) does it get no hero (logged `exempt:preserve-banner`; `banner` is `n/a`).
- AI-Ascension gets the hero in its own palette in the same layout (q57 `aia` default), with its existing banner `<picture>` kept below it. The other answer, "CompleteTech palette", is the AI-Ascension org row's `family: completetech`.

**Nav name:** the org identity name (CompleteTech-Skills: `CompleteTech LLC Skills`).

**Nav links:**

- CompleteTech-Skills, type `agent-skills` (exact):

  ```text
  **CompleteTech LLC Skills** · [Start here](ONBOARDING.md) · [Agent instructions](SKILL.md) · [Skill library](https://github.com/CompleteTech-Skills/agentic-services-orchestrator-skill/blob/main/references/skill-family.md) · [Contributing](CONTRIBUTING.md)
  ```

- Everything else: `**NAV NAME** · [All repositories](https://github.com/ORG) · [Contributing](C) · [Security](S)`. After `All repositories`, insert in this order, each only when it applies: `[Live site](https://HOST)` (Variant B, URL passes the homepage check), `[Play](LIVE-URL)` (Variant E), `[Docs](docs/)` (only when `docs/` holds at least one non-image file; `docs/images/` alone does not count). Private repositories append ` · Internal`. `C` and `S` are the repository's own `CONTRIBUTING.md` / `SECURITY.md` if present, else `https://github.com/ORG/.github/blob/main/CONTRIBUTING.md` (or `SECURITY.md`). `ORG` is the org's current login (after an approved rename, never the former one).

**Badges** (shields.io, flat, 2–4, in this order; minimum: type and license):

1. Language: `LANG-VER-1E3A8A?logo=LANG&logoColor=white`, with VER from `requires-python` or `engines.node` (`>=3.10` → `3.10%2B`); otherwise `language-LANG-1E3A8A`.
2. Type: `type-CARD%20CATEGORY-005ADD`. Skills keep theirs (`agent%20skill-Claude%20%7C%20Codex-005ADD`, `output-PDF-005ADD`).
3. License: `license-SPDX-64748B`, or `license-proprietary-64748B` for private repositories; omitted while a public repository has no license.
4. CI, public repositories only: the Actions badge of a workflow whose file name contains `test`, else `ci`, using the current owner.

Each label and message segment doubles `-` and `_` (shields.io's escapes) and is then percent-encoded, so `C#` reads `language-C%23-1E3A8A` and `#`, `?`, `/` or `%` never end the path early.

| Token | Hex | Use |
|---|---|---|
| Accent | `1E3A8A` | language or runtime |
| Brand blue | `005ADD` | type or format |
| Positive | `067647` | `dependencies-none-067647`, `network-offline-067647` |
| Neutral | `64748B` | license |

T2 uses these tokens, except jevplay-games (brand `E551BA`, accent `F386A1`, neutral `1E1E1E`, `labelColor=1E1E1E`). AI-Ascension keeps its badges unchanged. Never off-palette colours. Profile READMEs render badges offline (`--badges local`); repository READMEs use shields.io.

## Shared rules (MUST)

- **H1:** one per README, the product name. Derive it from the slug only when no H1 exists.
- **Title Case** (H1, H2, derived names): capitalize every word except a, an, and, as, at, but, by, for, in, of, on, or, the, to, via, vs (unless first). Keep exact case for: AI, API, CLI, MCP, CVE, LLM, OBS, PDF, QR, SDK, STS2, TCG, UI, URL, GitHub, CompleteTech, LibreEvolve, NetScaler, KiCad, jevplay.games, romgenie. Jev/JEV: keep the existing casing.
- **Images:** every `<img>` and `![]()` has literal alt text. README images are at most 300 KB, except example previews (at most 2600 px wide and 600 KB). Local images use relative paths.
- **Links:** for every `github.com/OWNER/REPO` or `raw.githubusercontent.com/OWNER/REPO` link, the canonical `full_name` from `gh api repos/OWNER/REPO` wins (case-sensitive). On 404, keep the link and log `dead-link`. Never remove a link to another owner.
- **Formatting:** no emoji. ` · ` separates nav and link-line items. Code fences have a non-empty info string (`text` for plain output).
- **Size:** under 500 KiB. No target length; never pad.
- **Callouts:** GitHub alert syntax only: `> [!NOTE]`, `> [!WARNING]`, `> [!IMPORTANT]`.
- **No placeholders:** a required section with no source facts is omitted and logged `needs-input:VARIANT:H2`; lint reports `incomplete`.
- **Workflow Diagram** is written only from an existing `.mmd` file or Mermaid block, with the classes `source`, `gate`, `output` and `final`.

**Restructuring an existing README (`readme --mode upgrade`):**

1. The old nav line, H1, tagline, badge rows and logo images are replaced by the header block. Other header images are kept directly under `---`.
2. Existing H2s are renamed case-insensitively: Installation → Install; Getting Started, Quickstart, Quick start → Quick Start; Licence → License.
3. An existing H2 that matches a variant H2 moves into that section, verbatim.
4. Any other existing H2 is kept verbatim, demoted to `###`, emoji removed from its heading, in its original order, under `## Notes` (immediately before the License section).
5. Content changes only by link rewrites, brand-string fixes and the heading changes above. Nothing is deleted: every original non-header line must appear in the output.
6. If non-whitespace characters drop by more than 10%, nothing is written; log `readme-shrink` (exit 1).

**Preserve list (additive changes only):** `CompleteTech-Skills/creative-studio`; every README in AI-Ascension, Jev-Engineering, jevplay-games, TouchedByAnAgent and LibreEvolve that starts with a banner `<img>` or `<picture>`; any README over 15,000 bytes. Allowed: insert the hero banner block at the top (q57 `pres`; the README's own banner stays directly under the new header); prepend the nav line in the §7.1 order; add or fix the License section; link rewrites; alt text; brand-string fixes; disclaimers; G/H callouts; the footer. A full re-layout needs approval.

## Variant matrix: H2 order (R required, O optional)

`## Notes` (O) may appear in every variant immediately before the final License section.

| Variant | Applies to | H2 sections, in order |
|---|---|---|
| A Skill | CompleteTech-Skills, type `agent-skills` | About R · OpenClaw / ClawHub Metadata R · Workflow Diagram R · What It Does R · Contents R · Quick Start R · Example R · Inputs O · Assets O · Brand Notes R · Runtime Permissions R · Network Boundary R · Source O · License R |
| B App / website | `website`, `web-app`, `mobile-app`, `chrome-extension` | About R · Live Site R (link only) · Features R · Tech Stack R · Quick Start R (local dev) · Deployment O · Status O · License R |
| C Library / tool / CLI / MCP server | `cli`, `library`, `api`, `mcp-server`, `bot`, `discord-bot`, `plugin`, `template`, `tutorial`, `agent-skills` outside Skills; public `infrastructure`, `hardware`, `workspace` | About R · Install R · Quick Start R · Usage R (`### Tools` then `### Client Setup` for MCP) · Configuration O · Workflow Diagram O · Development O · License R |
| D Research | `research`, `dataset` | About R · Findings R (or Status if there are none) · Method R · Data and Sources R · Reproduce O · Limits R · Citation O · License R |
| E Game | `game` | About R · Play R (live link) · How to Play R · Run Locally O · Credits and Disclaimer R · License R |
| F Security check | `security-check` | Quick Start R · The Report R · Version Rules R · Configuration Observations O · Limits R · Reference O · Licensing R |
| G Fork outside the watching org | `fork`, not in the watching org | Hero banner, then the fork callout, above the unchanged upstream README, then the footer (q27 default) |
| H Archived / legacy | `backup` and every repository about to be archived | Hero banner, then the archive callout; the body stays as it is; then the footer |
| I Private internal | private `infrastructure`, `hardware`, `workspace` | About R · Setup R · Usage R · Runbook O · Ownership R · License R |
| J `.github` repository | `.github` | About R · Files R · License R |

A private repository on variants A–E keeps that variant, adds the I callout and the private License text, and its nav line ends with ` · Internal`.

## Variant notes

**A Skill.** Header as above with the Skills nav line, then an untitled 1–3 sentence intro, then:

- About: `Part of the CompleteTech LLC agentic services skill library.` (skills named `agentic-*`) or `Part of the CompleteTech LLC skill library.`, then the responsibility sentence kept from the existing About.
- OpenClaw / ClawHub Metadata: skill key; version from `skill-package.json` (omit if absent); homepage and README URLs under `https://github.com/CompleteTech-Skills/`; runtime binaries (`python3` with `requirements.txt`, `node` with `package.json`); Python packages copied verbatim from `requirements.txt` (log `needs-input:pin` when unpinned; never edit it); discovery tags `latest` plus the final topics in merge order; the license line with the ClawHub phrase; the brand-assets line.
- ClawHub phrase: use "ClawHub publishing is intentionally skipped (see `CLAW_HUB_PUBLISHING.md`)" when that file contains "skipped"; "published on ClawHub as `SLUG`" when it contains "published as" followed by a backticked slug; otherwise "the repository is prepared for ClawHub publishing, not yet published (see `CLAW_HUB_PUBLISHING.md`)"; "the repository is not yet published on ClawHub" when the file is absent.
- Workflow Diagram: `Source: [assets/diagrams/workflow.mmd](assets/diagrams/workflow.mmd).` and the Mermaid block with the four fixed classes.
- What It Does: four verb-first bullets. Contents: one line per shipped file or folder. Quick Start: install plus the entry point. Example: the rendered preview, `Example files: …` links, a bold title naming the Northwind Trading Co. demo, 3–4 bullets and the command that regenerates it.
- Brand Notes: tone, plus "do not invent" boundaries. Runtime Permissions and Network Boundary: from `SKILL.md` and the scripts only.

**B App / website.** About (2–4 sentences from the repository), Live Site (`**[HOST](https://HOST)**`), Features (verb-first bullets), Tech Stack (a Layer / Technology table), Quick Start (install, dev server), Deployment (where and how; no secrets or host credentials).

**C Library / tool / CLI / MCP server.** About · Install (`pip install …`, `npm i …` or `git clone`) · Quick Start (the three most common commands) · Usage. MCP servers put a `### Tools` table (Tool, What it does, Inputs) and a `### Client Setup` JSON block in Usage. Configuration is an environment-variable table with no secret values.

**D Research.** `## Findings`, or `## Status` with "No findings yet." if there are none. Never overstate results. `## Limits` is required. `CITATION.cff` only when the README already has a citation or BibTeX block.

**E Game.** `## Play` links to `https://jevplay.games/GAME` (jevplay-games) or the live URL. For `jev-guess-who` (Guess Who?), `jev-mastermind` (Mastermind), `jev-2048-arcade` (2048), `jev-connect-four` (Connect Four), and any other game named after a third-party title (the registry names it), add `PRODUCT is an independent game and is not affiliated with or endorsed by the owners of ORIGINAL GAME.`

**F Security check** (all 48 repositories):

```markdown
<p align="center">
  <img src="docs/images/banner.png" alt="REPO-SLUG by CompleteTech LLC" width="100%">
</p>

**CompleteTech Security** · [All checkers](https://github.com/CompleteTech-Security) · [Reference](docs/REFERENCE.md) · [Licensing](LICENSING.md) · [Security](SECURITY-URL)

<p align="center">
  <a href="https://github.com/ORG/REPO/actions/workflows/tests.yml"><img src="https://github.com/ORG/REPO/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1E3A8A" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-none-067647" alt="No dependencies">
  <a href="LICENSING.md"><img src="https://img.shields.io/badge/license-AGPL--3.0%20%7C%20commercial-64748B" alt="AGPL-3.0 or commercial license"></a>
</p>

<p align="center"><b>GITHUB DESCRIPTION, VERBATIM</b></p>

---

## Quick Start
## The Report
## Version Rules
## Limits
## Licensing
```

Include each badge and nav item only if its workflow or file exists; `ORG` in badge URLs is the current owner.

**G Fork outside the watching org** (review q27 default, "Upstream README kept, with a short CompleteTech note, banner and footer"). Insert the hero banner block, then this callout, above the unchanged upstream README, and append the footer; change nothing else:

```markdown
> [!NOTE]
> **Fork of [PARENT](https://github.com/PARENT)** with STEWARD changes. Our changes: [compare with upstream](https://github.com/OWNER/REPO/compare/PARENT_OWNER:PARENT_BRANCH...DEFAULT_BRANCH). The upstream README follows unchanged; the upstream license applies.
```

A fork with 0 commits ahead of its parent (`ahead_by: 0` in the metadata; `meta --from-gh` reads it with a read-only compare GET) gets the short form, which claims no changes. Without `ahead_by` the short form is used too and `needs-input:ahead-by` is logged, so the note never claims changes nobody counted:

```markdown
> [!NOTE]
> **Fork of [PARENT](https://github.com/PARENT)**, kept by STEWARD. The upstream README follows unchanged; the upstream license applies.
```

If the user answers q27 "Full CompleteTech treatment" (`readme.fork_readme: full` in `brand.yaml`), the fork follows its §5.4 variant instead: pass it with `readme --variant` (otherwise G is written and `needs-input:fork-variant` logged). Watching-org forks get no README change at all.

**H Archived.** Insert directly under the hero banner block, before archiving (or in an approved unarchive, edit, re-archive cycle), and append the footer:

```markdown
> [!WARNING]
> **Archived on YYYY-MM-DD.** REASON. Use [OWNER/REPO](https://github.com/OWNER/REPO) instead. This repository is read-only.
```

Without a replacement, the middle sentence is "There is no replacement." REASON: backups `Dated backup snapshot kept for reference`; superseded `Superseded by a newer repository`; duplicate `Duplicate of a canonical repository`; otherwise `Retired`.

**I Private internal.** Below the `---`:

```markdown
> [!IMPORTANT]
> Internal CompleteTech LLC repository. Not for distribution.
```

(T2: the org display name; TouchedByAnAgent: `Internal Touched By An Agent repository.`) Ownership reads `Owner: @CompleteDotTech · Organization: ORG`.

**J `.github` repository.** `# ORG/.github`, then `Organization profile and default community health files for ORG DISPLAY NAME. Files here apply to every repository in the organization that does not have its own copy.`, a Files table listing only files that exist, and the License line `MIT; see LICENSE. CompleteTech LLC names and logos are reserved.`

## Disclaimers (README only)

| Repository or org | Line |
|---|---|
| CompleteTech-Pokemon repositories | `Not affiliated with, endorsed by, or sponsored by Nintendo, Game Freak, Creatures or The Pokémon Company.` |
| CompleteTech-ManageEngine/sdp-cloud-readiness | `Not affiliated with or endorsed by ManageEngine or Zoho Corporation.` |
| The five games listed under Variant E | the Variant E line |
| AI-Ascension | keep the existing Slay the Spire disclaimer |

Placement: the final paragraph of `## About`; Variant E: the final line of `## Credits and Disclaimer`; Variant F: the final line of `## Limits`.

## License section text (first matching row wins)

| # | Case | Body |
|---|---|---|
| 1 | Security (AGPL and commercial) | Section `## Licensing`: Available under the GNU AGPL-3.0 or a commercial license; see `LICENSE` and `LICENSING.md`. |
| 2 | Third-party code present (an upstream LICENSE, NOTICE or COPYING, a `-fork` suffix, a `vendor/` or `third_party/` tree, or a README or manifest naming an upstream) | Upstream code is licensed under LICENSE by UPSTREAM; see `PATH`. Public repositories add: STEWARD changes are offered under the same license. (UPSTREAM unknown: log `needs-input:upstream`.) |
| 3 | MIT and `BRAND_ASSETS.md` (Skills) | Code, templates, and documentation are licensed under the MIT License. CompleteTech LLC names, logos, seals, and brand assets are reserved and are not licensed for reuse except to identify this project. See `LICENSE` and `BRAND_ASSETS.md`. |
| 4 | MIT, other T1 | Code and documentation are licensed under the MIT License; see `LICENSE`. CompleteTech LLC names and logos are reserved and are not licensed for reuse except to identify this project. |
| 5 | MIT, T2 | As row 4, with the org display name in place of "CompleteTech LLC". |
| 6 | Existing non-MIT license | Licensed under the LICENSE NAME; see `PATH`. BRAND names and logos are reserved and are not licensed for reuse except to identify this project. |
| 7 | Private, none of the above | Proprietary. Copyright (c) CREATED-YEAR CompleteTech LLC. All rights reserved. (TouchedByAnAgent until decided: `Proprietary. All rights reserved.`) |
| 8 | Public, no license file | Omit `## License`; log `needs-input:license` (licenses are added only from the approved list). |

Never modify, rename or delete an existing LICENSE, NOTICE or COPYING file.

## Footer (decision 18; always the last block)

```html
<!-- showcase:footer:start -->
<p align="center">
  <a href="https://www.complete.tech">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo-dark.png">
      <img src="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo.png" alt="CompleteTech LLC" width="200">
    </picture>
  </a>
  <br>
  Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration
</p>
<!-- showcase:footer:end -->
```

The 10 lines between the markers are byte-exact; `footer --check` reports `fail:missing`, `fail:not-last`, `fail:drift` or `fail:duplicate` (an old footer-like block, centred with "Built by" and complete.tech outside code, kept before the decision 18 footer), and `footer --check README.md --online` also sends a read-only HEAD to both raw logo URLs and fails (`fail:offline`) unless both return 200 (the Phase 4.0 hard gate before any README PR links them). It comes after the License section. Scope: every in-scope README, T2 families included. Exceptions: watching-org forks (`exempt`; the watching org's `.github` gets the footer, and its other non-fork repositories are held, `hold:watching-non-fork`, until decided) and T3 until sign-off (refused). TouchedByAnAgent is included (decision 18); an org whose `footer` is set to `hold` in `brand.yaml` logs `hold`. Forks outside the watching org (G), archived repositories (H) and `.github` repositories (J) get the footer too. It is the only `<picture>` the skill emits.

## What `readme` does

| Mode | Behaviour |
|---|---|
| `auto` | `scaffold` when there is no README or it has fewer than 3 non-blank lines; otherwise `upgrade` |
| `scaffold` | Writes the variant's H2s in order. A required section is written only from repository facts (README fragments, manifests, `SKILL.md`, `.mmd` files); otherwise it is omitted and logged. The License body comes from the table above. |
| `upgrade` | The restructuring steps above, with the never-delete multiset check. The tagline block follows the `header` rule (with no description, a tagline written for the repository stays; only an inherited one is emptied, and the check does not count that dropped line as lost): the rebuilt header carries it, and on the preserve list (or over 15000 bytes) the block stays where it is. With no description, when upgrade rebuilds the header (not in preserve mode), a single bare `**...**` line opening the README after its header lines (H1, badges, banner, `---`) is the old tagline and moves into the block by the same rule; a second one, one beside a tagline block that already holds a line, a bold line inside a centred `<div align="center">` or `<p align="center">` block, any such line in preserve mode, and one in an untouched template copy whose template taglines are unknown (the rule would empty any line in the block there on the next run) stay as authored text. An old footer at the end of the README (a centred block whose every line is a footer line: centring, `<br>`/`<sub>`, complete.tech links, the footer's own logo image (its src or srcset is the brand footer logo URL, the same file on another branch, with a query, or in its github.com blob/raw form, or its alt is exactly the company; never an image because its file name contains "logo") and the "Built by" credit line, i.e. an unmarked copy of the footer or a drifted one) is replaced by the marked decision 18 footer, never kept beside it, on the preserve list too. A centred block with any other line (a partner or sponsor logo, any other image, a thanks line) is authored content and is kept; `lint readme` then reports `D18 footer fail:duplicate` if it reads like a footer |
| `header` | Touches the marker blocks only (what the Action runs). Authored text outside the blocks comes back byte-identical, fenced code included (a marker block, `<!-- showcase:license -->` or template-body block shown inside fenced or inline code is an example, never regenerated); blank lines are tidied only inside regenerated blocks and where a block meets authored text (a removed block leaves one blank line). With no description the tagline block is kept as written (logged `needs-input:description`), except an inherited tagline, which is emptied: the block holds exactly a tagline of the template the repository was generated from (`meta` `template_taglines`: the template README's tagline block, the first one outside code, when the repository was generated and today), or, only when those are unknown, the template body is still pristine; never in the template repository itself (R2: the tagline is the description, never another repository's line), and the paragraph after `<!-- showcase:license -->` (and its heading) is rewritten from the license table whenever it can be derived |
| `--bootstrap` | Template only. The block between `<!-- showcase:template-body:start -->` and `:end -->` starts with `<!-- showcase:template-body:pristine sha256=HEX -->`, the hash of the block's generated text. While the block still matches its hash byte for byte, bootstrap replaces it with the scaffolded variant body for this repository (each section holds only an HTML comment naming the facts it needs) under a new hash, rebuilds the header for the variant (Variant F: no H1; a CVE slug titles as `Acme CVE-2026-12345 Check`; the tagline block carries over and follows the `header` rule, so with no description a tagline written for the repository stays and only an inherited one is emptied), writes the license section from the table above (with or without a `LICENSE` file; a private repository reads "Proprietary...", a public Security repository gets `## Licensing`), and rewrites the owner tokens in `CONTRIBUTING.md` (only links to the template owner's `.github`; a link to another org's or an upstream's contributing guide or security policy stays as written). Because the hash still matches, a later run re-bootstraps when the type changes (the code landed, or `type:` was set in `.github/showcase.yml`). Once a person edits the block, the hash no longer matches: the marker is dropped (`bootstrap:edited`), the README goes through `upgrade` with the never-drop-a-line check, and the block is never rewritten again. A no-op when the markers are absent. |

The default is a dry run that prints a unified diff; `--write` writes `README.md`. A leading UTF-8 byte order mark is dropped before any mode reads the README (and by `lint readme`), so it never hides the H1. G and H only insert the hero banner block and their callout on top and append the footer; nothing else changes. A README that already opens with a blockquote keeps it. The G callout needs the parent in the metadata (`parent.full_name`, from `meta --from-gh`); without it the callout is skipped and `fork-parent-missing` is logged. The H callout needs the archive date and reason from the registry, so `readme` logs `needs-input:archive-callout` instead of writing it. Watching-org forks are never changed.

## What `lint readme` checks

The hero banner first, then the nav line (or the nav line first with `readme.nav_first: true`); the banner block is the first image and a plain `<img>` (a preserve-list README is exempt only when q57 `pres` is "Leave them unchanged"); G and H: the banner block, then the callout, the footer last; exactly one H1 outside fenced code (```` ``` ```` and `~~~` fences alike; except F); 2–4 badges in palette tokens; the bold tagline equals the description (with metadata); H2 order per variant, License last; footer last and exact, and no second footer-like block before it (`D18 footer fail:duplicate`); literal alt text on every image; local images resolve (URL-encoded paths such as `My%20Shot.png` are decoded) and stay within size; no placeholder tokens outside code and HTML comments; no emoji; info strings on code fences; size under 512,000 B; brand strings outside URLs and code. The result is `incomplete` when only logged `needs-input` omissions remain.
