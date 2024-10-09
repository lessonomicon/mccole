"""Convert Markdown to HTML."""

import argparse
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from markdown import markdown
from pathlib import Path
import sys

from .util import find_files, find_key_defs, get_inclusion, load_config, write_file


MARKDOWN_EXTENSIONS = ["attr_list", "def_list", "fenced_code", "md_in_html", "tables"]


def render(opt):
    """Main driver."""
    config = load_config(opt.config)
    skips = config["skips"] | {opt.out}
    env = Environment(loader=FileSystemLoader(opt.templates))

    files = find_files(opt, skips)
    sections = {
        path: info
        for path, info in files.items()
        if path.suffix == ".md"
    }
    extras = {
        "bibliography": find_key_defs(sections, "bibliography"),
        "glossary": find_key_defs(sections, "glossary"),
    }
    for path, info in sections.items():
        info["doc"] = render_markdown(env, opt, extras, path, info["content"])

    for path, info in files.items():
        result = str(info["doc"]) if path.suffix == ".md" else info["content"]
        output_path = make_output_path(opt.out, config["renames"], path)
        write_file(output_path, result)


def choose_template(env, source_path):
    """Select a template."""
    if source_path.name == "slides.md":
        return env.get_template("slides.html")
    return env.get_template("page.html")


def do_bibliography_links(doc, source_path, extras):
    """Turn 'b:key' links into bibliography references."""
    for node in doc.select("a[href]"):
        if node["href"].startswith("b:"):
            node["href"] = f"@root/bibliography.html#{node['href'][2:]}"


def do_glossary(doc, source_path, extras):
    """Turn 'g:key' links into glossary references and insert list of terms."""
    seen = set()
    for node in doc.select("a[href]"):
        if node["href"].startswith("g:"):
            key = node["href"][2:]
            node["href"] = f"@root/glossary.html#{key}"
            seen.add(key)
    _insert_term_list(doc, source_path, seen, extras)


def do_inclusions_classes(doc, source_path, extras):
    """Adjust classes of file inclusions."""
    for node in doc.select("code[file]"):
        inc_text = node["file"]
        if ":" in inc_text:
            inc_text = inc_text.split(":")[0]
        suffix = inc_text.split(".")[-1]
        for n in (node, node.parent):
            n["class"] = n.get("class", []) + [f"language-{suffix}"]


def do_markdown_links(doc, source_path, extras):
    """Fix .md links in HTML."""
    for node in doc.select("a[href]"):
        if node["href"].endswith(".md"):
            node["href"] = node["href"].replace(".md", ".html").lower()


def do_tables(doc, source_path, extras):
    """Eliminate duplicate table tags created by Markdown tables inside HTML tables."""
    for node in doc.select("table"):
        parent = node.parent
        if parent.name == "table":
            caption = parent.caption
            node.append(caption)
            parent.replace_with(node)


def do_title(doc, source_path, extras):
    """Make sure title element is filled in."""
    try:
        doc.title.string = doc.h1.get_text()
    except Exception as exc:
        print(f"{source_path} lacks H1 heading", file=sys.stderr)
        sys.exit(1)


def do_root_path_prefix(doc, source_path, extras):
    """Fix @root links in HTML."""
    depth = len(source_path.parents) - 1
    prefix = "./" if (depth == 0) else "../" * depth
    targets = (
        ("a[href]", "href"),
        ("link[href]", "href"),
        ("script[src]", "src"),
    )
    for selector, attr in targets:
        for node in doc.select(selector):
            if "@root/" in node[attr]:
                node[attr] = node[attr].replace("@root/", prefix)


def do_toc_lists(doc, source_path, extras):
    """Fix 'chapters' and 'appendices' lists."""
    for kind in ("chapters", "appendices"):
        selector = f"ol.{kind} ol"
        for node in doc.select(selector):
            node.parent.replace_with(node)
            node["class"] = node.get("class", []) + [kind]


def find_ordering(sections):
    """Create path-to-label ordering."""
    doc = sections[Path("README.md")]["doc"]
    chapters = {
        key: str(i+1)
        for i, key in enumerate(find_ordering_items(doc, "ol.chapters"))
    }
    appendices = {
        key: chr(ord("A")+i)
        for i, key in enumerate(find_ordering_items(doc, "ol.appendices"))
    }
    return {**chapters, **appendices}


def find_ordering_items(doc, selector):
    """Extract ordered items' path keys."""
    nodes = doc.select(selector)
    assert len(nodes) == 1
    return [
        link.select("a")[0]["href"].replace("/index.html", "").split("/")[-1]
        for link in nodes[0].select("li")
    ]


def fix_cross_references(sections, xref):
    """Fix all cross-references."""


def make_output_path(output_dir, renames, source_path):
    """Build output path."""
    if source_path.name in renames:
        source_path = Path(source_path.parent, renames[source_path.name])
    source_path = Path(str(source_path).replace(".md", ".html"))
    return Path(output_dir, source_path)


def parse_args(parser):
    """Parse command-line arguments."""
    parser.add_argument("--config", type=str, default="pyproject.toml", help="optional configuration file")
    parser.add_argument("--css", type=str, help="CSS file")
    parser.add_argument("--icon", type=str, help="icon file")
    parser.add_argument("--out", type=str, default="docs", help="output directory")
    parser.add_argument("--root", type=str, default=".", help="root directory")
    parser.add_argument("--templates", type=str, default="templates", help="templates directory")


def render_markdown(env, opt, extras, source_path, content):
    """Convert Markdown to HTML."""
    template = choose_template(env, source_path)
    html = markdown(content, extensions=MARKDOWN_EXTENSIONS)
    html = template.render(content=html, css_file=opt.css, icon_file=opt.icon)

    transformers = (
        do_bibliography_links,
        do_glossary,
        do_inclusions_classes,
        do_markdown_links,
        do_tables,
        do_title,
        do_toc_lists,
        do_root_path_prefix, # must be last
    )
    doc = BeautifulSoup(html, "html.parser")
    for func in transformers:
        func(doc, source_path, extras)

    return doc


def _insert_term_list(doc, source_path, seen, extras):
    """Insert list of defined terms."""
    target = doc.select("p#terms")
    if not target:
        return
    assert len(target) == 1, f"Duplicate p#terms in {source_path}"
    target = target[0]
    if not seen:
        target.decompose()
        return
    glossary = {key: extras["glossary"][key] for key in seen}
    glossary = {k: v for k, v in sorted(glossary.items(), key=lambda item: item[1].lower())}
    target.append("Terms defined: ")
    for i, (key, term) in enumerate(glossary.items()):
        if i > 0:
            target.append(", ")
        ref = doc.new_tag("a", href=f"@root/glossary.html#{key}")
        ref.string = term
        target.append(ref)


if __name__ == "__main__":
    opt = parse_args(argparse.ArgumentParser()).parse_args()
    render(opt)
