"""Convert Markdown to HTML."""

import argparse
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from markdown import markdown
from pathlib import Path
import sys

from .util import find_files, find_key_defs, load_config, write_file


COMMENT = {
    "js": "//",
    "py": "#",
    "sql": "--",
}

MARKDOWN_EXTENSIONS = [
    "attr_list",
    "def_list",
    "fenced_code",
    "md_in_html",
    "tables"
]


def render(opt):
    """Main driver."""

    # Setup.
    config = load_config(opt.config)
    skips = config["skips"] | {opt.out}
    env = Environment(loader=FileSystemLoader(opt.templates))

    # Find all files to be rendered.
    files = find_files(opt, skips)
    sections = {
        path: info
        for path, info in files.items()
        if path.suffix == ".md"
    }

    # Extract cross-reference keys.
    context = {
        "bibliography": find_key_defs(sections, "bibliography"),
        "glossary": find_key_defs(sections, "glossary"),
    }

    # Render all documents.
    for path, info in sections.items():
        info["doc"] = render_markdown(env, opt, context, path, info["content"])

    # Save results.
    for path, info in files.items():
        result = str(info["doc"]) if path.suffix == ".md" else info["content"]
        output_path = make_output_path(opt.out, config["renames"], path)
        write_file(output_path, result)


def choose_template(env, source):
    """Select a template."""
    if source.name == "slides.md":
        return env.get_template("slides.html")
    return env.get_template("page.html")


def do_bibliography_links(doc, source, context):
    """Turn 'b:key' links into bibliography references."""
    for node in doc.select("a[href]"):
        if node["href"].startswith("b:"):
            node["href"] = f"@root/bibliography.html#{node['href'][2:]}"


def do_glossary(doc, source, context):
    """Turn 'g:key' links into glossary references and insert list of terms."""
    seen = set()
    for node in doc.select("a[href]"):
        if node["href"].startswith("g:"):
            key = node["href"][2:]
            node["href"] = f"@root/glossary.html#{key}"
            seen.add(key)
    insert_defined_terms(doc, source, seen, context)


def do_inclusions(doc, source, context):
    """Adjust classes of file inclusions."""
    for node in doc.select("pre[data-file]"):
        inc_file = node["data-file"]
        path, content = inclusion_get(source, inc_file)
        language = f"language-{path.suffix.lstrip('.')}"
        if "data-keep" in node:
            content = inclusion_keep(source, path, content, node["data-keep"])
        code = doc.new_tag("code")
        node.append(code)
        code.string = content.rstrip()
        code["class"] = language
        node["class"] = language


def do_markdown_links(doc, source, context):
    """Fix .md links in HTML."""
    for node in doc.select("a[href]"):
        if node["href"].endswith(".md"):
            node["href"] = node["href"].replace(".md", ".html").lower()


def do_title(doc, source, context):
    """Make sure title element is filled in."""
    try:
        doc.title.string = doc.h1.get_text()
    except Exception as exc:
        print(f"{source} lacks H1 heading", file=sys.stderr)
        sys.exit(1)


def do_root_path_prefix(doc, source, context):
    """Fix @root links in HTML."""
    depth = len(source.parents) - 1
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


def inclusion_get(outer, inner):
    """Load external included file."""
    path = outer.parent / inner
    assert path.is_file(), \
        f"Bad inclusion in {outer}: {path} does not exist or is not file"
    return path, path.read_text()


def inclusion_keep(source, path, content, tag):
    """Keep a section of a file."""
    suffix = path.suffix.lstrip(".")
    assert suffix in COMMENT, \
        f"%inc in {source}: unknown inclusion suffix in {path}"
    before = f"{COMMENT[suffix]} [{tag}]"
    after = f"{COMMENT[suffix]} [/{tag}]"
    assert (before in content) and (after in content), \
        f"%inc in {source}: missing start/end for {COMMENT[suffix]} and {tag}"
    content = content.split(before)[1].split(after)[0]
    if content[0] == "\n":
        content = content[1:]
    return content


def insert_defined_terms(doc, source, seen, context):
    """Insert list of defined terms."""
    target = doc.select("p#terms")
    if not target:
        return
    assert len(target) == 1, f"Duplicate p#terms in {source}"
    target = target[0]
    if not seen:
        target.decompose()
        return
    glossary = {key: context["glossary"][key] for key in seen}
    glossary = {k: v for k, v in sorted(glossary.items(), key=lambda item: item[1].lower())}
    target.append("Terms defined: ")
    for i, (key, term) in enumerate(glossary.items()):
        if i > 0:
            target.append(", ")
        ref = doc.new_tag("a", href=f"@root/glossary.html#{key}")
        ref.string = term
        target.append(ref)


def make_output_path(output_dir, renames, source):
    """Build output path."""
    if source.name in renames:
        source = Path(source.parent, renames[source.name])
    source = Path(str(source).replace(".md", ".html"))
    return Path(output_dir, source)


def parse_args(parser):
    """Parse command-line arguments."""
    parser.add_argument("--config", type=str, default="pyproject.toml", help="optional configuration file")
    parser.add_argument("--css", type=str, help="CSS file")
    parser.add_argument("--icon", type=str, help="icon file")
    parser.add_argument("--out", type=str, default="docs", help="output directory")
    parser.add_argument("--root", type=str, default=".", help="root directory")
    parser.add_argument("--templates", type=str, default="templates", help="templates directory")


def render_markdown(env, opt, context, source, content):
    """Convert Markdown to HTML."""
    template = choose_template(env, source)
    html = markdown(content, extensions=MARKDOWN_EXTENSIONS)
    html = template.render(content=html, css_file=opt.css, icon_file=opt.icon)

    transformers = (
        do_bibliography_links,
        do_glossary,
        do_inclusions,
        do_markdown_links,
        do_title,
        do_root_path_prefix, # must be last
    )
    doc = BeautifulSoup(html, "html.parser")
    for func in transformers:
        func(doc, source, context)

    return doc


if __name__ == "__main__":
    opt = parse_args(argparse.ArgumentParser()).parse_args()
    render(opt)
