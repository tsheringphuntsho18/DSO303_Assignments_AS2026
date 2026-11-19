#!/usr/bin/env python3
"""Render diagram.mmd to a PNG/SVG using the Mermaid CLI.

Usage:
    python3 architecture/generate_diagram.py [--format png|svg] [--scale 3]

Requires Node.js. Uses `npx -y @mermaid-js/mermaid-cli` so nothing has to be
installed globally first — the first run downloads the CLI and caches it.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MMD_FILE = HERE / "diagram.mmd"
CONFIG_FILE = HERE / "mermaid-config.json"

PUPPETEER_CONFIG = '{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["png", "svg"], default="png")
    parser.add_argument("--scale", type=int, default=3, help="Output scale factor (png only)")
    parser.add_argument("--theme", default="default", choices=["default", "dark", "neutral", "forest"])
    args = parser.parse_args()

    if not MMD_FILE.exists():
        print(f"error: {MMD_FILE} not found", file=sys.stderr)
        return 1

    if shutil.which("npx") is None:
        print(
            "error: Node.js/npx not found. Install Node.js, or paste the contents of "
            "diagram.mmd into https://mermaid.live and export the image manually.",
            file=sys.stderr,
        )
        return 1

    out_file = HERE / f"diagram.{args.format}"
    puppeteer_cfg = HERE / "puppeteer-config.json"
    puppeteer_cfg.write_text(PUPPETEER_CONFIG)

    cmd = [
        "npx", "-y", "@mermaid-js/mermaid-cli",
        "-i", str(MMD_FILE),
        "-o", str(out_file),
        "-b", "white",
        "-t", args.theme,
        "-p", str(puppeteer_cfg),
    ]
    if args.format == "png":
        cmd += ["-s", str(args.scale)]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)

    puppeteer_cfg.unlink(missing_ok=True)

    if result.returncode != 0:
        print(
            "\nRendering failed. Fallback: paste diagram.mmd into https://mermaid.live "
            "and use File > Export Image.",
            file=sys.stderr,
        )
        return result.returncode

    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
