# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The Learn path: an optional guided sequence through the Methods chapters, SetuHQ's own Transit case,
the Galaxy and the Catalogue, started from the Overview.

Nothing is required: every step is an ordinary page, any visit counts as seen, and the path bar appears only
after the viewer starts the path. Progress is kept in this browser (localStorage, wrapped in try/catch) and
the page works the same when storage is blocked.
"""

from __future__ import annotations

import html

from setuhq.i18n import N_, k, ka, span
from setuhq.methods import CHAPTERS

LEARN_KEY = "setuhq-learn"


def learn_steps() -> list[dict]:
    """The path, in order: each Methods chapter, with SetuHQ's own Transit case after the transit chapter,
    then the Galaxy and the Catalogue."""
    steps = []
    for cid, title in CHAPTERS:
        steps.append({"id": "ch:" + cid, "label": title, "lid": f"chapter.{cid}", "href": f"#/methods?ch={cid}", "kind": KIND["ch"], "kid": "learn.kind.ch"})
        if cid == "transit":
            steps.append({"id": "transit", "label": STEP["transit"], "lid": "learn.step.transit", "href": "#/transit", "kind": KIND["run"], "kid": "learn.kind.run"})
    steps.append({"id": "galaxy", "label": STEP["galaxy"], "lid": "learn.step.galaxy", "href": "#/galaxy", "kind": KIND["galaxy"], "kid": "learn.kind.galaxy"})
    steps.append({"id": "catalogue", "label": STEP["catalogue"], "lid": "learn.step.catalogue", "href": "#/catalogue", "kind": KIND["catalogue"], "kid": "learn.kind.catalogue"})
    return steps


KIND = {"ch": N_("learn.kind.ch", "Methods chapter"), "run": N_("learn.kind.run", "SetuHQ's run"),
        "galaxy": N_("learn.kind.galaxy", "Galaxy"), "catalogue": N_("learn.kind.catalogue", "Catalogue")}
STEP = {"transit": N_("learn.step.transit", "SetuHQ's own transit: the case file"),
        "galaxy": N_("learn.step.galaxy", "Every known exoplanet, around the Sun"),
        "catalogue": N_("learn.step.catalogue", "Every record, searchable")}


def learn_card() -> str:
    """The Overview's Learn path card. The page fills in progress and the next step."""
    e = html.escape
    steps = learn_steps()
    items = "".join(f'<li data-step="{e(s["id"])}"><a href="{e(s["href"])}"><span class="lnum mono">{n + 1:02d}</span>'
                    f'<span class="ltxt"><span{k(s["lid"])}>{e(s["label"])}</span><span class="lkind"{k(s["kid"])}>{e(s["kind"])}</span></span><span class="ltick" aria-hidden="true"></span>'
                    f'<span class="sr lseen"{k("learn.unseen")}>, not visited yet</span></a></li>' for n, s in enumerate(steps))
    return f"""<section class="card learncard" id="learncard" aria-labelledby="h-learn">
        <div class="learnhead"><div><h2 id="h-learn"{k("learn.h")}>Learn path</h2>
          <p>{span("learn.intro", "{n} steps, from how a survey works to every known exoplanet. Optional: go in order or skip around; any page you open counts. Progress stays in this browser.", n=len(steps))}</p></div>
          <div class="learnbtns"><a class="btn primary" id="learngo" href="{e(steps[0]["href"])}"{k("learn.start")}>Start the path</a><button class="btn" type="button" id="learnreset"{k("learn.reset")}>Reset progress</button></div></div>
        <div class="learnmeter" role="progressbar" aria-label="Learn path progress"{ka(aria_label="learn.progress")} aria-valuemin="0" aria-valuemax="{len(steps)}" aria-valuenow="0"><i id="learnfill"></i></div>
        <p class="mono learncount" id="learncount">{span("learn.count", "{k} of {n} visited", k=0, n=len(steps))}</p>
        <details class="learnlist"><summary>{span("learn.all", "All {n} steps", n=len(steps))}</summary><ol id="learnsteps">{items}</ol></details>
      </section>"""


