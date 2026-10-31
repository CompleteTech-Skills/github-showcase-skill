"""Deterministic scaling regression for the per-document span caches: the work done by the reference-definition scan
grows near-linearly with the document, checked by counting layout builds and inline regions visited (mdcode.WORK),
never by seconds. Documents are synthetic."""
import pytest

from ctshowcase import mdcode, readmelint

N = 60


def reference_doc(n, fenced=False):
    parts = ["# Synthetic\n"]
    for i in range(n):
        parts.append(f"Paragraph {i} with `code {i}` and ![x{i}][ref{i}] and <b>tag</b> <i>em</i> ![in{i}](docs/images/in{i}.png) `more`.\n")
        if fenced:
            parts.append(f"\n```text\nblock {i} `tick`\n```\n")
        parts.append("")
    parts.append("")
    parts += [f"[ref{i}]: https://example.test/img{i}.png \"Title {i}\"" for i in range(n)]
    return "\n".join(parts) + "\n"


def reset():
    mdcode._layout.cache_clear()
    mdcode.inline_code_spans.cache_clear()
    mdcode.fence_spans.cache_clear()
    mdcode.continuation_starts.cache_clear()
    readmelint._definitions.cache_clear()
    mdcode._region_bounds.cache_clear()
    readmelint._definition_spans.cache_clear()
    readmelint._outside_code.cache_clear()
    mdcode.WORK.clear()


def measure(doc, action):
    reset()
    action(doc)
    return dict(mdcode.WORK)


def _spans(doc):
    assert len(readmelint._definition_spans(doc)) > 0


def _markdown(doc):
    assert readmelint._markdown_images(readmelint._outside_code(doc), doc)


def _images(doc):
    found = readmelint._images(readmelint._outside_code(doc), doc)
    assert len(found) >= doc.count("![x")


ACTIONS = {"definition_spans": _spans, "markdown_images": _markdown, "images": _images}


@pytest.mark.parametrize("fenced", [False, True], ids=["prose", "fence-heavy"])
@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_work_grows_near_linearly(name, fenced):
    small = measure(reference_doc(N, fenced), ACTIONS[name])
    large = measure(reference_doc(2 * N, fenced), ACTIONS[name])
    # the tokenizer builds the document layout once, however many definitions there are
    assert small["layout_builds"] == large["layout_builds"] <= 2, (small, large)
    # a quadratic walk from offset 0 per definition would roughly quadruple the regions visited
    assert large.get("regions", 0) <= 2.5 * small.get("regions", 0), (small, large)


def test_image_and_tag_comparisons_grow_near_linearly():
    """`_images` matches every HTML tag and Markdown image against the other by interval lookup (bisection), so the
    comparisons it makes grow with the number of tags and images, not with their product. Counted, never timed."""
    small = measure(reference_doc(N), _images)
    large = measure(reference_doc(2 * N), _images)
    assert small["span_checks"] > 0 and large["span_checks"] > 0, (small, large)
    assert large["span_checks"] <= 2.5 * small["span_checks"], (small, large)


def test_layout_is_built_once_per_document_across_the_whole_path():
    doc = reference_doc(N, fenced=True)
    reset()
    for _ in range(3):
        readmelint._images(readmelint._outside_code(doc), doc)
        readmelint._definition_spans(doc)
    assert mdcode.WORK["layout_builds"] == 1
