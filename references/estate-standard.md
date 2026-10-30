# CompleteTech GitHub estate standard (condensed)

Condensed from the CompleteTech GitHub Estate Standard, version `ct-std-v1` (revision 2, 2026-10-25; owner Timothy Wayne Gregg, `CompleteDotTech`). The user decisions in [decisions.md](decisions.md) outrank it and are already applied here. Topic, description, label and README rules have their own references.

**Rule words.** MUST and NEVER are hard rules. SHOULD rules are defaults; deviate only for a logged reason. Check results are `pass`, `warn`, `incomplete` (only logged `needs-input` omissions remain), `fail` or `n/a`. KB means 1000 bytes, except the README limit of 500 KiB (512,000 B).

## Tiers

| Tier | Owners | What applies |
|---|---|---|
| T1: full standard | CompleteTech-LLC, CompleteTech-Skills, CompleteTech-LLC-AI-Research, `CompleteTech-Security`, CompleteTech-Infrastructure, CompleteTech-Commerce, CompleteTech-Creative, CompleteTech-Pokemon, CompleteTech-Data, CompleteTech-Games, CompleteTech-Directories, CompleteTech-Hardware, CompleteTechDiscord-Games, CompleteTech-DiscordApps, CompleteTech-Patent-IP, CompleteTech-Career-Toolkit, CompleteTech-ManageEngine (17 orgs) | Everything |
| T1 user account | CompleteDotTech | Everything, as the Phase 8 capstone, last (decisions 9 and 20): About (name, bio, company, website, location, social links), avatar, public org memberships, contribution settings, profile README, profile repository, 6 profile pins, star Lists and a gist review. About method (review q92): the browser by default (Settings → Public profile, screenshots before and after); `PATCH user` only as a writer job under an approved `user-about` row, after `snapshot.py --user CompleteDotTech`. Social links only through `POST /user/social_accounts` (add only, at most 4). The skill itself never calls the API |
| T2: own brand, shared structure | AI-Ascension, Jev-Engineering, jevplay-games, LibreEvolve, TouchedByAnAgent | Everything, with the family palette and brand topic. AI-Ascension keeps its `labels.yml`, badges and banner `<picture>`. |
| T2-R: romgenie utility | romgenie-archive-repostiory, romgenie-following-repos | Descriptions, topics, profile, avatar and banner, settings for the watching and archive orgs; no labels, LICENSE, CODEOWNERS, social previews or README changes beyond the fork and archive callouts |
| T3: hygiene only | Pick-Your-AI, Jevelopers-neatHack-2026 | Nothing until the co-owners sign off a per-repository list |
| EXCLUDED | BunsDev, GoZippy, h-mascot, lmvdz, GalaxyRuler; MetatronAngelAgent and PrompDev (decisions 1 and 2: out of scope, another person's account; the standard's HOLD row is superseded) | NEVER write; these accounts belong to other people or are out of scope |

**TouchedByAnAgent hold:** until the user decides, add no CompleteTech name, steward line, location, complete.tech link or contact email anywhere in that org. Existing text stays. (Decision 18 includes it for the footer, pending confirmation on the review page.)

**Archived repositories** are included through an approved unarchive, polish, re-archive cycle (decision 6). Never leave one unarchived.

## The baseline look

Every in-scope repository gets the same elements, as its variant allows:

1. **Family nav line**: the README's first line is bold and names the family, followed by links separated by ` · ` (U+00B7 with a space on each side).
2. **Hero banner** (decision 13), then the H1, the badge row and the **bold tagline identical to the GitHub description**, then `---`.
3. **Fixed H2 order** per variant.
4. **Mermaid workflow diagram** with the 4-class pastel palette (`source`, `gate`, `output`, `final`) and a committed `.mmd` source; required for skills, optional elsewhere.
5. **Rendered example or screenshot.**
6. **Fixed License and brand-reservation paragraph.**
7. **GitHub description**: one sentence ending with a period.
8. **Topics** from a closed vocabulary, with exactly one brand topic.
9. **Namespaced issue labels**, one colour per namespace.
10. **Org-level branding**: avatar, banner, profile README, default community files and pins.
11. **The CompleteTech LLC footer** as the last block of every README (decision 18).

Never use emoji anywhere: descriptions, topics, labels, READMEs or profiles. Never use superlatives or marketing claims the code does not back up.

