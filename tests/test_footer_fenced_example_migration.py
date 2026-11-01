"""Issue 47 round 3: fenced footer-like examples and the footer workflow triggers.

Synthetic fixtures only.
"""
import copy

import pytest
import yaml

from conftest import ROOT, meta_dict
from ctshowcase import footer, readme
from ctshowcase.config import Brand
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize

LEGACY = "https://raw.githubusercontent.com/CompleteTech-LLC/.github/main/brand/"
PARENT = {"full_name": "someone/upstream", "default_branch": "main"}
VARIANTS = {"G": dict(fork=True, parent=PARENT), "H": dict(repo="host-backup-20260914")}
EXAMPLE = (
    "## Credits example\n\nA project may end with a credit like this:\n\n```md\n"
    "Built by [CompleteTech LLC](https://www.complete.tech)\n```\n"
)


def legacy_brand(brand):
    raw = copy.deepcopy(brand.raw)
    raw["footer"].update(logo_light_url=LEGACY + "logo.png", logo_dark_url=LEGACY + "logo-dark.png")
    return Brand(raw, brand.path)


def big_readme(brand, marked):
    filler = "".join(f"Authored upstream paragraph {i} that stays exactly as written by its authors.\n\n" for i in range(130))
    old = legacy_brand(brand)
    tail = footer.block(old) if marked else footer.markup(old)
    text = "# Upstream project\n\n" + filler + EXAMPLE + "\n" + tail + "\n"
    assert len(text.encode()) >= 10_000
    return text


@pytest.mark.parametrize("marked", [True, False], ids=["marked", "unmarked"])
@pytest.mark.parametrize("variant", ["G", "H"])
def test_fenced_footer_example_does_not_stop_the_replacement_footer(brand, tmp_path, variant, marked):
    ctx = RepoContext(brand, normalize(meta_dict(**VARIANTS[variant])), tmp_path)
    assert ctx.det["variant"] == variant
    before = big_readme(brand, marked)
    after, removed = readme.upgrade(ctx, before)
    assert LEGACY not in after
    assert EXAMPLE in after, "the fenced example is preserved"
    tail = after.split(EXAMPLE, 1)[1]
    assert footer.markup(brand) in tail, "the real footer with the current brand URLs follows the example"
    assert after.count(brand.raw["footer"]["logo_light_url"]) == 1
    assert after.count(brand.raw["footer"]["logo_dark_url"]) == 1
    assert removed, "the replaced footer lines are reported"
    assert readme.preservation(before, after, removed) == []
    again, _ = readme.upgrade(RepoContext(brand, normalize(meta_dict(**VARIANTS[variant])), tmp_path), after)
    assert again == after


def workflow():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "footer-assets.yml").read_text(encoding="utf-8"))
    return wf, wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True


def test_workflow_runs_on_push_to_main_with_the_pull_request_path_filter():
    _, triggers = workflow()
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["paths"] == triggers["pull_request"]["paths"]
    assert "assets/brand/**" in triggers["push"]["paths"]
    assert triggers["schedule"] and "workflow_dispatch" in triggers


def test_online_head_does_not_run_on_pull_requests_and_the_offline_check_does():
    wf, _ = workflow()
    steps = [s for job in wf["jobs"].values() for s in job["steps"]]
    online = [s for s in steps if "--online" in s.get("run", "")]
    assert len(online) == 1 and online[0]["if"] == "github.event_name != 'pull_request'"
    offline = [s for s in steps if "assets" not in s.get("run", "") and "brand.yaml" in s.get("run", "")]
    assert len(offline) == 1 and offline[0]["if"] == "github.event_name == 'pull_request'"
    # the offline step's command really passes against this checkout
    import subprocess
    import sys
    done = subprocess.run([sys.executable, "-c", offline[0]["run"].split('python -c "', 1)[1].rsplit('"', 1)[0]],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
