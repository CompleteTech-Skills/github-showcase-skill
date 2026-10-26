# ServiceDesk Plus Cloud Readiness

A local, read-only assessment of ManageEngine ServiceDesk Plus on-premises before migration to Cloud. It collects available inventory and metadata, records coverage gaps, and produces offline HTML, JSON, CSV, and Markdown reports.

**Python 3.10+ · standard library only · version 2.2.0**

This is an independent assessment tool, not a ManageEngine product or migration utility.

## Start an assessment

From the repository root, run either Windows launcher or the Python entry point:

```powershell
.\Run-All-Portals.cmd
# Or:
python .\sdp_cloud_readiness.py
```

Provide your ServiceDesk Plus URL and API key through the prompts. Keys are never accepted as literal command-line arguments or saved in reports. Reports go to a new timestamped directory under `sdp-assessments/` by default.

By default the scanner uses one collection key across selected portals. Use `--multi-key` for secure per-instance prompts, or `--credential-file` for explicit environment-reference assignments. An optional global credential is separate from directory discovery and instance collection. Missing access remains an explicit coverage gap. See [multiple credentials](docs/guides/multiple-credentials.md) for setup and limitations.

For repeated runs, fill the local `.env` beside the source entry point or portable `.pyz`. A first normal run creates a blank scaffold without replacing an existing file; [.env.example](.env.example) supplies 20 numbered key/portal-ID pairs. Set `SDP_HOST`, the actual portal IDs, and keys locally. Populated slots enable per-instance routing; slot numbers never imply portal IDs. Process variables take precedence. Use `--env-file <path>` or `--no-env` to override loading. See [local environment setup](docs/guides/local-env.md) for syntax, scope and conflict rules.

Run an offline demonstration without credentials or network access:

```powershell
python .\sdp_cloud_readiness.py --demo --output-dir .\sdp-assessments
```

## Configuration and guides

Copy the needed files from [examples/config](examples/config) to your working directory and replace their fictional values. Keep credentials out of these files.

```powershell
Copy-Item .\examples\config\connection.example.json .\connection.json
python .\sdp_cloud_readiness.py --config .\connection.json
```

- [Full usage guide](docs/guides/usage.md): options, reports, limits, and privacy boundaries.
- [Assess all portals](docs/guides/all-portals.md): discovery, explicit scope, and recovery.
- [Troubleshooting](docs/guides/troubleshooting.md) and [Windows key input](docs/guides/windows-key-input.md).
- [Documentation index](docs/README.md), [changelog](CHANGELOG.md), and [contributor guide](CONTRIBUTING.md).
- [Synthetic assessment](examples/synthetic-assessment/report.md) and [recovery assessment](examples/recovery-assessment/report.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `sdp_audit/` | Runtime package: transport, collection, analysis, and reporting |
| `tests/` | Unit and integration tests, with synthetic fixtures |
| `docs/guides/` | User instructions and troubleshooting |
| `docs/reference/` | API research, field discovery, and diagnostic contracts |
| `docs/development/` | Validation evidence and release verification |
| `docs/releases/` | Detailed version-specific behavior notes |
| `examples/config/` | Non-secret configuration templates |
| `examples/*-assessment/` | Committed synthetic report examples |
| `tools/` | Release tooling |
| `dist/` | Generated portable app, release ZIP, and checksums; ignored by Git |

## Build a portable release

```powershell
python .\tools\build_release.py
python .\dist\sdp_cloud_readiness.pyz --version
```

The build writes the portable app, source ZIP, Windows launchers, example HTML, and checksums to `dist/`. Extract the ZIP for a complete runnable distribution. In a source checkout, the Windows launchers use the source entry point; in an extracted release, they prefer the adjacent portable app.

## Data handling

Collection is restricted to reviewed HTTP GET operations. Raw ticket descriptions, notes, attachment bodies, credentials, and unnecessary personal fields are excluded from reports. Reports still contain internal structure, identifiers, counts, and configuration findings; review them before sharing. An assessment is not migration approval or proof of complete source visibility.

## License

Code and documentation are released under the [MIT License](LICENSE).
