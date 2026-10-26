# Description formula

The GitHub description (About box) of every in-scope repository. `showcase.py describe` runs every check below and answers `keep`, `edit` or `needs-writer`; it never composes a new sentence. The machine-readable rules are in `references/standard/descriptions.yaml`.

## Checks (MUST)

| ID | Check |
|---|---|
| D1 | `len(NFC(s)) ≤ 140`. A **new** sentence is at most 120. |
| D2 | Ends with `.`; first character uppercase. |
| D3 | One sentence: no `.`, `!` or `?` followed by whitespace except at the final character. |
| D4 | First word is not A, An, The or This. |
| D5 | No case-insensitive whole-word match for: wip, todo, beta, alpha, deprecated, experimental, coming soon, best, awesome, ultimate, world-class, cutting-edge, revolutionary, next-gen. |
| D6 | No en dash (U+2013), no em dash (U+2014), no emoji (Extended_Pictographic); no leading, trailing or double spaces. |
| D7 | No version numbers (`\bv?\d+\.\d+(\.\d+)*\b`). |
| D8 | Not made only of the slug's words (hyphens as spaces, case-insensitive) plus a, an, and, for, of, the, tool. |
| V1 | Voice by type. `agent-skills`, `cli`, `library`, `api`, `mcp-server`, `bot`, `discord-bot`, `plugin`, `chrome-extension`, `security-check`, `template`, `infrastructure`, `hardware` and `workspace` start with one of the verbs below. `website` starts `Source for `. `game` starts `PRODUCT: play `. `fork` starts `Fork of `. Repositories about to be archived and `backup` start `Archived: `. All other types start with a word that is neither one of those verbs nor A, An, The, This. |
| P1 | The `PRODUCT: ` prefix (PRODUCT = the README H1) is used only for type `game` and for T3 Pick-Your-AI repositories. |
| B1 | Contains `CompleteTech LLC` if and only if `BRAND_ASSETS.md` exists at the repository root. Never a `(CompleteTech LLC skill)` suffix. |
| X1 | No disclaimer. Third-party disclaimers go only in the README, and only for the repositories that need one. |

**V1 verbs:** Generate, Create, Draft, Check, Track, Compile, Serve, Coordinate, Build, Run, Convert, Extract, Monitor, Scan, Sync, Manage, Render, Automate, Analyze, Collect, Deploy, Export, Index, Map, Search, Test, Validate, Visualize, Control, Read, Record.

## Keep or edit (MUST)

1. If the current description passes every check, keep it byte for byte: `{"action": "keep"}`.
2. Otherwise make the smallest passing edit, in this order: add the final period; fix whitespace; fix the brand spelling; remove a `(CompleteTech LLC skill)` suffix; remove a disclaimer clause. Edited text only needs D1's 140 limit: `{"action": "edit", "text": …, "edits": [rule, …]}`.
3. Only if the edited text still fails (always the case for an empty description or a V1 or D8 failure) is a new sentence of at most 120 characters needed: `{"action": "needs-writer", "failing": [...], "template": …, "slots_known": {...}}`. A writer composes it from the repository's own facts; the tool fills a template only when every slot is known (fork, archived, `.github`, the profile repository, CVE security checks).

**README tagline:** wherever the README header applies, the bold tagline is this exact string. The GitHub description is the source of truth.

## Templates by type

| Type | Template |
|---|---|
| `agent-skills` | `VERB [branded CompleteTech LLC] ARTIFACTS FOR WHOM / FROM WHAT[, QUALIFIER].` |
| `cli`, `library`, `api`, `mcp-server`, `bot`, `discord-bot`, `plugin`, `chrome-extension`, `template`, `infrastructure`, `hardware`, `workspace` | `VERB OBJECT CONTEXT[, KEY PROPERTY].` |
| `security-check`, CVE slug | `Check PRODUCT versions for CVE-ID (SHORT TITLE), offline and dependency-free.` SHORT TITLE is the text between `CVE-ID · ` and the next ` · ` in the existing README subtitle; if absent, drop the parenthesis. PRODUCT is the product name as written in the README subtitle or first paragraph, else the slug tokens before `-cve-` in title case. |
| `security-check`, `ISSUE-check` slug | `Check PRODUCT versions for ISSUE NAME exposure, offline and dependency-free.` |
| `website` | `Source for FQDN, WHAT THE SITE OFFERS.` |
| `web-app`, `mobile-app`, `research`, `dataset`, `tutorial` | `NOUN PHRASE (what it is) FOR WHOM / SCOPE.` |
| `game` | jevplay-games: `PRODUCT: play GAME KIND against Jev at jevplay.games.` Other orgs: `PRODUCT: play GAME KIND[ CONTEXT].` |
| Private repositories | Same templates. Never client names, credentials or unreleased product names. |
| `fork` | Ahead: `Fork of PARENT with STEWARD changes.` 0 ahead outside the watching org: `Fork of PARENT.` Watching org: `Fork of PARENT, followed for reference.` STEWARD is `CompleteTech LLC` for T1, the org display name for T2. |
| About to be archived, `backup` | `Archived: WHAT IT WAS[; superseded by OWNER/REPO].` WHAT IT WAS is the current description without its final period, first letter lowercased (keep-case words excepted); if empty, the H1. Write it before archiving. |
| `.github` | `Organization profile and default community health files for ORG DISPLAY NAME.` |
| `CompleteDotTech/CompleteDotTech` | `Profile README for the CompleteDotTech account of CompleteTech LLC.` |

## Examples from the estate

| Repository | Current | Standard |
|---|---|---|
| Skills/agentic-envelope-skill | Generate branded CompleteTech LLC printable #10 addressed envelope PDFs and delivery packages. | Keep (94) |
| Skills/agentic-invoice-skill | Create branded CompleteTech LLC invoice PDFs for agentic development services, from deposit through final payment. | Keep (114) |
| Skills/org-time-tracking-skill | Account for time spent … (CompleteTech LLC skill). (146, suffix, V1 fails) | Track time spent with one organization from Outlook, Teams and calendar evidence as a branded CompleteTech LLC report. (118) |
| Skills/creative-studio | Codex skill for reusable 2D characters, … (V1 fails) | Create reusable 2D characters, sprite animations and optional 3D rigs with provenance and review workflows. (107) |
| Security/netscaler-cve-2026-19489-check | (varies) | Check NetScaler versions for CVE-2026-19489 (LSN SIP ALG memory corruption), offline and dependency-free. (105) |
| jevplay-games/jev-guess-who | (varies) | Noul Who: play a browser deduction game against Jev at jevplay.games. (69) |
| LLC/complete.tech | (varies) | Source for complete.tech, the CompleteTech LLC company website. (63) |
| Research/llama.cpp (fork, ahead) | upstream text | Fork of ggml-org/llama.cpp with CompleteTech LLC changes. (57) |
| Skills/github-showcase-skill | new | Generate CompleteTech LLC README banners, repo cards and profile art, and check repositories against the standard. (115) |
| LLC/completetech-repo-template | new | Create new CompleteTech repositories with the standard README, folder layout and showcase banner Action. (104) |
