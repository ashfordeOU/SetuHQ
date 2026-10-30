# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""/editions/: the open core, SetuHQ Pro and a custom study, compared row by row; the licences; CHEOPS's carve-out.

Facts, kept with docs/PRO.md and LICENSING.md: the open core is the whole engine, free, under the AGPL-3.0-only or a
commercial licence from Ashforde OÜ, with no feature gate. SetuHQ Pro is a proprietary overlay on the same engine,
offered under contract and in development: every Pro capability on the page is labelled "in development", and the page
never says Pro is live. There are no prices anywhere; every paid route starts with a message to
:data:`CONTACT`, shown as text the visitor can select, with a copy button. CHEOPS-derived features are never part of
Pro or of the commercial licence (CC BY-NC 3.0 IGO).
"""

from __future__ import annotations

from setuhq.i18n import N_, k as ik, span, t, th

import html
from urllib.parse import quote

from setuhq import brand

CONTACT = "contact@ashforde.org"
DEV = "in development"
ROWS = ("Why it matters", "Who it is for", "What is included", "Terms", "How to start")

OPEN = {
    "Why it matters": "Anyone can search a TESS light curve, see every check behind a verdict and repeat the numbers. The open core is the "
                      "whole engine, and everything on this site runs on it.",
    "Who it is for": ["Researchers, students and reviewers who need results they can rerun and cite",
                      "Contributors who run a sweep and send it in", "Developers who wire SetuHQ into code or an AI assistant over MCP"],
    "What is included": ["The search, the Sentinels and Probes, vetting and the transit fit", "The frozen real-TOI benchmark and the public "
                         "leaderboard", "The sweep, the MCP server, this site and the stand-alone case files, plates and reports",
                         "Flares, pulsations and public CHEOPS light curves (CHEOPS data under ESA's terms)"],
    "Terms": "Free under the AGPL-3.0-only, with no feature gate. The same code is also offered under a commercial licence from Ashforde OÜ.",
}
PRO = {
    "Why it matters": "Institutions need what a public repository cannot give: scale, privacy, packaging and accountability. Pro sells those, "
                      "never better science: every Pro number would come from the open engine, which anyone can rerun for free.",
    "Who it is for": ["Follow-up and mission teams that keep work private until release", "AI providers and research groups that want a "
                      "reviewer measured on the frozen benchmark", "Universities, planetariums and app makers"],
    "What is included": [("Pro Calibrate", "a calibration certificate for an AI reviewer on the frozen 662-TOI benchmark"),
                         ("Pro Workspace", "private target lists, embargoed candidates, team roles and an audit trail"),
                         ("Pro Sweeps", "hosted searches over sectors or target lists, with the customer's own AI provider key; results "
                          "come back as open contribution bundles"),
                         ("Pro Follow-up", "a follow-up packet per candidate: an ExoFOP-style export, an ephemeris with its uncertainty, "
                          "and when the target is observable from the customer's telescopes"),
                         ("Education & Dome", "classroom vetting exercises and a planetarium edition"),
                         ("Commercial licence & SDK", "the engine inside a closed product, with a stable API")],
    "Terms": "Available under contract, as a proprietary overlay that depends on the open core and never forks it. No free feature moves "
             "behind a licence. Pro is in development: nothing in this column is live yet.",
}
STUDY = {
    "Why it matters": "When the question is yours but the time is not: Ashforde OÜ runs the open engine on your question and hands back a "
                      "result you can rerun with the free code.",
    "Who it is for": ["Teams that need a sector sweep or a candidate dossier", "Instrument teams that want a yield study"],
    "What is included": ["A sector sweep, a candidate dossier or a yield study for a proposed instrument", "The open engine as it is: "
                         "no new code, every figure labelled as on this site", "Candidates stay candidates: a study is never a "
                         "confirmation of a planet"],
    "Terms": "Scoped to your question and delivered under contract.",
}


def _mailto(subject: str) -> str:
    return f"mailto:{CONTACT}?subject={quote(subject)}"


def _cell(v) -> str:
    e = html.escape
    if isinstance(v, str):
        return f"<p>{e(v)}</p>"
    items = []
    for x in v:
        if isinstance(x, tuple):
            items.append(f'<li><b>{e(x[0])}</b> <span class="eddev">{DEV}</span>: {e(x[1])}</li>')
        else:
            items.append(f"<li>{e(x)}</li>")
    return f'<ul>{"".join(items)}</ul>'


def mail_block(subject: str) -> str:
    """The contact address as selectable text, a copy button and a mail link with the route's subject."""
    return (f'<p class="edmail"><span>Write to</span> <code class="edaddr">{CONTACT}</code> '
            f'<button class="btn" type="button" data-copy="{CONTACT}" aria-label="Copy the address {CONTACT}">Copy</button>'
            f' <a href="{html.escape(_mailto(subject))}">or open your mail app</a> <span class="sr" role="status" aria-live="polite"></span></p>')


