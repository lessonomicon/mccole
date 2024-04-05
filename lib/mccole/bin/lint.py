"""Check project."""

import argparse
import ark
from bs4 import BeautifulSoup, Tag
import importlib.util
from pathlib import Path
import re
import shortcodes
import yaml

UNIQUE_KEYS = {
    "fig_def",
    "gloss",
    "tbl_def",
}


def main():
    options = parse_args()
    options.config = load_config(options)
    found = collect_all()
    for func in [
        check_bib,
        check_fig,
        check_gloss,
        check_tbl,
        check_xref,
    ]:
        func(options, found)


def check_bib(options, found):
    """Check bibliography citations."""
    expected = get_bib_keys(options)
    compare_keys("bibliography", expected, found["bib"])


def check_fig(options, found):
    """Check figure definitions and citations."""
    compare_keys("figure", set(found["fig_def"].keys()), found["fig_ref"])


def check_gloss(options, found):
    """Check glossary citations."""
    expected = get_gloss_keys(options)
    compare_keys("gloss", expected, found["gloss"])


def check_tbl(options, found):
    """Check table definitions and citations."""
    compare_keys("table", set(found["tbl_def"].keys()), found["tbl_ref"])


def check_xref(options, found):
    """Check chapter/appendix cross-references."""
    expected = options.config.chapters + options.config.appendices
    compare_keys("cross-ref", expected, found["xref"], unused=False)


def collect_all():
    """Collect values from Markdown files."""
    parser = shortcodes.Parser(inherit_globals=False, ignore_unknown=True)
    parser.register(collect_bib, "b")
    parser.register(collect_fig_def, "figure")
    parser.register(collect_fig_ref, "f")
    parser.register(collect_gloss, "g")
    parser.register(collect_tbl_def, "table")
    parser.register(collect_tbl_ref, "t")
    parser.register(collect_xref, "x")
    collected = {
        "bib": {},
        "fig_def": {},
        "fig_ref": {},
        "gloss": {},
        "tbl_def": {},
        "tbl_ref": {},
        "xref": {},
    }
    ark.nodes.root().walk(
        lambda node: collect_visitor(node, parser, collected)
    )
    return collected


def collect_bib(pargs, kwargs, found):
    """Collect data from a bibliography reference shortcode."""
    found["bib"].update(pargs)


def collect_fig_def(pargs, kwargs, found):
    """Collect data from a figure definition shortcode."""
    slug = kwargs["slug"]
    if slug in found["fig_def"]:
        print(f"Duplicate definition of figure slug {slug}")
    else:
        found["fig_def"].add(slug)


def collect_fig_ref(pargs, kwargs, found):
    """Collect data from a figure reference shortcode."""
    found["fig_ref"].add(pargs[0])


def collect_gloss(pargs, kwargs, found):
    """Collect data from a glossary reference shortcode."""
    found["gloss"].add(pargs[0])


def collect_tbl_def(pargs, kwargs, found):
    """Collect data from a table definition shortcode."""
    slug = kwargs["slug"]
    if slug in found["tbl_def"]:
        print("Duplicate definition of table slug {slug}")
    else:
        found["tbl_def"].add(slug)


def collect_tbl_ref(pargs, kwargs, found):
    """Collect data from a table reference shortcode."""
    found["tbl_ref"].add(pargs[0])


def collect_xref(pargs, kwargs, found):
    """Collect data from a cross-reference shortcode."""
    found["xref"].add(pargs[0])


def collect_visitor(node, parser, collected):
    """Visit each node, collecting data."""
    found = {
        "bib": set(),
        "fig_def": set(),
        "fig_ref": set(),
        "gloss": set(),
        "tbl_def": set(),
        "tbl_ref": set(),
        "xref": set(),
    }
    parser.parse(node.text, found)
    for kind in found:
        reorganize_found(node, kind, collected, found)


def compare_keys(kind, expected, actual, unused=True):
    """Check two sets of keys."""
    for key, slugs in actual.items():
        if key not in expected:
            print(f"unknown {kind} key {key} used in {listify(slugs)}")
        else:
            expected.remove(key)
    if unused and expected:
        print(f"unused {kind} keys {listify(expected)}")


def get_bib_keys(options):
    """Get actual bibliography keys."""
    text = Path(options.root, "info", "bibliography.bib").read_text()
    return set(re.findall(r"^@.+?\{(.+?),$", text, re.MULTILINE))


def get_gloss_keys(options):
    """Get actual glossary keys."""
    text = Path(options.root, "info", "glossary.yml").read_text()
    glossary = yaml.safe_load(text) or []
    if isinstance(glossary, dict):
        glossary = [glossary]
    return {entry["key"] for entry in glossary}


def listify(values):
    """Format values for printing."""
    return ", ".join(sorted(list(values)))


def load_config(options):
    """Load configuration file as module."""
    filename = Path(options.root, "config.py")
    spec = importlib.util.spec_from_file_location("config", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args():
    """Parse arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dom", required=True, help="DOM specification file")
    parser.add_argument("--html", nargs="+", default=[], help="HTML pages")
    parser.add_argument("--root", required=True, help="Root directory")
    return parser.parse_args()


def reorganize_found(node, kind, collected, found):
    """Copy found keys into overall collection."""
    for key in found[kind]:
        if key not in collected[kind]:
            collected[kind][key] = set()
        elif kind in UNIQUE_KEYS:
            print(f"{kind} key {key} redefined")
        slug = node.slug if node.slug else "@root"
        collected[kind][key].add(slug)


if __name__ == "__main__":
    main()
