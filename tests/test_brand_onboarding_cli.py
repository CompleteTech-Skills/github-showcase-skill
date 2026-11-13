"""Exercise onboarding through the installed public CLI with synthetic local data."""
import io
import json
import struct
import zlib

import pytest
from PIL import Image

from conftest import ROOT, meta_dict, run_cli
from ctshowcase.config import load_brand, schema_errors


@pytest.fixture
def copied_config(tmp_path):
    config = tmp_path / "package" / "references" / "brand.yaml"
    config.parent.mkdir(parents=True)
    config.write_bytes((ROOT / "references" / "brand.yaml").read_bytes())
    return config


def family_args(config, *extra):
    return ("--config", config, "brand", "add-family", "--name", "northwind-onboard",
            "--label", "Northwind Onboard", "--canvas", "#101820", "--ink", "#F5F5F5",
            "--accent", "#FFB81C", "--org", "Northwind-Onboard", "--tier", "T2",
            "--display-name", "Northwind Onboard", "--footer", "no", *extra)


def test_onboarding_is_registered_on_public_cli():
    assert "brand" in run_cli("--help").stdout
    for action in ("add-family", "add-org"):
        result = run_cli("brand", action, "--help")
        assert result.returncode == 0, result.stderr
        assert "--write" in result.stdout


def test_one_cli_command_creates_renderable_family_org_mark_and_lock(copied_config, tmp_path):
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (24, 24), (212, 173, 93, 255)).save(mark)
    target = copied_config.parent.parent / "assets" / "orgs" / "Northwind-Onboard" / "mark.png"
    before = copied_config.read_bytes()
    arguments = family_args(copied_config, "--mark", mark)

    planned = run_cli(*arguments)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    assert json.loads(planned.stdout)["result"] == "planned"
    assert copied_config.read_bytes() == before
    assert not copied_config.with_name("brand.lock.json").exists()
    assert not target.exists()

    written = run_cli(*arguments, "--write")
    assert written.returncode == 0, written.stderr + written.stdout
    brand = load_brand(copied_config)
    assert not schema_errors(brand.raw)
    assert brand.raw == json.loads(copied_config.with_name("brand.lock.json").read_text(encoding="utf-8"))
    assert target.read_bytes() == mark.read_bytes()
    assert brand.asset(brand.org("Northwind-Onboard")["mark"]) == target
    assert brand.logo_light().is_file()  # Bundled fallback remains available for an external config.
    assert brand.font_file(next(iter(brand.raw["fonts"]))).is_file()

    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Onboard", repo="onboarding-demo",
                                        description="Run the Northwind demonstration.", license="MIT")),
                    encoding="utf-8")
    common = ("--config", copied_config, "--meta", meta, "--no-repo-dir", "--format", "json")
    banner = tmp_path / "banner.png"
    refused = run_cli(*common, "banner", "--out", banner, "--key-chip", "Demo", "--chip", "Local")
    assert refused.returncode == 4
    assert "needs-input:palette-v1.1" in refused.stdout
    assert not banner.exists()

    rendered = run_cli(*common, "banner", "--allow-unmeasured", "--out", banner,
                       "--key-chip", "Demo", "--chip", "Local")
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert json.loads(rendered.stdout)["icon"]["source"] == "org-mark"
    assert banner.is_file()
    assert run_cli("lint", "banner", banner).returncode == 0

    card = tmp_path / "card.svg"
    rendered = run_cli(*common, "card", "--allow-unmeasured", "--out", card)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert json.loads(rendered.stdout)["icon"]["source"] == "org-mark"
    assert run_cli("lint", "svg", "--kind", "card", card).returncode == 0
    assert "CompleteTech" not in card.read_text(encoding="utf-8")


def test_add_org_cli_requires_policy_and_keeps_t3_refusal(copied_config, tmp_path):
    before = copied_config.read_bytes()
    args = ("--config", copied_config, "brand", "add-org", "--family", "pickyourai",
            "--org", "Northwind-Review", "--display-name", "Northwind Review")
    refused = run_cli(*args, "--write")
    assert refused.returncode == 2
    assert "--tier and --footer" in refused.stdout
    assert copied_config.read_bytes() == before
    written = run_cli(*args, "--tier", "T3", "--footer", "hold", "--write")
    assert written.returncode == 0, written.stdout + written.stderr
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(meta_dict(owner="Northwind-Review", repo="demo")), encoding="utf-8")
    out = tmp_path / "card.svg"
    refused = run_cli("--config", copied_config, "--meta", meta, "--no-repo-dir",
                      "--format", "json", "card", "--allow-unmeasured", "--out", out)
    assert refused.returncode == 2
    assert "t3-signoff" in refused.stdout
    assert not out.exists()


@pytest.mark.parametrize("extra", [("--icon-ink", "#101820"), ("--icon-spark", "not-a-colour")])
def test_invalid_palette_cli_leaves_configuration_and_assets_untouched(copied_config, tmp_path, extra):
    mark = tmp_path / "authorized.png"
    Image.new("RGBA", (8, 8), (90, 120, 150, 255)).save(mark)
    before = copied_config.read_bytes()
    result = run_cli(*family_args(copied_config, "--mark", mark, *extra, "--write"))
    assert result.returncode == 2
    assert copied_config.read_bytes() == before
    assert not copied_config.with_name("brand.lock.json").exists()
    assert not (copied_config.parent.parent / "assets").exists()


def test_cli_rejects_reserved_owner_without_reclassification(copied_config):
    before = copied_config.read_bytes()
    result = run_cli("--config", copied_config, "brand", "add-org", "--family", "pickyourai",
                     "--org", "BunsDev", "--display-name", "Northwind Review", "--tier", "T2",
                     "--footer", "no", "--write")
    assert result.returncode == 2
    assert "reserved" in result.stdout
    assert copied_config.read_bytes() == before


@pytest.mark.parametrize("image_data", [b"not-a-zlib-stream", zlib.compress(b"\x00")],
                         ids=["invalid-zlib", "incomplete-pixels"])
@pytest.mark.parametrize("action", ["add-family", "add-org"])
def test_invalid_png_pixels_refuse_before_onboarding_writes(copied_config, tmp_path, image_data, action):
    """CRC-valid PNG containers must also have decodable pixel data."""
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload)))
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", image_data) + chunk(b"IEND", b""))
    # Structure-only verification accepts both inputs; pixel decoding rejects them.
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image, pytest.raises(OSError):
        image.load()
    mark = tmp_path / "crc-valid-but-broken.png"
    mark.write_bytes(data)
    lock = copied_config.with_name("brand.lock.json")
    lock.write_bytes(b"previous lock bytes\n")
    before = {path: path.read_bytes() for path in (copied_config, lock, mark)}
    if action == "add-family":
        arguments = family_args(copied_config, "--mark", mark, "--write")
    else:
        arguments = ("--config", copied_config, "brand", "add-org", "--family", "completetech",
                     "--org", "Northwind-Onboard", "--tier", "T2", "--display-name", "Northwind Onboard",
                     "--footer", "no", "--mark", mark, "--write")
    result = run_cli(*arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "readable, valid PNG" in result.stdout
    assert all(path.read_bytes() == value for path, value in before.items())
    assert not (copied_config.parent.parent / "assets").exists()
