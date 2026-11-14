# Target formatting and validation

The skill can report the target checkout's formatter configuration and validation
commands. It recognizes `.prettierrc*`, `prettier.config.*`, `.editorconfig`, the
`prettier` key and validation scripts in `package.json`, shell snippets in
`AGENTS.md` and `CONTRIBUTING.md`, including inline code in run instructions,
and workflow `run` steps. This is heuristic discovery, not a complete parser.
Default TSV and Markdown doctor output reports tooling on stderr to preserve the
coverage row; JSON includes it in `tooling`. Reports retain their
source and mark commands **not run**. Discovery never executes these commands;
workflow steps can require secrets or services unavailable in a local checkout.

Formatting is optional: pass `readme --format-generated` or `card --format-generated`. The card command formats its SVG and generated JSON sidecar before writing either one. It uses the target's
already installed Prettier CLI with an exact version in `package.json` or an
exact `node_modules/prettier` version in its npm lockfile. Missing Node.js,
missing or mismatched local dependencies, and unsupported pinning mechanisms
return `needs-input:formatter`. No packages are installed or downloaded and no
package scripts or shell commands are run. Prettier may load the target's own
JavaScript configuration and plugins, so request formatting only for a trusted
checkout. `.editorconfig` detection alone does not select a formatter.

Text is passed on stdin with its final target path, so Prettier uses the target's
configuration. The caller still applies the usual content-preservation and
output-path checks before writing. A formatter failure leaves the requested
output unwritten. Existing authored README content is not silently reformatted
when preservation would reject the changes.
`--format-generated` cannot be combined with `readme --no-regroup`, which promises
to retain exact bytes outside managed blocks. Bootstrap formatting of
`CONTRIBUTING.md` accepts whitespace changes only after the normal owner-token
replacement; any other content change refuses the whole write.
This CLI does not generate `.github/showcase.yml` or `PROMPTS.md`; formatting
those files is outside this head's generator support.

The card SVG budget has two levels: 30,000 bytes is a target that produces an S10
warning, while 40,000 bytes is the hard failure threshold. A warning at 31,307
bytes is not evidence that rendering failed. A synthetic long-slug, long-chip
case currently produces 21,905 bytes and passes the SVG validator; chip layout
also retains its overflow/refusal rules. No budget is raised to hide warnings.

SVG formatting uses Prettier's HTML parser. To include SVGs in a later bare `prettier --check`, declare an override such as `{"overrides":[{"files":"*.svg","options":{"parser":"html"}}]}` in the target Prettier configuration. Other target formatting options continue to apply. The skill does not modify formatter configuration.
