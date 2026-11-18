# Account chart

`account-chart` maps one GitHub account as a single tree: the repositories it owns, each enterprise it owns or belongs to, each organization inside or outside an enterprise, and every public repository of each organization. It is a showcase surface in the estate's dark design, judged with the rest of the set (decision 10).

| Output | What it is |
|---|---|
| `NAME.mmd` | The tree as a themed Mermaid `flowchart LR`, ready for a README or GitHub's native `.mmd` view, and for mermaid-cli. |
| `NAME.svg` | The compositor render: the same tree in the banner and card design, outlined text, GitHub-safe (`lint svg --kind chart`). |
| `NAME.png` | The same scene rasterized at `--scale` (2 by default): the high-definition picture. |
| `NAME.md` | The README block: the image (linking to the PNG), the counts the image leaves out, and every repository as a link. |
| `NAME.mermaid.png` | Only with `--mmdc`: the Mermaid source drawn by mermaid-cli at natural size. |

## Commands

```bash
S=<skill-dir>/scripts/showcase.py
python3 $S account-chart capture-query                     # print the read-only reads; no network
python3 $S account-chart capture --out account.snapshot.json  # the signed-in account (or pass a LOGIN)
python3 $S account-chart render --snapshot account.snapshot.json --out-dir docs/images
python3 $S lint svg --kind chart docs/images/account-chart.svg
```

`render` options: `--name` (file stem, default `account-chart`; a `-dark`/`-light` stem is refused, decision 21), `--width` (1600–4800 px, default 2400; the height follows the account), `--scale 1|2|3|4` (PNG pixels per px; lowered automatically above 120 megapixels and logged `png-scale:<n>`), `--hide forks` and `--hide archived`, `--private note|omit`, `--avatar PATH` (the account's picture; default its brand mark, else a monogram), `--no-png`, `--mmdc [PATH]` with `--mmdc-config FILE`, and the resolver inputs `--registry`, `--decisions`, `--approved`, `--approved-yaml` and `--actions`. The global `--allow-t3` (or `--allow-t3` after the command) admits T3 orgs that have a valid sign-off record.

The resolver inputs `--registry`, `--approved`, `--approved-yaml` and `--actions`
also apply to `capture`. T3 reads require both `--allow-t3` and a valid applicable
sign-off record; a flag alone grants nothing.

## Capture and the snapshot

`capture` runs only GraphQL queries (`scripts/ctshowcase/queries/account_*.graphql`, each checked for a mutation before it runs) through `gh api graphql`, with string variables passed raw (`-f`). It pages every connection (`after` while `hasNextPage`). Enterprises and roles are what GitHub reports for the signed-in viewer, so they are captured only when LOGIN is the viewer (`enterprises:viewer-only` otherwise). An organization the viewer cannot read (SAML enforcement, a removed membership) is kept with `captured: false` and logged `org-uncaptured:<login>`; the chart shows it as "not captured", never as empty.

The snapshot (`account-chart/v1`, LF JSON) holds `captured` (an absolute date), `viewer`, `account` (login, name, company, location, website), the account's public `repositories`, its `not_public` count, `enterprises` (slug, name, role, organization logins) and `organizations` (login, name, member, role, captured, public `repositories`, `not_public`). A repository is `name`, `description`, `language`, `fork` and `archived`.

Capture evidence stays explicit. Optional `capture_state` values are `complete`,
`partial`, `uncaptured` and `unknown`; the root also records `organizations_state`
and `enterprises_state`, and each enterprise can record its membership
`capture_state`. Interrupted pagination retains partial evidence. Missing private
or internal counts are `null`, never an observed zero. Legacy snapshots retain
their explicit capture flags; an organization without a known capture flag is
unknown. The model, Markdown, Mermaid, SVG labels/descriptions and render JSON
`coverage` report retain these distinctions. Uncaptured or unknown lanes neither
name stale repositories nor claim that no public repositories exist.

**Privacy by construction.** Every connection that returns repository names asks for `privacy: PUBLIC`. Private and internal repositories are counted as `all` minus `public` and never named, so no private name can reach a snapshot, a chart, a fixture or a log. `render` refuses a hand-edited snapshot that marks a repository `private`, `isPrivate` or non-public `visibility` (exit 2, `privacy:not-public-repository`). The snapshot is still the account's own data: keep real snapshots out of fixtures and examples (synthetic stand-ins live in `examples/account-chart/`).

## The estate gates

`capture` checks an explicit account before any API read, checks the default
viewer immediately after identifying its login, and checks every discovered
organization before reading its repositories. Exclusions, aliases, HOLD and T3
sign-off use the shared resolver. Restricted repository rows are withheld before
snapshot publication. Permitted unregistered accounts retain neutral behavior.

`render` applies the same owner rules through that resolver (renamed orgs resolve, CQ-03):

| Owner or repository | In the chart | Log |
|---|---|---|
| The account itself excluded or on HOLD | Refused, nothing written (exit 2) | `exempt`, `hold` |
| Excluded org | Left out | `exempt:<login>` |
| Placeholder (merged) org | Left out | `placeholder:<login>` |
| T3 org without `--allow-t3` and a valid record | Left out | `t3-signoff:<login>` |
| A repository a T3 grant does not cover (a withdrawal) | Not named | `t3-signoff:<owner>/<repo>` |
| HOLD org (owner status or family `hold`) | Shown, its repositories not named ("on hold") | `hold:<login>` |
| Exposure-flagged repository (`decisions.json`) | Not named | `exposure-withheld` (no name, q24) |
| Org without a brand row | Neutral style | `needs-input:org-row:<login>` |
| Org whose family identity is pending | Neutral style, never CompleteTech art | `needs-input:brand-identity:<login>` |

With the private registry available (`--registry` or the bundle beside the skill), the Mermaid source, the SVG and the Markdown are also checked with the `lint public-leak` scope before anything is written (exit 1 on a hit).

Every selected output is preflighted before generation or capture. Symlinked
ancestors or leaves, nonregular files, hardlinks, collisions between outputs, and
aliases of snapshots, avatars, configuration or policy inputs are refused without
writing. Outputs are prepared together and published through the shared rollback
transaction; a generation or commit failure preserves previous output bytes.
Optional Mermaid rendering runs in temporary staging before publication.

## Layout

The tree reads top to bottom on the account family's canvas. The header is the account: avatar or monogram, the eyebrow `COMPANY · GITHUB ACCOUNT MAP`, the name, `github.com/<login>` and the profile chips (`profile.chips` in the account's brand row, else the website host, company and location). A trunk drops from the avatar; each child branches off on a rounded elbow to a gold junction:

