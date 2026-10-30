import pytest

from ctshowcase.color import contrast
from ctshowcase.config import load_repo_override, schema_errors, lock_in_sync
from ctshowcase.errors import ConfigError, NeedsInput, Refused

S23 = {  # §2.3 display names and eyebrows, verbatim
    "CompleteTech-LLC": ("CompleteTech LLC", None), "CompleteTech-Skills": ("CompleteTech Skills", "SKILLS"),
    "CompleteTech-LLC-AI-Research": ("CompleteTech AI Research", "AI RESEARCH"),
    "CompleTetech-Security": ("CompleteTech Security", "SECURITY"),
    "CompleteTech-Infrastructure": ("CompleteTech Infrastructure", "INFRASTRUCTURE"),
    "CompleteTech-Commerce": ("CompleteTech Commerce", "COMMERCE"), "CompleteTech-Creative": ("CompleteTech Creative", "CREATIVE"),
    "CompleteTech-Pokemon": ("CompleteTech TCG", "TCG"), "CompleteTech-Data": ("CompleteTech Data", "DATA"),
    "CompleteTech-Games": ("CompleteTech Games", "GAMES"), "CompleteTech-Directories": ("CompleteTech Directories", "DIRECTORIES"),
    "CompleteTech-Hardware": ("CompleteTech Hardware", "HARDWARE"),
    "CompleteTechDiscord-Games": ("CompleteTech Discord Games", "DISCORD GAMES"),
    "CompleteTech-DiscordApps": ("CompleteTech Discord Apps", "DISCORD APPS"),
    "CompleteTech-Patent-IP": ("CompleteTech Patent and IP", "PATENT AND IP"),
    "CompleteTech-Career-Toolkit": ("CompleteTech Career Toolkit", "CAREER TOOLKIT"),
    "CompleteTech-ManageEngine": ("CompleteTech ManageEngine Tools", "MANAGEENGINE TOOLS"),
    "AI-Ascension": ("AI Ascension", None), "Jev-Engineering": ("Jev Engineering", None),
    "jevplay-games": ("jevplay.games", None), "LibreEvolve": ("LibreEvolve", None),
    "TouchedByAnAgent": ("Touched By An Agent", None), "romgenie-following-repos": ("romgenie following", None),
    "romgenie-archive-repostiory": ("romgenie archive", None),
}


def test_schema_and_lock(brand):
    assert schema_errors(brand.raw) == []
    assert lock_in_sync(brand)


@pytest.mark.parametrize("owner", sorted(S23))
def test_every_org_row(brand, owner):
    org = brand.org(owner)
    assert org["known"]
    assert (org["display_name"], org.get("eyebrow")) == S23[owner]


def test_owner_lists(brand):
    for o in ("BunsDev", "GoZippy", "h-mascot", "lmvdz", "GalaxyRuler"):
        with pytest.raises(Refused):
            brand.check_owner(o)
    for o in ("MetatronAngelAgent", "PrompDev", "Pick-Your-AI", "Jevelopers-neatHack-2026"):
        with pytest.raises(Refused):
            brand.check_owner(o)
    assert brand.check_owner("romgenie-following-repos") == "watching"
    assert brand.check_owner("CompleteTech-Skills") is None


@pytest.mark.parametrize("family", ["completetech", "ai-ascension", "jev-engineering", "jevplay-games", "libreevolve",
                                    "touchedbyanagent", "romgenie", "pickyourai"])
def test_contrast(brand, family):
    f = brand.family(family)
    t, c = f["tokens"], f["canvas"]
    grounds = [c[k] for k in ("from", "to", "color") if k in c]
    for g in grounds:
        for key in ("eyebrow", "title", "subtitle", "body"):
            assert contrast(t[key], g) >= 4.5, (family, key, g)
    for chip in ("chip_key", "chip_attr"):
        assert contrast(t[chip]["fg"], t[chip]["bg"]) >= 4.5, (family, chip)


def test_auto_fg_picks(brand):
    from ctshowcase.color import best_fg
    for fam in ("touchedbyanagent", "romgenie"):
        t = brand.family(fam)["tokens"]
        assert t["chip_attr"]["fg"] == best_fg(t["chip_attr"]["bg"], [t["title"], *brand.raw["contrast_candidates"]])
    assert brand.family("romgenie")["tokens"]["chip_attr"]["fg"] != "#FFFFFF"  # white on brass is 3.25:1


def test_override_rejects_colours_and_fonts(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/showcase.yml").write_text("subtitle: ok\ncolor: '#FF0000'\n")
    with pytest.raises(ConfigError):
        load_repo_override(tmp_path)
    (tmp_path / ".github/showcase.yml").write_text("fonts: {title: x}\n")
    with pytest.raises(ConfigError):
        load_repo_override(tmp_path)
    (tmp_path / ".github/showcase.yml").write_text("subtitle: ok\nchips: {key: [A], attrs: [B]}\n")
    assert load_repo_override(tmp_path)[0]["subtitle"] == "ok"


def test_unmeasured_family_refuses(make_ctx):
    ctx = make_ctx(owner="LibreEvolve", repo="libre-thing")
    with pytest.raises(NeedsInput) as e:
        ctx.require_measured(False)
    assert e.value.code == 4 and "palette-v1.1" in e.value.log
    ctx.require_measured(True)


def test_config_crop_writes_measured_marks(tmp_path, brand):
    """`config --crop` (Phase 0.12): crops come only from measured boxes on the dark master; bulb_dark is masked."""
    import copy

    import pytest
    from PIL import Image

    from ctshowcase.config import Brand, write_crops
    from ctshowcase.errors import ConfigError, NeedsInput
    raw = copy.deepcopy(brand.raw)
    b = Brand(raw, brand.path)
    b.root = tmp_path
    (tmp_path / "assets" / "brand").mkdir(parents=True)
    master = Image.new("RGBA", (200, 100), (10, 20, 40, 255))
    for x in range(120, 140):  # a "cloud stroke": blue enough to be masked out of the bulb
        for y in range(10, 30):
            master.putpixel((x, y), (40, 60, 200, 255))
    master.save(tmp_path / raw["brand_assets"]["logo_dark"])
    with pytest.raises(NeedsInput):  # unmeasured: nothing is written
        write_crops(b)
    raw["brand_assets"]["crops"].update(measured=True, mark_dark=[10, 5, 190, 95], bulb_dark=[100, 0, 160, 60])
    out = write_crops(b)
    assert out["mark_dark"]["size"] == [180, 90] and out["bulb_dark"]["size"] == [60, 60]
    bulb = Image.open(tmp_path / out["bulb_dark"]["path"])
    assert bulb.getpixel((25, 15))[3] == 0 and bulb.getpixel((5, 5))[3] == 255
    raw["brand_assets"]["crops"]["mark_dark"] = [0, 0, 400, 50]
    with pytest.raises(ConfigError):
        write_crops(b)
