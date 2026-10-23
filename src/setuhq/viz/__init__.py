# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The site's visual components (the redesign's V01–V12), one module each, with fixed signatures:

* ``html(data, **opts) -> str``: the component's markup, readable without JavaScript, with its source line.
  It raises ValueError when ``data["source"]`` is missing: real data always shows where it comes from.
* ``CSS`` and ``JS``: its styles and code, concatenated here in a fixed order into :data:`VIZ_CSS` and
  :data:`VIZ_JS` (the site's stylesheet and the app's script carry them).
* optionally ``data(app_data) -> dict``: its section of a build-time data file; :func:`write_data` merges the
  sections by key (a key written twice is an error) into ``assets/data/stories-<hash>.json`` (and ``sky-<hash>.json``).

A component whose owner has not built it yet returns "" and its caller leaves the band out.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

ORDER = ("hero", "gallery", "tempstrip", "skyyears", "timeline", "lineup", "orbits", "panelring", "fold")
# The file each component's data() goes into (the rest have none).
DATA_FILE = {"hero": "stories", "gallery": "stories", "timeline": "stories", "lineup": "stories", "fold": "stories", "skyyears": "sky"}
DATA_BUDGET = {"stories": 40_000, "sky": 160_000}


def require_source(data) -> None:
    """Rule 1 of the honesty rules: a component that draws data names its source."""
    if not isinstance(data, dict) or not data.get("source"):
        raise ValueError("a visual component needs data['source']: real data always shows where it comes from")


def modules() -> list:
    return [importlib.import_module(f"setuhq.viz.{m}") for m in ORDER]


VIZ_CSS = "".join(m.CSS for m in modules())
VIZ_JS = "".join(m.JS for m in modules())


def collect(app_data: dict) -> dict[str, dict]:
    """Every component's data() section, merged into its file by key; a key two components write raises."""
    out: dict[str, dict] = {}
    for name in ORDER:
        mod = importlib.import_module(f"setuhq.viz.{name}")
        if not hasattr(mod, "data"):
            continue
        part = mod.data(app_data) or {}
        dest = out.setdefault(DATA_FILE.get(name, "stories"), {})
        for k, v in part.items():
            if k in dest:
                raise ValueError(f"viz.{name}: the data key {k!r} is already written by another component")
            dest[k] = v
    return out


def write_data(out_dir: str | Path, app_data: dict) -> dict[str, str]:
    """Write the build-time data files that have content; returns {file: its address}."""
    out_dir = Path(out_dir)
    paths = {}
    for name, body in collect(app_data).items():
        if not body:
            continue
        text = json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        rel = f"assets/data/{name}-{hashlib.sha256(text.encode()).hexdigest()[:10]}.json"
        (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / rel).write_text(text)
        paths[name] = "/" + rel
    return paths