LEARN_BAR = f"""<nav class="learnbar" id="learnbar" aria-label="Learn path"{ka(aria_label="learn.h")} hidden>
  <span class="lpos mono" id="learnpos"></span><a class="btn" id="learnprev" href="#/"{k("learn.back")}>‹ Back</a><a class="btn primary" id="learnnext" href="#/"{k("learn.next_btn")}>Next ›</a>
  <button class="btn" type="button" id="learnleave" aria-label="Leave the path"{ka(aria_label="learn.leave_label")}{k("learn.leave")}>Leave</button>
</nav>"""
N_("learn.h", "Learn path")
N_("learn.start", "Start the path")
N_("learn.reset", "Reset progress")
N_("learn.progress", "Learn path progress")
N_("learn.unseen", ", not visited yet")
N_("learn.back", "‹ Back")
N_("learn.next_btn", "Next ›")
N_("learn.leave", "Leave")
N_("learn.leave_label", "Leave the path")


LEARN_CSS = r"""
/* ---------- the Learn path ---------- */
.learncard{display:grid;gap:12px}
.learnhead{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;justify-content:space-between}
.learnhead h2{margin:0 0 4px}
.learnhead p{margin:0;max-width:62ch;color:var(--ink-2)}
.learnbtns{display:flex;flex-wrap:wrap;gap:8px}
.learnbtns .btn{min-height:44px}
.learnmeter{height:8px;border-radius:999px;background:var(--line);overflow:hidden}
.learnmeter i{display:block;height:100%;width:0;background:var(--blue);border-radius:999px;transition:width var(--d-3) var(--ease)}
.learncount{margin:0;font-size:12px;color:var(--ink-3)}
.learnlist summary{display:flex;align-items:center;gap:8px;min-height:44px;cursor:pointer;font-weight:600;list-style:none}
.learnlist summary::-webkit-details-marker{display:none}
.learnlist summary::before{content:"›";display:inline-block;transition:transform var(--d-1) var(--ease);color:var(--ink-3)}
.learnlist[open] summary::before{transform:rotate(90deg)}
.learnlist ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:4px}
.learnlist a{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;min-height:48px;padding:4px 10px;border-radius:12px;color:var(--ink);text-decoration:none}
.learnlist a:hover{background:var(--panel-2)}
.lnum{font-size:12px;color:var(--ink-3)}
.ltxt{display:grid;font-size:14px}
.lkind{font-size:11px;color:var(--ink-3)}
.ltick{width:18px;height:18px;border-radius:50%;border:1.5px solid var(--line-3)}
li[data-seen="1"] .ltick{background:var(--green);border-color:var(--green);box-shadow:inset 0 0 0 3px var(--bg-2)}
li[data-next="1"] a{background:var(--panel-2)}
.learnbar{position:fixed;left:50%;bottom:max(12px,env(safe-area-inset-bottom));transform:translateX(-50%);z-index:40;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:8px;
  width:max-content;max-width:calc(100vw - 24px);padding:8px;border-radius:22px;background:var(--bg-2);background:color-mix(in srgb,var(--bg-2) 90%,transparent);border:1px solid var(--line-2);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);box-shadow:0 10px 30px rgba(0,0,0,.35)}
.learnbar[hidden]{display:none}
.learnbar .btn{min-height:44px}
.learnbar .lpos{font-size:12px;color:var(--ink-2);padding:0 6px;max-width:42ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
body.learning main{padding-bottom:96px}
body.learning .ctscroll{height:min(calc(64vh - 76px),640px)}
@media (max-width:699.98px){
  .learnbar{left:12px;right:12px;transform:none;width:auto;flex-wrap:wrap;gap:6px}
  .learnbar .lpos{flex-basis:100%;text-align:center}
  .learnbar .lnt,.learnbar .lpre{display:none}
  body.learning main{padding-bottom:120px}
  body.learning .ctscroll{height:calc(70vh - 100px)}
  body.learning .gxsheet{bottom:calc(98px + env(safe-area-inset-bottom,0px))}
}
@media (prefers-reduced-motion: reduce){.learnmeter i,.learnlist summary::before{transition:none}}
"""


