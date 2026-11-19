# Use it for your own brand

`github-showcase-skill` works for any GitHub user, organization or Enterprise. It is made by CompleteTech LLC, and
the configuration it ships with (`references/brand.yaml`, `references/enterprise.yaml`) is CompleteTech's own
estate. That configuration is also the worked example: copy its shape, not its values.

## Two roles, never mixed

| Role | What it is | Where it comes from | Who it names |
|---|---|---|---|
| Skill attribution | Who made the tool: the `showcase:credit` block (*README styled with github-showcase-skill by CompleteTech LLC · Get the skill*), the hidden `generated-by` marker, the install link, the star line, the optional `github-showcase-skill` topic, the provenance stamp's `skill`/`skill_url`/`publisher`, and the package metadata | the `attribution:` block of the brand config | CompleteTech LLC, on every target |
| Target identity | Who owns the repository: logo, eyebrow, company label, palette, footer, brand topic, org profile wording, X handle, steward line, board titles, repository template, Enterprise desired state | your brand config (`--config FILE`) and your estate root (`SHOWCASE_ESTATE_ROOT`) | you |

Keep the `attribution:` block as it is in your copy. Everything else in the config describes you.

## What you get before you configure anything

An owner with no row in the selected brand config borrows none of CompleteTech's identity:

- **Banner, repo card and social preview** render in the neutral style (the `chart.neutral` tokens) under the
  owner's own login, with a wordmark where a logo would go. Alt text names the owner.
- **README** gets the owner's own nav line, `Organization: OWNER` under Ownership, no decision 18 footer
  (`exempt:footer`), and the skill credit as its last block.
- **Topics** propose no brand topic (`needs-input:brand-topic`).
- **`new OWNER/NAME`** needs `--template OWNER/REPO` (`needs-input:template`).
- **Org profile, About and Projects** lines that need your own wording are withheld with `needs-input:<field>`
  (for example `needs-input:x-handle`, `needs-input:operator-login`, `needs-input:projects-reference`) instead of
  printing CompleteTech's.

That is enough to try the generators on your own repositories. Configure your brand when you want your own look.

## 1. Make your own config

Copy the shipped config somewhere outside this checkout and pass it with `--config` on every command:

```bash
mkdir -p ~/my-estate && cp references/brand.yaml ~/my-estate/brand.yaml
```

## 2. Add your families and organizations, then remove ours

`brand add-family` derives a dark palette from a canvas, ink and accent colour and can add the first org;
`brand add-org` adds another org to an existing family. Both validate before writing, keep your comments and write
the lock beside your config. See [brand-onboarding.md](brand-onboarding.md) for the contrast rules, marks and
`--write`.

```bash
python scripts/showcase.py --config ~/my-estate/brand.yaml brand add-family --name octocat --label "Octocat Labs"   --canvas "#0D1117" --ink "#E6EDF3" --accent "#2F81F7" --org octocat-labs --tier T1   --display-name "Octocat Labs" --footer no --write
```

Add your own rows first: `families` and `orgs` must stay non-empty block mappings for onboarding to append to them.
Then, in your copy:

1. Delete CompleteTech's `families` and `orgs` rows, empty the `owners` lists, and replace or remove the
   `operator:` values (next section).
2. Replace `brand_strings` (company, short name, tagline, website), `brand_assets` and the `footer` block with your
   own, or keep `footer: no` on your org rows if you do not want a footer at all.
3. Keep `attribution:` unchanged.
4. Re-run `python scripts/showcase.py --config ~/my-estate/brand.yaml config --write-lock` after every edit. The
   lock goes beside your config as `brand.lock.json`, never over the shipped one.

A new family stays `measured: false` until you review its renders: pass `--allow-unmeasured` to `banner`, `card`
and the other generators while you review. Add `brand_topic`, `license_wording` and, for repository icons, an `art:`
block to your rows when you have them; until then the matching outputs say `needs-input`.

## 3. Name yourself as the operator

The `operator:` block says whose estate the config describes. Every value is optional; a missing one is withheld,
never filled from CompleteTech's.

| Key | Used for |
|---|---|
| `login` | your own user account: the steward account, `org profile --user`, star lists, Projects user boards |
| `repo_template`, `repo_template_title` | the `new` default `--template`, and the template README H1 that `readme --bootstrap` replaces |
| `steward.name`, `steward.email` | the contact line of Projects board READMEs |
| `projects.*` | the reference board, template owner, and Estate board names, titles and wording (`project` commands) |
| `profile.*` | your own `family`, affiliation sentences, private-org line, X handle, directory badge and "Also from" heading (`org profile`, `org about`) |

Family rows can also carry `owner_login` (the README Ownership line) and org rows `skill_library` (a skills
catalog org). CompleteTech's values in the shipped `references/brand.yaml` show every field filled in.

## 4. Create your private estate root

The `org about`, `org profile`, `org pins` and `project` commands read a private registry of your organizations.
Start from the synthetic example and keep the copy private (never commit it to a repository):

```bash
cp -r examples/estate ~/my-estate/bundle
# edit ~/my-estate/bundle/registry/estate.yaml: your orgs, tiers, final_repos, pins and profile text
# (the example's profile text describes CompleteTech's Northwind demo: replace all of it)
export SHOWCASE_ESTATE_ROOT=~/my-estate/bundle
python scripts/showcase.py --config ~/my-estate/brand.yaml org about octocat-labs --meta-dir ~/my-estate/meta
```

`examples/estate/` shows the layout: `registry/estate.yaml` (orgs, pins, profile, star lists),
`decisions/approved.tsv` (approvals) and `meta/` (captured repository metadata). Approvals stay yours to grant;
the skill never invents one. Without a registry, org commands that need it stop with `needs-input:registry`.

## 5. Enterprises

`references/enterprise.yaml` is CompleteTech's Enterprise desired state. `enterprise snapshot`, `doctor` and `diff`
read any Enterprise you administer. Do not act on `enterprise plan` or a bare `enterprise seat-check` for another
Enterprise: both compare against CompleteTech's desired state, so treat their output as informational only. Pass
`--user` to `seat-check` explicitly. A separate desired-state file for other Enterprises is tracked in
[#209](https://github.com/CompleteTech-Skills/github-showcase-skill/issues/209) (item 5).

## 6. Run it

Use [full-run-prompt.md](full-run-prompt.md) with `<BRAND_CONFIG>` set to your config and `<ESTATE_ROOT>` set to
your bundle. The skill stays read-only toward GitHub: it prints files, plans and writer jobs, and you decide what is
applied.
