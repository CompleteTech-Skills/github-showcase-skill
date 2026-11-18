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
README has a verified generated tagline with that text, including an already-current
tagline. A matching sentence or legacy sidecar does not authorize replacement of
authored text. Generated taglines carry a receipt over the exact payload after
normalizing only transport line endings. Edited or malformed receipts remain
authored, and a sidecar cannot restore their ownership.
With `--format-generated`, provenance records each final managed body, including
its resealed receipt and payload boundary blank lines, against the source
description. Doctor verifies the actual receipt before interpreting soft wraps;
it does not trim or reconstruct a receipt to make it valid. Exact legacy sidecar
records remain usable for drift checks without granting replacement ownership.
A live refresh clears the staged record only for the refreshed output.
Explicit report and change-record destinations must stay outside the files the
Action commits. The capture, output and provenance destinations must be distinct.
Staged social previews default to `assets/.showcase-staging/social-preview.png`.
An explicit staged path uses a `.showcase-staging` directory outside the
files the Action commits. A checkout's parent directory name does not reserve
its ordinary live preview paths.
A preview's sidecar stays beside the private image outside the canonical Action
artifact group. Reports preserve existing PNG and JPEG files, as well as paths
reserved by a queued live preview. On POSIX, staged provenance, reports and
change records use owner-only file permissions.
`content social --job` requires captured metadata and a live output path outside
that directory. Live social renders record provenance beside the image, so a
staged banner or card cannot overwrite that path even in metadata-only mode.
The default live PNG and JPEG destinations and existing images at the standard
social-preview dimensions also have this protection for older jobs.
An ordinary render replaces the record for each refreshed output with its current
hash and no staged description, while leaving untouched output records intact.
An existing unreadable or invalid sidecar blocks rendering before any artifact is
written (`staged-description:provenance`). Restore the sidecar from a verified
state before retrying; a missing sidecar remains supported for a new output group.
Card PNG previews have their own records. Banner and card records retain the
captured repository ID when available. The sidecar's top-level inputs and
fingerprint describe the latest live canonical banner or card artifact. Each
staged record is written before the associated artifact, so a partial render
remains guarded against automatic publication. When a write fails, outputs
whose bytes stayed unchanged keep their previous records. Before skipping generation,
the Action checks the selected banner and card for current records and matching
artifact hashes in a sidecar with per-output fingerprints. It also checks any existing README record when
README refresh is enabled. Older sidecars retain an `outputs` map and use the
top-level fingerprint for records without their own fingerprint.
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
records before committing and checks the staged Git blobs for proposals and
unrelated index changes. Local
writes to each output group share a sidecar lock. The Action holds that lock
while staging and validating its index snapshot. A partial live refresh
preserves unrelated staged records and cannot authorize their publication.
After a live render is skipped, foreign-art cleanup removes only an artifact
with its own provenance whose bytes and record still match the initial check.
The Action leaves a renderer's abandoned write scratch out of grouped commits.
Recover or remove that scratch manually before retrying the Action in the same checkout.
