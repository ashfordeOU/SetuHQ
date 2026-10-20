"""A run's code note: when a stored run was made with older code whose results a later fix would change, its
manifest carries ``code_note``, and every page built from the run (or from a catalogue that carries one) shows it
in a banner at the bottom of the window."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

PRE_FIX_NOTE = ("Pre-fix code: made with exoplan up to commit 5a03087, before two fixes that change default results: "
                "preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and vet.py's "
                "odd/even test no longer fails clean deep planets. Not re-run since.")

# Fixed to the bottom of the window, so it never changes the layout of a page whose panes fit the window exactly; on a
# page that scrolls, the body gets bottom padding equal to the banner's height, so nothing stays hidden under it. The
# banner takes taps itself (a tap on its text does not reach a link underneath), its dismiss button is 44 x 44 px,
# and a dismissal is remembered in localStorage (when the browser allows it).
BANNER_STYLE = ("position:fixed;left:0;right:0;bottom:0;z-index:2147483000;margin:0;padding:8px 60px 8px 16px;"
                "font:13px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;background:rgba(74,56,0,.96);"
                "color:#fff3cc;border-top:1px solid #a57c00;box-sizing:border-box")
BUTTON_STYLE = ("position:absolute;right:6px;top:50%;transform:translateY(-50%);width:44px;height:44px;"
                "background:none;border:1px solid #a57c00;color:#fff3cc;border-radius:6px;font:20px/1 system-ui,"
                "sans-serif;cursor:pointer")
BANNER_JS = """(function(){var b=document.getElementById('codenote');if(!b)return;var k='exoplan-codenote:'+b.dataset.key;
try{if(window.localStorage.getItem(k)){b.remove();return;}}catch(e){}
function pad(){var r=document.documentElement;document.body.style.paddingBottom='';
if(r.scrollHeight>window.innerHeight+1){document.body.style.paddingBottom=b.offsetHeight+'px';}}
window.addEventListener('load',pad);window.addEventListener('resize',pad);
b.querySelector('button').addEventListener('click',function(){try{window.localStorage.setItem(k,'1');}catch(e){}
document.body.style.paddingBottom='';b.remove();});})();"""


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def with_code_note(page: str, note: str | None) -> str:
    """The page with ``note`` as a banner (fixed to the bottom of the window, dismissable) inserted right after the
    opening ``<body>`` tag; the page is unchanged without a note."""
    if not note:
        return page
    key = hashlib.sha256(note.encode()).hexdigest()[:12]
    banner = (f'<div class="codenote" id="codenote" role="note" data-key="{key}" style="{BANNER_STYLE}">'
              f'{html.escape(note)}<button type="button" style="{BUTTON_STYLE}" aria-label="Dismiss this note">×</button>'
              f'</div><script>{BANNER_JS}</script>')
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + banner, page, count=1)
