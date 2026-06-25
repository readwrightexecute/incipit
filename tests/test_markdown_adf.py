"""Unit tests for the markdown → Atlassian Document Format converter."""

from app import markdown_adf
from app.wizard import flow, state


def _types(doc):
    return [n["type"] for n in doc["content"]]


def test_doc_envelope():
    doc = markdown_adf.to_adf("hello")
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert doc["content"][0]["type"] == "paragraph"


def test_empty_input_is_valid_doc():
    doc = markdown_adf.to_adf("")
    assert doc["type"] == "doc"
    assert isinstance(doc["content"], list) and doc["content"]


def test_headings_carry_levels():
    doc = markdown_adf.to_adf("# One\n\n### Three")
    heads = [n for n in doc["content"] if n["type"] == "heading"]
    assert heads[0]["attrs"]["level"] == 1
    assert heads[0]["content"][0]["text"] == "One"
    assert heads[1]["attrs"]["level"] == 3


def test_bold_and_italic_marks():
    doc = markdown_adf.to_adf("This is **bold** and *italic* text.")
    nodes = doc["content"][0]["content"]
    strong = [n for n in nodes if n.get("marks") == [{"type": "strong"}]]
    em = [n for n in nodes if n.get("marks") == [{"type": "em"}]]
    assert strong and strong[0]["text"] == "bold"
    assert em and em[0]["text"] == "italic"


def test_inline_code_mark():
    doc = markdown_adf.to_adf("run `pytest -q` now")
    nodes = doc["content"][0]["content"]
    code = [n for n in nodes if n.get("marks") == [{"type": "code"}]]
    assert code and code[0]["text"] == "pytest -q"


def test_inline_code_is_not_parsed_for_emphasis():
    doc = markdown_adf.to_adf("literal `a*b*c` span")
    nodes = doc["content"][0]["content"]
    code = [n for n in nodes if n.get("marks") == [{"type": "code"}]]
    assert code[0]["text"] == "a*b*c"  # the * inside code stayed literal


def test_fenced_code_block_with_language():
    md = "```python\nprint('hi')\nx = 1\n```"
    doc = markdown_adf.to_adf(md)
    block = doc["content"][0]
    assert block["type"] == "codeBlock"
    assert block["attrs"]["language"] == "python"
    assert block["content"][0]["text"] == "print('hi')\nx = 1"


def test_fenced_code_block_without_language():
    doc = markdown_adf.to_adf("```\nplain\n```")
    block = doc["content"][0]
    assert block["type"] == "codeBlock"
    assert "attrs" not in block
    assert block["content"][0]["text"] == "plain"


def test_bullet_list():
    doc = markdown_adf.to_adf("- one\n- two\n- three")
    lst = doc["content"][0]
    assert lst["type"] == "bulletList"
    assert len(lst["content"]) == 3
    item = lst["content"][0]
    assert item["type"] == "listItem"
    assert item["content"][0]["type"] == "paragraph"
    assert item["content"][0]["content"][0]["text"] == "one"


def test_ordered_list():
    doc = markdown_adf.to_adf("1. first\n2. second")
    lst = doc["content"][0]
    assert lst["type"] == "orderedList"
    assert len(lst["content"]) == 2
    assert lst["content"][1]["content"][0]["content"][0]["text"] == "second"


def test_link_mark():
    doc = markdown_adf.to_adf("see [docs](https://example.com/x)")
    nodes = doc["content"][0]["content"]
    link = [n for n in nodes if n.get("marks", [{}])[0].get("type") == "link"]
    assert link
    assert link[0]["text"] == "docs"
    assert link[0]["marks"][0]["attrs"]["href"] == "https://example.com/x"


def test_paragraphs_split_on_blank_line():
    doc = markdown_adf.to_adf("first para\n\nsecond para")
    paras = [n for n in doc["content"] if n["type"] == "paragraph"]
    assert len(paras) == 2
    assert paras[0]["content"][0]["text"] == "first para"
    assert paras[1]["content"][0]["text"] == "second para"


def test_mixed_document_structure():
    md = "# Title\n\nIntro **bold**.\n\n- a\n- b\n\n```sh\nls\n```"
    doc = markdown_adf.to_adf(md)
    assert _types(doc) == ["heading", "paragraph", "bulletList", "codeBlock"]


def test_assemble_final_output_converts_cleanly():
    # The real mega-prompt (bold field labels + ## headings) must yield headings.
    s = state.Session(id="t", created=0.0, idea="A todo app", project_type="new",
                      stakes="serious", form_factor="web")
    s.sections = [state.Section(id="overview", title="Overview", instruction="",
                                content="It does **things**.")]
    doc = markdown_adf.to_adf(flow.assemble_final(s))
    assert doc["type"] == "doc"
    assert any(n["type"] == "heading" for n in doc["content"])