## Brand strings (MUST)

| Use | Exact string |
|---|---|
| Company, in prose | **CompleteTech LLC** (never "Complete Tech LLC", "Completetech", "CompleTetech" or an all-caps form) |
| Short form | **CompleteTech** |
| All caps | Never in prose, descriptions, topics or Markdown. Allowed only in the official logo artwork and in compositor eyebrow lines on banners and cards (Poppins SemiBold, +6% tracking as measured on the golden, sky blue), in the form `COMPLETETECH LLC · LABEL`. |
| Tagline | **Innovation at Every Integration** |
| Website | `https://www.complete.tech` |
| X | `@CompleteTechLLC` |
| Security and contact email | `Timothy.Gregg@complete.tech` |
| Location | `Cincinnati, OH` |
| Brand topic | `completetech` (never `complete-tech`) |
| Steward line for T2 orgs | `Steward: CompleteTech LLC` (not TouchedByAnAgent until decided) |
| Third-party name in prose | `Pokémon` (with the accent); `The Pokémon Company` |
| Fictional client for every demo | **Northwind Trading Co.** (contact Morgan Reyes; project "Customer Support Email Triage Agent (Pilot)"; contract `ADSA-2026-0142`) |

## Golden rules for agents

1. **Diff first and idempotent.** GET the current state, compute the delta, write only the delta, then GET again to verify. Never write a value that is already equal.
2. **Never invent facts.** Descriptions, READMEs and topics come only from the repository's own code, README, manifests and history. If the facts for a section are unknown, omit the heading and log `needs-input:VARIANT:H2`. Never write placeholder text (TBD, TODO, Coming soon, N/A, Lorem, angle-bracket slots).
3. **Never lose content.** Restructure, never delete. Never delete text believed wrong; log `needs-input`.
4. **Never destroy.** Deleting, transferring, renaming, archiving, unarchiving, changing visibility or renaming a default branch happens only from an approved list.
5. **No confidential terms in public text.** Topics are public even on private repositories. Public org text never names a private repository, client, person, codename or strategy.
6. **One serialized writer** for all GitHub writes, and one owner per shared target.
7. **Agents never compose an org name, org description or tagline.** They come from the org identity table; a missing row is logged `needs-input`.
8. **Read-only browsing is allowed during planning.** Every write goes through the writer.

## Brand families

| Family | Orgs | Brand topic | Visual identity |
|---|---|---|---|
| CompleteTech | the 17 T1 orgs and CompleteDotTech | `completetech` | Blue cloud, gold circuit bulb, navy |
| AI Ascension | AI-Ascension | `ai-ascension` | Ink, paper and amber caret; its existing system is kept |
| Jev | Jev-Engineering, jevplay-games | `jev` | Jev-Engineering: near-black with cyan and violet nodes. jevplay-games: pink halftone and the pixel robot Jev. |
| LibreEvolve | LibreEvolve | `libreevolve` | Navy with an emerald lineage tree |
| Touched By An Agent | TouchedByAnAgent | `touchedbyanagent` | Maroon, amber and magenta; kept separate from CompleteTech core |
| romgenie (utility) | romgenie-archive-repostiory, romgenie-following-repos | `completetech` on own work and `.github`; none on forks | Glossy 3D vault objects on dark teal |
| Pick Your AI (T3) | Pick-Your-AI | `pick-your-ai` | Teal with an amber "P" (co-admin owned) |
| TicketStub (T3) | Jevelopers-neatHack-2026 | `ticketstub` (HOLD) | Owned by the team's `brand-kit` repository |

## Org identity (MUST, except the email row)

This table supplies the org `name`, the README nav name, the profile H1, the `.github` description and the card eyebrow. The tagline is the first sentence of the description, verbatim. Agents copy it; they never compose it.

