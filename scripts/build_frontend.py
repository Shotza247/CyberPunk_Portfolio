from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FILES = (
    "index.html",
    "admin.html",
    "styles.css",
    "admin.css",
    "theme-init.js",
    "portfolio.js",
    "profile-assistant.js",
    "badge-admin.js",
)


def validate_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PORTFOLIO_API_BASE_URL must be an HTTP(S) origin without credentials or query.")
    return value.rstrip("/")


def build(output_dir: Path, api_url: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in FRONTEND_FILES:
        shutil.copy2(ROOT / filename, output_dir / filename)

    images = ROOT / "images"
    if images.is_dir():
        shutil.copytree(images, output_dir / "images", dirs_exist_ok=True)

    api_origin = json.dumps(validate_api_url(api_url))
    config = f"window.PORTFOLIO_API_BASE_URL = {api_origin};\n"
    (output_dir / "api-config.js").write_text(config, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Render static portfolio frontend.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--api-url",
        default=os.getenv("PORTFOLIO_API_BASE_URL"),
        help="Public Vercel API origin; defaults to PORTFOLIO_API_BASE_URL.",
    )
    args = parser.parse_args()
    if not args.api_url:
        parser.error("Set PORTFOLIO_API_BASE_URL to the deployed API origin before building.")

    try:
        build(args.output_dir.resolve(), args.api_url)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
