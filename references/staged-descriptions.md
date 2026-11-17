# Staged descriptions

Pass `--description "A reviewed sentence."` to `banner`, `card`, `content social`
or `readme` to render from that proposal without changing the captured metadata
file or GitHub's About text. The hidden `social-preview` alias accepts the same
option. An empty or multiline value, or a value containing a managed README
marker, returns `needs-input:description`.

The command reports `staged-description` and the proposed text, its SHA-256 and
the captured live description's SHA-256. Art renderers use the proposal for
type detection and as the description input. README rendering uses the proposal
only in the managed tagline. For banners, an explicit or
configured subtitle takes precedence. Follow the normal description check and
the orchestrator's writer queue to approve the sentence for publication.

Each staged artifact has its own `staged_description` record in
`docs/images/.showcase.json`. Records for other outputs are retained, so rendering
only the card does not claim the banner was refreshed. For explicit output paths
outside the target checkout, the sidecar is placed beside that output; metadata-only
rendering uses that location too. README dry runs report the proposal without
writing a sidecar. `readme --write` records the proposal when the resulting
README has a managed tagline with that text, including an already-current tagline.
Explicit report and change-record destinations must stay outside the files the
Action commits. The capture, output and provenance destinations must be distinct.
Staged social previews default to `assets/.showcase-staging/social-preview.png`.
An explicit staged path must also be inside a `.showcase-staging` directory.
`content social --job` requires captured metadata and a live output path outside
that directory. Staging a preview leaves previously queued live files intact.
An ordinary render replaces the record for each refreshed output with its current
hash and no staged description, while leaving untouched output records intact.
Card PNG previews have their own records. Banner and card records retain the
captured repository ID when available. The sidecar's top-level inputs and
fingerprint describe the latest live canonical banner or card artifact. Each
staged record is written before the associated artifact, so a partial render
remains guarded against automatic publication. Before skipping generation,
the Action checks the selected banner and card for current records and matching
artifact hashes in a sidecar with per-output fingerprints. It also checks any existing README record when
README refresh is enabled. Older sidecars use the top-level fingerprint.
Canonical art with a stable exemption can cache that decision when no artifact
is present. Other selected art without a record is rechecked on the next run.

`doctor` compares each managed tagline block with what `readme` would write for the
live description in the supplied metadata (`readme.tagline_body`, the one place that
decides the tagline format, in any variant's form). A mismatch fails R2 and logs
`description-drift:readme`, even if the live sentence also appears somewhere else in
the document. Code examples are ignored. This is a local comparison, so capture
current metadata before relying on it. The existing R7 check still handles an absent
or unmanaged tagline.

When the live description is empty, `readme` preserves an authored tagline and
logs `needs-input:description`. `doctor` still reports drift if the current
managed tagline matches the recorded staged tagline digest, even after edits
elsewhere in the README. Upgrades for variants G (fork) and H (archive) write a callout.
`doctor` also checks any managed tagline those upgrades preserve.

The composite Action checks the canonical, nested art and root sidecars for staged
records before committing. Local writes to each output group share a sidecar lock. A partial live refresh preserves unrelated staged records and cannot authorize their publication.
