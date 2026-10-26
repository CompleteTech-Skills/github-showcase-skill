# Issue labels

All label plans (`labels --plan`, `org labels` and `adopt`) carry `group: labels:OWNER/REPO` for the writer's half-completed-group reconciliation. An explicit orchestrator group takes precedence. For archived repositories, `adopt` emits no mutations until metadata is re-captured inside the approved unarchive/polish/re-archive window; the user approval and writer remain required.

Condensed from `ct-std-v1` §6, verbatim where it matters. `showcase.py labels --emit-yml` prints the `labels.yml` below byte for byte; `labels --plan` runs passes A and B against the repository's current labels (renames before creates, never `--force`, never a delete) and prints the same plan as `gh label edit/create … -R OWNER/REPO` argv and as `scripts/writer.py` jobs (`--jobs FILE` appends them; `--gh` also prints command lines). The skill never writes labels: the orchestrator's writer applies the jobs after re-reading the live labels, and a standalone user runs the printed argv after approving it. The machine-readable file is `references/standard/labels.yml`.

GitHub limits: hex colours without `#`; descriptions at most 100 characters; renaming with `new_name` keeps the label on every issue and pull request. Org default labels seed new repositories only, and a form label that does not exist in the repository is silently not applied.

## Scope

- **Apply** to every non-fork, non-archived repo in T1 and T2 product orgs whose `has_issues` is `true` **after** the settings baseline is applied. Public repos first, then private.
- **`.github` repos** always get the standard set, whatever their `has_issues`.
- **AI-Ascension:** keeps its `labels.yml` and color tokens. R6 there means only that `dependencies` exists (`0366d6`, the standard set description); its Dependabot configs use `labels: ["dependencies"]`.
- **Don't apply** to T2-R, T3, HOLD, forks or archived repos.
- `labels --plan` (one repository) applies the same gates as `org labels`: a family on hold is refused (exit 2) unless `--allow-hold`; a T3 owner is refused (exit 2, `t3-signoff`) until co-owner sign-off, as `org labels` refuses it without `--allow-t3`; AI-Ascension gets only the `dependencies` create or patch; a repository with `has_issues: false` other than `.github`, forks, archived repositories (`archived`), T2-R and romgenie repositories answer `n/a`. Metadata without labels (a missing key, or `[]`, which is also what a failed capture records) is never planned against: whenever argv, writer jobs (`--jobs`), records (`--records`) or `gh` lines leave, `labels` reads the live labels first (read-only GET) and exits 4 (`needs-input:gh`) when it cannot. Writer job ids come from the operation (`p3.2-OWNER__REPO-label-<create|edit>-<name>[-to-<new>]-<hash8>` for `labels --plan` and `org labels`, `p3:label:OWNER__REPO:<create|edit>:<name>[-to-<new>]:<hash8>` for `adopt`), so a re-plan never reuses an id for other content.
- **Org default labels** [UI]: all T1 orgs and the T2 product orgs except AI-Ascension, which uses its own `labels.yml`. None for the romgenie orgs or CompleteDotTech. Removing GitHub's default entries from org defaults is exempt from the approval list.

## The standard set: 23 labels

One color per namespace. Hex values are lowercase without `#`. Every description starts with the namespace word and is ≤ 100 characters.