def section() -> str:
    e = html.escape
    cols = [("Open core", "Free · AGPL-3.0 or commercial licence", OPEN, '<a class="btn primary" href="/docs/">Get started</a>'),
            ("SetuHQ Pro", f"Available under contract · {DEV}", PRO,
             f'<a class="btn primary" href="{e(_mailto("SetuHQ Pro evaluation"))}">Request an evaluation</a>{mail_block("SetuHQ Pro evaluation")}'),
            ("Custom study", "Paid work, done for you", STUDY,
             f'<a class="btn" href="{e(_mailto("SetuHQ custom study"))}">Request a study</a>{mail_block("SetuHQ custom study")}')]
    head = "".join(f'<th scope="col"><span class="edname">{e(n)}</span><span class="edtag">{e(t)}</span></th>' for n, t, _, _ in cols)
    body = ""
    for r in ROWS:
        cells = "".join(f"<td>{start if r == 'How to start' else _cell(d[r])}</td>" for _, _, d, start in cols)
        body += f'<tr><th scope="row">{e(r)}</th>{cells}</tr>'
    return f"""<header><p class="eyebrow"{ik("nav.docs")}>Docs</p><h1 class="lead-h" id="h-editions" tabindex="-1"{ik("ed.h1")}>{t("ed.h1", "Editions.")}</h1>
        <p{ik("ed.intro")}>{t("ed.intro", "The whole engine is free, and stays free. Ashforde OÜ sustains it with a commercial licence, SetuHQ Pro and custom studies, not with a feature gate. There are no prices on this site: every paid route starts with a message.")}</p></header>
      <h2 id="ed-compare"{ik("ed.compare")}>{t("ed.compare", "Compare the editions")}</h2>
      <p{ik("ed.compare.p")}>{t("ed.compare.p", "Read across a row to compare the three.")}</p>
      <div class="tablewrap" tabindex="0" role="region" aria-labelledby="ed-compare"><table class="pltable edtable">
        <thead><tr><td></td>{head}</tr></thead><tbody>{body}</tbody></table></div>
      <p class="note"><b>Pro is in development.</b> Every Pro capability above is planned and labelled "{DEV}"; none is live, and none
        changes the science: Pro adds no detection, vetting or fitting method, and nothing it produces is a confirmation of a planet.
        What each one would build on is in <a rel="noopener" href="{brand.REPO_URL}/blob/main/docs/PRO.md">docs/PRO.md</a>.</p>
      <div class="prose">
        <h2 id="ed-licence">Licensing: one engine, two licences</h2>
        <p>The same code under either licence; nothing is held back from either.</p>
        <ul>
          <li><b>GNU AGPL-3.0-only.</b> Use, study, change and share SetuHQ for free. If you run a changed version as a network service,
            you offer its users the source.</li>
          <li><b>A commercial licence from Ashforde OÜ</b>, for use the AGPL does not suit: SetuHQ inside a closed product, or a hosted
            service without the source offer. It starts with a message.</li>
        </ul>
        {mail_block("SetuHQ commercial licence")}
        <p>SetuHQ's own data, benchmark, leaderboard data and paper are under CC BY 4.0; third-party data keeps its own terms. The plain-language
          guide: <a rel="noopener" href="{brand.REPO_URL}/blob/main/LICENSING.md">LICENSING.md</a>.</p>
        <h2 id="ed-cheops">CHEOPS data stay outside Pro and the commercial licence</h2>
        <p>SetuHQ reads public CHEOPS light curves. Those data, and every feature derived from them, stay under ESA's terms (CC BY-NC 3.0 IGO):
          they are never part of SetuHQ Pro or of the commercial licence, and any commercial use needs ESA's prior written authorisation
          (data.licences@esa.int). SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS
          mission or the CHEOPS Consortium. <a href="/docs/stellar/">The CHEOPS terms ›</a></p>
      </div>"""


CSS = """
.edtable{min-width:760px}.edtable td,.edtable th{font-family:var(--sans)}.edtable ul{margin:0;padding-left:18px}.edtable p{margin:0}.edname{display:block;font:600 16px var(--sans)}
.edtag,.eddev{font:500 12px var(--mono);color:var(--ink-3)}.eddev{color:var(--yellow)}.edmail{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.edaddr{user-select:all}
"""

