# Account chart

`account-chart` maps one GitHub account as a single tree: the repositories it owns, each enterprise it owns or belongs to, each organization inside or outside an enterprise, and every public repository of each organization. It is a showcase surface in the estate's dark design, judged with the rest of the set (decision 10).

| Output | What it is |
|---|---|
| `NAME.mmd` | The tree as a themed Mermaid `flowchart LR`, ready for a README or GitHub's native `.mmd` view, and for mermaid-cli. |
| `NAME.svg` | The compositor render: the same tree in the banner and card design, outlined text, GitHub-safe (`lint svg --kind chart`). |
| `NAME.png` | The same scene rasterized at `--scale` (2 by default): the high-definition picture. |
| `NAME.md` | The README block: the image (linking to the PNG), the counts the image leaves out, and every repository as a link. |
| `NAME-summary.svg` | The closing visual in the profile intro's design: the account's mark with gold circuit traces, and the code's languages as a bar and key with percentages (`lint svg --kind intro`). Written when the snapshot has per-language sizes and the eyebrow and name fit its type ladder (`summary-skipped:no-code-shares` or `summary-skipped:type-does-not-fit` otherwise). |
| `NAME.mermaid.png` | Only with `--mmdc`: the Mermaid source drawn by mermaid-cli at natural size. |

## Commands

```bash
S=<skill-dir>/scripts/showcase.py
python3 $S account-chart capture-query                     # print the read-only reads; no network
python3 $S account-chart capture --out account.snapshot.json  # the signed-in account (or pass a LOGIN)
python3 $S account-chart render --snapshot account.snapshot.json --out-dir docs/images
python3 $S lint svg --kind chart docs/images/account-chart.svg
```

