"""A run's code note: when a stored run was made with older code whose results a later fix would change, its
manifest carries ``code_note``, and every page built from the run (or from a catalogue that carries one) shows it
in a banner: at the top of a page that scrolls, fixed to the bottom of one that fits the window."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

PRE_FIX_NOTE = ("Pre-fix code: made with exoplan up to commit 5a03087, before two fixes that change default results: "
                "preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and vet.py's "
                "odd/even test no longer fails clean deep planets. Not re-run since.")

# Where the note sits: on a page that scrolls, it is an ordinary block at the top of the body, so it never covers
# anything (a fixed bar covered whatever a user, a keyboard focus or a test scrolled to the bottom edge); on a page
# that fits the window exactly (the app's popped Mission panes), it is a bar fixed to the bottom of the window, so the
# page's fit is unchanged. The choice is re-made when the page loads, resizes or changes route. The dismiss button is
# 44 x 44 px, and a dismissal is remembered in localStorage when the browser allows it.
_COMMON = ("margin:0;padding:8px 60px 8px 16px;font:13px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;"
           "background:#4a3800;color:#fff3cc;box-sizing:border-box;z-index:2147483000")
BANNER_STYLE = "position:relative;border-bottom:1px solid #a57c00;" + _COMMON
FIXED_STYLE = ("position:fixed;left:0;right:0;bottom:0;border-top:1px solid #a57c00;" + _COMMON
               + ";padding-right:116px;min-height:52px;display:flex;align-items:center")
# In the fixed bar the note is one line, cut with an ellipsis, and a "more" button opens it in full (on a phone the
# whole note took 126 px of a fit-to-window page); in the flow at the top of a scrolling page it is always in full.
CLAMP_STYLE = "display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1"
MORE_STYLE = ("position:absolute;right:56px;top:50%;transform:translateY(-50%);min-width:52px;height:44px;"
              "background:none;border:0;color:#ffd866;text-decoration:underline;font:13px/1 system-ui,sans-serif;"
              "cursor:pointer")
BUTTON_STYLE = ("position:absolute;right:6px;top:50%;transform:translateY(-50%);width:44px;height:44px;"
                "background:none;border:1px solid #a57c00;color:#fff3cc;border-radius:6px;font:20px/1 system-ui,"
                "sans-serif;cursor:pointer")
BANNER_JS = """(function(){var b=document.getElementById('codenote');if(!b)return;var k='exoplan-codenote:'+b.dataset.key;
try{if(window.localStorage.getItem(k)){b.remove();return;}}catch(e){}
var FLOW=b.getAttribute('style'),FIXED=b.dataset.fixed,CLAMP=b.dataset.clamp,open=false;
var t=b.querySelector('.cn-text'),m=b.querySelector('.cn-more');
function place(){if(!b.isConnected)return;b.setAttribute('style',FIXED);
var fits=document.documentElement.scrollHeight<=window.innerHeight+1;
if(fits){t.setAttribute('style',open?'':CLAMP);m.style.display='';m.textContent=open?'less':'more';
m.setAttribute('aria-expanded',open?'true':'false');}
else{b.setAttribute('style',FLOW);t.setAttribute('style','');m.style.display='none';}}
m.addEventListener('click',function(){open=!open;place();});
place();window.addEventListener('load',place);window.addEventListener('resize',place);
window.addEventListener('hashchange',function(){setTimeout(place,60);});
if(window.ResizeObserver){new ResizeObserver(function(){place();}).observe(document.body);}
b.querySelector('.cn-close').addEventListener('click',function(){try{window.localStorage.setItem(k,'1');}catch(e){}
b.remove();});})();"""


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def with_code_note(page: str, note: str | None) -> str:
    """The page with ``note`` as a dismissable banner inserted right after the opening ``<body>`` tag (see the
    comment above :data:`BANNER_STYLE` for where it sits); the page is unchanged without a note."""
    if not note:
        return page
    key = hashlib.sha256(note.encode()).hexdigest()[:12]
    banner = (f'<div class="codenote" id="codenote" role="note" data-key="{key}" data-fixed="{FIXED_STYLE}" '
              f'data-clamp="{CLAMP_STYLE}" style="{BANNER_STYLE}">'
              f'<span class="cn-text">{html.escape(note)}</span>'
              f'<button type="button" class="cn-more" style="{MORE_STYLE};display:none" aria-expanded="false">more'
              f'</button><button type="button" class="cn-close" style="{BUTTON_STYLE}" aria-label="Dismiss this note">×'
              f'</button></div><script>{BANNER_JS}</script>')
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + banner, page, count=1)
