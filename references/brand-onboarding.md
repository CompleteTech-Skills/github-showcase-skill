# Add a family and organization locally

`brand` scaffolds a dark family palette and an organization row in the selected
brand configuration. It makes no GitHub requests or changes. Use a local copy of
the installed skill and an explicitly selected config. Start with the dry run;
`--write` writes that config and the adjacent `brand.lock.json`. Existing families,
organization names, aliases and reserved owners cannot be replaced or reclassified.
Both the installed brand mapping and the selected configuration protect their
known identities and refusal policies. Omitting installed rows from an external
configuration cannot reclassify them. These lookups do not discover private
estate registry or approval files.

A synthetic example adds both rows with one command:

```bash
python scripts/showcase.py --config references/brand.yaml brand add-family \
  --name northwind-new --label 'Northwind New' \
  --canvas '#101820' --ink '#F5F5F5' --accent '#FFB81C' \
  --org Northwind-New --tier T2 --display-name 'Northwind New' --footer no
```

Review the JSON `proposed` rows, then repeat with `--write`. To add another org to
that family:

```bash
python scripts/showcase.py --config references/brand.yaml brand add-org \
  --family northwind-new --org Northwind-Team --tier T2 \
  --display-name 'Northwind Team' --footer no --write
```

`--tier`, `--display-name` and `--footer yes|no|hold` must be explicit whenever an
org is added. The command does not infer ownership, legal wording, approvals or a
CompleteTech affiliation. A T3 org is added to the refusal list; co-owner sign-off
is still required by the usual consent gate. No sign-off record is created.

Add `--mark path/to/authorized-mark.png` to either command to copy a valid PNG,
byte for byte, to `assets/orgs/ORG/mark.png` under the config's package root (the
parent of `references/`). The selected config's package-local asset takes precedence when present; bundled
fonts and fallback assets remain available from the installed skill. Existing
assets are never overwritten. Both PNG structure and pixel decoding are validated
before any writes; validation does not modify the copied bytes. Use only artwork
you are authorized to keep in this package. No asset is downloaded, cropped,
recoloured or published. Chunk checksums and decoded pixels must be valid; Pillow's
oversized-image warning and error limits are refused before pixel decoding. Invalid
marks return a controlled configuration error before any output is written.
Without a mark, existing family wordmark fallback behavior
applies; this is not a repository icon.

The palette requires six-digit hex values. The canvas must be dark. Text and chip
foregrounds meet 4.5:1 contrast; optional `--icon-ink` and `--icon-spark` must also
meet 4.5:1 on the derived icon-card ground. Other tokens derive from those inputs,
so a new family does not inherit CompleteTech colours. Fonts use the installed
package's defaults. Schema validation and UTF-8 JSON lock serialization complete
before writing, existing config comments and unrelated rows are retained, and the
lock is regenerated from the same validated data. Schema-valid YAML values that
JSON cannot represent (such as an unquoted date in an extra field) are refused
without changing the configuration, lock or mark; quote the value if it is meant
to be text before retrying.

Existing configuration and lock files must be writable regular files before any
output is created. If a later write fails, restoration of the configuration,
lock and newly copied mark is attempted independently. A restoration failure is
reported explicitly; it does not prevent cleanup of the other outputs.

A generated family remains `measured: false`: automated contrast checks do not
certify the artwork. Render with `--allow-unmeasured` for review, inspect the set,
and record the appropriate decision before marking the palette measured. This
command supplies no license wording, topic vocabulary or repository facts; those
remain explicit follow-up inputs. Generation and review do not authorize rollout.
For an organization's `.github` repository without a configured `brand_topic`,
`topics` preserves existing topics, suggests the known `github-profile` type and
logs `needs-input:brand-topic`; it never substitutes a CompleteTech affiliation.
The command exits 4 and emits no topic command or change record until that input
is supplied. `adopt` holds the topic job with a pending-input step, while `doctor`
reports R3 as `hold`. Existing explicitly configured brand topics continue to apply.
