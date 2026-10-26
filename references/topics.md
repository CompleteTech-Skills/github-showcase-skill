# Topic taxonomy (closed vocabulary)

Condensed from `ct-std-v1` §5, verbatim where it matters. `showcase.py topics` runs the merge algorithm below and prints `{current, proposed, equal_as_set, add[], remove[], logs[]}`; `--also-in ORG[,ORG]` (or `--registry [FILE]`, which reads the repo's `also_in` from `registry/estate.yaml`, read only; or an `also_in` list in the metadata) adds the org membership topics; `--gh` prints the single `gh api -X PUT repos/OWNER/REPO/topics -f names[]=…` command without running it. The machine-readable lists are `references/standard/topics.yaml` and `references/standard/types.yaml`.

GitHub limits: lowercase `[a-z0-9-]`, at most 50 characters each and 20 per repository (the estate uses at most 10). `PUT` replaces the whole set and rejects the whole set if one topic is invalid. **Topics are public even on private repositories.**

## Layers and counts (R3)

A topic belongs to the first layer it matches: brand (Brand topic) → family (Family topics, for that org) → org membership (Org membership topics) → type (Type) → domain (Domain vocabulary) → tech (Tech vocabulary), each a section below.

| Repo kind | Required set |
|---|---|
| Non-fork, non-`.github` | Exactly 1 brand; all applicable family topics; one org membership topic per `also_in` org; exactly 1 type; 0–3 domain; 0–3 tech. Every topic is in the brand, family, type and tech lists or Domain vocabulary, or is the Security vendor token (Domain vocabulary). **5–10 topics if public, 3–8 if private**; org membership topics count toward the maximum but not as brand topics. If the set is below the minimum after the merge algorithm, write it anyway, log `topics-short`, and report R3 as `warn`. |
| Fork | `fork` plus 0–4 tech topics taken from the parent's topics (Tech vocabulary only, after aliasing). No brand, no family. A fork listed in `also_in` also carries that org membership topic (counted toward the maximum of 10). |
| `.github` and `CompleteDotTech/CompleteDotTech` | Exactly `[<brand>, github-profile]` |

## Brand topic

`completetech` on every T1 repo and CompleteDotTech. T2: `ai-ascension`, `jev`, `libreevolve` or `touchedbyanagent`. T3 (after approval): `pick-your-ai`; `ticketstub` is HOLD. romgenie: `completetech` on own work and `.github`, none on forks.

## Family topics

Family topics apply only to non-fork repos other than `.github`, in this order:

| Org | Family topics | Scope |
|---|---|---|
| CompleteTech-Skills | `claude-skill`, `codex-skill`, `agentic-ai` | Only repos of type `agent-skills`. `claude-skill` is omitted only for `creative-studio`. |
| CompleTetech-Security | `security`, `cve` | all |
| CompleteTech-LLC-AI-Research | `ai-research` | all |
| CompleteTech-Infrastructure | `homelab` | all |
| AI-Ascension | `sts2` | all except `jev-factorio-agent` |
| jevplay-games | `browser-game` | only type `game` |
| All other orgs | none | — |

## Type: detection, topic, variant and card label

**Detection (first match wins, checked on the default branch).** "Dependency" means a name in `requirements*.txt`, `pyproject.toml` dependencies, or `package.json` `dependencies`/`devDependencies`. File patterns match anywhere in the tree unless "root" is stated.

| # | Rule | Type |
|---|---|---|
| 1 | `fork: true`, or slug ends `-fork` | `fork` |
| 2 | slug matches `-backup-\d{8}$` | `backup` |
| 3 | slug is `.github`, or the repo is `CompleteDotTech/CompleteDotTech` | `github-profile` |
| 4 | `is_template: true` | `template` |
| 5 | `SKILL.md` at root | `agent-skills` |
| 6 | owner `CompleTetech-Security` | `security-check` |
| 7 | dependency `@modelcontextprotocol/sdk`, `mcp` or `fastmcp`, or "MCP server" in the H1 or description | `mcp-server` |
| 8 | root `manifest.json` containing `"manifest_version"` | `chrome-extension` |
| 9 | root `.claude-plugin/plugin.json`, `plugin.json` or `*.plugin.json` | `plugin` |
| 10 | dependency `discord.js`, `discord.py`, `py-cord` or `nextcord` | `discord-bot` |
| 11 | dependency `python-telegram-bot`, `slack_bolt`, `@slack/bolt`, `telegraf` or `tmi.js` | `bot` |
| 12 | owner `jevplay-games`, `CompleteTech-Games` or `CompleteTechDiscord-Games` | `game` |
| 13 | `AndroidManifest.xml` or `*.xcodeproj` | `mobile-app` |
| 14 | slug ends `.home.complete.tech` | `infrastructure` |
| 15 | slug matches `\.(com\|tech\|llc\|club\|app\|ai\|games\|io\|net\|org)$` | `website` |
| 16 | `*.kicad_pro` or `*.kicad_pcb` | `hardware` |
| 17 | `compose.yaml`, `docker-compose.yml` or `*.tf` | `infrastructure` |
| 18 | dependency `react`, `next`, `vue`, `svelte`, `astro` or `streamlit` | `web-app` |
| 19 | dependency `fastapi`, `flask` or `express` | `api` |
| 20 | `[project.scripts]`, `console_scripts`, or `package.json` `"bin"` | `cli` |
| 21 | `pyproject.toml` or `setup.py`, or `package.json` with `main` or `exports` | `library` |
| 22 | owner `CompleteTech-LLC-AI-Research`, or `*.ipynb` ≥ 50% of files | `research` |
| 23 | slug matches `-in-\d+-steps$` | `tutorial` |
| 24 | `*.csv`, `*.json` and `*.parquet` ≥ 50% of bytes | `dataset` |
| 25 | otherwise | `workspace` |

**The 24 type topics are reserved.** A repo carries exactly one of them, and only as its type topic.

| Type topic | README variant ([readme-variants.md](readme-variants.md)) | Card category ([banner-layout.md](banner-layout.md)) |
|---|---|---|
| `agent-skills` | A in CompleteTech-Skills; C elsewhere | Agent skill |
| `website`, `web-app`, `mobile-app`, `chrome-extension` | B | Website, Web app, Mobile app, Chrome extension |
| `cli`, `library`, `api`, `mcp-server`, `bot`, `discord-bot`, `plugin`, `template`, `tutorial` | C | CLI tool, Library, API service, MCP server, Bot, Discord bot, Plugin, Template, Tutorial |
| `research`, `dataset` | D | Research, Dataset |
| `game` | E | Game |
| `security-check` | F | CVE checker |
| `fork` | G outside romgenie-following-repos (hero banner, fork note, footer; the note's short form when 0-ahead; review q27); in the watching org no README change | no card |
| `backup` (and every repo about to be archived) | H | no card |
| `github-profile` | J (`.github`) or the CompleteDotTech profile rules (`CompleteDotTech/CompleteDotTech`) | no card |
| `infrastructure`, `hardware`, `workspace` | I when private; C when public | Infrastructure, Hardware, Workspace |

A private repo on variants A–E keeps that variant, adds the I callout and the private License text (row 7 in [readme-variants.md](readme-variants.md)), and its nav line ends with ` · Internal`.

## Org membership topics (decision 5)

A repo has one home org and may be cross-listed on other orgs through `also_in` in `registry/estate.yaml` (never a fork). Each `also_in` org adds its org membership topic, so a topic search for that org finds its cross-listed repos. The values are the `org_topics` map in `references/standard/topics.yaml`, generated from the registry's `org_topic` (the registry wins if they differ; an org rename updates both).

- Placed after the family topics and before the type topic, in `also_in` order. The home org's own topic is never added; an existing one is dropped as outside the repo's vocabulary (so `completetech-llc` is no longer an alias of `completetech`).
- Counts toward the 10/8 maximum, not as a brand topic. If brand + family + org + type alone exceed the maximum, org topics drop from the end of the `also_in` list, logged `topics-over:ORG`; the profile cross-listing stays.
- The two romgenie utility orgs have none (`null`; logged `org-topic-none:ORG`). T3 org topics (`pick-your-ai`; `ticketstub` is HOLD) are added only after co-owner sign-off (logged `t3-signoff:also-in:ORG`). An org with no `org_topics` row logs `needs-input:org-topic:ORG`.

| Org | Topic | Org | Topic |
|---|---|---|---|
| CompleteTech-LLC | `completetech-llc` | CompleteTech-Directories | `completetech-directories` |
| CompleteTech-Skills | `completetech-skills` | CompleteTech-Hardware | `completetech-hardware` |
| CompleteTech-LLC-AI-Research | `completetech-ai-research` | CompleteTech-DiscordApps | `completetech-discord-apps` |
| CompleTetech-Security | `completetech-security` | CompleteTechDiscord-Games | `completetech-discord-games` |
| CompleteTech-Infrastructure | `completetech-infrastructure` | CompleteTech-Patent-IP | `completetech-patent-ip` |
| CompleteTech-Commerce | `completetech-commerce` | CompleteTech-Career-Toolkit | `completetech-career-toolkit` |
| CompleteTech-Creative | `completetech-creative` | CompleteTech-ManageEngine | `completetech-manageengine` |
| CompleteTech-Pokemon (TCG) | `completetech-tcg` | AI-Ascension | `ai-ascension` |
| CompleteTech-Data | `completetech-data` | Jev-Engineering | `jev-engineering` |
| CompleteTech-Games | `completetech-games` | jevplay-games | `jevplay-games` |
| LibreEvolve | `libreevolve` | TouchedByAnAgent | `touchedbyanagent` |
| Pick-Your-AI (T3) | `pick-your-ai` | Jevelopers-neatHack-2026 (T3) | `ticketstub` (HOLD) |
| romgenie-archive-repostiory | none | romgenie-following-repos | none |

## Tech vocabulary and alias map

**Featured:** `ai`, `llm`, `mcp`, `ai-agent`, `agentic-ai`, `claude`, `claude-code`, `openai`, `chatgpt`, `generative-ai`, `prompt-engineering`, `machine-learning`, `rag`, `langchain`, `python`, `javascript`, `typescript`, `nodejs`, `rust`, `cpp`, `react`, `nextjs`, `astro`, `tailwind`, `fastapi`, `docker`, `devops`, `actions`, `sdk`, `automation`, `security`, `privacy`, `vscode-extension`, `jupyter-notebook`.

**Allowed:** `pdf`, `pdf-generator`, `reportlab`, `streamlit`, `vllm`, `ollama`, `gemini`, `anthropic`, `discord`, `obs`, `kicad`, `blender`, `gltf`, `self-hosted`, `cve`, `reinforcement-learning`, `computer-vision`, `vue`, `c`, `csharp`, `go`, `java`, `kotlin`, `swift`, `shell`, `powershell`, `html`, `css`, `lua`, `godot`.

**Language map** (`GET /repos/{o}/{r}/languages`, top language): Python→`python`, JavaScript→`javascript`, TypeScript→`typescript`, C++→`cpp`, C→`c`, C#→`csharp`, Go→`go`, Rust→`rust`, Java→`java`, Kotlin→`kotlin`, Swift→`swift`, Shell→`shell`, PowerShell→`powershell`, HTML→`html`, CSS→`css`, Jupyter Notebook→`jupyter-notebook`, Dockerfile→`docker`, Lua→`lua`, GDScript→`godot`. Anything else is skipped.

**Framework map** (first dependency, in manifest order, found here): `react`→`react`, `next`→`nextjs`, `astro`→`astro`, `tailwindcss`→`tailwind`, `fastapi`→`fastapi`, `streamlit`→`streamlit`, `langchain`→`langchain`, `reportlab`→`reportlab`, `@modelcontextprotocol/sdk`/`mcp`/`fastmcp`→`mcp`, `openai`→`openai`, `anthropic`/`@anthropic-ai/sdk`→`anthropic`, `discord.js`/`discord.py`→`discord`, `ollama`→`ollama`, `vllm`→`vllm`.

Alias map (MUST):

```yaml
aliases:
  artificial-intelligence: ai
  llms: llm
  large-language-model: llm
  large-language-models: llm
  model-context-protocol: mcp
  ai-agents: ai-agent
  agents: ai-agent
  agent-skill: agent-skills
  claude-ai: claude
  claude-cli: claude-code
  claude-code-cli: claude-code
  agentic-workflows: agentic-ai
  agentic-development: agentic-ai
  genai: generative-ai
  gen-ai: generative-ai
  github-actions: actions
  tailwindcss: tailwind
  next-js: nextjs
  reactjs: react
  vuejs: vue
  node: nodejs
  node-js: nodejs
  py: python
  python3: python
  js: javascript
  ts: typescript
  golang: go
  c-plus-plus: cpp
  cplusplus: cpp
  jupyter: jupyter-notebook
  command-line: cli
  retrieval-augmented-generation: rag
  pdf-generation: pdf-generator
  home-assistant: home-automation
  mcp-servers: mcp-server
  complete-tech: completetech
```

## Merge algorithm

1. `GET /repos/{o}/{r}/topics`; lowercase; apply the alias map.
2. **Drop:**
   - topics not matching `^[a-z0-9][a-z0-9-]{0,49}$`;
   - topics matching `^(wip|todo|beta|alpha|deprecated|archived|latest|stable|experimental|v\d+(\.\d+)*|(19|20)\d{2})$`;
   - topics equal to the lowercased owner or starting with `<lowercased owner>-`, except the brand topic;
   - any Type type topic that is not this repo's type;
   - topics outside the vocabulary (Layers and counts), and topics that fail Topic safety.
3. Required set: brand + family + org membership (from `also_in`, never from existing topics) + type.
4. Domain: derive per Domain vocabulary (≤ 3).
5. Tech: the mapped top language, then the mapped framework, then surviving existing Tech vocabulary topics in GitHub's returned order; deduplicate; ≤ 3.
6. **Output order:** brand, family (Family topics order), org membership (`also_in` order), type, domain (derivation order), tech. Truncate from the end to 10 (public) or 8 (private).
7. Compare with the current topics **as sets**. If equal, skip. Otherwise `PUT /repos/{o}/{r}/topics` with the full ordered list.

## Topic safety (MUST)

- **Never** client names, person names, unreleased product names, credentials, hostnames or internal codenames. Never adult or explicit words.
- **Never** a game or entertainment brand on a private repo (`pokemon`, `amongus`, `nintendo`); use `trading-cards`, `emulation` or `games`.
- Technology product names in the vocabulary (`claude-skill`, `codex-skill`, `discord-bot`, `chrome-extension`, `discord`) and the family topic `sts2` are allowed on any repo. Any other trademark is allowed only through Domain vocabulary or the Security vendor token.
- TouchedByAnAgent domain topics come only from {`ble`, `wearables`, `smart-ring`}; never adult, `nsfw` or device brand names.

## Worked examples

| Repo | Before | After |
|---|---|---|
| Skills/agentic-invoice-skill | agentic-development, agentic-workflows, billing, claude-skill, codex-skill, completetech, invoice, pdf-generator | `completetech`, `claude-skill`, `codex-skill`, `agentic-ai`, `agent-skills`, `invoice`, `billing`, `python`, `reportlab`, `pdf-generator` (10) |
| Skills/creative-studio | 12 topics, no `claude-skill` | `completetech`, `codex-skill`, `agentic-ai`, `agent-skills`, `sprite-animation`, `character-animation`, `rigging`, `python`, `blender`, `gltf` (10) |
| Security/netscaler-cve-2026-19489-check | — | `completetech`, `security`, `cve`, `security-check`, `netscaler`, `python` (6) |
| jevplay-games/jev-connect-four | — | `jev`, `browser-game`, `game`, `board-game` (if "board game" is in the description), `<language>` (5) |
| Research/llama.cpp (fork) | upstream | `fork` plus ≤ 4 parent topics that are in Tech vocabulary (for example `llm`, `cpp`); no brand |
| Northwind-Trading-Co/ledger-sandbox (private) | — | `completetech`, `<detected type>`, `trading`, `finance` (if in the description), `python` (5; private minimum 3) |

In the invoice row, existing Domain vocabulary topics rank first (`invoice` occurs in the description; `billing` does not), and the tech layer is the language (`python`), the framework (`reportlab`), then the surviving `pdf-generator`.

## Domain vocabulary (closed; only the standard owner edits it)

Every entry is public-safe:

`finance`, `trading`, `ecommerce`, `marketing`, `sales`, `content-creation`, `podcast`, `social-media`, `publishing`, `directory`, `patents`, `career`, `trading-cards`, `emulation`, `games`, `board-game`, `puzzle-game`, `homelab`, `home-automation`, `email`, `invoice`, `billing`, `envelope`, `contract`, `proposal`, `case-study`, `testimonials`, `time-tracking`, `usage-tracking`, `orchestration`, `sprite-animation`, `character-animation`, `rigging`, `benchmarks`, `arxiv`, `game-agents`, `observability`, `data-visualization`, `ble`, `wearables`, `smart-ring`.

**Derivation:**

1. Candidates are Domain vocabulary entries found as whole words in the description, then in the H1, in order of first occurrence. Spaces become hyphens, and both sides are compared in singular form (`sprite animations` matches `sprite-animation`; `patent` matches `patents`). The entry is written as listed.
2. Existing topics that are in Domain vocabulary rank first: those found in the text in occurrence order, then the rest alphabetically.
3. CompleTetech-Security repos whose slug matches `-cve-\d{4}-\d+-check$` put the slug's first token (the vendor, for example `netscaler`) first, and keep that vendor topic through step 2's vocabulary drop. The owner is matched through the shared resolver (CQ-03), so after the approved rename to `CompleteTech-Security` (or under any letter case) the same repository keeps the same topics; the TouchedByAnAgent domain list below is matched the same way.
4. Keep at most 3. No match means no domain topic; log `needs-input:domain-topic`.