1. **Personal repositories**, first.
2. **Each enterprise**, in a gold-edged frame with its own gold trunk to its organizations.
3. **Each organization outside an enterprise.**

Every organization is a lane: its card (the family's plate, accent bar, eyebrow and display font; its brand mark or a monogram; an Owner or Member chip when GitHub reports the role) and its public repositories as pills that flow to the right edge and wrap. A pill carries the GitHub linguist colour of the repository's language (a colour too dark to read gets a muted ring), the name in monospace, and a fork or archive glyph; archived pills are dimmed. A lane also shows "private work" (only where the owner has non-public repositories, and never a count; `--private omit` drops it), "no public repositories", "on hold" or "not captured".

Order is deterministic: repositories by name (case-insensitive); organizations in family bands (the account's family first, then the families in `brand.yaml` order, then orgs without a family), flagship orgs first, then tier, then display name; enterprises by name. Colours, labels and the Mermaid font come from `brand.yaml` (`chart:` and the family tokens); the scripts hold no colour literals.

The image carries no counts (S16): the Markdown block states how many repositories are named, counted, withheld or hidden, and repeats every repository as a link with its description (S15).

## The Mermaid source

`NAME.mmd` is the same tree as a `flowchart LR`: the account, each enterprise (a hexagon), the personal repositories and every organization, each with a cluster of repository pills in rows of `chart.mermaid.columns`. Invisible links (`~~~`) build the rows and tie each row to its organization, so the rows keep their alphabetical order; organizations outside an enterprise hang off one "Organizations" hub. Colours are the brand tokens blended on the canvas (Mermaid styles take no alpha); repositories carry their language as the stroke, forks a dashed outline, archived repositories the muted colour. The init directive sets `fontFamily` at the top level (Mermaid ignores it under `themeVariables`) and `wrappingWidth: 600`, so labels stay on one line.

Mermaid refuses a diagram over its default `maxTextSize` (50,000 characters) or `maxEdges` (500, invisible links included); `render` logs `mermaid-size:<bytes>` or `mermaid-edges:<n>` when the source passes either, and still writes it. The compositor SVG and PNG have no such limit.

`--mmdc` draws the source with mermaid-cli (`mmdc` on `PATH`, or the given path) at `--scale`, on the canvas colour, at natural size (`flowchart.useMaxWidth: false`; otherwise mmdc fits the diagram to an 800 px page). `--mmdc-config` is passed as `-p` (puppeteer options, such as a local Chrome `executablePath`). The browser output is not byte-deterministic (`mmdc:not-deterministic`); a missing binary logs `needs-input:mmdc` and a failed run `mmdc-failed`, and neither changes the other outputs. CI's quality job renders every committed `.mmd` with mermaid-cli, including the example.

## Showing it on a profile

Render into the profile repository's checkout and paste or include `NAME.md`: it embeds `NAME.svg` at full width, links it to the HD PNG and lists every repository. The chart is regenerated from a fresh capture; it never edits GitHub. The example in `assets/examples/account-chart-example.*` is rendered from the synthetic snapshot by `examples/render_examples.sh`.
