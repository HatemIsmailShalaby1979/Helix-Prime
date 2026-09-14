"""PWA asset tests (P1.7).

The installable shell is three files plus icons: the manifest, the service
worker, and the offline page. These tests pin the shape the shell relies
on: the manifest parses and lists three icons, every icon file exists, the
service worker references a versioned cache name, and the offline page
exists so a failed navigation has something to show.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "helix_codex_app" / "static"


def test_manifest_parses_and_lists_three_icons() -> None:
    manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
    icons = manifest["icons"]
    assert isinstance(icons, list)
    assert len(icons) == 3
    purposes = {icon.get("purpose", "any") for icon in icons}
    assert "maskable" in purposes
    assert manifest["name"]
    assert manifest["start_url"] == "/app"
    assert manifest["display"] == "standalone"


def test_every_manifest_icon_file_exists() -> None:
    manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icon in manifest["icons"]:
        path = STATIC_DIR / icon["src"].replace("/static/", "")
        assert path.is_file(), icon["src"]
        assert path.stat().st_size > 0


def test_service_worker_exists_and_references_versioned_cache_name() -> None:
    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    match = re.search(r'CACHE_NAME\s*=\s*"([^"]+)"', sw)
    assert match is not None, "sw.js must define CACHE_NAME"
    assert re.search(r"-v\d+$", match.group(1)), "CACHE_NAME must be versioned"


def test_offline_page_exists() -> None:
    offline = STATIC_DIR / "offline.html"
    assert offline.is_file()
    text = offline.read_text(encoding="utf-8")
    assert "offline" in text.lower()
