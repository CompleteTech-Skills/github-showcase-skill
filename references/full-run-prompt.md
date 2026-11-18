# Full-capacity run prompt

A copy-ready operator prompt for one repository, organization, personal account or enterprise, for any GitHub user.
The skill renders deterministic surfaces and proposes GitHub changes. Optional image generation supplies only
illustration layers through the [image-generation recipe](art-direction.md#codex-image-generation-recipe).
Missing inputs, exemptions and owner-controlled work remain visible; nothing in this prompt writes to GitHub.

## How to use it

1. Copy the prompt below. Replace `<SKILL_DIR>`, `<PY>` and `<SCRATCH_DIR>` with absolute paths; `<PY>` is the
   venv Python (`.venv/bin/python` or `.venv\Scripts\python.exe`). Scratch must be outside every repository.
2. Set your identity. The shipped `references/brand.yaml` describes the CompleteTech estate. For your own
   accounts, add your family and organization rows to a config you own with `brand add-family` and
   `brand add-org` ([brand onboarding](brand-onboarding.md)) and set `<BRAND_CONFIG>` to it. Set
   `<ESTATE_ROOT>` only if you keep a private registry (layout: `examples/estate/`), and never commit it. Leave
   either empty and the agent proposes the onboarding dry run at STOP 1 instead of guessing.
3. Adjust the options and replace the single final TARGET line. Existing scoped authorization is reusable;
   STOP 1 asks only for an unresolved gate, and STOP 2 is the existing per-family pilot gate.
4. Send it to the agent. `SKILL.md` and the referenced command contracts remain authoritative if they change.

````markdown
# GitHub Showcase: full-capacity run

Run `github-showcase-skill` at `<SKILL_DIR>` on the final TARGET. Produce every applicable, authorized
surface, run its audits and leave reviewable plans and uncommitted local outputs. Continue independent work when
a surface is pending; never turn a refusal, missing input or exemption into apparent completion.

The operator's identity comes only from BRAND_CONFIG, ESTATE_ROOT and the TARGET. Never assume the skill's
shipped CompleteTech estate, its logins, legal wording, affiliation or approvals for an owner they do not name.

Read the target's maintainer instructions and the skill's `SKILL.md`, `references/decisions.md`,
`art-direction.md`, `content.md`, `staged-descriptions.md` and `profile-readmes.md`; for scope extensions also
read `org.md`, `projects.md` and `enterprise.md` under `references/`. Follow their gates and report conflicts.

## Hard rules and command notation
1. Run generation, checks and plans through `scripts/showcase.py`. Never hand-edit generated art, marker
   blocks or profile READMEs: change an authorized input and regenerate. Preserve authored content and ownership.
2. No GitHub writes, commits, pushes or settings changes. Leave jobs, records, exact argv and diffs for the
   approved writer (or standalone user). Read-only network access still requires the eligibility checks below.
3. Skip excluded owners. Never invent approval or add `--allow-hold`, `--allow-unmeasured` or `--allow-t3`
   yourself; never use `--allow-few-chips`. Flags lift only the specific documented gate, on supported commands.
4. The image model draws only illustration layers, never text, logos, marks, people or third-party IP.
   Use committed marks unchanged. One dark design per surface; only the configured footer uses `<picture>`
   (decision 18; an owner whose brand row sets `footer: no` is exempt).
5. Read the entire generated prompt before sending it. Only public facts may leave the machine. Private
   repositories use only family glyph fields and a neutral name, or stay pending. Keep raw captures, private
   names, jobs and candidates in scratch; never copy an estate bundle or registry into a repository.
6. Keep a scratch ledger with target, step, argv, exit, structured result/logs, output paths and sha256.
   Resume from verified outputs; do not regenerate paid art merely because the run was interrupted.

Use Python argv lists on both POSIX and Windows, never a space-joined executable string or `eval`:
```python
from pathlib import Path
import os
import subprocess
PY = str(Path(r"<PY>").resolve())
SKILL_DIR = Path(r"<SKILL_DIR>").resolve()
WS = Path(r"<SCRATCH_DIR>").resolve()
BRAND_CONFIG = r"<BRAND_CONFIG>"  # empty: the shipped references/brand.yaml
ESTATE_ROOT = r"<ESTATE_ROOT>"    # empty: no private registry (registry-free paths)
CONFIG = ["--config", str(Path(BRAND_CONFIG).resolve())] if BRAND_CONFIG else []
ENV = dict(os.environ)
if ESTATE_ROOT:
    ENV["SHOWCASE_ESTATE_ROOT"] = str(Path(ESTATE_ROOT).resolve())
BASE = [PY, str(SKILL_DIR / "scripts/showcase.py"), *CONFIG, "--format", "json"]
G = []  # global flags for THIS authorized invocation only; re-check scope/expiry each time
S = [*BASE, *G]  # scope commands: no repository capture/checkout
# Set these for EACH repository after its capture and checkout succeed:
M = WS / "meta" / OWNER / (REPO + ".json")
CHECKOUT = WS / "checkouts" / OWNER / REPO
R = [*S, "--meta", str(M), "--repo-dir", str(CHECKOUT)]
# Example: D is [] for unchanged descriptions; otherwise ["--description", proposed_text].
result = subprocess.run([*R, "banner", *D], cwd=CHECKOUT, env=ENV,
                        capture_output=True, text=True, encoding="utf-8", shell=False)
```
Below, `R command ...` means append those argument tokens to R; `S command ...` uses the scope prefix without
repository metadata. Substitute each path/text placeholder as ONE string argument; `[D]` means append D, not
literal brackets. Use absolute paths for ALL file arguments, including README, glyph YAML, prompt, candidate,
keyer inputs, reports and captures. Pass `env=ENV` to every invocation. Global T3 flags go before the command; supported hold/unmeasured flags go
after it. Rebuild the appropriate prefix for every invocation; do not let one repository's flags leak to another.

## 0. Local preflight and target eligibility (before any target network read)
- Prepare WS with `meta/`, `checkouts/`, `tools/`, `art/{prompts,runs,candidates,golden}/`, `proof/`, and
  scratch jobs/records/ledger paths. Use a venv with the pinned requirements; run `S fonts --check` and `S config`.
  Fetch missing fonts only when network use is authorized; otherwise record `needs-input:fonts`.
- Read an estate bundle in place only when one exists (ESTATE_ROOT, or the bundle beside the skill), including
  registry, decisions and approvals; without one, use the registry-free paths below. Resolve current/former
  owner logins with the skill's shared resolver and the selected brand config. Classify `OWNER/REPO`, an org
  login, `user:LOGIN` or `enterprise:SLUG` locally. Resolve a bare login from the config or registry, or after
  STOP 1 with `gh api users/LOGIN --jq .type`. An owner with no brand row is not refused: see Brand identity.
- Check exclusions, HOLD, family holds, unmeasured palettes, exposure/private-data decisions and T3 scope
  BEFORE `gh` enumeration, metadata reads, cloning or image capture. STOP 1: show the scope and unresolved
  gates first. Reuse existing explicit authorization only within its scope; otherwise hold the affected work.
- T3 needs the explicit flag for each permitted invocation AND a current, unrevoked record covering that
  owner/repository in the private sign-off file (`references/t3-signoff.md`). The default file or global
  `--t3-signoff-file PATH` is read, never fabricated. Repository-only consent does not authorize org-wide
  discovery, `.github`, unrelated repositories or image work. Preserve the separate writer approval gates.
- Before org enumeration, obtain local `S org doctor ORG --doctor-format json` diagnostics with the scoped
  flags; this reads supplied/local inputs and prints proposed reads, without executing them.
- Local diagnostics the contracts expressly allow (such as repository `doctor`'s T3 hold row, or HOLD org
  about/pins/health/doctor) remain available; their exception never grants permission for otherwise denied reads.
- Brand identity. An owner with no row in the selected config renders only in neutral style
  (`needs-input:org-row`). At STOP 1, ask the operator for the identity inputs: family name and label, dark
  canvas, ink and accent hex, tier, display name, `footer yes|no|hold`, and an authorized mark PNG if any. Then
  show the `S brand add-family ...` or `S brand add-org ...` dry run against BRAND_CONFIG
  (`references/brand-onboarding.md`). Never invent colours, legal wording or affiliation, and never write to
  the shipped `references/brand.yaml` of a shared install. Repeat with `--write` only after approval. A new
  family is `measured: false`: `--allow-unmeasured` needs the operator's explicit approval, and its outputs
  are review renders. Topic proposals wait for the org's `brand_topic` (`needs-input:brand-topic`).
- Check `gh auth status` when authorized reads are needed. With IMAGE_TOOL=codex, check `codex --version`
  and `codex exec --help`; with none, skip image tooling. Missing tools remain pending. OCR is optional and
  its absence is `needs-input:ocr-unavailable`. `enterprise:?` discovery waits until this preflight completes.
- Run-once check (decision 25), after the eligibility gates above and only for permitted targets:
  `S provenance check TARGET --format json` (`user:LOGIN` for a personal account;
  `--repo-dir CHECKOUT` or `--offline --meta M` when reads are not authorized; `--snapshot FILE` for the
  Enterprise). `fresh`: skip the target unless FORCE is yes. `stale`: rerun only the surfaces that `changed[]`
  names. `never`: run in full. `untracked`: run, and the final stamp backfills it. `foreign`: stop; never
  suggest running it. Record the status in the scratch ledger.

## 1. Scope and captures
- Repo: the named repository plus its owner's `.github` defaults when permitted. Org: use the registry or,
  only after owner-wide eligibility, paginated read-only `gh api --paginate orgs/ORG/repos?per_page=100`.
  Retain the complete list, including private/archived repositories, privately. Apply each repository's gates.
- Personal (`user:LOGIN`): after eligibility, map the account with
  `S account-chart capture LOGIN --out WS/account.snapshot.json`. This is read-only GraphQL; it applies the same
  gates, names only public repositories, and reports enterprise and role data only when LOGIN is the signed-in
  viewer. Keep the snapshot private. Scope is `LOGIN/LOGIN`, plus the public repositories the operator selects
  from the snapshot, plus, with a registry, its profile references (pins, more projects). Establish visibility from captures,
  applying each owner's gates before capture. Capture required source metadata even when no source checkout
  is needed; clone every repository selected for local changes. Do not render a sparse personal profile when
  required captures or the registry are missing: list the missing scope and keep that render pending.
- For each permitted slug, run `S meta --from-gh OWNER/REPO --out M` BEFORE cloning. This command checks
  excluded/HOLD/T3 eligibility before its loader; inspect its result/logs and saved capture before continuing.
  With a supplied current capture, validate its identity and completeness instead. Never edit the original M.
- Only then `gh repo clone OWNER/REPO CHECKOUT -- --depth 1` for local work; verify origin matches M. Apply
  this same order to `.github`. Watching-org forks are metadata-only; do not clone/render them. Missing
  defaults, archived upload/adopt windows and repository-specific holds remain pending, not bypassed.
- Set R for this repository. Resolve low-confidence type suggestions from its captured tree/checkout, then
  set a scoped `type:` in `.github/showcase.yml` if justified. Revisit STOP 1 before newly discovered gated work.

## 2. Facts before art (R always carries M and CHECKOUT)
1. `R describe --records RECORDS`. For `edit`, review `proposed`; for `needs-writer`, compose from the facts
   and `references/descriptions.md`. Validate the chosen sentence with `R describe --text TEXT` until its
   `action` is `keep`, then `R lint prose --prose-kind description --text TEXT`.
2. If TEXT differs from M's live description, save a reviewable scratch proposal with slug, captured before,
   proposed after, reason, validation result and argv `['gh', 'repo', 'edit', 'OWNER/REPO', '--description', TEXT]`.
   Do not execute it. Keep emitted change records too; `describe --text` returning `keep` alone is no proposal.
3. `R topics --gh --records RECORDS` (add `--registry REGISTRY` when available).
   `R labels --plan --org-defaults DOTGITHUB --jobs JOBS --records RECORDS` with verified defaults; when
   unavailable, omit that argument and retain held renames. Follow the .github-first label workflow in org.md;
   this run does not rewrite/apply issue forms or label changes. Required writer work stays pending.
4. Set D to `[]` for an unchanged description, else `['--description', TEXT]`. Append D ONLY to `R banner`,
   `R card`, `R content social` and `R readme` (including dry runs). No other command accepts this staging flag.
   Never modify M to make checks pass. Staged outputs remain proposals; R2 drift and R10 upload stay pending
   until the approved writer acts, fresh metadata is captured, and affected surfaces are regenerated without D.
   Topic proposals likewise wait for fresh capture before final art reconciliation.

## 3. Optional image layers
### Repository icon (before banner, card and social)
1. Reuse `assets/icon.png` only if `R content icon check --strict --min-contrast 4.5` passes applicable QA.
   With IMAGE_TOOL=none or unavailable, keep any valid existing art; missing icons stay `needs-input:repo-icon`.
2. Define absolute `P = WS/art/prompts/OWNER/REPO`, `C = WS/art/candidates/OWNER/REPO`; create them.
   Write `P/glyph.yaml`: option A needs glyph_name, glyph_description, spark_placement, size_class
   (WIDE|TALL|SQUARE|DIAGONAL); option B needs subject and 3–5 objects from the approved library/family motif.
3. `R content icon prompt --option ICON_OPTION --glyph P/glyph.yaml --out P/icon.md` must report `ok`.
   Read the full file for privacy; put only its fenced text prompt in `P/prompt.txt`. Its operator notes
   (including "Then: run normalize") are not instructions for the image agent.
4. Run four candidate slots serially, one image per invocation, each in its own new empty absolute SLOT.
   Build argv `['codex', 'exec', '--json', '--skip-git-repo-check', '-C', str(SLOT), ... , '-']`, adding
   `['-m', IMAGE_MODEL]` only for a named model and repeatable `['-i', str(REFERENCE)]` for approved references.
   Read PROMPT_TEXT from the absolute P/prompt.txt, then capture the result explicitly:
   ```python
   result = subprocess.run(argv, input=PROMPT_TEXT, capture_output=True,
                           text=True, encoding="utf-8", shell=False)
   (SLOT / "run.jsonl").write_text(result.stdout, encoding="utf-8")
   (SLOT / "run.stderr.txt").write_text(result.stderr, encoding="utf-8")
   ```
   Record `result.returncode` in the scratch ledger and handle nonzero exits as failed attempts before
   selecting an image. Never use shell input redirection.
   - Select the first readable image path reported by THAT invocation, then copy to absolute C/slot-N.png.
     Never use a directory listing or the newest generated image. No readable path: retry the unchanged
     prompt at most 3 attempts for that slot, then stop it with `art-fail`.
   - References must be text-free approved family art. When the family's art direction requires an exact
     reference image (for example the jevplay-games mascot), attach that file; if it is unavailable, hold the
     slot. Never attach banners or cards.
   - One tool/model per family. Request a seed only through `content icon prompt --seed N`; report the
     returned model identity or `not exposed`. IMAGE_TOOL=api uses the same public prompt verbatim, one image
     per call, only when that capability is authorized. Optional art is never a prerequisite for other audits.
5. Inspect at 200%: reject text/glyph-like marks, people, third-party marks, margin violations, uneven ground
   or off-palette art. For survivors in generation order, run
   `R content icon normalize --in C/slot-N.png --ground auto --strict --min-contrast 4.5 --preview PROOF/icon-48.png`
   then `R content icon check --strict --min-contrast 4.5` (add `--ocr` when available).
   For corner dE 3–5 only, use `--ground-tolerance 5`; never lower QA. First pass wins, with a recorded reason.
   If four candidates fail QA, try four new slots once, then `art-fail`; the surfaces may use the org fallback.
6. Record provenance in CHECKOUT/assets/PROMPTS.md: verbatim public prompt, date, tool/model, requested seed,
   references, requested/selected images, selection/reject reasons, skill version, sha256 and size. Record the
   session id and image filename or `$CODEX_HOME`-relative path, never a real absolute user path. Raw art stays scratch.

### Org illustration and pilot (org targets)
- Fill art-direction's illustration template: verbatim family style lock, org subject, 3–5 approved motif
  objects, wide 1536×1024, flat family canvas, palette/highlights, exclusions and family additions. Save the
  prompt at absolute WS/art/prompts/ORG/org-banner.md and apply the same privacy/candidate/visual QA rules.
- Key the selected absolute candidate with argv `[PY, str(WS/'tools/key_illustration.py'), str(CANDIDATE),
  str(ILLUSTRATION), CANVAS_HEX]` using Appendix B. ILLUSTRATION is WS/art/ORG-illustration.png. This is an
  illustration, not an icon: do not use icon normalization. The org compositor centers it in the 464×320 slot
  (1040,40)–(1504,360). Record provenance alongside any approved destination asset, otherwise in scratch.
- STOP 2: before generating the rest of a family, finish its first applicable banner/card/social (and org
  surface), show both contact-sheet page colours, and wait for the existing pilot approval unless that
  family's golden references are already approved. Copy approved text-free art to WS/art/golden/FAMILY.

## 4. Repository surfaces (R, in order; respect personal-profile exceptions in section 6)
1. `R banner [D]` writes CHECKOUT/docs/images/banner.png. Missing chips/subtitle must come from facts;
   `art-fail` needs shorter source text, never truncation. Preserve valid banner exemptions.
2. `R card --png PROOF/OWNER__REPO-card.png [D]`. Forks, backups and `.github` may be `exempt:no-card`.
3. Changed description: `R content social [D]`, WITHOUT `--job`; report its actual private staging output
   (default CHECKOUT/assets/.showcase-staging/social-preview.png), sidecar and pending upload. Unchanged:
   `R content social --job --jobs JOBS`; record its applicability/result, output path and any withheld job.
4. `R readme --diff [D]`: save the JSON `diff` field as PROOF/OWNER__REPO-readme.diff, then
   `R readme --write [D]` only after its dry-run checks pass. `readme-shrink` stops this repository's writes.
5. `R footer --check CHECKOUT/README.md` when the owner's brand row has `footer: yes`; otherwise report the
   footer exempt (`S footer --org OWNER` states the reason). Add `--online` only when the read is authorized,
   else report that remote check unrun. Do not treat offline footer validation as live URL evidence.

## 5. Repository content audits (R; proposals only)
- `R content links --base-ref origin/DEFAULT_BRANCH --cache WS/links-cache.json --diff`; use the verified
  captured default branch and ensure that ref exists. Add `--online` only for authorized network checks.
- `R content linguist`; `R content images --out-dir PROOF/OWNER__REPO-images`.
- Save separate read-only captures for `gh api repos/O/R/actions/runs?per_page=50`,
  `gh api repos/O/R/actions/workflows` and `gh api repos/O/R/pages`. Then
  `R content actions --runs RUNS --workflows WORKFLOWS [--pages PAGES]`; omit pages on a recorded 404.
  Missing/failed captures are unknown, never fabricated empty objects; the result must retain their limits.
- Sidebar facts are NOT M. Save a separate JSON object with `releases`, `packages`, `deployments`: each is
  a captured count, complete list, or object with `total_count`/`totalCount`. Use paginated GETs of
  `repos/O/R/releases` and `repos/O/R/deployments`; packages need complete owner package listings for all
  applicable package types (`orgs/O/packages?package_type=TYPE`, or `users/O/packages?package_type=TYPE`),
  mapped by `repository.full_name`. Keep raw captures and coverage evidence. Never turn a failed/partial
  listing into zero. Combine captured pages before counting/list serialization. Leave an unknown key absent (e.g. `{}` when all are unknown), then run
  `R content sidebar --facts SIDEBAR_FACTS --jobs JOBS`; retain `needs-input:sidebar-facts:*` and withheld jobs.
  Use `--packages` only with proven complete package coverage, since absent repos then count as zero.
- `R adopt OWNER/REPO --jobs JOBS --records RECORDS` if no docs/images/.showcase.json existed before this
  run. Captured archived state stays pending until the approved unarchive window and a fresh capture.

## 6. Scope extensions (S, never R)
### Organization
- Without a registry, keep about/profile/pins pending (`needs-input:registry`). Supported partial work:
  `S org labels ORG --repos-from-gh --checkouts WS/checkouts --dot-github DOTGITHUB --jobs JOBS`,
  `S org health ORG --dot-github DOTGITHUB`, and `S org doctor` below. Registry-free labels must receive no
  registry, metadata or decision inputs; preserve its owner gates and held reference rewrites.
- With the registry: `S org about ORG --jobs JOBS`; `S org labels ORG --meta-dir WS/meta
  --checkouts WS/checkouts --dot-github DOTGITHUB --jobs JOBS`; `S org pins ORG --meta-dir WS/meta --jobs JOBS`;
  `S org health ORG --meta-dir WS/meta --dot-github DOTGITHUB`. Pass required explicit bundle paths if not
  auto-discovered. The top metadata directory includes cross-owner captures; complete profile inputs first.
- Preview with `S org profile ORG --meta-dir WS/meta` first. Inventory the target README and planned asset
  paths; an existing authored/unproven asset is preserved, with optional rendering directed to scratch instead.
  This preview does not bypass the real checkout's profile-retemplate gate: an authored profile still needs
  that approval before dependent writes. Only after destination ownership and inputs are established run
  `S org profile ORG --meta-dir WS/meta --out-dir DOTGITHUB --render`. Inspect result, logs, assets AND outputs.
  `needs-approval:profile-retemplate`, leaks, refusal or missing required inputs stop dependent writes.
  Preserve a kept banner (`banner:keep-existing:*`) and every authored/unproven asset. Only replace an org
  banner when this successful invocation lists its org-banner asset AND that exact output was written by
  this run with verified bytes; no keep-existing log or pending gate may apply. Then, if art is available:
  `S org-banner --org ORG --illustration ILLUSTRATION --out GENERATED_BANNER`. Otherwise render optional
  art only to a fresh scratch output and report the existing/missing hero unchanged. A generated intro hero
  is not an org-banner output. Never force `--banner` to evade keep-existing or re-template approval.
- For a T1 flagship's generated intro hero, run the applicable `S intro --org ORG --out INTRO` only after
  successful profile generation: create a missing listed asset, or refresh an existing asset only with verified
  generated ownership; use scratch for an authored/unproven asset.
  `S org-tile --org ORG --illustration ILLUSTRATION --out PROOF/ORG-tile.svg --png PROOF/ORG-tile.png`;
  on `art-fail:tile-name`, retry without illustration. Skip optional illustration flags when no art exists.
- `S lint public-leak FILE... --meta-dir WS/meta` for every public output. Without registry use only
  `--denylist PRIVATE_DENYLIST` and report its limited coverage; an empty/missing list cannot certify privacy.
- `S org doctor ORG --doctor-format json` prints snapshot `reads`. After the scope gates, run each read argv,
  save raw responses. For `profile_readme`, also GET `repos/ORG/.github/contents/profile/README.md` and decode
  its base64 content (the directory listing is not README text). Assemble `{org, graphql, repos, profile_readme}`.
  Then `S org doctor ORG --snapshot SNAPSHOT --dot-github DOTGITHUB --avatar AVATAR
  --doctor-format md --header`. Omit absent optional file flags; missing evidence stays unknown, never invented.
- Projects: eligible `gh project list --owner ORG --format json` finds N; then
  `S project capture-query --owner ORG --number N` emits FOUR reads: GraphQL, REST project, REST fields and
  `gh project field-list`. Run each returned `reads[].argv` from WS; save its `out` under WS (cross-check has
  null out: choose PROOF/ORG-project-fields.json). Keep raw GraphQL/node IDs separate from normalized data.
  Run the COMPLETE emitted normalize command, rebased to S with absolute paths:
  `S project normalize --capture RAW_GRAPHQL --rest-fields RAW_FIELDS --out SPEC`. Never execute its text
  through a shell. Then `S project lint --capture SPEC --owner ORG --role org`.
  Missing/failing board: `S project copy-plan --target ORG --jobs JOBS` plans stage 1 only; stage 2 waits for
  approved writer action and a fresh target-board capture. Never run a mutation from the returned jobs.
- With registry: `S doctor --estate --meta-dir WS/meta --out WS/NEW_PROPOSALS.yaml`.

### Personal account (`user:LOGIN`, built last)
- Account chart, for any LOGIN: `S account-chart render --snapshot WS/account.snapshot.json --out-dir PROOF/chart`,
  then `S lint svg --kind chart PROOF/chart/account-chart.svg`. Copy it into PROFILE_CHECKOUT/docs/images only
  when the operator wants it there and that path holds no authored file. Its `account-chart.md` block is a
  README proposal for the operator to place, not an automatic edit.
- Generated profile README. `S org profile --user LOGIN` supports only the personal account configured in the
  skill (today `CompleteDotTech`, with the registry's top-level `profile`). For that account:
  - Require the complete section 1 capture set and the registry profile first. Without them, render no
    profile and report the missing inputs.
  - Run sections 2, 3 (icon), 4 (card/social/footer only) and 5 on `LOGIN/LOGIN`. `banner` is exempt, and
    `readme` is skipped because `org profile --user` owns README.md.
  - Apply the same no-output preview and destination ownership checks before
    `S org profile --user LOGIN --meta-dir WS/meta --out-dir PROFILE_CHECKOUT --render`, then
    `S intro --profile LOGIN --out PROFILE_CHECKOUT/assets/intro.svg` under the generated-asset ownership rule.
- Any other LOGIN: report the generated profile README as unsupported, never hand-write it. Run sections 2, 3
  and 5 on `LOGIN/LOGIN`. Render its banner, card and social preview only to PROOF for review. Keep `readme`
  to `R readme --diff [D]` as a proposal, never `--write`, because a profile README is authored content.
  `S intro --profile LOGIN --out PROOF/intro.svg` works once LOGIN has a brand row.
- Run `S lint public-leak FILE...` on every public output (with `--meta-dir WS/meta` and the registry when
  present). Never infer completeness from an exit-0 sparse profile or missing visibility.

### Enterprise
- `S enterprise snapshot --slug SLUG --out SNAPSHOT` runs read-only GraphQL;
  `S enterprise snapshot-query --slug SLUG` prints the queries. Keep the snapshot private in WS/enterprise.
- The E-checks, seat check and plan compare the snapshot with the skill's `references/enterprise.yaml`, which
  describes the CompleteTech Enterprise. For any other enterprise, report their cells as informational against
  that file and queue no plan jobs until the operator supplies a reviewed desired-state file of their own in
  their skill copy. Pass `--user LOGIN` to seat-check only for a user the operator names.
- `S enterprise doctor --snapshot SNAPSHOT [--baseline OLD]`, `S enterprise seat-check --snapshot SNAPSHOT`,
  `S enterprise plan --snapshot SNAPSHOT --jobs JOBS --records RECORDS`; with baseline also
  `S enterprise diff --baseline OLD --snapshot SNAPSHOT`. No art, billing, policy or domain changes here.
- Report member orgs from the snapshot; with FAN_OUT=no, their org-doctor rows are unrun, not inferred.
  With FAN_OUT=yes, restart each member at eligibility/preflight before its own reads or local work.

## 7. Verify and report
- Each repository: `R lint all`, then `R doctor --header --format md` (retain JSON doctor evidence too).
  Use `R lint svg --kind card CARD` and `R lint banner BANNER` only for present applicable outputs; retain
  valid absent-card/banner exemptions. Missing required outputs remain failures; do not invent files to lint.
- Inspect structured result/logs and applicable cells, not exit 0 alone. Report local `skill_complete`,
  `owner_pending`, `done`, staging drift, incomplete/manual/unrun checks and exemptions separately.
- `S contact-sheet PRESENT_BANNERS... --mode stack --labels --out PROOF/banners`; skip an empty set.
  For orgs use `S contact-sheet --org ORG --cross-surface --avatar A --banner B --card C --social D
  --org-banner E --out PROOF/ORG-g4`, supplying only real applicable files. Missing surfaces remain logged
  incomplete; staged previews must be labelled staged. View both `.on-github-dark.png` and `.on-github-light.png`.
  Correct clipping, illegibility or palette errors by regenerating authorized inputs and rerun affected checks.
- Report scope/exclusions and authorization, doctor rows, files with sha256/KB and `git status --short`, art
  provenance/rejections, reviewable description/topic/label/README proposals, jobs grouped by kind/approval,
  and EVERY pending or unrun item with its reason. Description/topics precede dependent final regeneration
  and upload in the future writer sequence. State plainly that nothing was written to GitHub.
- Last, for each target the run touched: `SHOWCASE_STAR_PROMPT=1 S provenance stamp TARGET --repo-dir CHECKOUT`
  (or `--jobs $WS/jobs.jsonl` without a checkout; an enterprise stamp stays in the private `ESTATE_ROOT/registry/`, never in a repository).
  It writes nothing when the run changed nothing. If a star line appears, relay it to the person word for word
  and never run `gh repo star` yourself.

## Appendix A: interpret exit AND result/logs
| Exit | Meaning | Response |
|---|---|---|
| 0 | May include warn, incomplete, n/a, pending input or proposals | Inspect result, logs, outputs and cells before continuing dependencies. |
| 1 | Check failed or needs-writer | Fix inputs, validate the proposal, or retain the failure. |
| 2 | Usage/config error or refusal | Fix usage; preserve excluded/hold/T3 refusal and stop dependent work. |
| 3 | art-fail | Fix source text/chips or use the next candidate; never truncate. |
| 4 | Needs input/approval | Supply only authorized inputs or report the specific pending gate. |

## Appendix B: `$WS/tools/key_illustration.py` (Pillow only, a declared dependency)
```python
"""Key a flat-ground illustration to transparency for `org-banner` / `org-tile --illustration`
(art-direction.md: CIE76 dE <= 6 from the ground, 2 px feather, trimmed to the alpha box). Pillow only.
Usage: python key_illustration.py IN.png OUT.png [GROUND_HEX]   (default ground: the four corners, which must agree)"""
import sys
from PIL import Image, ImageFilter


def lab(p):
    def lin(c):
        c /= 255.0
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = (lin(float(v)) for v in p[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def de(a, b):
    return sum((p - q) ** 2 for p, q in zip(a, b)) ** 0.5


src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
w, h = im.size
if len(sys.argv) > 3:
    hx = sys.argv[3].lstrip("#")
    ground = tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
else:
    corners = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    spread = max(de(lab(a), lab(b)) for a in corners for b in corners)
    if spread > 3.0:
        sys.exit(f"corners are not one flat ground (dE {spread:.2f} > 3): regenerate with a flat background")
    ground = tuple(round(sum(c[i] for c in corners) / 4) for i in range(3))
g, cache = lab(ground), {}


def key(p):
    if p not in cache:
        cache[p] = 0 if de(lab(p), g) <= 6.0 else 255
    return cache[p]


pixels = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
alpha = Image.new("L", im.size)
alpha.putdata([key(p) for p in pixels])
rgba = im.convert("RGBA")
rgba.putalpha(alpha.filter(ImageFilter.GaussianBlur(2)))
box = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
if not box:
    sys.exit("nothing left after keying")
rgba.crop(box).save(out, optimize=True)
print(f"keyed {src} -> {out} box={box} ground=#{''.join(f'{v:02X}' for v in ground)}")
```

## Run options (defaults; edit before sending)
- ICON_OPTION: A (A = Neon Night glyph, B = isometric illustration)
- IMAGE_TOOL: codex (codex, api, or none; optional capability, never assumed available)
- IMAGE_MODEL: default (pin only a named model; one per family)
- PILOT_APPROVED: no (yes only for already approved golden references of this family)
- FAN_OUT: no (enterprise only; each member still passes its own eligibility gates)
- FORCE: no (yes reruns a target that `provenance check` reports `fresh`)

TARGET: <OWNER/REPO | ORG | user:LOGIN | enterprise:SLUG>
````

## Verification boundary

Generalized for any operator on 2026-11-18, on Windows with Python 3.14 and the pinned requirements, on top of
the account-chart guards in #205:
- A synthetic outside owner with no brand row rendered neutrally (`needs-input:org-row`).
- `brand add-family --write` into a scratch copy of the config, selected with `--config`, gave that owner its
  own label and palette with no CompleteTech branding. The shipped `references/brand.yaml` was unchanged.
- The new family was refused without `--allow-unmeasured` (exit 4), and `footer --org` reported it exempt.
- Another user's `LOGIN/LOGIN` repository is treated as an ordinary repository, which is why its README stays
  a proposal. `intro --profile` needs a brand row for LOGIN (exit 4 without one).
- `org profile --user` refuses every login except the skill's configured personal account.
- `account-chart render` on the synthetic Northwind snapshot passed `lint svg --kind chart`.

The earlier checks below still apply to the unchanged steps.

Checked offline on 2026-11-18 with Python 3.12 on Linux: 10 CLI help contracts, 69 CLI invocations/assertions
on synthetic Northwind inputs, and 75 focused regression tests. This covered absolute paths containing spaces,
mocked metadata-loader gates, staged/live surfaces and unchanged captures, social upload refusal, R2 drift,
card/banner exemptions, sidebar unknowns, registry-free boundaries, profile preview/ownership/keep controls, project
capture/normalize plans and enterprise fixture checks. Plan argv were inspected, never executed against GitHub.
The prior Windows/Python 3.14 run against `bc4e10b` predates these repairs and does not validate them.

Appendix B is unchanged and retains the supplied/automatic-ground, foreground, feather/crop and
empty/unequal-corner refusal coverage; the repair also rechecked its identity and supplied/automatic-ground
outputs. No real image generation, live GitHub capture, writer action, Windows rerun or fresh-VM run is claimed.
The prompt is operator guidance, not evidence that a real target has been processed or its art approved.
