"""Offline public-CLI regressions: a remote authority cannot become a local badge."""
import json
import os

import pytest

from conftest import run_cli
from test_personal_hero_badge_urls import generated as generated
from test_personal_hero_inline_seams import fixture_repo, snapshot


@pytest.fixture(scope="module", autouse=True)
def offline_cli(tmp_path_factory):
    """Prevent even attempted network access in every actual CLI child process."""
    directory = tmp_path_factory.mktemp("url-authority-offline")
    attempts = directory / "network-attempts.txt"
    (directory / "sitecustomize.py").write_text(
        "import os, socket\n"
        "def deny_network(*args, **kwargs):\n"
        "    with open(os.environ['SHOWCASE_TEST_NETWORK_ATTEMPTS'], 'a') as stream:\n"
        "        stream.write('network access attempted\\n')\n"
        "    raise AssertionError('URL authority tests forbid network access')\n"
        "socket.create_connection = deny_network\n"
        "socket.getaddrinfo = deny_network\n"
        "socket.socket.connect = deny_network\n"
        "socket.socket.connect_ex = deny_network\n",
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as patch:
        previous = os.environ.get("PYTHONPATH")
        patch.setenv("PYTHONPATH", str(directory) + (os.pathsep + previous if previous else ""))
        patch.setenv("SHOWCASE_TEST_NETWORK_ATTEMPTS", str(attempts))
        patch.delenv("SHOWCASE_ESTATE_ROOT", raising=False)
        yield
    assert not attempts.exists(), "The public CLI attempted network access"


REMOTE_ART = [
    pytest.param("https://example.test/docs/images/badges/synthetic.svg", id="https-canonical"),
    pytest.param("https://example.test/../../docs/images/badges/synthetic.svg", id="https-parent-segments"),
    pytest.param("https://example.test/docs/./images/../images/badges/synthetic.svg", id="https-path-segments"),
    pytest.param("http://example.test/../../docs/images/badges/synthetic.svg", id="http-parent-segments"),
    pytest.param("https://viewer@example.test:8443/../../docs/images/badges/synthetic.svg",
                 id="authority-userinfo-port"),
    pytest.param("https://[2001:db8::1]/../../docs/images/badges/synthetic.svg", id="authority-ipv6"),
    pytest.param("art+https://example.test/../../docs/images/badges/synthetic.svg", id="valid-custom-scheme"),
    pytest.param("//example.test/docs/images/badges/synthetic.svg", id="scheme-relative-canonical"),
    pytest.param("//example.test/../docs/images/badges/synthetic.svg", id="scheme-relative-parent-segment"),
]


def opening_art(url):
    """Significant authored whitespace and mixed endings expose normalization writes."""
    return (b"\xef\xbb\xbf![Authored opening artwork](" + url.encode("ascii")
            + b")  \r\n\r\n# Synthetic profile\n\nKeep  these authored notes.  \r\n")


def readme(directory, meta, mode):
    return run_cli("--format", "json", "--meta", meta, "--repo-dir", directory,
                   "readme", "--mode", mode, "--badges", "local",
                   "--records", directory / "records.jsonl", "--write")


@pytest.mark.parametrize("mode", ["scaffold", "header", "upgrade"])
@pytest.mark.parametrize("url", REMOTE_ART)
def test_remote_opening_art_stays_authored_without_local_intro(tmp_path, mode, url):
    source = opening_art(url)
    meta = fixture_repo(tmp_path, source, None)
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "unchanged" and report["written"] is False, report
    assert (tmp_path / "README.md").read_bytes() == source
    assert snapshot(tmp_path) == before, "Authored art must not create intro, badges, provenance or records"


@pytest.mark.parametrize("spelling", ["canonical", "dot-segment", "parent-segment"])
def test_actual_local_generated_badge_still_requires_intro(tmp_path, generated, spelling):
    url = generated["badge_path"]
    if spelling == "dot-segment":
        url = "./" + url.replace("docs/images/", "docs/./images/", 1)
    elif spelling == "parent-segment":
        url = url.replace("docs/images/badges/", "docs/images/badges/../badges/", 1)
    meta = fixture_repo(tmp_path, opening_art(url), None)
    badge = tmp_path / generated["badge_path"]
    badge.parent.mkdir(parents=True, exist_ok=True)
    badge.write_bytes(generated["badge"])
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, "scaffold")

    assert result.returncode == 4, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "needs-input" and "needs-input:intro" in result.stdout, report
    assert snapshot(tmp_path) == before, "A missing intro must refuse atomically"


@pytest.mark.parametrize("mode", ["scaffold", "header", "upgrade"])
def test_local_art_leaving_generated_badge_directory_stays_authored(tmp_path, mode):
    source = opening_art("docs/images/badges/../synthetic-art.svg")
    meta = fixture_repo(tmp_path, source, None)
    (tmp_path / "docs/images/synthetic-art.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>\n')
    before = snapshot(tmp_path)

    result = readme(tmp_path, meta, mode)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["result"] == "unchanged" and report["written"] is False, report
    assert (tmp_path / "README.md").read_bytes() == source
    assert snapshot(tmp_path) == before
