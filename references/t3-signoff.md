# T3 sign-off records (`--require-t3-signoff`)

`--allow-t3` is enforced by default. The tool requires `--require-t3-signoff` to be on (it is on by default) and verifies the operator's claim that a co-owner signed off against a record file. A T3 run therefore needs a valid, unexpired record that covers the owner and, when the record is scoped, the repository.

## Where the file lives

The canonical private path is `<estate_root>/decisions/t3-signoffs.yaml`, where the estate root is `resolver.estate_root()`: `SHOWCASE_ESTATE_ROOT` when set, otherwise the skill's parent bundle. An explicit `--t3-signoff-file PATH` or `SHOWCASE_T3_SIGNOFF_FILE=PATH` overrides the canonical path. The records belong in the private estate bundle (issue 24: tracked there, never copied into target repositories). Never copy a record into a repository. Real records come only from the estate bundle; the files under `tests/fixtures/t3-signoff/` are synthetic.

## Format

The contract is [t3-signoff.schema.json](t3-signoff.schema.json). YAML dates are written bare (`2099-12-31`); convert them to ISO strings before validating with a generic JSON Schema validator. `scripts/ctshowcase/signoff.py` checks the same rules (`problems()`): a string date or timestamp must match the schema's `date` or `awareTimestamp` pattern before it is parsed, so compact (`20991231`) and week (`2099-W52-1`) forms are invalid in both. The one deliberate difference is that a pattern-shaped but impossible date (`2099-02-30`) is also invalid in the tool. Tests keep the two in step, including one that applies the schema's patterns without needing `jsonschema`.

```yaml
signoffs:
  - id: t3s-001                # carried onto writer jobs (signoff_id, and approval_id when none is set) and change records (signoff_id)
    owner: Example-Co-Owned    # any login of the org; renamed logins resolve through its aliases
    repos: ["*"]               # "*" (also needed for owner-wide actions), repository names, or OWNER/NAME
    approved: true             # a boolean; only true grants
    approver: example-co-owner # who signed off
    approved_on: 2026-01-15    # the date they signed off
    expires: 2099-12-31        # a date (valid through that day) or a timestamp with a UTC offset (valid before that instant)
    note: "optional free text"
```

| Field | Required | Rule |
|---|---|---|
| `id` | yes | non-empty string |
| `owner` | yes | non-empty string |
| `repos` | yes | `"*"`, a name, or a non-empty list of names / `OWNER/NAME` |
| `approved` | yes | boolean (`"true"` as a string is invalid) |
| `approver` | yes | non-empty string |
| `approved_on` | yes | date `YYYY-MM-DD` |
| `expires` | yes | date `YYYY-MM-DD`, or a timestamp with `Z` or `+HH:MM`; a timestamp without an offset is invalid |
| `note` | no | string |

No other fields are allowed. The file itself is an object with the one key `signoffs`, a list of record objects; a top-level list, any other top-level key or a non-object entry makes the whole file authorize nothing (`t3-signoff:missing`), as the schema refuses it.

## Refusals

Each refusal exits 2 with result `refused`.

| Log | Meaning |
|---|---|
| `t3-signoff:no-file` | no record file was found; the log names the resolved path |
| `t3-signoff:missing` | no approved record for the owner (also an unreadable or non-YAML file, or a file whose envelope breaks the schema) |
| `t3-signoff:invalid` | the owner has records but every one breaks the schema; the error names the record id and the first problem |
| `t3-signoff:scope` | the owner has valid approved records but none covers the repository |
| `t3-signoff:expired` | every covering record is past `expires` |

Excluded owners (`exempt`) and HOLD owners (`hold`) are refused before the record is read. Repository `doctor` stays read-only: it reports R7 `hold` instead of refusing, and under the flag shows the granting record as `signoff_id`.

The owner checked is also the one that holds the repository today: a repository named under one org whose approved pending transfer resolves to a T3 org is gated as that T3 org's (org label jobs, profile home repositories, favorites and star-List items). A T3 org's association carries that org's record id (`signoff_id`; `signoff_ids` lists every id when more than one record applies): the topics change record of `topics --also-in`, the topics job and change record of `adopt` for a repository whose metadata lists the org in `also_in`, and the `project estate-plan` jobs that put the org in the personal board's Org field (its `orgs` entry shows the id too). A job's existing `approval_id` is kept.
