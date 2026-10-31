# T3 sign-off records (`--require-t3-signoff`)

`--allow-t3` alone is trust-only: the operator asserts that a co-owner signed off. The opt-in global `--require-t3-signoff` (or `SHOWCASE_REQUIRE_T3_SIGNOFF=1`; default off) makes the tool verify that claim against a record file. Without the flag nothing here applies and `--allow-t3` behaves as before.

## Where the file lives

Pass the file explicitly: the global `--t3-signoff-file PATH`, or `SHOWCASE_T3_SIGNOFF_FILE=PATH`. **There is no default location.** The records belong in the private estate bundle (issue 24: tracked there, never copied into target repositories), but the canonical path inside the bundle is still the maintainer's choice. Until it is chosen, the tool never picks a file on its own, and `--require-t3-signoff` without a file refuses with `t3-signoff:no-file`. Real records come only from the estate bundle; the files under `tests/fixtures/t3-signoff/` are synthetic.

## Open maintainer decisions (not resolved by this change)

- **Default off.** Enforcement is opt-in (`--require-t3-signoff`) because a behaviour-changing default stays off unless the issue says otherwise and no maintainer has asked for default-on. Flipping the default is a follow-up decision for #23 and #25; until it is recorded, a run without the flag is still trust-only.
- **Canonical file path (#24, "Choose file path").** Not chosen: this is deferred to the maintainer, so the subtask stays open and the issue PR should not claim it. A record file given without `--require-t3-signoff` is never read; the run logs `t3-signoff:file-ignored` (and prints it on stderr in text mode) instead of looking enforced.

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
| `t3-signoff:no-file` | the flag is on but no record file was given |
| `t3-signoff:missing` | no approved record for the owner (also an unreadable or non-YAML file, or a file whose envelope breaks the schema) |
| `t3-signoff:invalid` | the owner has records but every one breaks the schema; the error names the record id and the first problem |
| `t3-signoff:scope` | the owner has valid approved records but none covers the repository |
| `t3-signoff:expired` | every covering record is past `expires` |

Excluded owners (`exempt`) and HOLD owners (`hold`) are refused before the record is read. Repository `doctor` stays read-only: it reports R7 `hold` instead of refusing, and under the flag shows the granting record as `signoff_id`.

Under `--require-t3-signoff` only, the owner checked is also the one that holds the repository today: a repository named under one org whose approved pending transfer resolves to a T3 org is gated as that T3 org's (org label jobs, profile home repositories, favorites and star-List items). Without the flag those cases behave as before. A T3 org's association carries that org's record id (`signoff_id`; `signoff_ids` lists every id when more than one record applies): the topics change record of `topics --also-in`, the topics job and change record of `adopt` for a repository whose metadata lists the org in `also_in`, and the `project estate-plan` jobs that put the org in the personal board's Org field (its `orgs` entry shows the id too). A job's existing `approval_id` is kept.