LEARN_JS = r"""
// ---------- the Learn path: optional, any visit counts, progress kept in this browser ----------
const LEARN = D.learn || [];
const LEARN_KEY = 'setuhq-learn';
function learnRead(){
  try { const s = getStorage(), raw = s && s.getItem(LEARN_KEY), v = raw ? JSON.parse(raw) : null;
    if (v && Array.isArray(v.seen)) return {seen: v.seen.filter(id => LEARN.some(x => x.id === id)), active: !!v.active}; } catch (e) { /* blocked or malformed */ }
  return {seen: [], active: false};
}
const learn = learnRead();
function learnSave(){ try { const s = getStorage(); if (s) s.setItem(LEARN_KEY, JSON.stringify({v: 1, seen: learn.seen, active: learn.active})); } catch (e) { /* storage blocked: progress lasts this visit */ } }
// Which step a route is: a Methods chapter, the Transit case, the Galaxy or the Catalogue.
function learnStepOf(p){
  if (!p) return null;
  if (p.route === 'methods') return 'ch:' + (MX && MX.chapters.includes(p.params.get('ch')) ? p.params.get('ch') : (MX ? MX.chapters[0] : ''));
  return ['transit', 'galaxy', 'catalogue'].includes(p.route) ? p.route : null;
}
function learnNext(){ return LEARN.find(x => !learn.seen.includes(x.id)) || null; }
function learnRender(){
  const card = $('#learncard'), n = LEARN.length, k = learn.seen.length;
  if (card){
    const nx = learnNext();
    $('#learnfill').style.width = (k / n * 100) + '%';
    card.querySelector('.learnmeter').setAttribute('aria-valuenow', String(k));
    $('#learncount').textContent = T('learn.count', '{k} of {n} visited', {k, n}) + (k === n ? T('learn.complete', ' · path complete') : '');
    const go = $('#learngo');
    go.textContent = !k ? T('learn.start', 'Start the path') : nx ? T('learn.continue', 'Continue: {step}', {step: T(nx.lid, nx.label)}) : T('learn.again', 'Start again from step 1');
    go.setAttribute('href', R((nx || LEARN[0]).href));
    $$('#learnsteps li').forEach(li => { const seen = learn.seen.includes(li.dataset.step); li.dataset.seen = seen ? '1' : '0'; li.dataset.next = nx && nx.id === li.dataset.step ? '1' : '0';
      li.querySelector('.lseen').textContent = seen ? T('learn.seen', ', visited') : T('learn.unseen', ', not visited yet'); });
  }
}
// The path bar: shown on a step's page once the viewer has started the path, with Back, Next and Leave.
function learnBar(step){
  const bar = $('#learnbar'), i = LEARN.findIndex(x => x.id === step), on = learn.active && i >= 0;
  bar.hidden = !on; document.body.classList.toggle('learning', on);
  if (!on) return;
  $('#learnpos').innerHTML = `<span class="lpre">${esc(T('learn.h', 'Learn path'))} · </span>${esc(T('learn.pos', '{i} of {n}', {i: i + 1, n: LEARN.length}))} · ${esc(T(LEARN[i].lid, LEARN[i].label))}`;
  const prev = LEARN[i - 1], next = LEARN[i + 1];
  // Never hide the button that has focus: on step 1, Back hands focus to Next first.
  if (!prev && document.activeElement === $('#learnprev')) $('#learnnext').focus();
  $('#learnprev').hidden = !prev; if (prev) $('#learnprev').setAttribute('href', R(prev.href));
  $('#learnnext').innerHTML = next ? `${esc(T('learn.next', 'Next'))}<span class="lnt">: ${esc(T(next.lid, next.label))}</span> ›` : esc(T('learn.finish', 'Finish ›'));
  $('#learnnext').setAttribute('aria-label', next ? T('learn.next_label', 'Next: {step}', {step: T(next.lid, next.label)}) : T('learn.finish_label', 'Finish the path')); $('#learnnext').setAttribute('href', next ? R(next.href) : '/');
}
function learnVisit(p){
  const step = learnStepOf(p);
  if (step && !learn.seen.includes(step)){ learn.seen.push(step); learnSave(); }
  if (p && p.route === 'overview') learnRender();
  learnBar(step);
}
if ($('#learncard')){
  $('#learngo').addEventListener('click', () => { learn.active = true; if (learn.seen.length === LEARN.length) learn.seen = []; learnSave(); });
  $('#learnsteps').addEventListener('click', e => { if (e.target.closest('a')){ learn.active = true; learnSave(); } });
  $('#learnreset').addEventListener('click', () => { learn.seen = []; learn.active = false; learnSave(); learnRender(); say(T('learn.cleared', 'Learn path progress cleared.')); });
}
if ($('#learnbar')){
  // Leaving hides the bar, so focus moves to the page's heading (or main), not to <body>.
  $('#learnleave').addEventListener('click', () => { learn.active = false; learnSave(); learnBar(null);
    const h = $(`#route-${current} h1`) || $('#main'); if (h){ if (!h.hasAttribute('tabindex')) h.setAttribute('tabindex', '-1'); h.focus({preventScroll: true}); }
    say(T('learn.left', 'Left the Learn path. Your progress is kept.')); });
  $('#learnnext').addEventListener('click', () => { if ($('#learnnext').getAttribute('href') === '/'){ learn.active = false; learnSave(); } });
}
"""
