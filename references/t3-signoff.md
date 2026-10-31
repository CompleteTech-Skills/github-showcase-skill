# T3 sign-off records (`--allow-t3` needs one)

`--allow-t3` is enforced by default: the tool verifies the operator's claim that a co-owner signed off against a record file. `--require-t3-signoff` is an accepted no-op, kept for compatibility, and changes nothing. There is no opt-out: no flag or environment variable turns the check off. A T3 run therefore needs a valid, unexpired record that covers the owner and, when the record is scoped, the repository.

## Where the file lives

The canonical private path is `<estate_root>/decisions/t3-signoffs.yaml`, where the estate root is `resolver.estate_root()`: `SHOWCASE_ESTATE_ROOT` when set, otherwise the skill's parent bundle. The order is the explicit `--t3-signoff-file PATH`, then `SHOWCASE_T3_SIGNOFF_FILE=PATH`, then the canonical path. When no estate root resolves there is no default path and the refusal is `t3-signoff:no-file` saying so; the flag is never trusted instead. The tool reads the file and never creates it. The records belong in the private estate bundle (issue 24: tracked there, never copied into target repositories). Never copy a record into a repository. Real records come only from the estate bundle; the files under `tests/fixtures/t3-signoff/` are synthetic.

## Format

The contract is [t3-signoff.schema.json](t3-signoff.schema.json). YAML dates are written bare (`2099-12-31`); convert them to ISO strings before validating with a generic JSON Schema validator. `scripts/ctshowcase/signoff.py` checks the same rules (`problems()`): a string date or timestamp must match the schema's `date` or `awareTimestamp` pattern before it is parsed, so compact (`20991231`) and week (`2099-W52-1`) forms are invalid in both. The one deliberate difference is that a pattern-shaped but impossible date (`2099-02-30`) is also invalid in the tool. Tests keep the two in step, including one that applies the schema's patterns without needing `jsonschema`.

```yaml
signoffs:
  - id: t3s-001                # carried onto writer jobs (signoff_id, and approval_id when none is set) and change records (signoff_id)
    owner: Example-Co-Owned    # any login of the org; renamed logins resolve through its aliases
    repos: ["*"]               # "*" (also needed for owner-wide actions), repository names, or OWNER/NAME
    approved: true             # a boolean; only true grants
    approver: example-co-owner # who signed off
    approved_on: 2026-01-15    # the date they signed off (not in the future)
    expires: 2099-12-31        # not before approved_on; a date (valid through that day) or a timestamp with a UTC offset (valid before that instant)
    note: "optional free text"
```

| Field | Required | Rule |
|---|---|---|
| `id` | yes | non-empty string |
| `owner` | yes | non-empty string |
| `repos` | yes | `"*"`, a name, or a non-empty list of names / `OWNER/NAME` |
| `approved` | yes | boolean (`"true"` as a string is invalid) |
| `approver` | yes | non-empty string |
| `approved_on` | yes | date `YYYY-MM-DD`, not later than today (a sign-off that has not happened yet grants nothing) |
| `expires` | no | optional; absent means no expiry. When present: date `YYYY-MM-DD`, or a timestamp with `Z` or `+HH:MM`; a timestamp without an offset is invalid; not earlier than `approved_on` |
| `note` | no | string |

No other fields are allowed. The file itself is an object with the one key `signoffs`, a list of record objects; a top-level list, any other top-level key or a non-object entry makes the whole file authorize nothing (`t3-signoff:missing`), as the schema refuses it.

## Refusals

Each refusal exits 2 with result `refused`.

| Log | Meaning |
|---|---|
| `t3-signoff:no-file` | no record file was found; the log names the resolved path |
| `t3-signoff:missing` | no approved record for the owner (also an unreadable or non-YAML file, or a file whose envelope breaks the schema) |
| `t3-signoff:invalid` | the owner has no usable approved record and a malformed one is the cause (it breaks the schema, has `approved_on` in the future or `expires` before `approved_on`, or `expires` is null or unparseable), or a malformed record would have covered the repository (a `repos` that is not `"*"`, a name or a non-empty list of names is invalid, never `scope`); the error names the record id and the first problem. Two records with one id are also invalid |
| `t3-signoff:scope` | the owner has valid approved records but none covers the repository; an `OWNER/NAME` repository is covered only when that owner is the record's org (only `*` covers another account's repository) |
| `t3-signoff:expired` | every covering record is past `expires` |
| `t3-signoff:revoked` | every otherwise-grantable record was withdrawn by a later or same-day `approved: false` record (see Withdrawal) |

## Withdrawal

The file is append-only, so no edit of the original grant is needed. An `approved: false` record for the same owner, with `approved_on` on or after a grant's `approved_on`, whose `repos` cover the grant's scope (`*`, or every repository the grant names), withdraws that grant, and the refusal is `t3-signoff:revoked`. A false record dated before the grant, or scoped to fewer repositories than the grant covers, does not revoke it. A new `approved: true` record dated after the withdrawal grants again. Grants on distinct scopes are independent, so each keeps its own record id.

Excluded owners (`exempt`) and HOLD owners (`hold`) are refused before the record is read. Repository `doctor` stays read-only: it reports R7 `hold` instead of refusing, and with `--allow-t3` shows the granting record as `signoff_id`.

The owner checked is also the one that holds the repository today: a repository named under one org whose approved pending transfer resolves to a T3 org is gated as that T3 org's (org label jobs, profile home repositories, favorites and star-List items). A T3 org's association carries that org's record id (`signoff_id`; `signoff_ids` lists every id when more than one record applies, for example a star-List item job that adds a T3 repository to a T3 org's List carries the favorite's record and the List org's record): the topics change record of `topics --also-in`, the topics job and change record of `adopt` for a repository whose metadata lists the org in `also_in`, and the `project estate-plan` jobs that put the org in the personal board's Org field (its `orgs` entry shows the id too). A job's existing `approval_id` is kept.
