#!/usr/bin/env bash
# Regenerate every committed example in assets/examples/ from public or synthetic metadata only (spec A9.1).
# Usage: bash examples/render_examples.sh   (from the skill root, with requirements.txt installed; the optional
# resvg_py package adds the intro's static frame to the contact sheet)
set -euo pipefail
cd "$(dirname "$0")/.."
S="${PYTHON:-python3} scripts/showcase.py"
O=assets/examples
F=tests/fixtures/meta
mkdir -p "$O"
rm -f "$O"/contact-sheet-*.png "$O"/*.on-github-*.png

# Synthetic Northwind Trading Co. fixtures (STANDARD §1.2 fictional client). Its checkout sets a one-line subtitle in
# .github/showcase.yml: the full description does not fit the banner on one line.
$S --meta examples/meta/northwind-support-triage-agent.json --repo-dir examples/repos/northwind-support-triage-agent \
   banner --out "$O/banner-example.png"
$S --meta examples/meta/northwind-support-triage-agent.json --repo-dir examples/repos/northwind-support-triage-agent \
   card --out "$O/card-example.svg" --png "$O/card-example.png"
$S --meta examples/meta/northwind-support-triage-agent.json --repo-dir examples/repos/northwind-support-triage-agent \
   content social --out "$O/social-preview-example.png" >/dev/null
$S --meta examples/meta/northwind-cve-2026-00001-check.json --no-repo-dir \
   card --out "$O/card-northwind-cve-check.svg" --png "$O/card-northwind-cve-check.png"

# Public repositories (read-only `meta --from-gh` captures in tests/fixtures/meta)
# php2shell-check as the skill derives it today (the Security org's Neon Night mark until the repository has its own
# icon), and in the golden's own configuration (the full logo on the white card) for the layout comparison.
$S --meta "$F/CompleteTech-Security__php2shell-check.json" --repo-dir examples/repos/php2shell-check \
   banner --out "$O/banner-php2shell.png"
$S --meta "$F/CompleteTech-Security__php2shell-check.json" --repo-dir examples/repos/php2shell-check \
   banner --icon assets/brand/logo.png --out "$O/banner-php2shell-golden.png"
$S --meta "$F/CompleteTech-Security__php2shell-check.json" --repo-dir examples/repos/php2shell-check \
   card --out "$O/card-php2shell.svg" --png "$O/card-php2shell.png"
# agentic-email-skill: its description's head does not fit one line, so the example passes the subtitle the
# repository should set in its .github/showcase.yml.
$S --meta "$F/CompleteTech-Skills__agentic-email-skill.json" --no-repo-dir \
   banner --subtitle "Draft sales and lifecycle email sequences as branded PDFs" --out "$O/banner-agentic-email-skill.png"
$S --meta "$F/CompleteTech-Skills__agentic-email-skill.json" --no-repo-dir \
   card --out "$O/card-agentic-email-skill.svg" --png "$O/card-agentic-email-skill.png"
$S --meta "$F/jevplay-games__jev-minesweeper.json" --repo-dir examples/repos/jev-minesweeper \
   banner --out "$O/banner-jev-minesweeper.png"
$S --meta "$F/jevplay-games__jev-minesweeper.json" --repo-dir examples/repos/jev-minesweeper \
   card --out "$O/card-jev-minesweeper.svg" --png "$O/card-jev-minesweeper.png"
$S --meta "$F/CompleteTech-Security__netscaler-cve-2026-19489-check.json" --no-repo-dir \
   banner --out "$O/banner-netscaler-cve-2026-19489-check.png"
$S --meta "$F/CompleteTech-LLC-AI-Research__ai-self-replication-study.json" --no-repo-dir \
   banner --out "$O/banner-ai-self-replication-study.png"
# A T2 family without an icon or approved mark: its wordmark on the family's dark plate (palette not yet measured).
$S --meta "$F/Jev-Engineering__TypeCheck.json" --no-repo-dir \
   banner --allow-unmeasured --out "$O/banner-jev-engineering-typecheck.png"
$S --meta "$F/Jev-Engineering__TypeCheck.json" --no-repo-dir \
   card --allow-unmeasured --out "$O/card-jev-engineering-typecheck.svg" --png "$O/card-jev-engineering-typecheck.png"

# Org tile, org banner, profile intro, footer
$S org-tile --org CompleteTech-Skills --avatar examples/orgs/CompleteTech-Skills/avatar-500.png --out "$O/org-tile-example.svg" --png "$O/org-tile-example.png"
$S org-banner --org CompleteTech-Skills --out "$O/org-banner-example.jpg"
$S intro --profile CompleteDotTech --out "$O/intro-example.svg"
$S --format json footer --raw > "$O/footer-example.md"

# README scaffold for the synthetic CLI repo (dry run captured as the resulting file)
tmp="$(mktemp -d)"; cp -r examples/repos/northwind-support-triage-agent/. "$tmp/"
$S --meta examples/meta/northwind-support-triage-agent.json --repo-dir "$tmp" readme --mode scaffold --write > /dev/null
cp "$tmp/README.md" "$O/readme-example.md"; rm -rf "$tmp"

# Contact sheets: the set as GitHub shows it (README column 1012 px and phone 390 px), on both page colours.
# Cards are passed as their PNG previews; the intro SVG is rendered through resvg_py when it is installed, which
# shows the static frame renderers without CSS animation see.
$S contact-sheet "$O/banner-php2shell.png" "$O/banner-php2shell-golden.png" "$O/banner-agentic-email-skill.png" \
   "$O/banner-jev-minesweeper.png" "$O/banner-netscaler-cve-2026-19489-check.png" "$O/banner-ai-self-replication-study.png" \
   "$O/banner-jev-engineering-typecheck.png" "$O/banner-example.png" --mode stack --widths 1012,390 --labels \
   --title "README hero banners" --out "$O/contact-sheet-banners.png"
$S contact-sheet "$O/card-php2shell.png" "$O/card-agentic-email-skill.png" "$O/card-jev-minesweeper.png" \
   "$O/card-example.png" "$O/card-northwind-cve-check.png" "$O/card-jev-engineering-typecheck.png" "$O/org-tile-example.png" \
   --mode grid --cols 3 --labels --title "Repo cards and org tile" --out "$O/contact-sheet-cards.png"
if ${PYTHON:-python3} -c "import resvg_py" 2>/dev/null; then
  $S contact-sheet "$O/intro-example.svg" "$O/social-preview-example.png" "$O/org-banner-example.jpg" --mode stack \
     --widths 1012 --labels --title "Profile intro (static frame), social preview, org banner" --out "$O/contact-sheet-profile.png"
else
  echo "resvg_py not installed: the intro's static frame is not on a contact sheet (pip install resvg_py)" >&2
fi

# Dogfood: this skill's own hero banner and card (README Variant A)
$S --meta examples/meta/github-showcase-skill.json --repo-dir . banner --out docs/images/banner.png
$S --meta examples/meta/github-showcase-skill.json --repo-dir . card --out docs/images/card.svg