`render` options: `--name` (file stem, default `account-chart`; a `-dark`/`-light` stem is refused, decision 21), `--width` (1600–4800 px, default 2400; the height follows the account), `--scale 1|2|3|4` (PNG pixels per px; lowered automatically above 120 megapixels and logged `png-scale:<n>`), `--hide forks` and `--hide archived`, `--show all-orgs|private-work|.github|external-forks` (repeatable; see below), `--allow-hold` (show HOLD organizations; also accepted by `capture`), `--static-summary` (the summary SVG without motion), `--avatar PATH` (the account's picture; default its brand mark, else a monogram), `--no-png`, `--mmdc [PATH]` with `--mmdc-config FILE`, and the resolver inputs `--registry`, `--decisions`, `--approved`, `--approved-yaml` and `--actions`. The global `--allow-t3` (or `--allow-t3` after the command) admits T3 orgs that have a valid sign-off record.

Before any output is written, the complete output plan is checked, including the PNG and optional `NAME.mermaid.png`. Symlinked or junction destinations and ancestors, hard-linked destinations, nonregular files, and aliases of another output or a source file are refused (exit 2, `usage:account-chart-path`). Source files include the snapshot, avatar, Mermaid configuration and executable, brand configuration and assets, estate/resolver inputs and the active sign-off file. Configured org marks and standard brand assets remain protected even when an organization or asset is not drawn; changing visibility cannot authorize overwriting a source asset. `capture --out` uses the same check before making any network request. A bad destination preserves every existing artifact; ordinary files in an ordinary directory can be regenerated with identical bytes. Rendering completes in memory before the compositor files are replaced. Destination states are recorded before generation and checked again before publication, so an intervening edit is refused. The shared grouped writer stages replacements and rolls back already replaced leaves if a later replacement fails. This is not a guarantee against process termination, rollback failure or hostile concurrent filesystem replacement. Optional Mermaid rendering uses an internally resolved temporary directory; user-selected output paths retain the strict symlink checks.

## Capture and the snapshot

`capture` runs only GraphQL queries (`scripts/ctshowcase/queries/account_*.graphql`, each checked for a mutation before it runs) through `gh api graphql`, with string variables passed raw (`-f`). It pages every connection (`after` while `hasNextPage`). Enterprises and roles are what GitHub reports for the signed-in viewer, so they are captured only when LOGIN is the viewer (`enterprises:viewer-only` otherwise). An organization the viewer cannot read (SAML enforcement, a removed membership) is kept with `captured: false` and logged `org-uncaptured:<login>`; the chart shows it as "not captured" or "capture failed", never as empty.

`capture` accepts the same resolver inputs as `render` and applies the existing exclusion, HOLD and T3 sign-off gates before reading repository data (`--allow-hold` lets it read HOLD organizations). An explicit refused account makes no request. With no LOGIN, the first query reads only the viewer's login, then applies those gates before any account, organization or enterprise capture. Discovered excluded, placeholder, HOLD or unsigned T3 organizations have no repository queries run. Owner-wide T3 capture needs both `--allow-t3` and an existing valid `*` grant; repository-scoped grants do not authorize an owner-wide query. A later repository withdrawal and exposure flags filter the public repository data before it can be saved. The resolver and sign-off checks run again before continuation requests; there is no separate capture consent policy. Before accepting any repository page, its returned login must be present, pass the same owner gates and match the requested account or organization through the resolver (case-equivalent and registered aliases are accepted). A missing, malformed or mismatched returned identity refuses the entire capture with `usage:capture-identity`, preserving an existing output without logging the rejected identity or repository payload. Discovery queries that do not request a source login/enterprise slug remain compatible, but any supplied source identity is checked on every page. Ordinary transport/connection failures still retain honest partial observations.

The snapshot (`account-chart/v1`, LF JSON) holds `captured` (an absolute date), `viewer`, `account` (login, name, company, location, website), the account's public `repositories`, its `not_public` count, `enterprises` (slug, name, role, organization logins) and `organizations` (login, name, member, role, captured, public `repositories`, `not_public`). A repository is `name`, `description`, `language`, `fork` and `archived`, plus, from captures that read them, `stars` (`stargazerCount`), `code` (bytes per language, from the first 25 languages by size) with `code_other` (the bytes past them), and for a fork its `parent` (`OWNER/NAME`, or null when GitHub reports no upstream). The snapshot's `language_colors` maps each language to GitHub's linguist colour, used where `brand.yaml` `languages` has none. A snapshot without these fields still renders: without sizes the colour key has no percentages and no summary is written (`needs-input:language-sizes`), and without parents every fork counts as external (`needs-input:fork-parents`); capture again to fill them.

New snapshots also carry `coverage` for personal `repositories`, `organizations` membership and `enterprises` membership, plus `capture_status` on each organization and enterprise organization list. Values are `complete`, `uncaptured`, `failed`, `partial` or `unknown`. A failed continuation, missing cursor, repeated cursor, missing connection or mismatched repository count cannot become a complete inventory. Successfully observed pages remain available as partial evidence. Explicitly uncaptured, failed or unknown repository inventories suppress stale repository rows and counts; complete and partial observations remain usable. Legacy missing private-count fields retain their existing interpretation. The existing organization `captured` boolean remains authoritative; `capture_status` explains an incomplete (`false`) flag. Older snapshots remain readable: an organization's `captured: false` means `uncaptured`, and otherwise absent state fields retain the original complete-capture interpretation. Markdown, Mermaid, SVG accessibility text, chart pills and the JSON render report preserve incomplete evidence; counts then describe observed data only, and no uncaptured organization is described as having no public repositories.

**Privacy by construction.** Every connection that returns repository names asks for `privacy: PUBLIC`. Private and internal repositories are counted as `all` minus `public` and never named, so no private name can reach a snapshot, a chart, a fixture or a log. `render` refuses a hand-edited snapshot that marks a repository `private`, `isPrivate` or non-public `visibility` (exit 2, `privacy:not-public-repository`). The snapshot is still the account's own data: keep real snapshots out of fixtures and examples (synthetic stand-ins live in `examples/account-chart/`).

`--allow-hold` applies only to organization lanes and their permitted capture reads. It never releases the root account from HOLD; an explicit or discovered held root still refuses before account data is read or chart files are written. Chart-only holds use the resolver too, including aliases and continuation-page checks.

Owner restrictions are independent across every resolved alias. An organization that is both HOLD and T3 still needs explicit T3 opt-in and a current, applicable sign-off; a HOLD allowance never supplies consent or overrides exclusion. Repository withdrawals are rechecked for both visible repositories and optional fork-parent facts.

The persisted `language_colors` map is built only from retained repository nodes. An exposure-withheld or consent-withdrawn repository cannot add a language or overwrite a permitted language's colour, in either the personal or organization capture lane. Invalid and superseded duplicate repository nodes do not contribute language colours either.

A fork's optional parent fact passes exposure, withdrawal and owner-policy checks before the snapshot is saved. A withheld parent is removed without naming it in logs (`fork-parent-withheld`, `needs-input:fork-parents`). Its upstream ownership remains unknown, so the normal external-fork fallback applies; repeating capture does not bypass the policy.

## What the chart leaves out by default

The chart shows public work. By default `render` leaves out four things, and `--show` brings each back (repeatable):

| Left out by default | `--show` | Log |
|---|---|---|
| An organization with no public repository to show: none at all, only private or internal work, or only repositories a render option hides (`.github`, `--hide forks`, `--hide archived`) | `all-orgs` (its lane then reads "private work" or "no public repositories") | `no-public:<login>` |
| The "private work" pill, and the private and internal counts in the Markdown block | `private-work` | none |
| Repositories named `.github` (organization profile and health repositories) | `.github` | none |
| A fork of a repository outside the account: its upstream (`parent`) belongs to neither the account nor one of the snapshot's organizations, or GitHub reports none. A fork of the account's own or its organizations' repositories stays | `external-forks` | none |

An organization left out contributes nothing to the map's counts. Its omitted repository categories remain available for the count-free Markdown explanation: "no public repositories shown" does not mean the organization has no public repositories. Only an organization whose inventory was completely observed is ever left out: an uncaptured, failed, partial or unknown capture is always shown with its capture state, so a missing capture is never mistaken for an organization without public repositories. A HOLD organization is not on the chart at all unless `--allow-hold` (see the estate gates below). An explicit `--hide forks` names the broader "forks" category for every fork, external or not. An enterprise stays even when none of its organizations has a public repository. The snapshot itself is unchanged: `capture` records every organization, and the choice is made at render time.

## The estate gates

`render` applies the same owner rules as every other command, through the shared resolver (renamed orgs resolve, CQ-03). `capture` applies the corresponding eligibility and sign-off checks before its reads, as described above:

| Owner or repository | In the chart | Log |
|---|---|---|
| The account itself excluded or on HOLD | Refused, nothing written (exit 2) | `exempt`, `hold` |
| Excluded org | Left out | `exempt:<login>` |
| Placeholder (merged) org | Left out | `placeholder:<login>` |
| T3 org without `--allow-t3` and a valid record | Left out | `t3-signoff:<login>` |
| A repository a T3 grant does not cover (a withdrawal) | Not named | `t3-signoff:<owner>/<repo>` |
| HOLD org (owner status, a family with `hold: true`, or the chart's own `chart.hold` list in `brand.yaml`) | Left out entirely; with `--allow-hold` shown like any organization (capture needs `--allow-hold` too, to read its repositories) | `hold:<login>`, `hold-allowed:<login>` |
| Exposure-flagged repository (`decisions.json`) | Not named | `exposure-withheld` (no name, q24) |
| Org without a brand row | Neutral style | `needs-input:org-row:<login>` |
| Org whose family identity is pending | Neutral style, never CompleteTech art | `needs-input:brand-identity:<login>` |

Omitted organizations contribute no numeric map totals. Their repository withholding
checks still produce the applicable gate logs, including the unnamed `exposure-withheld`
decision. A withheld repository does not contribute a `.github`, fork or archive
omission category; those categories describe only records permitted by the estate gates.

With the private registry available (`--registry` or the bundle beside the skill), the Mermaid source, the SVG and the Markdown are also checked with the `lint public-leak` scope before anything is written (exit 1 on a hit).

## Layout

The tree reads top to bottom on the account family's canvas. The header is the account: avatar or monogram, the eyebrow `COMPANY · GITHUB ACCOUNT MAP`, the name, `github.com/<login>` and the profile chips (`profile.chips` in the account's brand row, else the website host, company and location). A trunk drops from the avatar; each child branches off on a rounded elbow to a gold junction:

1. **Personal repositories**, first.
2. **Each enterprise**, in a gold-edged frame with its own gold trunk to its organizations.
3. **Each organization outside an enterprise.**

Every organization is a lane: its card (the family's plate, accent bar, eyebrow and display font; its brand mark or a monogram; an Owner or Member chip when GitHub reports the role) and its public repositories as pills that flow to the right edge and wrap. A pill carries the GitHub linguist colour of the repository's language (a colour too dark to read gets a muted ring), the name in monospace, its stars when it is not a fork and has more than 10 (a gold star drawn as a path and a count such as `128` or `1.2k`), and a fork or archive glyph; archived pills are dimmed. A lane also shows a capture state such as "not captured", and with `--show` "private work" (only where the owner has non-public repositories, never a count) or "no public repositories".

The legend is the chart's colour key: every language a pill's dot shows and every language with at least 1% of the code, each with its share of the code across the repositories the chart names, forks excluded (one decimal, `<0.1%` for a trace), most first; the rest of the code as "Other languages"; "No language" for repositories GitHub assigns none. Under it come only the markers the chart draws (fork, archive, private work, roles) and the brand line.

Older owned configs may omit `chart.labels.no_language` and `chart.labels.other_languages`; their compatible defaults are `No language` and `Other languages`. Explicit nonempty custom labels remain supported.

Order is deterministic: repositories by name (case-insensitive); organizations in family bands (the account's family first, then the families in `brand.yaml` order, then orgs without a family), flagship orgs first, then tier, then display name; enterprises by name. Colours, labels and the Mermaid font come from `brand.yaml` (`chart:` and the family tokens); the scripts hold no colour literals.

The image carries no map counts (S16): the Markdown block states how many repositories are named and withheld (plus the private and internal counts with `--show private-work`), names without counts what the render options leave out ("Not shown: ..."), repeats the colour key's percentages as a sentence, and repeats every repository as a link with its description and star count (S15). These are scoped captured-data display exceptions beside S16 in [svg-rules.md](svg-rules.md), not live measurements or permission to bypass the estate gates.

## The summary SVG

`NAME-summary.svg` closes the README block in the profile intro's design (1280x360, the intro kind): the account's configured mark (otherwise the CompleteTech dark master only for a resolved CompleteTech family association, otherwise the account's monogram) on the family plate, gold circuit traces drawing out from it, the eyebrow and the account's name, and the code's languages as a bar that grows in segment by segment over a key of up to three rows (the smallest languages fold into "Other languages" when they do not fit). Signals travel the traces after the motion settles; `prefers-reduced-motion` shows the settled frame (S20, S21). It is written only when the colour key has shares (`summary-skipped:no-code-shares` otherwise) and when the account's eyebrow and name fit the summary's type ladder; a longer name leaves the summary out with `summary-skipped:type-does-not-fit` while the chart, Mermaid source and Markdown are still written. `--static-summary` writes the settled frame without motion, for a page that already shows an animated intro (S11: one animated asset per page).

When the summary compacts its key, the Markdown retains the original chart share line and adds the actual compacted summary key beside its image. Its image alternative text uses that same compacted key. Segment boundaries are proportional and bounded at SVG precision; very small shares can have zero drawable width, while their names and percentages remain in the key and Markdown.

## The Mermaid source

`NAME.mmd` is the same tree as a `flowchart LR`: the account, each enterprise (a hexagon), the personal repositories and every organization, each with a cluster of repository pills in rows of `chart.mermaid.columns`. Invisible links (`~~~`) build the rows and tie each row to its organization, so the rows keep their alphabetical order; organizations outside an enterprise hang off one "Organizations" hub. Colours are the brand tokens blended on the canvas (Mermaid styles take no alpha); repositories carry their language as the stroke, forks a dashed outline, archived repositories the muted colour. The init directive sets `fontFamily` at the top level (Mermaid ignores it under `themeVariables`) and `wrappingWidth: 600`, so labels stay on one line.

Mermaid refuses a diagram over its default `maxTextSize` (50,000 characters) or `maxEdges` (500, invisible links included); `render` logs `mermaid-size:<bytes>` or `mermaid-edges:<n>` when the source passes either, and still writes it. The compositor SVG and PNG have no such limit.

`--mmdc` draws the source with mermaid-cli (`mmdc` on `PATH`, or the given path) at `--scale`, on the canvas colour, at natural size (`flowchart.useMaxWidth: false`; otherwise mmdc fits the diagram to an 800 px page). `--mmdc-config` is passed as `-p` (puppeteer options, such as a local Chrome `executablePath`). The browser output is not byte-deterministic (`mmdc:not-deterministic`); a missing binary logs `needs-input:mmdc` and a failed run `mmdc-failed`, and neither changes the other outputs. CI's quality job renders every committed `.mmd` with mermaid-cli, including the example.

## Showing it on a profile

Render into the profile repository's checkout and paste or include `NAME.md`: it embeds `NAME.svg` at full width, links it to the HD PNG and lists every repository. The chart is regenerated from a fresh capture; it never edits GitHub. The example in `assets/examples/account-chart-example.*` is rendered from the synthetic snapshot by `examples/render_examples.sh`.