| Owner | Name = nav name = profile H1 | Description | Eyebrow (T1 cards) |
|---|---|---|---|
| CompleteTech-LLC | CompleteTech LLC | Company sites, client tools and AI integration work from Cincinnati, Ohio. Innovation at Every Integration. | none: `COMPLETETECH LLC` alone |
| CompleteTech-Skills | CompleteTech Skills (nav name stays `CompleteTech LLC Skills`) | Claude and Codex agent skills for the agentic-services lifecycle, from discovery to invoice. A CompleteTech LLC organization. | SKILLS |
| CompleteTech-LLC-AI-Research | CompleteTech AI Research | Agent harnesses, game-playing agents, benchmarks and AI experiments. A CompleteTech LLC organization. | AI RESEARCH |
| `CompleteTech-Security` | CompleteTech Security | Offline, dependency-free CVE version checkers for network appliances and Node.js. A CompleteTech LLC organization. | SECURITY (banner category `SECURITY TOOLS`, as on the golden banner) |
| CompleteTech-Infrastructure | CompleteTech Infrastructure | Homelab services, self-hosted hosts and Windows helper tools. A CompleteTech LLC organization. | INFRASTRUCTURE |
| CompleteTech-Commerce | CompleteTech Commerce | Trading, market research and vending projects. A CompleteTech LLC organization. | COMMERCE |
| CompleteTech-Creative | CompleteTech Creative | Writing, podcast, social media and content production tools. A CompleteTech LLC organization. | CREATIVE |
| CompleteTech-Pokemon | CompleteTech TCG | Trading-card shop, community site and Game Boy emulation tools. Not affiliated with Nintendo or The Pokémon Company. A CompleteTech LLC organization. | TCG |
| CompleteTech-Data | CompleteTech Data | Business directories and public datasets, mostly for Ohio. A CompleteTech LLC organization. | DATA |
| CompleteTech-Games | CompleteTech Games | Crossword, puzzle and strategy game projects. A CompleteTech LLC organization. | GAMES |
| CompleteTech-Directories | CompleteTech Directories | Directory websites and the data behind them. A CompleteTech LLC organization. | DIRECTORIES |
| CompleteTech-Hardware | CompleteTech Hardware | KiCad electronics projects and hardware build tooling. A CompleteTech LLC organization. | HARDWARE |
| CompleteTechDiscord-Games | CompleteTech Discord Games | Games built as Discord activities. Not affiliated with Discord Inc. A CompleteTech LLC organization. | DISCORD GAMES |
| CompleteTech-DiscordApps | CompleteTech Discord Apps | Discord apps and community bots. Not affiliated with Discord Inc. A CompleteTech LLC organization. | DISCORD APPS |
| CompleteTech-Patent-IP | CompleteTech Patent and IP | Patent research and intellectual-property tracking tools. A CompleteTech LLC organization. | PATENT AND IP |
| CompleteTech-Career-Toolkit | CompleteTech Career Toolkit | Resume and career document tooling. A CompleteTech LLC organization. | CAREER TOOLKIT |
| CompleteTech-ManageEngine | CompleteTech ManageEngine Tools | ServiceDesk Plus cloud-readiness tools. Not affiliated with ManageEngine or Zoho Corporation. A CompleteTech LLC organization. | MANAGEENGINE TOOLS |
| AI-Ascension | AI Ascension | AI game-agent toolkit for Slay the Spire 2. Not affiliated with Mega Crit. Steward: CompleteTech LLC. | — |
| Jev-Engineering | Jev Engineering | Jev structured-decision research and tooling. Steward: CompleteTech LLC. | — |
| jevplay-games | jevplay.games | Browser games played against Jev at jevplay.games. Steward: CompleteTech LLC. | — |
| LibreEvolve | LibreEvolve | Open-source code-evolution workbench. Steward: CompleteTech LLC. | — |
| TouchedByAnAgent | Touched By An Agent | HOLD: leave unchanged | — |
| romgenie-following-repos | romgenie following | Forks of AI-agent projects followed by CompleteTech LLC. Credit and licenses belong to their upstream authors. | — |
| romgenie-archive-repostiory | romgenie archive | Retired CompleteTech LLC repositories, kept read-only for reference. | — |

Formula for future orgs: T1 `WHAT THE ORG HOLDS. A CompleteTech LLC organization.`; T2 `WHAT IT HOLDS. Steward: CompleteTech LLC.` A new description is a proposal until the user adds it to this table. T2 cards show the display name as text, not caps.

## Repository naming

