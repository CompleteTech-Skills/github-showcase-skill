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
show recognized command prefixes and flags. Discovery shows exact Prettier
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
replacement fails, Showcase restores earlier files in the group. README and CONTRIBUTING formatting requires the pinned
Prettier's Markdown AST check (`--debug-check`) to pass. GitHub alerts are protected with a Prettier ignore comment on their enclosing
Markdown block, and Showcase refreshes the
ownership digest of a pristine template body after formatting. Bootstrap
applies the normal CONTRIBUTING owner-token replacement before formatting.
The art sidecar must retain the same typed JSON values and unique keys.
`.github/showcase.yml` supplies input configuration. Format it and author-maintained
files such as `PROMPTS.md` through the target repository's own workflow.

The card SVG budget has two levels: 30,000 bytes is a target that produces an S10
warning, while 40,000 bytes is the hard failure threshold. A warning at 31,307
bytes is not evidence that rendering failed. A synthetic long-slug, long-chip
case passes the SVG validator; chip layout
also retains its overflow/refusal rules. No budget is raised to hide warnings.

SVG formatting uses Prettier's HTML parser. Showcase compares the output's XML
structure to the original drawing. A Prettier ignore comment preserves the
accessible title. To include SVGs in a later bare `prettier --check`, declare an override such as `{"overrides":[{"files":"*.svg","options":{"parser":"html"}}]}` in the target Prettier configuration. Other target formatting options continue to apply. The skill does not modify formatter configuration.
