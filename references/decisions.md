# User decisions this skill implements

Verbatim excerpt from `decisions/USER_DECISIONS.md` (Timothy Wayne Gregg, 2026-10-25) in the estate hand-off bundle, except that the skill note under decision 18 is skill maintenance and not part of the user decision, and that [proposed decision 25](#proposed-decision-25-provenance-attribution-and-the-star-nudge) at the end is a skill-maintenance **PROPOSAL pending user confirmation**, not a user decision. These decisions outrank the estate standard `ct-std-v1` (`STANDARD.md`), the art direction and every audit proposal. Where this skill's references paraphrase the standard, the decisions below have already been applied.

Skill maintenance (#47): the footer logo URLs configured in `references/brand.yaml` were repaired because the former URLs returned 404. Layout, credit and artwork are unchanged. The user decisions below are unmodified.

| Decision | Where the skill applies it |
|---|---|
| 5 One home | `org profile` lists a repository under its home org and cross-lists it under `also_in` orgs ("Also from CompleteTech"); `org labels` plans only repositories homed in the org ([org.md](org.md)). |
| 6 Coverage | `doctor` covers private and archived repositories; watching-org forks are metadata-only (`exempt`); T3 waits for sign-off (exit 2). |
| 10 Set review | `contact-sheet` (grid, stack and avatar modes on `#0d1117` and `#ffffff`). |
| 12 Own icon | `assets/icon.png` resolution order; `doctor` column `icon`; `needs-input:repo-icon` until it exists. |
| 13 Hero banner | `banner` (golden layout, [banner-layout.md](banner-layout.md)); `readme` header block; `lint readme` banner-first rule. |
| 14 Pins | `org pins`: per-pin checks, `browser` pin jobs and the per-org star List plan ([org.md](org.md)); pins are set in the browser by the orchestrator. |
| 15 Profile kit | `org profile` renders the kit's section order from the registry's public slice ([org.md](org.md), [profile-readmes.md](profile-readmes.md)). |
| 18 Footer | `footer`, `footer --check`, `lint readme` footer-last rule. |
| 19 Brand master | `brand_assets.dark_master` in `brand.yaml`; no runtime crop. |
| 21 Dark designs | One file per surface; `lint svg` rule D21 fails `-dark`/`-light` siblings; the footer is the only `<picture>`. |
| 22 Skill and template | This package and `completetech-repo-template` (its workflow calls `action.yml`). |
| 23 Orgs and Projects | `org` and `project` command groups ([org.md](org.md), [projects.md](projects.md)); rules in [orgs-and-projects.md](orgs-and-projects.md). |
| 24 Enterprise | `enterprise` command and [enterprise.md](enterprise.md): read-only snapshot query and snapshot, E-checks, seat check, printed change records and writer jobs. |
| 25 Provenance (PROPOSAL) | `provenance check`, `stamp` and `star`; the credit block after the footer; the `provenance` rows of `doctor`, `org doctor` and `enterprise doctor`. Pending user confirmation. |

## Structure

5. **One home, many showcases.**
   - Each repo has one home org.
   - A repo that also fits other orgs is listed in `registry/estate.yaml` under `also_in`. It is then cross-listed on those orgs' profile READMEs and carries their org topic.
   - **Never fork a repo to make it appear in a second org.**

## Coverage

6. **Every in-scope repo is updated:** About (description, website, topics), labels, README and art. That includes private repos, repos moved in Phase 2, and older repos found in Phase 0.
   - **Already-archived repos are included too**, via the `polish-archived` group action: unarchive → polish → re-archive. This overrides any "no writes to archived repos" rule in `STANDARD.md`.
   - The only exceptions:
     - `secrets-risk` repos
     - T3/co-owned orgs (Pick-Your-AI, Jevelopers-neatHack-2026) until their co-owners sign off
     - watching-org forks, which keep their upstream README (metadata only)

## Look and art

10. **The bar is "the most beautiful GitHub collection ever".** Art is judged **as a set**, in the contexts where it is actually seen (contact-sheet gates in Phase 5).

12. **Every in-scope repo gets its own icon or logo.** No repo falls back to a shared org image. Watching-org forks are the only exception. This overrides `STANDARD.md` §9.1 rule 6 and the "no AI-Ascension art in v1" rule. T3 art still waits for co-owner sign-off.

13. **Every in-scope repo's README opens with a hero banner.**
    - **Golden reference:** `art/golden/readme-banner-php2shell-check.png` (the php2shell-check README), 1280×360. It has:
      - a navy grid canvas
      - a rounded white card on the left holding the logo
      - an eyebrow line, `COMPANY · CATEGORY`, in sky blue
      - the repo name large, in monospace
      - a one-line subtitle
      - two to four fact chips (gold for the key identifier, blue for attributes)
      - an accent bar along the bottom
    - Repos outside the security org get the same layout. The left card holds the **repo's own icon** (decision 12). Before the icon exists, it holds the org's avatar mark. Each family's palette replaces the CompleteTech palette.
    - The banner is typeset by the compositor (`STANDARD.md` §9.5); the image model never draws text.
    - The badge row and the bold one-line description follow the banner, exactly as on php2shell-check.

14. **Pins:** up to 6 public pins and up to 6 members-only pins per org (through each repo page's "Edit Pins" menu), plus 6 personal profile pins. Optional per-org star Lists on the user's account.

15. **Profile READMEs** follow `showcase/PROFILE_README_KIT.md`. That kit is curated from awesome-github-profile-readme: content first, nothing that depends on a third-party server, and no novelty widgets.

## Footer and brand master

18. **Every in-scope README ends with the CompleteTech LLC footer** (user screenshot, 2026-10-25):
    - a centred logo about 200 px wide, linking to https://www.complete.tech
    - under it, the line `Built by [CompleteTech LLC](https://www.complete.tech) · Innovation at Every Integration`

    Use `<picture>` so **dark mode shows the transparent dark logo (no white box)** and light mode shows the light logo. Exact markup:
    ```html
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
    ```

    **Skill note (#47, not part of the user decision):** The footer URLs this skill currently emits are configured in `references/brand.yaml` (`footer.logo_light_url` and `footer.logo_dark_url`) and point to this repository's published masters: https://raw.githubusercontent.com/CompleteTech-Skills/github-showcase-skill/main/assets/brand/logo.png and .../logo-dark.png (same sha256 as listed in `assets/brand/README.md`). The former `CompleteTech-LLC/.github/main/brand/` URLs shown in the decision above returned 404. Layout, credit text, theme selection and artwork are unchanged.

    - Scope: all in-scope repos, T2 families included ("all of them").
    - Exceptions: watching-org forks (not the user's work), and T3 orgs until their co-owners sign off.
    - TouchedByAnAgent is included on this instruction. `STANDARD.md` §12.5 #4 had left it open; confirm on the review page.

19. **Brand master: use the better logo version.** The complete.tech website's theme has a dark full logo, `complete-tech-logo-dark-full.png`.
    - It is 1200×599 with a transparent background and a gradient wordmark. A copy is in `art/brand-candidates/`, with `logo-compare.png` showing it on both GitHub themes.
    - It is the preferred **dark** master, pending the user's confirmation on the review page. The current `logo.png` stays the **light** master until a transparent light version exists.
    - If adopted, the estate planner re-measures the `STANDARD.md` §9.2 crop boxes (`mark-dark.png`, `bulb-dark.png`) on the new master in P0. Never reuse the old pixel coordinates.

## Dark designs, template and skill

21. **Dark designs everywhere** ("I like the dark ones").
    - The README hero banner, the repo cards, org tiles and the profile intro use the **dark** design on both GitHub themes: one file each, no light variant. The navy plates read well on white too, as php2shell-check shows.
    - This overrides `showcase/SVG_RULES.md` S22's light/dark pairs and the light card variant.
    - The one exception is the footer logo (#18). It keeps `<picture>`, because the logo itself must stay visible on both themes.

22. **Make it repeatable with a template and a skill:**
    - **Skill:** a CompleteTech-Skills skill package (same layout as `agentic-email-skill`: `SKILL.md` + `AGENTS.md` + `agents/openai.yaml` for Claude and Codex, `references/`, `scripts/`, `assets/`, `tests/`, validators, CI). It packages the standard and the generators:
      - README hero banner
      - repo card
      - profile intro
      - footer
      - README scaffolding per variant
      - description, topic and label checks
      - the SVG linter
      - contact-sheet gates

      Any agent can make a repo match the estate with it. **The orchestrator uses this skill to do the work.**
    - **Template repo:** new repos start from it. It holds the README skeleton, the folder layout, and a GitHub Action that regenerates the banner and card from the repo's description and topics on change.
    - Both repos are **created** by the orchestrator in Phase 4. They are listed in `APPROVED_ACTIONS.yaml` as `create-repo` items.

## Organizations and Projects

23. **The skill also covers organizations and GitHub Projects** (user, 2026-10-25).
    - **Reference board:** the user's org project https://github.com/orgs/Pick-Your-AI/projects/1, worked through its **"Workstream Overview"** view.
    - **Phase 0 (read-only):** capture that project as the golden template: fields with options and colours, views with layout, grouping, sort and visible fields, README, short description, linked repos, workflows. Save it to `registry/projects/workstream-overview.template.json`, with screenshots of every view.
    - **Rollout:** projects are copied from that template to the orgs the user approves, and a cross-org personal "Estate" project is offered. Each project's README and short description follow the standard.
    - **Pick-Your-AI is co-owned (T3):** reading its project is fine; changing it needs co-owner sign-off.
    - **Never deleted:** projects, project fields and project items (enforced by the guard).

## Enterprise

24. **The CompleteTech Enterprise is in scope** (user, 2026-10-25), and the skill gets an enterprise module.
    - **Phase 0 (read-only):** discover the enterprise slug; capture the profile, the orgs inside and outside it, members, outside collaborators, pending invitations, license and seat usage, verified domains, policies and rulesets into `registry/enterprise.snapshot.json`.
    - **Phase 1:** polish the enterprise profile and settings, approved items only (`enterprise` approvals).
      - Prefer **one enterprise-level verified domain**. Research confirmed it badges enterprise-owned orgs whose website and email match. Verify both `complete.tech` and `www.complete.tech`, and set each org's blog and email to match.
      - Free romgenie's seat with the safe procedure in that file.
    - **Policies:** changes are proposals only. Each enterprise policy affects every org, so each needs its own tick.
    - **Report:** the final report shows the enterprise before and after (seats, orgs, policies, domain).

## Proposed decision 25: provenance, attribution and the star nudge

**PROPOSAL pending user confirmation.** This is not part of `decisions/USER_DECISIONS.md`. Skill maintenance proposed
it on 2026-11-18 and the skill implements it as written below. Until the user confirms it, every item may still
change, and nothing here outranks decisions 1 to 24.

25. **Know before running, record when it ran, credit the skill, and ask for a star at most rarely.**
    - **One stamp per target**, validated against [`provenance.schema.json`](provenance.schema.json). The
      `provenance` block holds `skill`, `skill_url`, `publisher` ("CompleteTech LLC"), `skill_version`, `standard`,
      `target {kind, id}` (the resolver's canonical id, so a renamed org still finds its stamp), `first_run_at`,
      `last_run_at`, `last_changed_at` (UTC ISO-8601), `run_count`, `fingerprint` and `surfaces[]`.

      | Target | Stamp |
      |---|---|
      | Repository | the existing `docs/images/.showcase.json`, extended (no second file) |
      | Organization | `.github/showcase.json` in the `ORG/.github` repository |
      | Personal profile | `.github/showcase.json` in the `USER/USER` repository |
      | Enterprise | `<estate root>/registry/enterprise.showcase.json`, beside `registry/enterprise.snapshot.json` in the private estate bundle ([enterprise.md](enterprise.md)); never a public repository |

    - **No timestamp-only commits.** Timestamps and `run_count` are never part of the fingerprint, so they never make a
      target look changed and never loop the Action. `last_run_at` is written only in the same Action commit, checkout
      commit or writer batch as the run's other changes. A run that changes nothing writes nothing, is reported
      `fresh` and is counted only in the operator's local ledger. The one stamp-only write is the first stamp of a
      target that has none (`never`, or the `untracked` backfill).
    - **Pre-run check.** `provenance check TARGET` answers `never`, `fresh` (skip unless `--force`), `stale` (rerun
      only the surfaces in `changed[]`), `untracked` (showcased before stamps existed; offer the stamp-only backfill)
      or `foreign` (excluded owner, T3 without sign-off, watching-org fork; never suggest running).
    - **Credit wording.** Directly after the decision 18 footer, in its own `showcase:credit` marker block (never
      inside the footer, whose markup stays byte-identical and stays the only `<picture>`): a hidden
      `<!-- generated-by: github-showcase-skill v=<version> std=ct-std-v1 -->` marker and the visible line *README
      styled with [github-showcase-skill](https://github.com/CompleteTech-Skills/github-showcase-skill) by
      CompleteTech LLC · [Get the skill](https://github.com/CompleteTech-Skills/github-showcase-skill#quick-start)*, rendered from `attribution` in `brand.yaml`. Repository READMEs, org profile READMEs and the
      personal profile README carry it; the Enterprise has no README and gets none. `footer --check` and `lint
      readme` require it, and one regeneration adds it to an old footer. Optional and off by default: a
      `github-showcase-skill` topic proposed by `provenance stamp --propose-topic` as a writer job that needs approval.
    - **Star thresholds** (confirmed 2026-11-18: runs 5, 10, 15, ...). The operator's ledger (`~/.config/github-showcase-skill/state.json`,
      `%APPDATA%\github-showcase-skill\state.json` on Windows, `$SHOWCASE_STATE_DIR` to override) counts completed
      runs: one successful `provenance stamp` is one completed run, and nothing else counts. At **5** completed runs
      the skill makes one read-only GET of `user/starred/CompleteTech-Skills/github-showcase-skill`. If the skill is
      starred, that is recorded and it never asks again. If not, it prints one line with the link and `gh repo star
      CompleteTech-Skills/github-showcase-skill`, then asks again every **5** further runs (runs 5, 10, 15, ...),
      and never again after a decline. A missing, unauthenticated or offline `gh` is silent and never counts as "not starred". The
      skill never stars on the operator's behalf, never prompts in CI, with `--format json` or without a TTY, and
      honours `--no-star-prompt` and `SHOWCASE_NO_STAR_PROMPT=1`. The ledger stores no target names and sends no
      telemetry.

    **Confirmed by the user (2026-11-18):** the Enterprise stamp beside the snapshot, the credit wording with the
    *Get the skill* install prompt, and the star asks at runs 5, 10, 15, .... **Still to confirm:** the
    no-timestamp-only-commit rule, the other stamp locations, and `provenance stamp` as the one counted command.
