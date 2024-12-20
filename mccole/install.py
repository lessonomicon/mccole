"""Install files needed for building sites."""

import argparse
import importlib.resources
from pathlib import Path
import sys


INSTALL_FILES = (
    "templates/page.html",
    "templates/slides.html",
    "static/page.css",
    "static/slides.css",
    "static/slides.js",
)


def install(opt):
    """Install package files."""
    outdir = Path(opt.root)
    outdir.mkdir(parents=True, exist_ok=True)
    root = importlib.resources.files(__name__.split(".")[0])
    mapping = {
        root.joinpath(filename): outdir.joinpath(Path(filename))
        for filename in INSTALL_FILES
    }

    exists = {str(dst) for dst in mapping.values() if dst.exists()}
    if exists and (not opt.force):
        print(f'not overwriting {", ".join(sorted(exists))} (use --force)', file=sys.stderr)
        sys.exit(1)

    for src, dst in mapping.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    

def parse_args(parser):
    """Parse command-line arguments."""
    parser.add_argument("--force", action="store_true", help="overwrite")
    parser.add_argument("--root", type=str, default=".", help="root directory")
    return parser


if __name__ == "__main__":
    opt = parse_args(argparse.ArgumentParser()).parse_args()
    install(opt)
