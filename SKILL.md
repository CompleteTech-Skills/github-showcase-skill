---
name: github-showcase-skill
description: >-
  Generate CompleteTech LLC README hero banners, repo cards, social previews, repo icons, org tiles, profile intros
  and footers; audit repos against the CompleteTech GitHub estate standard (About description, topics, labels, README
  variants, links, language bar, Actions, images, About sidebar, SVG rules); render org profile READMEs and plan org
  About fields, pins, star lists, labels and health files; capture, lint and copy GitHub Projects boards from the
  estate template; and snapshot, check and plan the CompleteTech Enterprise. Read-only toward GitHub: it emits files,
  JSON plans and gh/writer jobs. Use when creating, polishing or auditing any CompleteTech, AI Ascension, Jev
  Engineering, jevplay-games, LibreEvolve or TouchedByAnAgent repo, README, org, org profile, GitHub Project or the
  Enterprise so it matches the rest of the estate.
version: 1.0.0
metadata:
  openclaw:
    skillKey: github-showcase-skill
    homepage: https://github.com/CompleteTech-Skills/github-showcase-skill
    requires:
      bins:
        - python3
    install:
      - kind: uv
        package: fonttools==4.67.0
      - kind: uv
        package: uharfbuzz==0.57.0
      - kind: uv
        package: pillow==13.0.0
      - kind: uv
        package: pyyaml==6.0.3
---

# GitHub Showcase Skill

## At a Glance

| What it creates | Best for | Output |
|---|---|---|
| README hero banners, repo cards, social previews, repo icons, org banners and tiles, profile intros, the estate footer, README scaffolds, org profile READMEs, standard checks, and plans for orgs, GitHub Projects, the Enterprise and repository content | Making any CompleteTech-family repository, README, org, org profile, project board, the Enterprise or the profile page match the estate, and keeping it that way | `docs/images/banner.png` (1280×360 or 2560×720), `docs/images/card.svg`, `assets/social-preview.png` (1280×640), `assets/icon.png` (1024×1024), org banner JPG (1600×400), tile and intro SVGs, README marker blocks, `profile/README.md` and `profile/data.json`, JSON check results and plans, change records, `scripts/writer.py` jobs (JSON lines), coverage rows |

