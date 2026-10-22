// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Run in the page (page.evaluate): every visible element inside <main> whose visible right edge lies past the window.
// html and body hide sideways overflow, so a page can be wider than the window with no scroll bar: its text is then
// cut off at the right edge, and document.scrollWidth does not show it. This looks at each element instead.
// Not counted, by name: what sits inside a deliberate sideways scroller listed in SCROLLERS (wide tables and the
// like, which scroll on a phone), and decorative drawing (ART: canvas, svg) that may run past the edge on purpose.
// A scroller not on the list is reported (as "unlisted scroller"), so a new one is a decision, not an accident.
// What an ancestor hides with overflow (other than html and body) is cut to that ancestor first.
(() => {
  const W = document.documentElement.clientWidth;
  const out = [];
  const ART = "canvas, svg, svg *, .planetfig, .planetfig *";
  const SCROLLERS = "%SCROLLERS%";
  const scroller = (el) => { const s = getComputedStyle(el); return /(auto|scroll)/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1; };
  const name = (el) => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).join(".") : "");
  for (const el of document.querySelectorAll("main *")) {
    if (scroller(el) && !el.matches(SCROLLERS) && el.getBoundingClientRect().width > 1 && !el.closest("[hidden]")) out.push(`unlisted scroller ${name(el)}`);
  }
  for (const el of document.querySelectorAll("main *")) {
    if (el.matches(ART)) continue;
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "contents") continue;
    let r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;  // empty, or screen-reader-only text
    let right = r.right, left = r.left, skip = false;
    for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      if (a.hidden || getComputedStyle(a).display === "none") { skip = true; break; }
      if (scroller(a) && a.matches(SCROLLERS)) { skip = true; break; }
      const o = getComputedStyle(a).overflowX;
      if (o !== "visible") { const q = a.getBoundingClientRect(); right = Math.min(right, q.right); left = Math.max(left, q.left); }
    }
    if (skip || right - left < 2) continue;
    if (right > W + 1) {
      out.push(`${name(el)} right=${Math.round(right)} "${(el.textContent || "").trim().slice(0, 30)}"`);
    }
  }
  return out.slice(0, 40);
})()
