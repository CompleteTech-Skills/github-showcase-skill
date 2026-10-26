<!-- showcase:banner:start -->
<p align="center">
  <img src="docs/images/banner.png" alt="completetech-repo-template by CompleteTech LLC" width="100%">
</p>
<!-- showcase:banner:end -->

<!-- showcase:nav:start -->
**CompleteTech LLC** · [All repositories](https://github.com/CompleteTech-LLC) · [Contributing](CONTRIBUTING.md) · [Security](https://github.com/CompleteTech-LLC/.github/blob/main/SECURITY.md)
<!-- showcase:nav:end -->

<div align="center">

# CompleteTech Repo Template

<!-- showcase:badges:start -->
![Type Template](https://img.shields.io/badge/type-Template-005ADD)
<!-- showcase:badges:end -->

<!-- showcase:tagline:start -->
**Create new CompleteTech repositories with the standard README, folder layout and showcase banner Action.**
<!-- showcase:tagline:end -->

</div>

---

<!-- showcase:checklist:start -->
> [!IMPORTANT]
> **Finish setting up this repository** (this box disappears once every item is checked):
> - [ ] Name follows the standard: lowercase kebab-case, ≤ 40 characters, no `-repo`, `-new` or `-test` suffix.
> - [ ] Description is one sentence ending with a period, ≤ 120 characters, starting with the verb for its type. The Showcase run's summary (Actions → Showcase → latest run) checks it and proposes the topics to set.
> - [ ] Set the topics proposed in that run summary (Settings → About → Topics).
> - [ ] Run `showcase.py adopt <owner>/<repo>` locally (from the github-showcase skill, with your own `gh` login) and apply what it prints: the settings, topics, labels and security baseline that a repository created from this template does not carry (the workflow's token cannot set them).
> - [ ] Until the code lands, set `type:` in `.github/showcase.yml` (for example `cli`, `library` or `web-app`), and give the banner two to four fact chips with `chips:` there.
> - [ ] Add `assets/icon.png` (see `assets/README.md`); until then the banner shows the org mark or the brand fallback.
> - [ ] Check the Showcase run: it runs on creation, when `.github/showcase.yml` or the icon changes, weekly, and from Actions → Showcase → Run workflow.
> - [ ] Fill every section below from real facts; delete none of the headings that apply. Editing a section makes it yours: the workflow never rewrites it again.
> - [ ] License: none is added by default. See `.github/showcase/LICENSE-POLICY.md`.
<!-- showcase:checklist:end -->

<!-- showcase:template-body:start -->
<!-- showcase:template-body:pristine sha256=d5f7647622afd9ce113ab82949deefa15bf385dc351334126df7f2208ecc35f6 -->
## About

This repository is the starting point for new CompleteTech LLC repositories. It carries the standard README layout, the `docs/images/` folder the hero banner and repo card are generated into, and a workflow that regenerates both from the repository description, topics and icon.

## Install

Select **Use this template** on GitHub, choose the owner organization, and create the repository.

## Quick Start

1. Set the description and topics on the new repository.
2. Add `assets/icon.png`, and `type:` plus `chips:` in `.github/showcase.yml` until the code lands.
3. Open **Actions → Showcase**: the first run fills this README for the repository's type and draws its banner and card.

## Usage

The workflow calls [`github-showcase-skill`](https://github.com/CompleteTech-Skills/github-showcase-skill). On its first run in a new repository, it replaces this section block with the sections of the README variant that matches the detected repository type, and fills in the banner, badges and description. While nobody has edited that block, later runs refill it when the type changes (for example once the code lands); after the first edit it is yours. Later runs also regenerate the banner and card when the description, topics, type or icon change.

GitHub turns off scheduled workflows in public repositories after 60 days without activity. If description or topic edits stop showing up in the banner, re-enable the workflow under Actions, or run it by hand.

## Configuration

Optional per-repository settings live in `.github/showcase.yml`. They cover content only: type, icon path, subtitle, chips and variant.
<!-- showcase:template-body:end -->

## License

<!-- showcase:license -->
No license is granted. Add one only as described in `.github/showcase/LICENSE-POLICY.md`.

<!-- showcase:footer:start -->
<p align="center">
  <a href="https://www.complete.tech">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo-dark.png">
      <img src="https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/logo.png" alt="CompleteTech LLC" width="200">
    </picture>
  </a>
  <br>
  Built by <a href="https://www.complete.tech">CompleteTech LLC</a> · Innovation at Every Integration
</p>
<!-- showcase:footer:end -->
