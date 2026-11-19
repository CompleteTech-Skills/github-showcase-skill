"""Independent exact-tail oracle for generated synthetic identity fixtures.

The configured software attribution is distinct from an organization's identity.
Only its complete documented bytes, immediately before the exact final decision
18 footer, may be omitted from the original body-affiliation assertions. These
expectations do not call the production credit builder, matcher or parser.
"""
import pytest

from test_footer import DECISION_18


CREDIT_START = "<!-- showcase:credit:start -->"
CREDIT_END = "<!-- showcase:credit:end -->"
FOOTER_START = "<!-- showcase:footer:start -->"
FOOTER_END = "<!-- showcase:footer:end -->"
EXACT_FOOTER = f"{FOOTER_START}\n{DECISION_18}\n{FOOTER_END}"


def configured_credit(raw):
    """Documented literal layout, with content from the selected brand fixture."""
    attribution = raw["attribution"]
    return (
        f"{CREDIT_START}\n"
        f"<!-- generated-by: {attribution['skill']} v=1.0.0 std=ct-std-v1 -->\n"
        f'<p align="center"><sub>{attribution["credit_prefix"]} '
        f'<a href="{attribution["skill_url"]}">{attribution["skill"]}</a> '
        f'{attribution["credit_suffix"]} · '
        f'<a href="{attribution["install_url"]}">{attribution["install_label"]}</a></sub></p>\n'
        f"{CREDIT_END}"
    )


def identity_sections(text, raw, *, footer_required=True):
    """Validate the complete final pair, then omit only credit from pre-footer text."""
    markers = (CREDIT_START, CREDIT_END, FOOTER_START, FOOTER_END)
    if not footer_required:
        assert all(marker not in text for marker in markers)
        return text, ""

    assert all(text.count(marker) == 1 for marker in markers)
    assert text.count("<picture>") == 1
    expected_credit = configured_credit(raw)
    assert text.rstrip().endswith(EXACT_FOOTER)
    footer_start = text.index(FOOTER_START)
    credit_start = text.index(CREDIT_START)
    credit_end = credit_start + len(expected_credit)
    assert credit_start == 0 or text[:credit_start].endswith("\n\n")
    assert text[credit_start:footer_start] == expected_credit + "\n\n"
    # Keep every byte outside the validated credit and the separately checked
    # footer, including both separators and any authored affiliation context.
    return text[:credit_start] + text[credit_end:footer_start], text[footer_start:]


def synthetic_readme(raw, body="# Synthetic independent organization\n\n"):
    return body + configured_credit(raw) + "\n\n" + EXACT_FOOTER + "\n"


def test_identity_oracle_removes_only_the_exact_configured_credit(brand):
    body = "# Synthetic independent organization\n\nKeep this exact authored context.  \n\n"
    text = synthetic_readme(brand.raw, body)
    remaining, final_footer = identity_sections(text, brand.raw)
    assert remaining == body + "\n\n"
    assert final_footer == EXACT_FOOTER + "\n"


@pytest.mark.parametrize("mutation", [
    "foreign-generator", "forged-marker", "foreign-url", "extra-text", "extra-child",
    "extra-attribute", "duplicate-credit", "extra-credit-marker", "credit-after-footer",
    "authored-between", "inline-prefix", "fenced-credit", "changed-footer", "duplicate-footer",
    "trailing-authored",
])
def test_identity_oracle_rejects_unproven_credit_and_footer(brand, mutation):
    credit = configured_credit(brand.raw)
    text = synthetic_readme(brand.raw)
    mutations = {
        "foreign-generator": text.replace("generated-by: github-showcase-skill", "generated-by: northwind-docs"),
        "forged-marker": text.replace("README styled with", "Organization maintained by"),
        "foreign-url": text.replace(brand.raw["attribution"]["skill_url"], "https://example.invalid/authored-tool"),
        "extra-text": text.replace(CREDIT_END, "Authored affiliation: CompleteTech LLC.\n" + CREDIT_END),
        "extra-child": text.replace("</sub>", "<span>Steward: CompleteTech LLC.</span></sub>"),
        "extra-attribute": text.replace('<sub>', '<sub title="CompleteTech affiliation">'),
        "duplicate-credit": credit + "\n\n" + text,
        "extra-credit-marker": CREDIT_START + "\n" + text,
        "credit-after-footer": "# Synthetic\n\n" + EXACT_FOOTER + "\n\n" + credit + "\n",
        "authored-between": text.replace("\n\n" + FOOTER_START, "\n\nSteward: CompleteTech LLC.\n\n" + FOOTER_START),
        "inline-prefix": text.replace(CREDIT_START, "Authored neighbor." + CREDIT_START),
        "fenced-credit": text.replace(credit, "```html\n" + credit + "\n```"),
        "changed-footer": text.replace('width="200"', 'width="220"'),
        "duplicate-footer": EXACT_FOOTER + "\n\n" + text,
        "trailing-authored": text + "Steward: CompleteTech LLC.\n",
    }
    changed = mutations[mutation]
    assert changed != text
    with pytest.raises(AssertionError):
        identity_sections(changed, brand.raw)


@pytest.mark.parametrize("forbidden", ["CompleteTech LLC", "CompleteDotTech", "#005ADD", "complete.tech"])
@pytest.mark.parametrize("position", ["heading", "paragraph", "immediately-before-credit"])
def test_identity_oracle_keeps_outside_affiliation_for_the_original_assertions(brand, forbidden, position):
    from test_brand_boundaries import assert_no_complete_tech_leak
    from test_org_profile_identity import FORBIDDEN

    body = {
        "heading": f"# {forbidden}\n\nSynthetic independent organization.\n\n",
        "paragraph": f"# Synthetic\n\nAffiliation: {forbidden}.\n\nKeep authored context.\n\n",
        "immediately-before-credit": f"# Synthetic\n\nSteward: {forbidden}.\n\n",
    }[position]
    remaining, _ = identity_sections(synthetic_readme(brand.raw, body), brand.raw)
    assert remaining == body + "\n\n"
    assert forbidden in remaining
    if forbidden != "complete.tech":
        with pytest.raises(AssertionError):
            assert_no_complete_tech_leak("synthetic-independent", remaining)
    if forbidden != "#005ADD":
        assert not all(token.lower() not in remaining.lower() for token in FORBIDDEN)


def test_footer_exempt_identity_keeps_the_entire_document(brand):
    text = "# Synthetic\n\nAuthored affiliation: CompleteTech LLC.\n"
    assert identity_sections(text, brand.raw, footer_required=False) == (text, "")
    with pytest.raises(AssertionError):
        identity_sections(synthetic_readme(brand.raw), brand.raw, footer_required=False)
