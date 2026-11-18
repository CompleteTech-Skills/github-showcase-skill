# Target formatting and validation

The skill can report the target checkout's formatter configuration and validation
commands. It recognizes `.prettierrc*`, `prettier.config.*`, `.editorconfig`, the
`prettier` key and validation scripts in `package.json`, shell snippets in
`AGENTS.md` and `CONTRIBUTING.md`, including inline code in run instructions,
and recognizable validation commands from workflow `run` steps. Discovery reads
regular files inside the target checkout and identifies commands by their names
and surrounding instructions.
Default TSV and Markdown doctor output reports tooling on stderr to preserve the
coverage row; JSON includes it in `tooling`. Reports retain their
source category and mark commands **not run**. Package scripts appear by name,
and workflows appear under `.github/workflows`. Instructions and workflow steps
show recognized command prefixes and flags, including simple `&&` chains. Discovery shows exact Prettier
versions and reports other declarations as unsupported without displaying them.
Discovery never executes these commands.

Pass `readme --format-generated`, `banner --format-generated`, or
`card --format-generated` to apply the target's Prettier settings. Use the flag
on both art commands when they update the same JSON sidecar. The banner applies
formatting to the sidecar, and the card applies it to the SVG and the sidecar
before writing either one. These commands use the target's installed Prettier
package with an exact version in `package.json` or an
exact `node_modules/prettier` version in its npm lockfile. Missing Node.js,
missing or mismatched local dependencies, and unsupported pinning mechanisms
return `needs-input:formatter`. No packages are installed or downloaded and no
package scripts or shell commands are run. Prettier may load the target's own
JavaScript configuration and plugins, so request formatting only for a trusted
checkout. Formatter discovery stops at the target checkout. The installed
Prettier applies the target's EditorConfig without inheriting parent settings. Formatted outputs, including an optional PNG preview,
stay within the target checkout.

Text is passed on stdin with its final target path, so Prettier uses the target's
configuration. The caller still applies the usual content-preservation and
output-path checks before writing. A formatter failure leaves the requested
output unwritten. The related files are prepared before any are replaced. If a
replacement fails, Showcase restores earlier files in the group. An explicit
README change record participates in the same write. README and CONTRIBUTING
formatting checks the Markdown AST and repeat-format stability with the pinned
Prettier. GitHub alerts are protected with a Prettier ignore comment on their enclosing
Markdown block, and Showcase refreshes the
ownership digest of a pristine template body after formatting. Verified generated
tagline receipts are similarly resealed after the content check. The receipt
itself must survive unchanged before resealing; an authored or edited tagline
cannot gain ownership through formatting. After exact verification, metadata and
lint ignore empty separator lines around the rendered tagline.
The digest still covers those lines. Wrapping preserves whitespace inside
literal markup and code. These checks happen before any write. Bootstrap
applies the normal CONTRIBUTING owner-token replacement before formatting.
The art sidecar must retain the same typed JSON values and unique keys.
`.github/showcase.yml` supplies input configuration. Format it and author-maintained
files such as `PROMPTS.md` through the target repository's own workflow.

The card SVG budget has two levels: 30,000 bytes is a target that produces an S10
warning, while 40,000 bytes is the hard failure threshold. A warning at 31,307
bytes is not evidence that rendering failed. A synthetic long-slug, long-chip
case passes the SVG validator; chip layout
also retains its overflow/refusal rules. No budget is raised to hide warnings.

SVG formatting uses Prettier's HTML parser when the target supplies no parser override. Showcase compares the output's XML
structure to the original drawing. A Prettier ignore comment preserves the
accessible title. To include SVGs in a later bare `prettier --check`, declare an override such as `{"overrides":[{"files":"*.svg","options":{"parser":"html"}}]}` in the target Prettier configuration. Other target formatting options continue to apply. The skill does not modify formatter configuration.


## Bound output groups

Internal callers that retain `capture_output_bindings(paths)` from their first
preflight can pass that mapping as `bindings=` to `write_formatted_outputs`.
This opt-in mode binds publication, rollback and cleanup to the originally
inspected real directory objects. POSIX uses directory-relative descriptors;
Windows uses native relative-handle acquisition, held directory guards and
handle-relative content mutations.
Unknown destinations, changed originals, links and substituted parents fail
closed. A caller may omit an optional output without adding a new destination.
The existing unbound writer retains its existing behavior.

The writer prepares all bytes before replacing outputs and restores ordinary
partial failures. If another writer replaces a published leaf, it preserves that
leaf and retains recovery backups with an explicit `formatter-rollback` error.
This is not an operating-system multi-file transaction, crash-recovery protocol,
or a guarantee against arbitrary concurrent leaf writers, scratch-entry
substitution between its identity check and removal, or inode reuse during the
capture-to-write interval. Capture handles close before generation. If an
actor renames an original directory, restored bytes remain in that original
directory object; the writer does not reclaim the actor-controlled pathname.
Native Windows behavior requires the Windows test job; POSIX race probes do not
establish Windows runtime evidence.
