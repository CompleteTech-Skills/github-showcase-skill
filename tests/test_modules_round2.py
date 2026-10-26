"""Regression tests for module test round 2 on real estate data (org profiles, project READMEs, content): the defects
that are not covered beside their module's own tests. Synthetic metadata and public org names only."""
from ctshowcase import iconbox
from ctshowcase import readme as R
from ctshowcase.context import RepoContext
from ctshowcase.meta import normalize
from ctshowcase.scene import Text


def test_derived_title_keeps_the_descriptions_brand_casing():
    """`Php2shell Check` on the php2shell-check social preview: the README has no H1 (decision 13 layout)."""
    desc = "Passive PHP2Shell (CVE-2026-109618) exposure checker with branded HTML reports."
    assert R.cased_title("php2shell-check", desc) == "PHP2Shell Check"
    assert R.cased_title("acme-cve-2026-12345-check", "Checks things.") == "Acme CVE-2026-12345 Check"
    assert R.cased_title("invoice-parser-cli", "Parse invoices from the command line.") == R.slug_title("invoice-parser-cli")


def test_product_name_and_social_title_use_the_cased_title(brand, fonts):
    from ctshowcase import social
    meta = normalize({"owner": "CompleteTech-LLC", "repo": "php2shell-check", "visibility": "public",
                      "description": "Passive PHP2Shell exposure checker with branded HTML reports."})
    ctx = RepoContext(brand, meta, None)
    assert R.product_name(ctx) == "PHP2Shell Check"
    _, info = social.social_layout(ctx, fonts)
    assert info["title_lines"] == ["PHP2Shell Check"]


def test_dotted_family_wordmark_breaks_at_the_dot(brand, fonts):
    """The jevplay.games wordmark was typeset at about 8 px on one line in the 88 px card tile."""
    meta = normalize({"owner": "jevplay-games", "repo": "jev-demo", "visibility": "public",
                      "description": "A demo game against Jev."})
    nodes = iconbox.wordmark(RepoContext(brand, meta, None), fonts, (0, 0, 88, 88))
    texts = [n for n in nodes if isinstance(n, Text)]
    assert [t.text for t in texts] == ["jevplay", ".games"]
    assert min(t.size for t in texts) >= 14
