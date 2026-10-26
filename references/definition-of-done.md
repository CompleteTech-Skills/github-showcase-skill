# Definition of done

A repository is done when every check that applies is `pass` (R3 may be `warn`; R7 may be `incomplete`) and the decision columns pass. `showcase.py doctor` prints one row per repository with exactly these columns, so rows from the whole estate concatenate into the coverage matrix:

```text
owner/repo  type  variant  R1 R2 R3 R4 R5 R6 R7 R8 R9 R10 R11  banner icon card footer  done
```

Each cell is `pass`, `warn`, `incomplete`, `fail`, `n/a` or `unknown`. The `done` cell reports done only when every applicable cell is `pass`, `warn` or `incomplete`. `doctor` reads `--repo-dir` and `--meta` only and makes no network calls; live-only checks are `unknown` without the metadata fields they need. Exit 1 when any cell is `fail`.

## Repository checks

| # | Check | Verified by | `doctor` source |
|---|---|---|---|
| R1 | Name passes N1–N4 (N5 is `warn` only), or is exempt, or is on the approved rename list | regex | naming rules in `references/standard/naming.yaml` |
| R2 | Description passes D1–D8, V1, P1, B1, X1, and equals the README tagline wherever the header applies (T3: description only) | metadata `description` | `describe` |
| R3 | Topics follow the counts and vocabulary; below the minimum after the merge → `warn` with `topics-short` | metadata `topics` | `topics` (`equal_as_set`) |
| R4 | `homepage` is empty, or unchanged and logged `homepage-review`, or a standard URL that passes the GET check | live GET | `unknown` without a recorded check |
| R5 | Settings match the baseline | metadata `has_*`, `delete_branch_on_merge` | `unknown` without those fields |
| R6 | Where labels apply (archived repositories included: decision 6 polishes them in an unarchive, polish, re-archive cycle): a superset of the standard set with exact name, colour and description (AI-Ascension: `dependencies` exists with `0366d6`) | metadata `labels` | `labels --plan` (no ops left) |
| R7 | README matches its variant: nav line, banner, H2 order, every image resolves, canonical GitHub links, no placeholder text, under 500 KiB; logged omissions → `incomplete`; preserve-list repositories checked for the additive items only | `lint readme` | `lint readme` |
| R8 | A LICENSE is present and unchanged, or added from the approved list, or none is required | metadata `license` and the checkout | license rows |
| R9 | CompleteTech-Skills `agent-skills` repositories: `assets/logo.png` and `assets/logo-dark.png` are byte-identical to the brand files; `n/a` elsewhere | sha256 | checkout |
| R10 | Custom social preview on T1 and T2 public, non-fork, non-archived repositories (excluding `.github`, `*.github.io` and the profile repository) | live GraphQL `usesCustomOpenGraphImage` | `unknown` without the field |
| R11 | `health_percentage` is 100 for public, non-fork, non-archived, non-`.github` repositories in T1 and T2 orgs other than romgenie (excluding those waiting on the license list) | metadata `health_percentage` | `unknown` without the field |
| R12 | Custom properties set (orgs only; only if adopted) | org properties | not a repository column |

## Decision columns

| Column | Decision | Passes when |
|---|---|---|
| `banner` | 13 | `docs/images/banner.png` passes `lint banner` (opaque RGB, 1280×360 or 2560×720, at most 300 KB, sidecar sha matches) and the README's first image is the banner block; a banner with fewer than two chips is `incomplete` and the row is not `done`. Forks outside the watching org (G, review q27), backups and archived repositories (H) and `.github` repositories (J) need it too. `n/a` only for watching-org forks, preserve-list READMEs when review q57 `pres` is "Leave them unchanged" (`exempt:preserve-banner`, `preserve-list`; with the default the hero goes above their own banner), `CompleteDotTech/CompleteDotTech` (its README opens with the intro) and a placeholder org's `.github`; `hold` for hold families and T3 |
| `icon` | 12 | `assets/icon.png` exists and is valid (1024×1024 RGBA, at most 300 KB); `fail` while the banner still uses the org mark or a family fallback (CompleteTech logo or family wordmark). Forks outside the watching org, backups, archived repositories and `.github` repositories need one (a `.github` icon never reuses the org's avatar glyph). `n/a` only for watching-org forks (`watching-fork`) and a placeholder org's `.github`; `hold` for T3 and hold families |
| `card` | 21 | `docs/images/card.svg` passes `lint svg --kind card` and is the only card file (no `-dark` or `-light` sibling); `n/a` for forks, backups and `github-profile` repositories (no card, STANDARD §5.4) and watching-org forks |
| `footer` | 18 | `footer --check README.md` passes: the exact footer is the README's last block, after the License section. Forks outside the watching org, backups, archived repositories and `.github` repositories need it. `n/a` for watching-org forks and owners whose `footer` is `false`; `hold` for an org whose `footer` is `hold` and for T3 owners. TouchedByAnAgent is included (decision 18); set its `footer` to `hold` in `brand.yaml` only if the user declines on the review page |

The template repository adds one more signal: `checklist: open` while any box in its setup checklist is unchecked.

## Organization checks

O1–O11 (avatar, About fields, `.github` profile, default files, `labels.yml`, pins, X account, listing on the CompleteDotTech profile, org banner, Workstreams project, verified badge) are in [orgs-and-projects.md](orgs-and-projects.md). `org doctor ORG --snapshot FILE` reports O1, O2, O3, O4, O6, O9 and O11 for one org ([org.md](org.md)); `project lint` checks O10 ([projects.md](projects.md)); O5, O7 and O8 are verified by the orchestrator. The repository `doctor` covers repositories only.

## Not done means

- A `fail` cell: fix the cause, never the check.
- `needs-input:DETAIL`: a fact is missing; a writer or the user supplies it. Never fill it with placeholder text.
- `art-fail`: text did not fit the fixed ladder; shorten the source or set a `subtitle` override; never truncate.
- `hold`, `t3-signoff`, `exempt`: waiting on a user decision or out of scope by rule; reported, not worked around.