| Name | Color | Description |
|---|---|---|
| `type:bug` | `1d76db` | Type: something is broken or behaves incorrectly |
| `type:feature` | `1d76db` | Type: new capability or enhancement |
| `type:docs` | `1d76db` | Type: documentation, README or examples |
| `type:maintenance` | `1d76db` | Type: refactor, tooling, CI or dependency upkeep |
| `type:security` | `1d76db` | Type: security hardening; report vulnerabilities privately per SECURITY.md |
| `type:research` | `1d76db` | Type: investigation or evidence needed before implementation |
| `type:question` | `1d76db` | Type: question or request for information |
| `type:accessibility` | `1d76db` | Type: accessibility barrier or improvement |
| `priority:p0` | `b60205` | Priority: immediate; security, data loss or release blocker |
| `priority:p1` | `d93f0b` | Priority: major functional blocker or shared prerequisite |
| `priority:p2` | `fbca04` | Priority: important planned work |
| `priority:p3` | `c2e0c6` | Priority: lower-impact enhancement or maintenance |
| `status:needs-triage` | `f9d0c4` | Status: new; needs review and labels |
| `status:ready` | `f9d0c4` | Status: triaged and ready to work on |
| `status:blocked` | `f9d0c4` | Status: waiting on another issue, decision or dependency |
| `status:needs-review` | `f9d0c4` | Status: work done; needs review or verification |
| `status:deferred` | `f9d0c4` | Status: valid but intentionally postponed |
| `resolution:duplicate` | `cfd3d7` | Resolution: already tracked in another issue or pull request |
| `resolution:invalid` | `cfd3d7` | Resolution: not a valid issue for this repository |
| `resolution:wont-fix` | `cfd3d7` | Resolution: will not be worked on |
| `good first issue` | `7057ff` | Good for newcomers |
| `help wanted` | `008672` | Extra attention is needed |
| `dependencies` | `0366d6` | Pull requests that update a dependency file |

Keep `good first issue`, `help wanted` and `dependencies` **byte-exact**: GitHub and Dependabot depend on them.

**Extensions** (repo-specific; never created by default): `area:<component>` `5319e7` "Area: …"; `scope:epic` / `scope:program` `bfdadc` "Scope: …"; `priority:p4` `e4e669` "Priority: speculative or explicitly deferred" (exists in creative-studio).

## Migration map and apply algorithm

| Existing | → Standard |
|---|---|
| `bug` | `type:bug` |
| `enhancement`, `feature` | `type:feature` |
| `documentation`, `docs`, `type:documentation` | `type:docs` |
| `question` | `type:question` |
| `accessibility` | `type:accessibility` |
| `duplicate` | `resolution:duplicate` |
| `invalid` | `resolution:invalid` |
| `wontfix`, `won't fix` | `resolution:wont-fix` |
| `security` | `type:security` |
| `research` | `type:research` |
| `maintenance`, `chore` | `type:maintenance` |
| `blocked` | `status:blocked` |
| `epic` | `scope:epic` (extension; only if it exists) |
| `good first issue`, `help wanted`, `dependencies` | unchanged; fix only color and description |

**Algorithm** (names compared case-insensitively; renames before creates):

```
Pass A, for each label L in labels.yml in file order (then the epic → scope:epic extension):
  if L.name exists:
      PATCH only the color, description and name casing that differ
      if any alias of L also exists → log label-conflict (the rules for existing labels rule 2)
  elif an alias of L exists (first in aliases order):
      run the rules for existing labels rule 0; if it blocks → log label-referenced, skip L
      if rule 0 cannot run (no checkout, and the captured file list does not prove that no file it reads exists)
          → log needs-input:label-references, hold the rename, skip L
      if a form's labels: key or a dependabot.yml labels: entry assigns it → log label-rewrite-first, hold the rename, skip L
      else PATCH it with new_name=L.name plus color and description
      any other alias of L that also exists → log label-conflict
Pass B, for each L still missing: POST create
Never use `gh label create --force`.
```

Address a label as `PATCH /repos/{o}/{r}/labels/{name}` with `{name}` percent-encoded (`won%27t%20fix`), or `gh label edit "<old>" --name <new> --color <c> --description <d> -R <o>/<r>`. A rename keeps the label on every issue and PR.

## Rules for existing labels