| # | Rule | Test |
|---|---|---|
| N1 | Lowercase kebab-case; dots only in domain names | `^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)*$`; a dotted name must end in `.com`, `.tech`, `.llc`, `.club`, `.app`, `.ai`, `.games`, `.io`, `.net` or `.org` |
| N2 | No leading `_`, `-` or digit | `^[a-z]` |
| N3 | No underscores, no uppercase | covered by N1 |
| N4 | No filler suffixes or dates | fails on a trailing `-repo`, `-project`, `-code`, `-new`, `-final`, `-test` or `-v2`-style suffix, or on an 8-digit date unless the name ends `-backup-YYYYMMDD` (which must be archived) |
| N5 | At most 40 characters | `warn` only |
| N6 | No third-party trademark as the leading word of a new repository | human review |
| N7 | No typos | human review |

**Exempt (never rename):** GitHub forks (they keep the upstream name), `.github`, `ORG.github.io`, `CompleteDotTech/CompleteDotTech`, and anything T3 or HOLD. Renames are approval-gated and break Actions `uses:` references and Pages project URLs.

| Type | Pattern | Examples |
|---|---|---|
| Skill | `DOMAIN-skill`; lifecycle skills use `agentic-DOMAIN-skill` | `agentic-invoice-skill`, `github-showcase-skill` |
| Security check | `VENDOR[-PRODUCT]-cve-YYYY-N-check` or `ISSUE-check` | `netscaler-cve-2026-19489-check`, `php2shell-check` |
| Website | The exact FQDN it serves, without `www.` | `complete.tech`, `northwind-trading.com` |
| Self-hosted host | `HOST.home.complete.tech` | `nas.home.complete.tech` |
| MCP server (new) | `SUBJECT-mcp-server` | `sts2-mcp-server` |
| Product component | `PRODUCT-COMPONENT` | `pick-your-ai-website`, `sts2-gateway` |
| Jev family | `jev-THING` | `jev-sentinel`, `jev-tic-tac-toe` |
| Docker variant | `BASE-docker` | `northwind-dashboard-docker` |
| Private workspace | `SUBJECT-workspace` | `northwind-workspace` |
| Lesson | `VERB-…-in-N-steps` | `build-ai-workflows-in-5-steps` |
| Copy of upstream code that is not a GitHub fork | `UPSTREAM-fork` | `sqlite-fork` |
| Backup snapshot | `SOURCE-backup-YYYYMMDD`, then archived | `northwind-backup-20260101` |

The H1 is the product name and may differ from the slug (`jev-guess-who` has the H1 `Noul Who`).

## Homepage (About box website)

Check: a GET with a browser user agent and a 20 s timeout; a final `200` passes. Never clear or replace a non-empty homepage automatically; log `homepage-review` when it differs or fails. For an empty homepage, the first that passes: (1) a domain-named repository's `https://FQDN` (`complete.tech` stores `https://www.complete.tech`); (2) the repository's GitHub Pages URL; (3) a registry page (ClawHub, PyPI, npm) whose repository URL points back; (4) the family hub for public repositories: CompleteTech-Skills `https://www.complete.tech`, jevplay-games `https://jevplay.games`, TouchedByAnAgent `https://touchedbyanagent.com`, AI-Ascension its Pages site, Pick-Your-AI `https://pickyour.ai`; (5) otherwise empty. Never a github.com URL, an org page, a dead link or a private host.

## Forks, backups and archives

| Case | Action |
|---|---|
| GitHub fork, 0 commits ahead, parent outside the estate | Transfer to the watching org `romgenie-following-repos` (approval-gated); description `Fork of PARENT, followed for reference.`; topics `fork` plus up to 4 parent tech topics; no README change |
| GitHub fork whose parent is a T1 or T2 org | Stays; `Fork of` description; variant G: hero banner, the fork note (its short form when 0-ahead) and the footer |
| GitHub fork with its own commits | Stays; `Fork of PARENT with STEWARD changes.`; `fork` topic; README variant G: hero banner, fork note with the compare link, footer (q27 default) |
| Non-network copy (`-fork` suffix) | Stays private; README credits the upstream; the upstream LICENSE must be present |
| Backup snapshot (`-backup-YYYYMMDD`) | `Archived:` description, variant H callout, then archive in place (approval-gated) |
| Retired own repository | Description and H callout, then archive (private: in the archive org; public: in place); approval-gated |

Watching-org forks get no commits, no art, no README change, no pins and no social preview. Archive whenever anything of value remains; delete only empty or exact-duplicate repositories with no stars, forks, releases, Pages, issues or references, after a full backup and approval.
