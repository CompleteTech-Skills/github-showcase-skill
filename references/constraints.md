# Constraints, write discipline and approvals

Condensed from `ct-std-v1` §10 and §12. The skill proposes; a single serialized writer applies. Everything here constrains what the skill may propose and how the writer must apply it.

## Platform limits

| Item | Limit |
|---|---|
| Topics | Lowercase `[a-z0-9-]`, at most 50 characters, at most 20 per repository (the estate uses at most 10). `PUT` replaces the whole set and rejects the whole set (422) if one topic is invalid. Topics are public even on private repositories. |
| Description | About 350 characters enforced in practice; the estate uses at most 140 (new sentences at most 120). |
| Org description | At most 160 characters. |
| Labels | Hex without `#`; description at most 100 characters; renaming with `new_name` keeps attachments. Org default labels seed new repositories only. A form label that does not exist in the repository is silently not applied. |
| Social preview | PNG, JPG or GIF under 1 MB, at least 640×320, 1280×640 best; public repositories only; browser upload only. |
| Avatar | Under 1 MB, under 3000×3000, about 500×500 recommended; browser upload only. |
| Pins | At most 6 public and 6 members-only per org; org owners only; browser only. |
| `.github` repository | Must be public. LICENSE cannot be a default. A repository-level issue-template folder overrides all defaults. |
| README | Truncated after 500 KiB. |
| Write rate (whole account, shared with the web UI) | At most 80 content-creating requests per minute, 500 per hour, 100 concurrent. Wait at least 1 s between writes. On 403 or 429, honour `retry-after` / `x-ratelimit-reset`, otherwise back off at least 60 s exponentially. |
| Archived repositories | Read-only; edits need an approved unarchive, edit, re-archive cycle. |
| Transfers | Blocked if the target has the same name or a fork in the same network. Actions references, Pages, org-scoped settings, App installations and org webhooks do not follow. |
| Org rename | The old name becomes claimable at once; old-name API calls return 404. Logins are case-insensitive, so a case-only change frees nothing. |
| GitHub Actions events | There is no event for description or topic edits. The template workflow runs on push to the icon or config, on a weekly schedule and on demand; the fingerprint makes a no-change run cheap. |

## Write discipline

1. **One serialized writer queue** for every REST call, git push and UI write. Planners and this skill emit change records.
2. **Change record:** `{std, owner, repo, kind: api|file|ui, target, before_sha256, after, rule}`. The writer rejects a record whose `before` no longer matches the live state. Commands that propose writes take `--records FILE`.
3. **Diff first.** GET, compute the delta, write only the delta, GET again to verify. Never write a value that is already equal.
4. **Log every write with its rule** and every skip with a code: `needs-input[:DETAIL]`, `license-review`, `label-conflict`, `label-referenced`, `label-rewrite-first`, `needs-input:label-references`, `hold`, `t3-signoff` (with the opt-in `--require-t3-signoff`: `t3-signoff:no-file|missing|invalid|expired|scope`, see [t3-signoff.md](t3-signoff.md)), `archived`, `topics-short`, `dead-link`, `fork-parent-missing`, `pages-mismatch`, `pages-readme-index`, `homepage-review`, `readme-shrink`, `apache-notice-review`, `art-fail`, `exempt`, `deploy-relink`, `dns-update`, `ui-danger-dialog`.
5. **Never commit logs** or the moves list to a public repository: they name private repositories.

## Content commits

Files a content pass may create or modify (everything else is source code and is never touched):

- `README.md`, `ONBOARDING.md`, `CITATION.cff`, `LICENSE` (approved adds only);
- `.github/CODEOWNERS`, `.github/ISSUE_TEMPLATE/**`, `.github/PULL_REQUEST_TEMPLATE.md`;
- `assets/icon.png`, `assets/logo*.png`, `assets/social-preview.*`, `assets/screenshot.webp`, `assets/diagrams/workflow.mmd`, `assets/examples/example.png` (recompression only), `assets/PROMPTS.md`;
- `docs/images/banner.png`, `docs/images/card.svg`, `docs/images/.showcase.json`;
- `.github/showcase.yml` and `.github/workflows/showcase.yml` (workflow files need the `workflow` token scope).

Link-only edits are allowed in `SKILL.md`, `references/skill-family.md`, the `skill-package.json` `repository` field, and the repository URLs in `package.json` and `pyproject.toml`. `requirements.txt` is never edited.

**Commit messages:** `docs: apply CompleteTech repository standard (ct-std-v1) [skip ci]`, `docs: add CompleteTech brand art (ct-std-v1) [skip ci]`, and the Action's `docs: regenerate showcase banner and card (ct-std-v1) [skip ci]`. Pull requests omit `[skip ci]`. If branch protection blocks the push, open a pull request; never bypass protection and never force-push. Never commit to forks in the watching org. If GitHub Pages builds from the README's directory and there is no `index.html` or `index.md`, do not edit that README; log `pages-readme-index`.

## Repository settings baseline

| Setting | Target |
|---|---|
| `default_branch` | `main`; a rename is approval-gated |
| `has_issues` | `true` for non-forks; `false` for forks in the watching and archive orgs |
| `has_wiki` | `false` only when the wiki is verifiably empty |
| `has_projects` | `false`, unless the repository has a linked project |
| `has_discussions` | `false`, unless discussions exist or the user approves a community hub |
| `delete_branch_on_merge` | `true` |
| Private vulnerability reporting, Dependabot alerts | enabled on public non-fork repositories |
| Pages | read-only; log `pages-mismatch` |
| "Include in the home page" | Releases only if releases exist; Packages and Deployments only if they exist (browser) |
| `is_template` | never changed (the template repository is created as a template once) |

## Approval-gated actions

These need an explicit, per-item, human-approved list, even when the orchestrator runs without permission prompts:

- deleting a repository, org, label (pass 2), project, project field or project item (projects are never deleted at all);
- transferring a repository or leaving a fork network;
- renaming a repository, org or default branch; creating a placeholder org;
- archiving or unarchiving;
- any visibility change (it erases stars and watchers and exposes Actions logs);
- enabling, changing or removing Pages;
- any write to T3, HOLD or EXCLUDED owners;
- adding a LICENSE to a repository that has none (except org `.github` repositories, which get MIT), or adding a `LICENSING.md`;
- a full re-template of an existing org profile, or a full re-layout of a preserve-list README;
- creating a repository (the skill and template repositories are `create-repo` items).

Before any delete: a mirror clone with LFS objects, the wiki, releases, and exported issues and comments, with checksums recorded. No backup, no delete.

## Browser-only work

Avatar uploads, social previews, pins, org default labels, social accounts, the About-box "Include in the home page" settings, star Lists and placeholder orgs are done in the user's signed-in browser session. Never type credentials; stop on re-authentication prompts. Never click inside a "Danger Zone" section, and never type an owner, repository or org name into a confirmation field; press Escape and log `ui-danger-dialog`. Screenshot and verify after every upload; each browser action counts toward the write budget.