0. **References first.** Before renaming label L in repo R, search R and `<Org>/.github` for L as a whole token in `.github/**` and in every Renovate config file. If L appears in `.github/workflows/*`, `release.yml`, `labeler.yml` or a Renovate config file, skip the rename and log `label-referenced`. The Renovate config files are the ones Renovate itself reads: `renovate.json`, `renovate.json5`, `.github/renovate.json`, `.github/renovate.json5`, `.gitlab/renovate.json`, `.gitlab/renovate.json5`, `.gitea/renovate.json`, `.gitea/renovate.json5`, `.forgejo/renovate.json`, `.forgejo/renovate.json5`, `.renovaterc`, `.renovaterc.json`, `.renovaterc.json5` (names matched case-insensitively), and the `renovate` key of the root `package.json`: there only a string inside that key counts, so a label word in the package's description or keywords does not block, and a `package.json` that does not parse blocks when it mentions `"renovate"` and L as a token anywhere. In `<Org>/.github` only the default issue forms count (files directly in its `.github/ISSUE_TEMPLATE/`, `ISSUE_TEMPLATE/` or `docs/ISSUE_TEMPLATE/`), and only when R has no file in a `.github/ISSUE_TEMPLATE/` of its own, because GitHub then applies the owner's defaults to R. If it is assigned only by the `labels:` key of an issue form or of a Markdown issue template's front matter, or by a `labels:` entry in `dependabot.yml` (the file is parsed as YAML, after any byte order mark: an inline or multi-line value, a block list, a quoted key or an alias all count, and names match case-insensitively; a file that does not parse holds the rename wherever L appears in it as a token), rewrite those references through the migration map in the same work unit as the rename, rewrite first: `labels --plan` holds the rename out of the argv and writer jobs, logs `label-rewrite-first` and lists every `path:line` to rewrite (`rewrite_first` in the JSON, one line each on stderr, with `repo` set to `<Org>/.github` for a default form there); `adopt` holds it the same way and logs the code. The rewrite is a content change in the estate/polish PR, never a label job; once it merges, re-run the plan on the merged checkout and the rename leaves as a job. A rename the plan holds is never emitted bare, because `gh label edit --name` does not touch repository files and a form naming a missing label is silently not applied. Rule 0 never silently skips: without a checkout (`labels --plan` with no `--repo-dir`, `adopt` with none, and `org labels`, which never has one) a rename is planned only when the metadata's `files` is the complete tree `meta --from-gh` captures (`files_complete: true`, which it records only when GitHub returned the recursive tree untruncated) and it lists none of the files rule 0 reads (`.github/ISSUE_TEMPLATE/*`, `.github/dependabot.yml`, `.github/workflows/*`, any `.github/**` file named `release.yml`, `labeler.yml`, `renovate.json` or `renovate.json5`, and every other Renovate config file above). A listed `package.json` alone does not hold the rename: a file list cannot show whether it has a `renovate` key, Renovate deprecates configuring it there, and holding every JavaScript repository's renames on that guess would leave the check unusable without a checkout; a missed reference there only lets Renovate re-add the old label to its own pull requests, which the checkout pass (`--repo-dir`) catches. The owner's `.github` must be proven the same way when R has no forms of its own: by a checkout (`--org-defaults DIR` on `labels` and `adopt`), or by its complete captured tree listing no default issue form (`--org-defaults FILE`, the `meta --from-gh <Org>/.github` JSON; `org labels` reads it from `--meta-dir`). `--org-defaults` must be the OWNER's `.github`: a JSON whose `owner` (or `owner.login`, or `full_name`) names another org, or a checkout whose `origin` names another org or repository, is refused (usage, exit 2); old and new logins of the owner resolve alike (CQ-03). A JSON that names no owner, or a checkout without a GitHub `origin` of its own, cannot prove the absence of default forms: a default form found in it still holds the rename (`label-rewrite-first`), and finding none holds it as `needs-input:label-references`. Otherwise (no capture, a truncated or unmarked list, the fixtures' partial `{path: value}` map, or a listed reference file or default form) the rename is held as a skip logged `needs-input:label-references` with `check_files` (the listed reference files, or these patterns when the capture cannot prove absence; entries in the owner's `.github` are prefixed `<Org>/.github:`): `labels --plan` reports them as `needs_checkout` (result `needs-input`, exit 4, when nothing else is pending), `adopt` adds a pending step and `org labels` marks the repository `needs-input`. Re-plan with `--repo-dir` on a checkout (and `--org-defaults` for the owner's `.github`). Creates and colour or description patches that are not renames are planned as usual. `--references` is kept for compatibility and changes nothing: the check always runs. The same check covers `epic` → `scope:epic`. A label word in prose (a form's description or field label such as "Describe the bug", the pull request template, `CONTRIBUTING.md`) names no label: it never holds a rename.
1. **Never delete a label in pass 1**, including unused labels.
2. If both a legacy label and its target exist (for example `bug` and `type:bug`), do not relabel any issue. Log `label-conflict` with both issue counts.
3. A label whose name equals a standard-set name (case-insensitive) gets the standard-set name casing, color and description exactly. Other labels in `type:`, `priority:`, `status:`, `resolution:`, `area:` or `scope:` keep their name and description and get the namespace color (`area:` `5319e7`, `scope:` `bfdadc`, `priority:p4` `e4e669`, others per the standard set). A description prefix `Workflow:` becomes `Status:`, `Hierarchy:` becomes `Scope:`, and any other missing prefix gets `<Namespace>: ` prepended.
4. Other custom labels (for example ai-usage-ledger-skill `privacy`, `security-audit`): keep name and description; only lowercase the hex.
5. Labels exist before any issue form that references them is pushed, in both the `.github` repo and the target repos.
6. Pass 2, after human review, may delete labels with zero issues and PRs (open and closed) that no template or workflow references. [APPROVAL]

## `labels.yml` (in every T1 and T2 product org's `.github` root, except AI-Ascension; data, not a workflow)

```yaml
# CompleteTech label standard ct-std-v1. Apply with the §6.3 algorithm: rename aliases with
# PATCH new_name (pass A), then create what is missing (pass B). Never `gh label create --force`.
- {name: "type:bug",            color: "1d76db", description: "Type: something is broken or behaves incorrectly", aliases: ["bug"]}
- {name: "type:feature",        color: "1d76db", description: "Type: new capability or enhancement", aliases: ["enhancement", "feature"]}
- {name: "type:docs",           color: "1d76db", description: "Type: documentation, README or examples", aliases: ["documentation", "docs", "type:documentation"]}
- {name: "type:maintenance",    color: "1d76db", description: "Type: refactor, tooling, CI or dependency upkeep", aliases: ["maintenance", "chore"]}
- {name: "type:security",       color: "1d76db", description: "Type: security hardening; report vulnerabilities privately per SECURITY.md", aliases: ["security"]}
- {name: "type:research",       color: "1d76db", description: "Type: investigation or evidence needed before implementation", aliases: ["research"]}
- {name: "type:question",       color: "1d76db", description: "Type: question or request for information", aliases: ["question"]}
- {name: "type:accessibility",  color: "1d76db", description: "Type: accessibility barrier or improvement", aliases: ["accessibility"]}
- {name: "priority:p0",         color: "b60205", description: "Priority: immediate; security, data loss or release blocker"}
- {name: "priority:p1",         color: "d93f0b", description: "Priority: major functional blocker or shared prerequisite"}
- {name: "priority:p2",         color: "fbca04", description: "Priority: important planned work"}
- {name: "priority:p3",         color: "c2e0c6", description: "Priority: lower-impact enhancement or maintenance"}
- {name: "status:needs-triage", color: "f9d0c4", description: "Status: new; needs review and labels"}
- {name: "status:ready",        color: "f9d0c4", description: "Status: triaged and ready to work on"}
- {name: "status:blocked",      color: "f9d0c4", description: "Status: waiting on another issue, decision or dependency", aliases: ["blocked"]}
- {name: "status:needs-review", color: "f9d0c4", description: "Status: work done; needs review or verification"}
- {name: "status:deferred",     color: "f9d0c4", description: "Status: valid but intentionally postponed"}
- {name: "resolution:duplicate", color: "cfd3d7", description: "Resolution: already tracked in another issue or pull request", aliases: ["duplicate"]}
- {name: "resolution:invalid",  color: "cfd3d7", description: "Resolution: not a valid issue for this repository", aliases: ["invalid"]}
- {name: "resolution:wont-fix", color: "cfd3d7", description: "Resolution: will not be worked on", aliases: ["wontfix", "won't fix"]}
- {name: "good first issue",    color: "7057ff", description: "Good for newcomers"}
- {name: "help wanted",         color: "008672", description: "Extra attention is needed"}
- {name: "dependencies",        color: "0366d6", description: "Pull requests that update a dependency file"}
```

Expected writes for a repo with only GitHub's defaults: 7 renames and 14 creates (8 and 13 if `accessibility` exists), plus color and description patches on `good first issue` and `help wanted`.
