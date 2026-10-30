# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Site features shared across pages: every labelled figure's "Source / limits", first-visit hints, and the styles and
scripts of /explore/tess-now/ (:mod:`setuhq.tessnow`), /candidates/be-the-vetter/ (:mod:`setuhq.vetter`) and
/editions/ (:mod:`setuhq.editions`).

* **Source / limits.** On every stage that carries one of the five labels, the script adds a ``<details>`` (a
  keyboard-operable disclosure; Escape closes it) built from the figure's own label and caption: what the label
  means, the source the caption names, and the figure's ``data-limits`` when it states its own. It overlays the stage,
  so nothing moves when it is added.
* **First-visit hints.** A figure with ``data-hint`` (the orbits, V08: "Sizes not to scale · phases illustrative")
  shows the hint on the stage until it is dismissed; the dismissal is kept in localStorage when the browser allows it.
"""

from __future__ import annotations

from setuhq.i18n import N_

from setuhq import editions, tessnow, vetter

# What each label means and what it does not claim (the five labels of docs/SITE.md).
LIMITS = {
    "real data, cited": N_("limits.real", "Stored measurements, binned or folded as stored."),
    "model from stored values": N_("limits.model", "A model drawn from stored numbers; not an image of the object."),
    "artist's impression": N_("limits.art", "Not an observation: a look chosen from measured radius and irradiation."),
    "illustration": N_("limits.illustration", "Explains an idea; not data."),
    "speculative model": N_("limits.speculative", "Beyond what is measured: a possibility, not a result."),
}
LIMIT_IDS = {"label.real": "real data, cited", "label.model": "model from stored values", "label.art": "artist's impression",
             "label.illustration": "illustration", "label.speculative": "speculative model"}

CSS = """
.srclim{position:absolute;right:10px;bottom:10px;z-index:3;color:var(--stage-ink);font-size:12px}
.srclim summary{cursor:pointer;padding:4px 9px;border-radius:var(--r-xs);background:var(--stage-tag-bg);font:500 11px/1.6 var(--mono)}
.srclim[open]{left:10px;top:10px;display:flex;flex-direction:column-reverse;gap:6px}.srclim[open] summary{align-self:flex-end}
.srclim div,.fxhint{padding:8px 10px;border-radius:var(--r-xs);background:#0B0F18;color:var(--stage-ink)}.srclim p{margin:0 0 4px}
.fxhint{position:absolute;left:10px;top:10px;z-index:3;margin:0;padding:2px 2px 2px 10px;font:500 12px var(--mono)}
""" + tessnow.CSS + vetter.CSS + editions.CSS

# The shell's part (site-<hash>.js, with SetuUI's other figure utilities): runs on every page, the deploy-time stubs
# included; the app calls SetuUI.limits(root) for each view it shows and each figure it draws later.
SHELL_JS = r"""
(function(){
const LIM = """ + __import__("json").dumps(LIMITS, ensure_ascii=False) + r""", LID = """ + __import__("json").dumps(LIMIT_IDS, ensure_ascii=False) + r""", K = 'setuhq-hints', q = (s, e) => Array.from((e || document).querySelectorAll(s));
const TT = (id, en, a) => window.SetuI18n ? SetuI18n.T(id, en, a) : en;
const esc = s => String(s).replace(/[&<>"]/g, c => '&#' + c.charCodeAt(0) + ';'), seen = () => { try { return JSON.parse(localStorage.getItem(K)) || []; } catch (e) { return []; } };
SetuUI.limits = root => q('.stage-tag', root).forEach(tag => {
  if (window.SetuI18n) SetuI18n.apply(tag);
  const st = tag.closest('.stage'); if (!st || st._sl || (st.offsetWidth && st.offsetWidth < 200)) return; st._sl = 1;
  const id = tag.dataset.i18n, en = LID[id] || tag.textContent.trim().toLowerCase(), fig = st.closest('figure') || st, lab = tag.textContent.trim(), cap = fig.querySelector('figcaption') || document.getElementById(fig.getAttribute('aria-labelledby') || '-'), h = fig.dataset.hint;
  const src = ((cap && cap.textContent.match(/Sources?:\s*([^]*?)(?:\.\s+(?=[A-Z])|\.?\s*$)/)) || [])[1];
  const lim = LIM[en] ? TT('limits.' + (id || '').slice(6), LIM[en]) : '', s = src ? esc(src) : TT('limits.caption', 'as the caption states');
  st.insertAdjacentHTML('beforeend', `<details class="srclim"><summary>${TT('limits.summary', 'Source / limits')}</summary><div><p><b>${esc(lab)}.</b> ${lim}</p><p>${TT('limits.source', 'Source: {s}.', {s})}</p></div></details>`
    + (h && !seen().includes(h) ? `<p class="fxhint">${esc(TT('hint.orbits', h))} <button type="button" class="btn" data-fxh="${esc(h)}" aria-label="${TT('hint.dismiss', 'Dismiss the hint: {h}', {h: TT('hint.orbits', h)})}">×</button></p>` : ''));
});
addEventListener('click', e => {
  const b = e.target.closest('[data-fxh]'), c = e.target.closest('[data-copy]');
  if (b){ const s = seen(), m = b.closest('.stage').querySelector('summary'); s.push(b.dataset.fxh); try { localStorage.setItem(K, JSON.stringify(s)); } catch (x) {}
    q('.fxhint').forEach(p => p.lastChild.dataset.fxh === b.dataset.fxh && p.remove()); m.focus(); }
  if (c){ const say = c.parentNode.querySelector('[role=status]'), no = () => { getSelection().selectAllChildren(c.previousElementSibling); say.textContent = 'Address selected: press Ctrl or Cmd C'; };
    navigator.clipboard ? navigator.clipboard.writeText(c.dataset.copy).then(() => { say.textContent = 'Copied ' + c.dataset.copy; }, no) : no(); }
});
addEventListener('keydown', e => { const d = e.key === 'Escape' && e.target.closest && e.target.closest('.srclim[open]'); if (d){ d.open = false; d.firstChild.focus(); } });
})();
"""
N_("hint.orbits", "Sizes not to scale · phases illustrative", note="A first-visit hint on the orbit figures.")
# The app's part (app-<hash>.js): the two pages' own wiring, run by the router the first time each page shows.
JS = tessnow.JS + vetter.JS