Every surface uses one **dark** design on both GitHub themes (decision 21): navy grid canvas, a card for the repo icon (or the org's Neon Night mark), a sky-blue eyebrow, the repo slug in monospace, two to four fact chips and an accent bar. All text is typeset from the bundled OFL fonts with HarfBuzz and outlined to paths, so outputs are deterministic and never depend on a web font or an image model. One CLI, `scripts/showcase.py`, does every generation, check and plan: the repository commands below, and four command groups, `org`, `project`, `enterprise` and `content`, for orgs, GitHub Projects, the Enterprise and repository content.

## Use When

| Situation | Start with |
|---|---|
| A repository needs its README hero banner or repo card | `banner`, then `card` (and `content social` for R10) |
| A README must be scaffolded or upgraded to its standard variant, with the footer | `readme` (dry run), then `readme --write`, then `footer --check` |
| A description, topic set or label set must be checked before a write is queued | `describe`, `topics`, `labels --plan` |
| An org profile or the personal profile needs cards, tiles, a banner or the animated intro | `card`, `org-tile`, `org-banner`, `intro` and [references/profile-readmes.md](references/profile-readmes.md) |
| An org needs its profile README, About fields, pins and star List, labels or `.github` health files, or an org must be verified as done | `org profile`, `org about`, `org pins`, `org labels`, `org health`, `org doctor` ([references/org.md](references/org.md)) |
| An org needs its GitHub Project board from the estate template, or a board must be checked | `project capture-query`, `normalize`, `copy-plan`, `readme`, `lint`, `estate-plan` ([references/projects.md](references/projects.md)) |
| The CompleteTech Enterprise must be captured, checked or planned | `enterprise snapshot-query` or `snapshot`, then `enterprise doctor`, `seat-check`, `plan` ([references/enterprise.md](references/enterprise.md)) |
| A repository's links, language bar, Actions, README images, About sidebar, icon or social preview must be checked or produced | `content links`, `linguist`, `actions`, `images`, `sidebar`, `icon`, `social` ([references/content.md](references/content.md)) |
| A new repository is created from `completetech-repo-template` | `new OWNER/NAME --type T` (the create job, then `adopt`), then the composite Action in `action.yml` (runs `readme --bootstrap`) |
| A repository exists but never went through the standard (created by an agent, a pipeline or a transfer) | `adopt OWNER/REPO`; for the whole estate, `doctor --estate` (intake proposals and template drift) |
| A set must be reviewed the way GitHub shows it | `contact-sheet` |
| Coverage must be reported or a repository verified as done | `lint all`, then `doctor` |

Do not use it for accounts outside the estate. Excluded owners (BunsDev, GoZippy, h-mascot, lmvdz, GalaxyRuler, and per decisions 1 and 2 MetatronAngelAgent and PrompDev) and T3 owners before co-owner sign-off (Pick-Your-AI, Jevelopers-neatHack-2026) are refused with exit 2.

## Boundaries

| This skill does | This skill does not |
|---|---|
| Render banners, cards, tiles, intros and contact sheets from metadata and committed brand files. | Draw illustrations, or let an image model draw text, logos or marks. |
| Lint descriptions, topics, labels, READMEs, SVGs and banner PNGs against `ct-std-v1` and the user decisions. | Compose a new description sentence, an org description or a tagline; it returns `needs-writer` with the template. |
| Propose GitHub changes as diffs, `gh` command lines, change records and `scripts/writer.py` jobs (`browser` jobs with exact click paths for UI-only steps) for a serialized writer. | Perform GitHub writes on its own. The only write is the Action committing into its own repository; label plans leave as `gh` argv and writer jobs (`labels --plan`). |
| Write only the paths given by `--out`, `--out-dir`, `--jobs`, `--report` or `--records`, or README marker blocks and `docs/images/*` with `--write`. | Delete text from a README, crop or recolour a mark, or truncate text with an ellipsis. |
| Read metadata from a JSON file or with read-only `gh api` GETs, and read the private estate registry without copying it. | Read credentials, persist state, schedule jobs, change repository settings, or copy the registry's private data into a repository. |

## Core Workflow

Run every command **from inside the target repository's checkout**, with the skill's script by path: `python3 <skill-dir>/scripts/showcase.py ...`. With `--meta`, the checkout must be the repository the metadata describes (its `origin` is compared); otherwise pass `--repo-dir DIR` or `--no-repo-dir`. A missing `--repo-dir` exits 2, and default outputs (`docs/images/...`) are always written inside the target checkout, never into the current directory or the skill.

| Step | Command | Gate |
|---|---|---|
| 1 | `meta --from-gh OWNER/REPO --out meta.json`, or pass an existing `--meta` file. It also records `pushed_at` and `last_substantive_commit` (CQ-16: the newest default-branch commit whose message does not match `ct-std-v1\|showcase banner and card\|\[skip ci\]`) | Refused owners stop here (exit 2); T3 owners pass only with `--allow-t3`, after an approved `t3-metadata` or `t3-signoff` row. Watching-org forks get metadata only. Archived repositories are in scope (decision 6): the orchestrator unarchives, polishes and re-archives them. |
| 2 | `describe` | `keep`, `edit` (smallest passing edit, in `proposed`) or `needs-writer`. On `needs-writer`, write the sentence yourself from the template in [references/descriptions.md](references/descriptions.md) and the repository's facts, then re-run `describe --text "..."` until it answers `keep`. The tool never composes it. |
| 3 | `topics`, `labels --plan` | Proposals only. Add `--records FILE` to emit change records, `--gh` to print the exact `gh` commands. |
| 4 | Apply the approved description and topics on GitHub (the writer), or write them into `meta.json` | Before any art: the banner subtitle, the card and the README tagline come from the description, so rendering first breaks R2 (tagline equals description) the moment the writer applies the new one. |
| 5 | `banner`, then `card` (and `content social`) | `art-fail` (exit 3) writes nothing. `needs-input` (exit 4) names the missing fact, including fewer than two fact chips (`needs-input:banner-chips`; add `chips:` to `.github/showcase.yml` or pass `--key-chip`/`--chip`). |
| 6 | `readme`, then `readme --write` | Dry run prints a unified diff first. `readme-shrink` (exit 1) writes nothing. |
| 7 | `footer --check README.md`, `lint all` | Every applicable check passes; `incomplete` is allowed for logged `needs-input` omissions. |
| 8 | `doctor --header` | One coverage row. `done` only when every applicable cell is `pass`, `warn`, `incomplete` or `n/a`, and the banner has two to four chips. |
| 9 | `contact-sheet` | A human (or an independent verifier) views the set on both GitHub page colours before rollout. Pass PNGs: `card --png`, `org-tile --png` previews, or install the optional `resvg_py` (`requirements-preview.txt`) so SVG inputs (the intro's static frame) render too; otherwise an SVG input exits 2. |

**Who applies GitHub changes.** Under the estate orchestrator, every proposal (description, topics, labels, README) goes to its single writer queue as change records. Used standalone, with no orchestrator: show the user the `--gh` command lines (or the `argv` of `labels --plan`) and the README diff; the user runs them after approving that repository's changes. The skill itself never runs a write.

**Install.** System Python on Ubuntu 24.04, Debian 12 and Homebrew refuses `pip install` ("externally managed environment"). Use a virtual environment (or `uv`):

```bash
python3 -m venv .venv && . .venv/bin/activate      # or: uv venv && . .venv/bin/activate
python -m pip install -r <skill-dir>/requirements.txt  # or: uv pip install -r <skill-dir>/requirements.txt
```

```bash
cd ../agentic-email-skill                               # the target checkout
S=<skill-dir>/scripts/showcase.py
python3 $S meta --from-gh CompleteTech-Skills/agentic-email-skill --out /tmp/meta.json
python3 $S --meta /tmp/meta.json describe
python3 $S --meta /tmp/meta.json banner                 # writes docs/images/banner.png in this checkout
python3 $S --meta /tmp/meta.json doctor --header
```

| Exit | Meaning |
|---|---|
| 0 | ok, including `warn`, `incomplete` and `n/a` |
| 1 | a check failed |
| 2 | usage or config error, or an excluded, hold or T3 owner |
| 3 | `art-fail`: text does not fit the fixed size ladder, or the PNG budget cannot be met |
| 4 | `needs-input` blocks a generator (for example an empty description) |

Checks (`describe`, `topics`, `labels`, `readme`, `footer`, `meta`, `fingerprint`, `config`) print one JSON object with `command`, `owner`, `repo`, `result` and `logs[]`; `lint` prints one JSON line per file; `org`, `project`, `enterprise` and `content` print one JSON object with `action` (`org doctor --doctor-format tsv|md` prints a row). Generators (`banner`, `card`, `org-banner`, `org-tile`, `intro`, `contact-sheet`) print a short text summary by default; pass the global `--format json` (before the command) for the same JSON object. `doctor` prints a TSV row (`--format json|md` after `doctor`). In text mode a refusal goes to stderr. Log codes are the standard's: `needs-input:<detail>`, `art-fail`, `topics-short`, `label-conflict`, `label-referenced`, `label-rewrite-first`, `needs-input:label-references` (a rename held because §6.4 rule 0 needs a checkout: re-plan with `--repo-dir`), `readme-shrink`, `dead-link`, `exempt`, `hold`, `t3-signoff`, `archived`, plus `needs-input:metadata` (a failed metadata capture, exit 4), `needs-input:file-tree` (no checkout and no tree in the metadata, so the type is provisional), `needs-input:visibility`, `needs-input:banner-chips` (fewer than two chips), `needs-input:key-chip` (no gold chip: the type category would repeat the eyebrow), `needs-input:subtitle` (no one-line subtitle: add `subtitle:`), `type-override:<type>`, `type-config:<type>` (from `.github/showcase.yml`) and `bootstrap:edited`.

## Orgs, Projects, the Enterprise and Content

CLI stdout and stderr use UTF-8, including redirected Windows output, raw footer markup,
JSON, help and errors. Decode captured CLI output as UTF-8; JSON keeps Unicode characters
without ASCII escaping. No `PYTHONIOENCODING` workaround is needed.

The four command groups follow the same rules as the repository commands: read-only toward GitHub, one JSON object on stdout (`command`, `action`, `owner`, `result`, `logs[]`), the same exit codes, and refusals for excluded, HOLD and T3 owners. What they add:

**Command-name contract.** The orchestrator, the standard and other workstreams call these names, so they are fixed: the repository commands in the Command Reference; the top-level generators `banner`, `card`, `org-banner`, `org-tile`, `intro` and `contact-sheet`; and the groups `org {profile,about,pins,labels,health,doctor}`, `project {capture-query,normalize,copy-plan,readme,lint,estate-plan}`, `enterprise {snapshot-query,discover,snapshot,doctor,seat-check,diff,plan}` and `content {social,icon,links,linguist,actions,images,sidebar}`. The social preview is `content social`; the old top-level `social-preview` still parses as a hidden, deprecated alias (same options, same file, logged `deprecated:social-preview`) and is not documented as a command.

- **Writer jobs.** Every planned GitHub change is a `scripts/writer.py` job `{id, phase, kind, repo|org, approval_id?, group?, argv, note}`; `--jobs FILE` appends them as JSON lines. Label jobs carry `group: labels:OWNER/REPO` for the writer's half-completed-group reconciliation unless the orchestrator passes its own group. UI-only steps are `kind: "browser"` jobs with `url`, `ui_action` and the exact click path in `steps`. A job that needs an approval carries the id `scripts/writer.py` looks up in `decisions/APPROVED_ACTIONS.yaml` (`ent-001`/`ent-002` for the Enterprise, `q41.orgs`/`q41.estate` for a project copy, the ids you pass with `--approval-id` or `--approval`). Mutations are always inline in `argv`; only read queries load from a file. The skill never runs a job: the orchestrator's writer does, after its guard and approval checks, or, used standalone, the user does after approving it.
- **One org resolver (CQ-03).** Every org lookup (in `enterprise doctor` too) goes through `scripts/ctshowcase/resolver.py`, which maps old and new logins from `former_slugs` in `brand.yaml` or the registry, the registry's `placeholders`, and approved `org-rename`/`org-merge` items; repository slugs the registry writes after a pending `rename` or `transfer` resolve to today's slug the same way. After an approved rename (for example `CompleTetech-Security` to `CompleteTech-Security`) the brand row, the registry row, the watching-org exemption and every refusal still resolve, and jobs name the new login.
- **The estate registry is private.** `org` reads `registry/estate.yaml` (`--registry FILE`, or the bundle beside the skill, or `$SHOWCASE_ESTATE_ROOT`) and renders public pages only from its public slice. Never copy the registry into a repository. Without it, `org` exits 4 (`needs-input:registry`); `project`, `enterprise` and `content` run on their input files alone. `examples/estate/` is a synthetic Northwind registry for trying every `org` action offline.

| Group | Typical sequence | Reference |
|---|---|---|
| `org` | `org about ORG --jobs J`, `org labels ORG --meta-dir M --jobs J`, `org profile ORG --meta-dir M --out-dir <ORG/.github checkout>`, `org pins ORG --jobs J`, then `org doctor ORG --snapshot S` | [references/org.md](references/org.md) |
| `project` | `project capture-query` (reference board), `normalize`, `copy-plan --target ORG` (stage 1), re-capture, `copy-plan --copied FILE --files-dir DIR --jobs J` (stage 2), `readme`, `lint` | [references/projects.md](references/projects.md) |
| `enterprise` | `enterprise snapshot-query --slug S` or `snapshot --slug S --out F`, then `doctor`, `seat-check`, `plan --jobs J`; `diff` after the run | [references/enterprise.md](references/enterprise.md) |
| `content` | `content links --base-ref origin/main`, `linguist`, `actions`, `images`, `sidebar --facts F`, `icon prompt`, `icon normalize`, `icon check`, `social --job` | [references/content.md](references/content.md) |

```bash
S=<skill-dir>/scripts/showcase.py
SHOWCASE_ESTATE_ROOT=<skill-dir>/examples/estate python3 $S org profile Northwind-Trading-Co --meta-dir <skill-dir>/examples/estate/meta
python3 $S project copy-plan --target CompleteTech-Skills --source CompleteTech-LLC/7 --jobs jobs.jsonl
python3 $S enterprise plan --snapshot registry/enterprise.snapshot.json --jobs jobs.jsonl
python3 $S --meta meta.json content links --base-ref origin/main --diff     # inside the target checkout
```

## Command Reference

```text
python3 <skill-dir>/scripts/showcase.py [--config PATH] [--repo-dir DIR | --no-repo-dir] [--meta FILE] [--type TYPE] [--format json|text] [--quiet] [--version] <command> [options]

meta --from-gh OWNER/REPO [--out FILE] [--allow-t3]
fingerprint [--out-dir docs/images] [--github-output]
fonts [--check | --fetch]
config [--write-lock] [--crop]
describe [--text TEXT] [--type TYPE] [--records FILE]
topics [--records FILE] [--gh] [--also-in ORG[,ORG] | --registry [FILE]]
labels --emit-yml
labels --plan [--references] [--records FILE] [--gh] [--jobs FILE] [--allow-hold]
banner [--out docs/images/banner.png] [--scale 2] [--icon PATH] [--subtitle TEXT]
       [--key-chip TEXT]... [--chip TEXT]... [--category TEXT] [--allow-unmeasured] [--allow-hold]
       [--allow-few-chips] [--png-budget 300000]
card [--out docs/images/card.svg] [--png PATH] [--icon PATH] [--allow-unmeasured] [--allow-hold]
org-banner --org OWNER --out PATH [--illustration PATH]
org-tile --org OWNER [--avatar PATH] [--illustration PATH] [--out PATH] [--png PATH]
intro (--profile CompleteDotTech | --org OWNER) [--name TEXT] [--eyebrow TEXT] [--tagline TEXT]
      [--chip key:TEXT] [--chip attr:TEXT]... [--mark PATH] [--height 320|360] [--static] [--out assets/intro.svg]
footer [--check README.md [--online]] [--org OWNER] [--raw]
readme [--mode auto|scaffold|upgrade|header] [--variant auto|A|B|C|D|E|F|G|H|I|J]
       [--write] [--diff] [--records FILE] [--bootstrap]
lint svg --kind intro|card|tile|plate|divider FILE...
lint readme [README.md] [--variant auto]
lint banner [docs/images/banner.png]
lint all
lint public-leak FILE... [--meta-dir DIR] [--registry FILE] [--decisions FILE] [--org ORG[,ORG]]
lint prose [FILE...] [--text TEXT]... [--prose-kind text|description|tagline] [--preserved] [--allow WORD]...
contact-sheet INPUT... --out PATH [--mode grid|stack|avatar] [--tile W] [--cols N] [--gap 24]
              [--widths 1012,390] [--mask none|circle|rounded] [--labels] [--title TEXT]
contact-sheet --org OWNER --cross-surface --out PATH [--avatar PNG] [--banner PNG] [--card SVG|PNG] [--social PNG]
              [--org-banner JPG]
doctor [--format tsv|json|md] [--header]
doctor --estate --meta-dir DIR [--registry FILE] [--template-dir DIR --checkouts DIR] [--out NEW_PROPOSALS.yaml]
new OWNER/NAME --type TYPE [--description TEXT] [--template OWNER/REPO] [--records FILE] [--jobs FILE] [--approval-id ID]
adopt OWNER/REPO [--records FILE] [--jobs FILE] [--approval-id ID]
enterprise snapshot-query --slug SLUG
enterprise discover
enterprise snapshot --slug SLUG [--out registry/enterprise.snapshot.json]
enterprise doctor|seat-check|plan --snapshot FILE [--baseline FILE] [--user LOGIN] [--records FILE] [--jobs FILE]
    doctor: [--registry FILE] [--approved FILE] [--approved-yaml FILE] [--actions FILE]
enterprise diff --baseline OLD --snapshot NEW

org profile|about|pins|labels|health|doctor ORG [--registry FILE] [--meta-dir DIR] [--decisions FILE]
    [--approved FILE] [--approved-yaml FILE] [--actions FILE] [--allow-t3] [--jobs FILE]
    profile: [--out-dir DIR] [--render] [--banner PATH] [--lists FILE] [--email-approved] [--allow-unmeasured]
    pins: [--lists FILE] [--repo-ids FILE]      health/doctor: [--dot-github DIR]
    doctor: [--snapshot FILE] [--avatar PATH] [--doctor-format tsv|json|md] [--header]
org profile --user CompleteDotTech [--registry FILE] [--meta-dir DIR] [--out-dir DIR] [--render] [--allow-t3]
project capture-query --owner OWNER --number N
project normalize --capture FILE [--rest-fields FILE] [--out FILE]
project lint --capture FILE --owner OWNER [--role org|template|estate] [--display-name TEXT]
project copy-plan --target ORG|@me [--role org|template|estate] [--source OWNER/N] [--copied FILE]
    [--workstreams FILE] [--repos OWNER/REPO,...] [--approval-id ID] [--files-dir DIR] [--no-status-update] [--jobs FILE]
    (stage 2 with --jobs needs --files-dir: the REST view bodies the jobs' --input names)
project readme --capture FILE --owner OWNER [--out FILE]
project estate-plan [--copied FILE] [--user-id ID] [--source OWNER/N] [--jobs FILE]
content social [--out PATH] [--title TEXT] [--icon PATH] [--job] [--allow-unmeasured] [--allow-hold]
content icon prompt|normalize|check [--option A|B] [--glyph FILE] [--art-direction FILE] [--in PNG]
    [--ground auto|transparent|keep] [--out PATH] [--preview PATH]
content links [FILE...] [--readme-path PATH] [--base-ref REF] [--online] [--cache FILE] [--strict] [--diff]
content linguist [--min-share 0.02] [--language NAME]
content actions [--runs FILE] [--workflows FILE] [--pages FILE] [--changed PATH...] [--approval WORKFLOW=ID]
content images [FILE...] [--base-ref REF] [--approval-id ID] [--out-dir DIR] [--online]
content sidebar --facts FILE [--packages FILE]... [--current FILE] [--repo OWNER/REPO]
    every content action: [--report FILE] [--jobs FILE] [--registry FILE] [--approved FILE] [--approved-yaml FILE] [--actions FILE]
```

| Command | What it does | Writes |
|---|---|---|
| `meta` | Normalizes repository metadata from read-only `gh api` GETs and adds the detected type, variant and family. Stdlib only. A `--meta` file keeps every key a later check reads ([references/meta.schema.json](references/meta.schema.json)): `has_pages`, `size`, `template_repository` (the full_name GitHub records for a repository generated from a template) and `template_taglines` (that template's README tagline when the repository was generated and today, read by `--from-gh`), the About sidebar counts (`releases`, `deployments`, `packages`, `environments`), and the R10 evidence `uses_custom_og_image` (the captured GraphQL `usesCustomOpenGraphImage` is mapped to it; only a boolean counts, and two spellings that disagree leave R10 `unknown`). `--from-gh` makes no GraphQL call, so add the flag from the social preview job's read-only check. | `--out` |
| `fingerprint` | Hashes description, topics, visibility, license, language, icon, override file, skill version and brand config; reports `changed` against `docs/images/.showcase.json`. Stdlib only. | `$GITHUB_OUTPUT` with `--github-output` |
| `config` | Validates `references/brand.yaml` against its schema and checks the stdlib lock copy; `--write-lock` regenerates `references/brand.lock.json` after an edit. | `references/brand.lock.json` with `--write-lock` |
| `fonts` | `--check` verifies `assets/fonts/FONTS.json` sha256; `--fetch` downloads the pinned OFL fonts (ClawHub installs). | `assets/fonts/` with `--fetch` |
| `describe` | Runs D1–D8, V1, P1, B1 and X1 and answers `keep`, `edit` or `needs-writer`. | `--records` |
| `topics` | Runs the closed-vocabulary merge algorithm (brand, family, org membership, type, domain, tech; 10 public, 8 private). `--also-in ORG[,ORG]` (or `--registry`, which reads the repository's `also_in` from the private registry, read only, or an `also_in` list in the metadata) adds one org membership topic per cross-listing org from `org_topics` (never the home org's own). | `--records` |
| `labels` | Emits `labels.yml`, or plans renames before creates (never `--force`, never a delete) from the metadata's labels or, without them, a read-only GET of the live labels. `--plan` prints the `gh` argv and the `scripts/writer.py` jobs (the writer re-reads the live labels before applying); standalone users run the printed argv themselves after approving it. A rename is planned only after §6.4 rule 0: in the `--repo-dir` checkout, or, without one, when the metadata's complete file tree (`files_complete: true`) lists no file rule 0 reads; a repository without issue forms of its own is also checked against the owner's `.github` default forms (`--org-defaults` takes a checkout or its metadata JSON). Otherwise it is held (`needs-input:label-references`, `needs_checkout`; [references/labels.md](references/labels.md)). `--references` is a no-op kept for compatibility. The `org labels` gates apply: a family on hold is refused (exit 2) unless `--allow-hold`; a T3 owner is refused (exit 2, `t3-signoff`) until co-owner sign-off; AI-Ascension gets only the `dependencies` create or patch; `has_issues: false` repositories (except `.github`), forks, archived repositories, T2-R and romgenie answer `n/a`. With `--plan`, `--jobs`, `--records` or `--gh`, metadata without labels is never planned against: the live labels are read first (exit 4, `needs-input:gh`, when they cannot be). Job ids come from the operation, never its position. | `--records`, `--jobs` |
| `banner` | Renders the golden-layout hero PNG: navy grid canvas, icon card, eyebrow, slug, one-line subtitle, 2–4 chips, accent bar. Fewer than two chips exits 4 unless `--allow-few-chips` (result `incomplete`). | `--out`, sidecar under `docs/images/` |
| `card` | Renders the 400×160 repo card SVG (no `<text>`, lint must pass first) and an optional PNG preview; same eyebrow and chip order as the banner. | `--out`, `--png` |
| `org-banner` | Renders the 1600×400 org profile banner JPG (STANDARD §9.5). | `--out` |
| `org-tile` | Renders the 400×160 org tile for profile directories. | `--out`, `--png` |
| `intro` | Renders the profile intro (animated only for the personal profile and T1 flagship orgs; `.still` reduced-motion frame). | `--out` |
| `footer` | Prints the decision 18 footer between `showcase:footer` markers, or checks that the README ends with it; `--check --online` also HEADs both raw logo URLs and fails (`fail:offline`) unless both return 200 (the Phase 4.0 hard gate). `--org OWNER` answers `exempt`, `exempt:footer` or `hold` for an org outside the footer's scope; for the watching org, `--check` still reads the README (its `.github` gets the footer, and `--org` cannot tell it from a fork). | stdout |
| `readme` | Scaffolds, upgrades or refreshes the header marker blocks; never drops a line (multiset check). `--bootstrap` fills a template body only while its marker's sha256 still matches (a person's edit makes the block theirs). | `README.md` with `--write`; `CONTRIBUTING.md` with `--bootstrap` |
| `lint` | SVG rules, README rules (R7 plus decisions 13 and 18) and banner PNG checks; `public-leak` checks any public file the run writes against the estate's private set (private slugs and names under every login of the owner, members-only pins, internal notes from the org rows, the registry's top-level notes and judge_changes and the profile's internal keys; OPS-03), reading the private registry and `--meta-dir` only; `prose` runs the CQ-17 checks on text the run writes (§1.2 brand strings, no emoji, no placeholders, the §4.1 formula for descriptions and taglines, typos when the optional `codespell` is installed; `--preserved` text only warns). | nothing |
| `contact-sheet` | Lays outputs out the way GitHub shows them, on `#0d1117` and `#ffffff` (proofing surfaces, not asset variants). `--org ORG --cross-surface` is the G4 gate: the org avatar at 32 px, a hero banner, a repo card, the social preview and the org banner on one labelled sheet; a missing surface is logged `needs-input:cross-surface:<surface>` (result `incomplete`). | `PATH.on-github-dark.png`, `PATH.on-github-light.png` |
| `doctor` | Prints the definition-of-done row: `R1`–`R11`, `banner`, `icon`, `card`, `footer`, `done`. No network. `--estate` classifies every repository in `--meta-dir` that `registry/estate.yaml` does not list with `decisions/POLICY.md` (`keep`, `move`, `archive`, `delete`, `merge`, `rename`, `rename-default-branch`; never acted on) and diffs the template-managed files of template-born checkouts against the current template (bump PRs are proposals). | `--out` (merges its own entries into `NEW_PROPOSALS.yaml`; others stay) |
| `new` | Plans a repository from the template: the `gh repo create OWNER/NAME --template CompleteTech-LLC/completetech-repo-template --private` writer job, then `adopt` on it (naming N1–N4 and the §5.4 type are checked first; the watching org, placeholder orgs and refused owners exit 2). | `--records`, `--jobs` |
| `adopt` | What "Use this template" does not carry, as Phase 3 change records and writer jobs: the §10.1 settings (wiki, Projects and Discussions only after their reads), the §5.6 topics, the §6 label passes, private vulnerability reporting and Dependabot alerts on public non-forks, plus a UI checklist (social preview upload job, About sidebar). An archived capture plans no jobs or change records, only a `pending` entry: re-capture the metadata inside the approved unarchive window, then adopt again. Metadata from `--meta`, else read-only `gh api` GETs. A family on hold (`hold: true`) is refused (exit 2). | `--records`, `--jobs` |
| `enterprise` | Decision 24: `snapshot-query` prints the validated read queries; `discover` and `snapshot` run read-only GraphQL queries; `doctor` (E1–E14), `seat-check`, `diff` and `plan` (change records and writer jobs) work offline on snapshots against `references/enterprise.yaml`. | `--out`, `--records`, `--jobs` |
| `org` | Decisions 5, 8, 9, 14, 15, 18, 20 and 23: the org profile README from the registry's public slice (leak-checked), the personal CompleteDotTech README with `profile --user` (kit order, leak-checked against the whole estate), About payload, pin and star List plan, label jobs for every repository homed in the org, `.github` health cells, and the O-check row. | `--out-dir` (profile only, after the leak check; an existing hand-made profile also needs a `profile-retemplate` approval), `--jobs` |
| `project` | Decision 23, STANDARD §13: capture query, template spec, board lint (O10), two-stage copy plan (structure only, nothing deleted, mutations inline), board README, and the private Estate board. | `--out`, `--files-dir`, `--jobs` |
| `content` | Audit gaps CQ-04, RP-09 (links), RP-07, CQ-08 (language bar), RP-06, RP-01, CQ-13 (Actions), RP-03, RP-10 (images), RP-05 (sidebar), RT-04 (repo icon) and R10 (`content social`: the 1280×640 repository social preview, STANDARD §9.5, in the same family design, plus with `--job` its browser upload job). | `--report`, `--jobs`, `--out`, `--out-dir`, `--preview`, `--cache` |

`--type` replaces type detection with a §5.4 type (logged `type-override:<type>`); use it only when neither a checkout nor a captured file tree is available, for example with registry metadata. Without a tree, the type is provisional (`needs-input:file-tree`); a README link to a root `SKILL.md` still counts as rule 5.

`lint readme` and `lint all` refuse excluded, hold and T3 owners like every other repository command. `lint all` fails an applicable banner or card that is missing; an exempt one is linted only if it exists. Forks outside the watching org, backups, archived and `.github` repositories need the banner (they have no card); a preserve-list README is exempt from the banner only when review q57 `pres` is "Leave them unchanged".

Banner refusals: a watching-org fork returns `exempt` and writes nothing; the watching org's `.github` gets the banner and icon like any `.github`; another watching-org repository that is not a fork is refused (exit 2, `hold:watching-non-fork`) until decided, then `--allow-hold`; `CompleteDotTech/CompleteDotTech` (it opens with the intro) and a placeholder org's `.github` return `exempt:*`. Every other repository gets the hero banner (decisions 12, 13 and 18): forks outside the watching org (G), backups and archived repositories (H) and `.github` repositories (J) included, while `card` returns `exempt:no-card` for forks, backups and `.github`. AI-Ascension (`banner: keep-existing`) gets the hero in its own palette above its existing banner (q57 `aia` and `pres` defaults) and returns `exempt:keep-existing` only when `readme.preserve_banner` is `unchanged`; TouchedByAnAgent (`hold: true`) needs `--allow-hold`; families marked `measured: false` need `--allow-unmeasured` (otherwise exit 4, `needs-input:palette-v1.1`).

## Decisions That Override the Standard

These user decisions outrank `STANDARD.md` (`ct-std-v1`). Full text: [references/decisions.md](references/decisions.md).

| Decision | Effect on this skill |
|---|---|
| 12 | Every in-scope repository gets its own icon at `assets/icon.png`; until then the banner uses the org's Neon Night mark (every T1 org but CompleteTech-LLC), then the CompleteTech logo (CompleteTech-LLC) or, in every other family, the family's typeset wordmark on its dark plate, and logs `needs-input:repo-icon`. |
| 13 | Every README opens with the hero banner in the php2shell-check layout, then the nav line (q57 `nav` default), then the title, badge row and bold description; forks outside the watching org, backups, archived and `.github` repositories included. |
| 18 | Every README ends with the exact CompleteTech LLC footer. It is the only `<picture>` the skill emits. |
| 19 | The dark logo master is configurable (`brand_assets.dark_master` is `current` or `candidate`); generators never crop a mark at runtime. |
| 21 | One dark design per surface (banner, card, tile, intro) on both GitHub themes. No light variants, no `-dark`/`-light` sibling files. |
| 22 | This skill and `completetech-repo-template` make the standard repeatable; the template's Action calls `action.yml`. |
| 23 | Orgs and GitHub Projects are covered: project boards are copied from the captured golden template, never deleted. |
| 24 | The CompleteTech Enterprise is covered read-only: snapshot, E-checks, the romgenie seat check and printed change records; policies stay proposals. |

## Brand and Family Data

- `references/brand.yaml` is the single place for colours, fonts, logo paths, eyebrows, company labels, footer strings and per-org rows. A hex colour literal in `scripts/` fails the quality gate.
- Precedence: schema defaults, then `families.<family>`, then `orgs.<Org>`, then the repository's `.github/showcase.yml`, then CLI flags. Repository files and flags change **content** only (icon, subtitle, chips, category, variant); colours and fonts are never overridable.
- Icon on the banner card and the card tile, first match wins: `--icon`, `.github/showcase.yml` `icon`, then `assets/icon.png`, then the org mark (`assets/orgs/<Org>/mark.png`), then a family fallback: the light CompleteTech logo for CompleteTech orgs (its cloud-and-bulb crop, `mark_light`, in icon boxes under 200 px), and for every other family (AI-Ascension, Jev-Engineering, jevplay-games, LibreEvolve, TouchedByAnAgent, romgenie, T3) its display name typeset in the family font on the family plate. A T2 surface never carries the CompleteTech logo.
- An icon that brings its own opaque ground (four corners alike) fills the card with that ground and is drawn full-bleed, so there is never a plate inside a plate; dark plates get a 2 px accent edge. jevplay-games icons are scaled nearest-neighbour at an integer factor.
- `.github/showcase.yml` may carry `type:` (a §5.4 type for a repository whose code has not landed) and `for: OWNER/REPO` (any login of the org, the name in any case, or the slug an approved rename or transfer gives it; the overrides apply only to that repository, so a template's own chips and subtitle never reach the repositories created from it).
- Navy surfaces (intro, org tile) use the selected dark master or `mark-dark.png` when committed. Marks are never cropped, masked or recoloured.
- `readme:` holds the review-page answers that shape README scaffolding, at their defaults: `nav_first: false` (q57 `nav`: hero banner, then nav line), `preserve_banner: above` (q57 `pres`: the hero goes above a preserve-list README's own banner; `unchanged` leaves those READMEs without one) and `fork_readme: note` (q27: forks outside the watching org keep the upstream README under the hero banner and the §7.4 G note; `full` gives them their §5.4 variant). Change a value only after the user's answer, then `config --write-lock`.

## Resource Guide

| Resource | Role |
|---|---|
| [references/estate-standard.md](references/estate-standard.md) | Tiers, brand strings, golden rules, org identity table, repo naming. |
| [references/descriptions.md](references/descriptions.md) | Description checks D1–D8, V1, P1, B1, X1, keep-or-edit order, templates by type. |
| [references/topics.md](references/topics.md) | Topic layers, type detection rules 1–25, vocabulary, aliases, merge algorithm, safety. |
| [references/labels.md](references/labels.md) | The 23-label set, migration map, apply algorithm and `labels.yml`. |
| [references/readme-variants.md](references/readme-variants.md) | Header block with banner and footer, variants A–J, H2 order, license rows, preserve list. |
| [references/banner-layout.md](references/banner-layout.md) | Banner and card geometry measured from the golden, chip rules, eyebrow rules. |
| [references/art-direction.md](references/art-direction.md) | Family palettes, motifs, asset sizes, prompt template for illustrations, art QA. |
| [references/svg-rules.md](references/svg-rules.md) | GitHub-safe SVG rules with decision 21 applied, and what `lint svg` checks. |
| [references/profile-readmes.md](references/profile-readmes.md) | Org and personal profile README structure, cards, intros and what to skip. |
| [references/orgs-and-projects.md](references/orgs-and-projects.md) | Org About fields, O-checks, org `.github` contents, profile rules and the GitHub Projects rules. |
| [references/org.md](references/org.md) | The `org` command group: inputs (with or without the estate bundle), the public slice and leak check, the org resolver (CQ-03), writer jobs and refusals. |
| [references/projects.md](references/projects.md) | The `project` command group: capture, normalize, lint, the two-stage copy plan, README and the Estate board. |
| [references/content.md](references/content.md) | The `content` command group: links, language bar, Actions, images, sidebar, repo icon and the social preview. |
| [references/enterprise.md](references/enterprise.md) | The enterprise module: commands, writer jobs, `enterprise.yaml` desired state, E-checks and guardrails (decision 24). |
| [references/constraints.md](references/constraints.md) | Platform limits, write discipline, approval-gated actions, change records. |
| [references/definition-of-done.md](references/definition-of-done.md) | Checks R1–R12 and O1–O11 mapped to `doctor` and `lint` cells. |
| [references/decisions.md](references/decisions.md) | The user decisions this skill implements, verbatim. |
| `references/brand.yaml`, `references/brand.schema.json`, `references/repo-config.schema.json`, `references/meta.schema.json` | Brand data and the schemas for it, for `.github/showcase.yml` and for metadata. |
| `references/standard/` | Machine-readable standard: topics, types, labels, descriptions, README variants, naming. |
| `examples/` | Synthetic Northwind Trading Co. metadata, small fixture checkouts, an example `.github/showcase.yml`, a synthetic estate (`examples/estate/`: registry and metadata for the `org` commands), and `render_examples.sh`, which regenerates every committed preview. |
| `action.yml` | Composite GitHub Action that regenerates the banner and card when inputs change. |

## Runtime Permissions

| Area | Runtime behavior |
|---|---|
| Execution | Runs the local Python entry point `scripts/showcase.py` (and `scripts/action_commit.sh`, `scripts/action_prepare.py` inside the Action only). |
| Reads | The target repository directory (`--repo-dir`), a metadata JSON (`--meta`) or directory (`--meta-dir`), `references/` and `assets/`; for the `org`, `project` and `content` groups also the estate registry and the approval files (`--registry`, `--approved`, `--approved-yaml`, `--actions`, `--decisions`, or the bundle beside the skill), read only and never copied. |
| Writes | Only paths given by `--out`, `--png`, `--records`, `--jobs`, `--report`, `--out-dir`, `--files-dir`, `--preview` or `--cache`; with `--write`, the README marker blocks and `docs/images/*`; with `--bootstrap`, `CONTRIBUTING.md` owner tokens; `content icon normalize` defaults to `assets/icon.png` in the target checkout. |
| Network | None by default. `meta --from-gh`, and `labels --plan` and `adopt` without metadata, run read-only `gh api` GETs; `enterprise discover` and `enterprise snapshot` run read-only `gh api graphql` queries; `content links --online` and `content images --online` make cached, rate-limited HEAD/GET requests to the hosts the files link to and read-only `gh api` GETs; `fonts --fetch` downloads the pinned fonts over HTTPS; `footer --check --online` sends one HEAD to each of the two decision 18 logo URLs on raw.githubusercontent.com. `org`, `project`, `enterprise snapshot-query`, `plan` and every other command only print the commands they plan. |

| Not Included | Boundary |
|---|---|
| GitHub writes | None: no `gh` write verbs, no `git push`, no settings, labels, topics or description changes. Proposals go to the orchestrator's single writer queue as change records and writer jobs, or, used standalone, to the user, who runs the printed argv after approving it. |
| Credentials | Does not read tokens, browser sessions or secrets; `gh` uses its own authentication. |
| System changes | No persistence, schedules, privilege escalation or deletes. |

## Network Boundary

Generation, checking and planning are local. The only network calls are the read-only `gh api` GETs of `meta --from-gh`, `labels --plan` and `adopt`, the read-only GraphQL queries of `enterprise discover` and `enterprise snapshot` (api.github.com), the opt-in link and image checks of `content links --online` and `content images --online` (the hosts the checked files link to, cached and rate-limited), the font download of `fonts --fetch`, and the two read-only HEAD requests of `footer --check --online` (raw.githubusercontent.com), each run only when asked. The skill posts no metadata or run data anywhere else. The composite Action is the only component that pushes, and only into the repository it runs in.
