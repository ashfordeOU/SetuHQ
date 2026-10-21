# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""examples/quickstart.ipynb runs offline from the stored pi Men run, and is committed with its outputs cleared.

The notebook's code cells are run in order as one script in a fresh interpreter (no Jupyter kernel needed), with
a non-interactive matplotlib backend and no network: the same code a reader runs, cell by cell."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "examples" / "quickstart.ipynb"


def _notebook() -> dict:
    return json.loads(NB.read_text(encoding="utf-8"))


def test_outputs_are_cleared_and_wording_is_honest():
    nb = _notebook()
    assert nb["nbformat"] == 4
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None, cell["id"]
    text = " ".join("".join(c["source"]) for c in nb["cells"]).lower()
    assert "candidate, never a confirmation" in text
    for word in ("superintelligence", "confirmed planet", "we discovered", "discovered a planet"):
        assert word not in text, word


def test_notebook_runs_offline(tmp_path):
    code = [("".join(c["source"])) for c in _notebook()["cells"] if c["cell_type"] == "code"]
    script = tmp_path / "quickstart.py"
    script.write_text("\n\n".join(code) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    env.update(MPLBACKEND="Agg", SETUHQ_ROOT=str(ROOT), HTTPS_PROXY="http://127.0.0.1:9",
               HTTP_PROXY="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9", http_proxy="http://127.0.0.1:9")
    done = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-4000:]
    out = done.stdout
    assert "candidates in runs/tess-pi-men-s1" in out
    assert "counts:" in out and "Probe · Typical" in out
    assert "label: potential_planet" in out or "label: noise" in out
    assert "tools the server exposes: search_catalogue" in out
