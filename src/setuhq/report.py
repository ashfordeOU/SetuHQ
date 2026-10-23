# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Static report site for a run: one HTML page with no build step and no external assets.

The page shows the run summary, a pipeline diagram, each dip with its vetting outcome and the blind-coded image
the reviewers saw, the known-planet validation, the injection benchmark and the provenance manifest.

It is drawn in the site's visual system (setuhq.design): the colour tokens under the report's own names
(``design.REPORT_ALIASES``), the light set for print (``design.PRINT_CSS``), self-hosted Geist and Geist Mono (copied
beside a stand-alone report), and a black stage at the top with the run's star as a static disc in its blackbody
colour (``renderer.star_svg``, from the Teff the run's stellar.json stores). No script beyond the theme choice, no
renderer and no WebGL: the page works opened from disk and printed. The theme follows the site's choice when one is
stored, else the device's.

The search feed's page (:func:`build_discovery_site`, ``setuhq discover``) uses the same sheet, with the feed's
tables and a static bar chart of its entries per night.
"""

from __future__ import annotations

import csv
import html
import json
import shutil
from pathlib import Path

from setuhq import brand
from setuhq.design import BASE_CSS, PRINT_CSS, REPORT_ALIASES, tokens_css
from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_count, dip_state, panel_mode, public_text

# The site's tokens under the report's own names (design.REPORT_ALIASES), the light set for print, the shared stage, and
# the report's layout in the site's type (self-hosted Geist, copied beside a stand-alone report).
REPORT_CSS = """
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:var(--t-body);letter-spacing:-.01em;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:var(--sen);text-underline-offset:2px}
:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:6px}
.wrap{max-width:1100px;margin:0 auto;padding:0 max(16px,env(safe-area-inset-left))}
header.hero{padding:24px 0 0}
.herostage{display:grid;grid-template-columns:auto minmax(0,1fr);gap:20px 28px;align-items:center;padding:24px 28px 26px}
.herostage .stardisc{width:clamp(88px,14vw,150px);height:auto;display:block}
.herostage .brandlogo{height:24px;width:auto;aspect-ratio:579/132;flex:none;max-width:none;display:block;margin-bottom:14px}
.herostage .kick{font:var(--t-eyebrow);letter-spacing:.14em;text-transform:uppercase;color:var(--stage-dim);margin:0 0 8px}
h1{font:var(--t-h1);letter-spacing:-.04em;margin:0 0 10px;text-wrap:balance}
.herostage h1{color:var(--stage-ink)}
p.lead{font:var(--t-lede);max-width:72ch;margin:0 0 8px;color:var(--stage-dim)}
.herostage .count{font:600 17px/1.35 var(--sans);color:var(--stage-ink);margin:0 0 6px}
.herostage .runstar{font:var(--t-data);color:var(--stage-dim);margin:0}
.herostage .probes{font:var(--t-small);color:var(--stage-ink);margin:8px 0 0}
h2{font:var(--t-h2);letter-spacing:-.02em;margin:44px 0 12px}
h3{font:var(--t-h3);letter-spacing:-.01em;margin:0 0 6px;overflow-wrap:anywhere}
nav{position:sticky;top:0;z-index:5;background:var(--glass);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);border-bottom:1px solid var(--line);margin-top:20px}
nav .wrap{display:flex;flex-wrap:wrap;gap:4px 14px;padding-top:4px;padding-bottom:4px}
summary{display:flex;align-items:center;min-height:44px;cursor:pointer}
nav a{color:var(--ink-2);text-decoration:none;white-space:nowrap;font-size:14px;font-weight:500;display:inline-flex;align-items:center;justify-content:center;min-height:44px;min-width:44px}
nav a:hover{color:var(--ink)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-l);padding:18px}
.stat{font:700 30px/1.1 var(--sans);letter-spacing:-.02em}
.stat small{display:block;font:var(--t-small);color:var(--ink-3);margin-top:6px;letter-spacing:0}
.stat.cand{color:var(--yellow)}
.pipeline{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}
.step{flex:1 1 150px;background:var(--panel);border:1px solid var(--line);border-radius:var(--r-s);padding:12px}
.step b{display:block;font:var(--t-eyebrow);letter-spacing:.06em;text-transform:uppercase;color:var(--sen);margin-bottom:6px}
.step span{font:var(--t-small);color:var(--ink-2)}
.arrow{align-self:center;color:var(--ink-3)}
.cands{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.tags{margin:4px 0 10px}
.tag{display:inline-flex;align-items:center;font:500 12px/1.2 var(--sans);padding:3px 9px;border-radius:var(--r-pill);margin:2px 4px 2px 0;border:1px solid var(--line-2);color:var(--ink-2)}
.tag.cand{color:var(--yellow);border-color:var(--yellow)}
.tag.open{color:var(--ink-2);border-color:var(--line-3)}
.tag.rej{color:var(--red);border-color:var(--red)}
.plate{margin:0 0 10px;background:#fff;border-radius:var(--r-s);border:1px solid var(--line-2);padding:8px 8px 6px}
.plate img{display:block;width:100%;height:auto}
.plate figcaption{font:400 11.5px/1.4 var(--mono);color:#424245;padding:6px 2px 0}
.bar{height:6px;background:var(--line-2);border-radius:var(--r-pill);overflow:hidden;margin:8px 0 10px}
.bar>i{display:block;height:100%;background:var(--blue)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:14px}
.kv>div{min-width:0;overflow-wrap:anywhere}
.grid>*,.cands>*{min-width:0}
code{overflow-wrap:anywhere}
.kv div:nth-child(odd){color:var(--ink-3)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font:var(--t-eyebrow);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)}
.scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--r-m);padding:4px 14px}
.note{font:var(--t-small);color:var(--ink-3)}
p.note{max-width:90ch}
code,pre{font-family:var(--mono);font-size:12.5px}
pre{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-s);padding:14px;overflow-x:auto}
.chart{margin:0}
.chart svg{display:block;width:100%;max-width:720px;height:auto}
.chart text{font:400 11px var(--mono);fill:var(--ink-3)}
.chart .axis{stroke:var(--line-2)}
.chart .new{fill:var(--yellow)}
.chart .known{fill:var(--blue)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font:var(--t-small);color:var(--ink-2);margin:8px 0 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
footer{margin:48px 0 24px;color:var(--ink-3);font:var(--t-small)}
@media (max-width:600px){.cands{grid-template-columns:1fr}.step{flex-basis:100%}.arrow{display:none}
  .herostage{grid-template-columns:1fr;padding:20px 18px}.herostage .stardisc{width:84px}}
@media print{nav{display:none}body{font-size:12px}.card,.scroll,.step{break-inside:avoid}}
"""
STYLE = tokens_css(":root", aliases=REPORT_ALIASES) + PRINT_CSS + BASE_CSS + REPORT_CSS
FONTS_HREF = "assets/fonts/fonts.css"  # beside a stand-alone report; a page of the site uses the site's copy
REVIEWED_IMAGE = "The image the reviewers saw (no markers)"


def _md_tables(text: str) -> str:
    """Render the pipe tables and paragraphs our own report files use. Anything else is shown as text."""
    out: list[str] = []
    table: list[list[str]] = []
    para: list[str] = []

    def flush_para():
        if para:
            out.append("<p class='note'>" + html.escape(" ".join(para)) + "</p>")
            para.clear()

    def flush_table():
        if not table:
            return
        header, body = table[0], [r for r in table[2:]]
        cells = "".join(f"<th>{html.escape(c)}</th>" for c in header)
        rows = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in body)
        out.append(f"<div class='scroll' tabindex='0' role='region' aria-label='Table, scrolls sideways on a narrow screen'><table><thead><tr>{cells}</tr></thead><tbody>{rows}</tbody></table></div>")
        table.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            flush_para()
            table.append([c.strip() for c in line.strip("|").split("|")])
            continue
        flush_table()
        if not line or line.startswith("#"):
            flush_para()
            continue
        para.append(line.replace("`", ""))
    flush_para()
    flush_table()
    return "\n".join(out)


def _panel_section(run_dir: Path) -> str:
    """Every reviewer's answer for every subject, so disagreement between reviewers is visible."""
    with (run_dir / "classifications.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    by_subject: dict[str, list[dict]] = {}
    for row in rows:
        by_subject.setdefault(row["subject_ids"], []).append(row)
    cards = []
    for subject_id, reviews in sorted(by_subject.items()):
        body = []
        for row in reviews:
            annotations = json.loads(row["annotations"])
            metadata = json.loads(row["metadata"])
            marks = annotations[0]["value"]
            spans = ", ".join(f"{m['t_start']:.3f}–{m['t_end']:.3f}" for m in marks) or "none"
            body.append(
                "<tr>"
                f"<td>{html.escape(row['user_name'])}</td>"
                f"<td>{html.escape(row['label'].replace('_', ' '))}</td>"
                f"<td>{html.escape(spans)}</td>"
                f"<td class='note'>{html.escape((metadata.get('rationale') or '')[:260])}</td>"
                "</tr>"
            )
        cards.append(
            f"<div class='card' style='margin-bottom:14px'><h3>{html.escape(subject_id)}</h3>"
            "<div class='scroll' tabindex='0' role='region' aria-label='Reviewer labels and rationales'><table><thead><tr><th>reviewer</th><th>label</th><th>marks (BTJD)</th><th>rationale</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return "".join(cards) or "<p class='note'>No classifications recorded.</p>"


def _load_candidates(run_dir: Path) -> list[dict]:
    with (run_dir / "candidates.csv").open() as handle:
        return list(csv.DictReader(handle))


def _score_bar(score: float) -> str:
    width = max(0.0, min(1.0, score)) * 100
    return f"<div class='bar' title='consensus score {score:.2f}'><i style='width:{width:.0f}%'></i></div>"


def _outcomes(run_dir: Path, rows: list[dict]) -> tuple[dict[str, str], dict]:
    """Each dip's vetting outcome as the case file decides it (passed, flagged or rejected), and the run's star as
    its stellar.json stores it. Without the case file's data (an incomplete run), passed or rejected from candidates.csv."""
    from setuhq.docket import docket_data

    try:
        d = docket_data(run_dir, title="report")
        return {c["candidate_id"]: c.get("outcome") for c in d["candidates"]}, d.get("star") or {}
    except Exception:  # noqa: BLE001  (a run without the case file's inputs still gets its report)
        return {r["candidate_id"]: ("passed" if r["passed"] == "True" else "rejected") for r in rows}, {}


def _candidate_card(row: dict, image_rel: str | None, outcome: str | None = None) -> str:
    if outcome is None:
        outcome = "passed" if row["passed"] == "True" else "rejected"
    cls, word, phrase = dip_state(outcome)
    flags = [f for f in row["flags"].split(";") if f]
    tags = [f"<span class='tag {cls}' title='{html.escape(phrase)}'>{html.escape(word)}</span>"]
    tags += [f"<span class='tag'>{html.escape(f.replace('_', ' '))}</span>" for f in flags]
    cid = html.escape(row["candidate_id"])
    image = (f"<figure class='plate'><img src='{html.escape(image_rel)}' alt='Blind-coded subject plot for {cid}: the light curve "
             f"the reviewers marked, with no target name and no markers' loading='lazy'><figcaption>{REVIEWED_IMAGE}</figcaption></figure>"
             if image_rel else "")
    period = f"{float(row['period_days']):.3f} d" if row.get("period_days") else "n/a"
    return f"""
<article class='card cand'>
  <h3>{cid}</h3>
  <p class='tags'>{''.join(tags)}</p>
  {image}
  {_score_bar(float(row['score']))}
  <div class='kv'>
    <div>Status</div><div>{html.escape(phrase)}</div>
    <div>Mid-time</div><div>{float(row['t_center']):.3f} {html.escape(row['time_unit'])}</div>
    <div>Duration</div><div>{float(row['duration_hours']):.2f} h</div>
    <div>Depth</div><div>{float(row['depth_ppm']):.0f} ppm</div>
    <div>SNR</div><div>{float(row['snr']):.1f}</div>
    <div>Panel agreement</div><div>{float(row['score']) * 100:.0f}% of skill-weighted reviewers, {row['n_reviewers']} marked it</div>
    <div>Says planet</div><div>{float(row['planet_fraction']) * 100:.0f}% of panel</div>
    <div>Reviewers</div><div>{html.escape(row['reviewers'].replace(';', ', '))}</div>
    <div>Periodic hint</div><div>{period}</div>
  </div>
</article>"""


def _star_line(star: dict) -> tuple[str, str]:
    """The hero's star: a static disc in its blackbody colour (renderer.star_svg) and the line that says where its
    Teff comes from; ("", "") when the run stores no Teff."""
    if not star or not star.get("teff"):
        return "", ""
    from setuhq.renderer import star_svg

    r = f", {star['radius']:.2f} R☉" if star.get("radius") else ""
    words = (f"{star.get('target') or 'The star'} in its blackbody colour: {star['teff']:,.0f} K{r} "
             f"({star.get('source') or 'as the run stores it'}, the run's stellar.json).")
    return star_svg(star["teff"], 60, uid="report", label=f"{star.get('target') or 'The star'}, drawn in its blackbody colour at {star['teff']:,.0f} K"), html.escape(words)


THEME_JS = ('try{var t=localStorage.getItem("setuhq-theme");if(t==="light"||t==="dark"||t==="system")'
            'document.documentElement.setAttribute("data-theme",t)}catch(e){}')


def _head(title: str, description: str, path: str, fonts_href: str) -> str:
    return (f"<!doctype html>\n<html lang='en' data-theme='system'><head><meta charset='utf-8'>\n"
            f"<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>\n"
            f"<meta name='color-scheme' content='dark light'>\n<title>{html.escape(title)}</title>\n<script>{THEME_JS}</script>\n"
            f"{brand.head(title, description, path)}\n"
            + (f"<link rel='stylesheet' href='{html.escape(fonts_href)}'>\n" if fonts_href else "")
            + f"<style>{STYLE}</style></head>")


def build_report(
    run_dir: str | Path,
    out_dir: str | Path,
    *,
    title: str = "SetuHQ run",
    validation_md: str | Path | None = None,
    benchmark_md: str | Path | None = None,
    path: str | None = None,
) -> Path:
    """The run report. ``path``: its address when it is a page of the site (it then uses the site's one copy of the
    fonts); without it the report is stand-alone and gets its own copy beside it."""
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    candidates = _load_candidates(run_dir)
    counts = manifest["counts"]
    outcome, star = _outcomes(run_dir, candidates)
    count_line = dip_count([outcome.get(c["candidate_id"]) for c in candidates])
    n_cand = sum(1 for c in candidates if dip_state(outcome.get(c["candidate_id"]))[1] == "candidate")
    probes_only = panel_mode(manifest) == "probes_only"

    cards = []
    for row in candidates:
        image_rel = None
        source = run_dir / "subjects" / f"{row['subject_id']}.png"
        if source.exists():
            target = assets / source.name
            shutil.copyfile(source, target)  # byte for byte: the image the reviewers saw
            image_rel = f"assets/{source.name}"
        cards.append(_candidate_card(row, image_rel, outcome.get(row["candidate_id"])))

    sections = {
        "overview": "Overview",
        "pipeline": "Pipeline",
        "candidates": "Candidates",
        "panel": "Panel",
        "validation": "Validation",
        "benchmark": "Benchmark",
        "provenance": "Provenance",
    }
    nav = "".join(f"<a href='#{k}'>{v}</a>" for k, v in sections.items())
    validation_html = _md_tables(public_text(Path(validation_md).read_text())) if validation_md else "<p class='note'>No validation run attached.</p>"
    benchmark_html = _md_tables(public_text(Path(benchmark_md).read_text())) if benchmark_md else "<p class='note'>No benchmark attached.</p>"
    packages = " · ".join(f"{k} {v}" for k, v in manifest.get("packages", {}).items())
    reviewers = "".join(
        f"<tr><td>{html.escape(r['id'])}</td><td>{html.escape(r['kind'])}</td><td>{r['weight']:.3f}</td></tr>"
        for r in manifest.get("reviewers", [])
    )
    skipped = ", ".join(manifest.get("skipped_reviewers", [])) or "none"
    disc, star_words = _star_line(star)
    run_name = manifest.get("config_name") or run_dir.name
    fonts_href = "" if path else FONTS_HREF
    head = _head(title, f"The archived report of SetuHQ's stored run {run_name}: every candidate, its vetting and provenance. Candidates, never confirmations.",
                 path or brand.page_path(out_dir), fonts_href)

    page = f"""{head}
<body>
<header class='hero' id='overview'><div class='wrap'>
 <div class='stage herostage'>{disc}<div>
  <a href="/" aria-label="SetuHQ, home">{brand.logo(themed=False, height=24)}</a>
  <p class='kick'>Run report · {html.escape(run_name)}</p>
  <h1>{html.escape(title)}</h1>
  <p class='count'>{html.escape(count_line)}</p>
  <p class='lead'>A transit search where a panel of independent reviewers marks dips in blind-coded light curves, consensus is skill-weighted, and every candidate keeps its provenance. Only a dip that passed vetting is a candidate, and a candidate is unconfirmed.</p>
  {f"<p class='runstar'>{star_words}</p>" if star_words else ""}{f"<p class='probes'><b>{html.escape(PROBES_ONLY)}.</b></p>" if probes_only else ""}
 </div></div>
</div></header>
<nav class='report-nav' aria-label='Sections'><div class='wrap'>{nav}</div></nav>
<main class='wrap'>

<section class='grid' style='margin-top:24px' aria-label='The run in numbers'>
  <div class='card stat'>{counts['light_curves']}<small>light curves</small></div>
  <div class='card stat'>{counts['subjects']}<small>blind-coded subjects</small></div>
  <div class='card stat'>{counts['classifications']}<small>independent reviews</small></div>
  <div class='card stat'>{len(candidates)}<small>dips the panel agreed on</small></div>
  <div class='card stat cand'>{n_cand}<small>candidates (passed vetting, unconfirmed)</small></div>
</section>

<section id='pipeline'><h2>How a run works</h2>
<div class='pipeline'>
  <div class='step'><b>1 · Ingest</b><span>TESS SPOC from MAST or CHEOPS FITS, time system kept as delivered</span></div><div class='arrow'>→</div>
  <div class='step'><b>2 · Clean &amp; detrend</b><span>Spike clip, masked local-quadratic baseline, 10-min bins</span></div><div class='arrow'>→</div>
  <div class='step'><b>3 · Blind subjects</b><span>13-day segments with opaque IDs. The target name never reaches a reviewer</span></div><div class='arrow'>→</div>
  <div class='step'><b>4 · Review panel</b><span>Each subject marked and labelled by every reviewer, independently</span></div><div class='arrow'>→</div>
  <div class='step'><b>5 · Consensus</b><span>Clustered marks, skill-weighted score, panel must say "potential planet"</span></div><div class='arrow'>→</div>
  <div class='step'><b>6 · Vet</b><span>SNR, duration, edges, odd/even depth, secondary eclipse, ephemeris fit</span></div>
</div>
<p class='note'>Thresholds, weights and every input are written to <code>manifest.json</code>, so a result can be rerun exactly.</p>
</section>

<section id='candidates'><h2>Candidates</h2>
<p class='note'>{html.escape(count_line)}. Each dip is named by its vetting outcome: a candidate passed vetting and is unconfirmed; a flagged dip is open; a rejected dip is not a candidate. Rejected and flagged dips are kept on purpose, so a reader can see what the vetting decided and why. Each image is the blind-coded plot the reviewers saw, byte for byte.</p>
<div class='cands'>{''.join(cards)}</div>
</section>

<section id='panel'><h2>Panel decisions</h2>
<p class='note'>Every reviewer's answer for every blind-coded subject. Disagreement is kept visible, because it is where the consensus is earned. {html.escape(ATTRIBUTION)}{f" {html.escape(PROBES_ONLY)}." if probes_only else ""}</p>
{_panel_section(run_dir)}
</section>

<section id='validation'><h2>Validation against known planets</h2>{validation_html}</section>
<section id='benchmark'><h2>Injection recovery</h2>{benchmark_html}</section>

<section id='provenance'><h2>Provenance</h2>
<div class='grid'>
 <div class='card'><h3>Reviewer panel</h3><div class='scroll' tabindex='0' role='region' aria-label='Reviewer panel table'><table><thead><tr><th>id</th><th>kind</th><th>weight</th></tr></thead><tbody>{reviewers}</tbody></table></div>
 <p class='note'>Skipped (unavailable here): {html.escape(skipped)}</p></div>
 <div class='card'><h3>Run</h3><div class='kv'>
   <div>Config</div><div>{html.escape(manifest['config_name'])}</div>
   <div>Config SHA-256</div><div><code>{html.escape(manifest['config_sha256'][:16])}…</code></div>
   <div>Created</div><div>{html.escape(manifest['created_at'])}</div>
   <div>SetuHQ</div><div>{html.escape(manifest.get('setuhq_version') or manifest['exoplan_version'])}</div>
   <div>Packages</div><div class='note'>{html.escape(packages)}</div>
 </div></div>
</div>
<details style='margin-top:14px'><summary>Raw manifest</summary><pre>{html.escape(json.dumps(manifest, indent=2))}</pre></details>
</section>

<footer>Generated by SetuHQ. Code: AGPL-3.0-only or a commercial licence from Ashforde OÜ; results: CC BY 4.0. Results on synthetic data are not claims about real sky data.</footer>
</main></body></html>
"""
    from setuhq.codenote import code_note, with_code_note

    out_path = out_dir / "index.html"
    out_path.write_text(with_code_note(page, code_note(run_dir)))
    if not path:
        from setuhq.docket import copy_page_fonts

        copy_page_fonts(out_dir)
    brand.copy_assets(out_dir)
    return out_path


def _per_night(catalog: dict) -> list[tuple[str, int, int]]:
    """(UTC night, new candidates, known-TOI matches) for each night a batch ran, in order."""
    nights: dict[str, list[int]] = {}
    for r in catalog.get("runs", []):
        d = nights.setdefault(str(r.get("time", ""))[:10], [0, 0])
        d[0] += int(r.get("new") or 0)
        d[1] += int(r.get("known") or 0)
    return [(k, v[0], v[1]) for k, v in sorted(nights.items()) if k]


def night_chart(catalog: dict) -> str:
    """The feed's entries per night as a static stacked bar chart (SVG, no script), with its numbers in a table."""
    rows = _per_night(catalog)[-30:]
    if not rows:
        return "<p class='note'>No batch has run yet.</p>"
    W, H, L, B, T = 720, 220, 40, 30, 14
    top = max(1, max(n + k for _, n, k in rows))
    bw = (W - L - 10) / len(rows)
    y = lambda v: H - B - (H - B - T) * v / top  # noqa: E731
    out = [f"<line class='axis' x1='{L}' x2='{W - 10}' y1='{H - B}' y2='{H - B}'/>",
           f"<text x='{L - 6}' y='{y(top) + 4:.0f}' text-anchor='end'>{top}</text><text x='{L - 6}' y='{H - B + 4}' text-anchor='end'>0</text>"]
    for i, (night, new, known) in enumerate(rows):
        w = min(bw * 0.7, 44)
        x = L + i * bw + (bw - w) / 2
        if known:
            out.append(f"<rect class='known' x='{x:.1f}' y='{y(known):.1f}' width='{w:.1f}' height='{H - B - y(known):.1f}' rx='2'/>")
        if new:
            out.append(f"<rect class='new' x='{x:.1f}' y='{y(known + new):.1f}' width='{w:.1f}' height='{y(known) - y(known + new):.1f}' rx='2'/>")
        if len(rows) <= 12 or i % max(1, len(rows) // 8) == 0:
            out.append(f"<text x='{x + w / 2:.1f}' y='{H - B + 16}' text-anchor='middle'>{html.escape(night[5:])}</text>")
    total_new, total_known = sum(n for _, n, _ in rows), sum(k for _, _, k in rows)
    label = (f"Search feed entries per night, {rows[0][0]} to {rows[-1][0]} (UTC): {total_new} new candidates and "
             f"{total_known} matches to known TOIs in all.")
    body = "".join(f"<tr><td>{html.escape(nt)}</td><td>{n}</td><td>{k}</td></tr>" for nt, n, k in rows)
    return (f"<figure class='chart card'><svg viewBox='0 0 {W} {H}' role='img' aria-label='{html.escape(label)}'>{''.join(out)}</svg>"
            "<p class='legend'><span><i style='background:var(--yellow)'></i>new candidate (unconfirmed)</span>"
            "<span><i style='background:var(--blue)'></i>match to a known TOI</span></p>"
            f"<figcaption class='note'>{html.escape(label)} Source: the feed's catalogue, one bar per night a batch ran.</figcaption></figure>"
            f"<details><summary>The numbers per night</summary><div class='scroll'><table><thead><tr><th>night (UTC)</th><th>new</th><th>known TOI</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div></details>")


def build_discovery_site(catalog_path: str | Path, out_dir: str | Path) -> Path:
    """Public page for the search feed. Every entry is labelled a candidate, not a confirmed planet."""
    catalog = json.loads(Path(catalog_path).read_text())
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = catalog.get("candidates", [])
    new = [r for r in rows if r["status"] == "new_candidate"]
    known = [r for r in rows if r["status"] == "known_toi"]

    def table(items: list[dict], label: str) -> str:
        if not items:
            return "<p class='note'>None yet.</p>"
        head = "".join(f"<th>{h}</th>" for h in ["TIC", "status", "mid-time (BTJD)", "period (d)", "duration (h)", "depth (ppm)", "SNR", "panel score", "found (UTC)"])
        body = "".join(
            "<tr>"
            f"<td>{r['tic']}</td>"
            f"<td>{html.escape(dip_state(r['status'])[2])}</td>"
            f"<td>{r['t_center']:.3f}</td>"
            f"<td>{'' if r['period_days'] is None else format(r['period_days'], '.3f')}</td>"
            f"<td>{r['duration_hours']:.2f}</td>"
            f"<td>{r['depth_ppm']:.0f}</td>"
            f"<td>{r['snr']:.1f}</td>"
            f"<td>{r['score']:.2f}</td>"
            f"<td>{html.escape(str(r['found'])[:16].replace('T', ' '))}</td>"
            "</tr>"
            for r in items
        )
        return (f"<div class='scroll' tabindex='0' role='region' aria-label='{html.escape(label)}'><table><thead><tr>{head}</tr></thead>"
                f"<tbody>{body}</tbody></table></div>")

    runs = catalog.get("runs", [])[-5:]
    run_rows = "".join(
        f"<tr><td>{html.escape(r['time'])}</td><td>{len(r['targets'])}</td><td>{r['new']}</td><td>{r['known']}</td><td>{len(r['errors'])}</td></tr>"
        for r in reversed(runs)
    )
    title = "SetuHQ search feed"
    head = _head(title, "Dips from SetuHQ's search batches that passed vetting and match no known ephemeris: leads for review, not planets.",
                 brand.page_path(out_dir), FONTS_HREF)
    page = f"""{head}
<body>
<header class='hero'><div class='wrap'>
 <div class='stage herostage' style='grid-template-columns:minmax(0,1fr)'><div>
  <a href="/" aria-label="SetuHQ, home">{brand.logo(themed=False, height=24)}</a>
  <p class='kick'>setuhq discover · scheduled batches</p>
  <h1>Search feed</h1>
  <p class='count'>{html.escape(dip_count([r['status'] for r in rows]))}, from {catalog.get('targets_reviewed', 0)} targets reviewed</p>
  <p class='lead'>An AI review panel searches TESS light curves on a schedule. Each entry is a dip that passed the pipeline's vetting and matches no known ephemeris, or a match to a known TOI that checks the pipeline. These are candidates. None is a confirmed planet until independent follow-up confirms it.</p>
 </div></div>
</div></header>
<main class='wrap'>
<section class='grid' style='margin-top:24px' aria-label='The feed in numbers'>
  <div class='card stat cand'>{len(new)}<small>new candidates (no TOI match)</small></div>
  <div class='card stat'>{len(known)}<small>matches to known TOIs</small></div>
  <div class='card stat'>{catalog.get('targets_reviewed', 0)}<small>targets reviewed</small></div>
  <div class='card stat' style='font-size:18px'>{html.escape(str(catalog.get('updated', 'never'))[:16].replace('T', ' '))}<small>last update (UTC)</small></div>
</section>
<section><h2>Entries per night</h2>{night_chart(catalog)}</section>
<section><h2>New candidates</h2>{table(new, "New candidates")}</section>
<section><h2>Matches to known TOIs</h2><p class='note'>Recovery of published signals. This is how the pipeline is checked on real data.</p>{table(known, "Matches to known TOIs")}</section>
<section><h2>Recent runs</h2><div class='scroll' tabindex='0' role='region' aria-label='Recent runs'><table><thead><tr><th>run (UTC)</th><th>targets</th><th>new</th><th>known</th><th>errors</th></tr></thead><tbody>{run_rows or "<tr><td colspan='5'>no runs yet</td></tr>"}</tbody></table></div></section>
<footer>Generated by SetuHQ from <code>{html.escape(catalog.get('config', ''))}</code>. Config SHA-256 <code>{html.escape(catalog.get('config_sha256', '')[:16])}</code>. Results on synthetic data are not claims about real sky data.</footer>
</main></body></html>
"""
    from setuhq.codenote import with_code_note
    from setuhq.docket import copy_page_fonts

    out = out_dir / "index.html"
    out.write_text(with_code_note(page, catalog.get("code_note")))
    copy_page_fonts(out_dir)
    brand.copy_assets(out_dir)
    return out
