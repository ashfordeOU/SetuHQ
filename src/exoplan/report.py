"""Static report site for a run: one HTML page with no build step and no external assets.

The page shows the run summary, a pipeline diagram, each vetted candidate with its
blind-coded subject plot, the known-planet validation, the injection benchmark and
the provenance manifest. Light and dark themes follow the system setting.
"""

from __future__ import annotations

import csv
import html
import json
import shutil
from pathlib import Path

STYLE = """
:root{--bg:#f6f7fb;--panel:#ffffff;--ink:#14161f;--muted:#5b6175;--line:#e2e5ef;--accent:#4f46e5;--accent-2:#0ea5a4;--good:#16a34a;--bad:#dc2626;--warn:#d97706;--radius:14px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0b0d14;--panel:#141826;--ink:#e8ebf5;--muted:#9aa1b8;--line:#262c40;--accent:#818cf8;--accent-2:#2dd4bf;--good:#4ade80;--bad:#f87171;--warn:#fbbf24}}
:root[data-theme="dark"]{--bg:#0b0d14;--panel:#141826;--ink:#e8ebf5;--muted:#9aa1b8;--line:#262c40;--accent:#818cf8;--accent-2:#2dd4bf;--good:#4ade80;--bad:#f87171;--warn:#fbbf24}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header.hero{padding:56px 16px 36px;background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#fff}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
h1{font-size:clamp(28px,5vw,42px);margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:24px;margin:40px 0 12px;letter-spacing:-.01em}
h3{font-size:17px;margin:0 0 6px}
p.lead{font-size:18px;max-width:760px;margin:0;opacity:.95}
nav{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;gap:18px;overflow-x:auto;padding-top:12px;padding-bottom:12px}
nav a{color:var(--muted);text-decoration:none;white-space:nowrap;font-size:14px;display:inline-flex;align-items:center;min-height:44px}
nav a:hover{color:var(--accent)}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px}
.stat{font-size:30px;font-weight:700;letter-spacing:-.02em}
.stat small{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-top:2px}
.pipeline{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}
.step{flex:1 1 150px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.step b{display:block;color:var(--accent);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.step span{font-size:14px;color:var(--muted)}
.arrow{align-self:center;color:var(--muted)}
.cands{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.cand img{width:100%;border-radius:10px;border:1px solid var(--line);background:#fff}
.tag{display:inline-block;font-size:12px;padding:2px 9px;border-radius:999px;margin:2px 4px 2px 0;border:1px solid var(--line);color:var(--muted)}
.tag.pass{color:var(--good);border-color:var(--good)}
.tag.fail{color:var(--bad);border-color:var(--bad)}
.tag.flag{color:var(--warn);border-color:var(--warn)}
.bar{height:8px;background:var(--line);border-radius:999px;overflow:hidden;margin:8px 0}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-2))}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:14px}
.kv>div{min-width:0;overflow-wrap:anywhere}
.grid>*,.cands>*{min-width:0}
code{overflow-wrap:anywhere}
.kv div:nth-child(odd){color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:4px 14px}
.note{font-size:14px;color:var(--muted)}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
pre{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;overflow-x:auto}
footer{margin:48px 0 24px;color:var(--muted);font-size:13px}
@media (max-width:600px){.cands{grid-template-columns:1fr}.step{flex-basis:100%}.arrow{display:none}}
"""


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
        out.append(f"<div class='scroll'><table><thead><tr>{cells}</tr></thead><tbody>{rows}</tbody></table></div>")
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
            "<div class='scroll'><table><thead><tr><th>reviewer</th><th>label</th><th>marks (BTJD)</th><th>rationale</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div></div>"
        )
    return "".join(cards) or "<p class='note'>No classifications recorded.</p>"


def _load_candidates(run_dir: Path) -> list[dict]:
    with (run_dir / "candidates.csv").open() as handle:
        return list(csv.DictReader(handle))


def _score_bar(score: float) -> str:
    width = max(0.0, min(1.0, score)) * 100
    return f"<div class='bar' title='consensus score {score:.2f}'><i style='width:{width:.0f}%'></i></div>"


def _candidate_card(row: dict, image_rel: str | None) -> str:
    passed = row["passed"] == "True"
    flags = [f for f in row["flags"].split(";") if f]
    tags = [f"<span class='tag {'pass' if passed else 'fail'}'>{'passed vetting' if passed else 'rejected'}</span>"]
    tags += [f"<span class='tag flag'>{html.escape(f)}</span>" for f in flags]
    image = f"<img src='{html.escape(image_rel)}' alt='Blind-coded subject plot for {html.escape(row['candidate_id'])}' loading='lazy'>" if image_rel else ""
    period = f"{float(row['period_days']):.3f} d" if row.get("period_days") else "n/a"
    return f"""
<article class='card cand'>
  <h3>{html.escape(row['candidate_id'])}</h3>
  {''.join(tags)}
  {image}
  {_score_bar(float(row['score']))}
  <div class='kv'>
    <div>Mid-time</div><div>{float(row['t_center']):.3f} {html.escape(row['time_unit'])}</div>
    <div>Duration</div><div>{float(row['duration_hours']):.2f} h</div>
    <div>Depth</div><div>{float(row['depth_ppm']):.0f} ppm</div>
    <div>SNR</div><div>{float(row['snr']):.1f}</div>
    <div>Panel agreement</div><div>{float(row['score']) * 100:.0f}% of skill-weighted reviewers, {row['n_reviewers']} marked it</div>
    <div>Says planet</div><div>{float(row['planet_fraction']) * 100:.0f}% of panel</div>
    <div>Reviewers</div><div>{html.escape(row['reviewers'])}</div>
    <div>Periodic hint</div><div>{period}</div>
  </div>
</article>"""


def build_report(
    run_dir: str | Path,
    out_dir: str | Path,
    *,
    title: str = "exoplan run",
    validation_md: str | Path | None = None,
    benchmark_md: str | Path | None = None,
) -> Path:
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    candidates = _load_candidates(run_dir)
    counts = manifest["counts"]
    passed = [c for c in candidates if c["passed"] == "True"]

    cards = []
    for row in candidates:
        image_rel = None
        source = run_dir / "subjects" / f"{row['subject_id']}.png"
        if source.exists():
            target = assets / source.name
            shutil.copyfile(source, target)
            image_rel = f"assets/{source.name}"
        cards.append(_candidate_card(row, image_rel))

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
    validation_html = _md_tables(Path(validation_md).read_text()) if validation_md else "<p class='note'>No validation run attached.</p>"
    benchmark_html = _md_tables(Path(benchmark_md).read_text()) if benchmark_md else "<p class='note'>No benchmark attached.</p>"
    packages = " · ".join(f"{k} {v}" for k, v in manifest.get("packages", {}).items())
    reviewers = "".join(
        f"<tr><td>{html.escape(r['id'])}</td><td>{html.escape(r['kind'])}</td><td>{r['weight']:.3f}</td></tr>"
        for r in manifest.get("reviewers", [])
    )
    skipped = ", ".join(manifest.get("skipped_reviewers", [])) or "none"

    page = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<link rel='icon' href='data:,'>
<title>{html.escape(title)}</title>
<style>{STYLE}</style></head>
<body>
<header class='hero' id='overview'><div class='wrap'>
  <h1>{html.escape(title)}</h1>
  <p class='lead'>A transit search where a panel of independent reviewers marks dips in blind-coded light curves, consensus is skill-weighted, and every candidate keeps its provenance. Built to follow the Planet Hunters CHEOPS workflow.</p>
</div></header>
<nav><div class='wrap'>{nav}</div></nav>
<main class='wrap'>

<section class='grid' style='margin-top:28px'>
  <div class='card stat'>{counts['light_curves']}<small>light curves</small></div>
  <div class='card stat'>{counts['subjects']}<small>blind-coded subjects</small></div>
  <div class='card stat'>{counts['classifications']}<small>independent reviews</small></div>
  <div class='card stat'>{counts['consensus_events']}<small>consensus dips</small></div>
  <div class='card stat' style='color:var(--good)'>{counts['passed_vetting']}<small>passed vetting</small></div>
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
<p class='note'>Passed candidates are the catalogue. Rejected and flagged events are kept on purpose, so a reader can see what the vetting decided and why.</p>
<div class='cands'>{''.join(cards)}</div>
</section>

<section id='panel'><h2>Panel decisions</h2>
<p class='note'>Every reviewer's answer for every blind-coded subject. Disagreement is kept visible, because it is where the consensus is earned.</p>
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
   <div>exoplan</div><div>{html.escape(manifest['exoplan_version'])}</div>
   <div>Packages</div><div class='note'>{html.escape(packages)}</div>
 </div></div>
</div>
<details style='margin-top:14px'><summary>Raw manifest</summary><pre>{html.escape(json.dumps(manifest, indent=2))}</pre></details>
</section>

<footer>Generated by exoplan. MIT licensed. Results on synthetic data are not claims about real sky data.</footer>
</main></body></html>
"""
    out_path = out_dir / "index.html"
    out_path.write_text(page)
    return out_path


def build_discovery_site(catalog_path: str | Path, out_dir: str | Path) -> Path:
    """Public page for the discovery catalogue. Every entry is labelled a candidate, not a confirmed planet."""
    catalog = json.loads(Path(catalog_path).read_text())
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = catalog.get("candidates", [])
    new = [r for r in rows if r["status"] == "new_candidate"]
    known = [r for r in rows if r["status"] == "known_toi"]

    def table(items: list[dict]) -> str:
        if not items:
            return "<p class='note'>None yet.</p>"
        head = "".join(f"<th>{h}</th>" for h in ["TIC", "mid-time (BTJD)", "period (d)", "duration (h)", "depth (ppm)", "SNR", "panel score", "found (UTC)"])
        body = "".join(
            "<tr>"
            f"<td>{r['tic']}</td>"
            f"<td>{r['t_center']:.3f}</td>"
            f"<td>{'' if r['period_days'] is None else f'{r['period_days']:.3f}'}</td>"
            f"<td>{r['duration_hours']:.2f}</td>"
            f"<td>{r['depth_ppm']:.0f}</td>"
            f"<td>{r['snr']:.1f}</td>"
            f"<td>{r['score']:.2f}</td>"
            f"<td>{html.escape(r['found'])}</td>"
            "</tr>"
            for r in items
        )
        return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"

    runs = catalog.get("runs", [])[-5:]
    run_rows = "".join(
        f"<tr><td>{html.escape(r['time'])}</td><td>{len(r['targets'])}</td><td>{r['new']}</td><td>{r['known']}</td><td>{len(r['errors'])}</td></tr>"
        for r in reversed(runs)
    )
    page = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<link rel='icon' href='data:,'>
<title>exoplan discoveries</title>
<style>{STYLE}</style></head>
<body>
<header class='hero'><div class='wrap'>
  <h1>Discovery feed</h1>
  <p class='lead'>An AI review panel searches TESS light curves on a schedule. Each entry is a dip that passed the pipeline's vetting and matches no known ephemeris. These are candidates. None is a confirmed planet until independent follow-up confirms it.</p>
</div></header>
<main class='wrap'>
<section class='grid' style='margin-top:28px'>
  <div class='card stat'>{len(new)}<small>new candidates</small></div>
  <div class='card stat'>{len(known)}<small>matches to known TOIs</small></div>
  <div class='card stat'>{catalog.get('targets_reviewed', 0)}<small>targets reviewed</small></div>
  <div class='card stat' style='font-size:16px'>{html.escape(catalog.get('updated', 'never'))}<small>last update (UTC)</small></div>
</section>
<section><h2>New candidates</h2>{table(new)}</section>
<section><h2>Matches to known TOIs</h2><p class='note'>Recovery of published signals. This is how the pipeline is checked on real data.</p>{table(known)}</section>
<section><h2>Recent runs</h2><div class='scroll'><table><thead><tr><th>run (UTC)</th><th>targets</th><th>new</th><th>known</th><th>errors</th></tr></thead><tbody>{run_rows or "<tr><td colspan='5'>no runs yet</td></tr>"}</tbody></table></div></section>
<footer>Generated by exoplan from <code>{html.escape(catalog.get('config', ''))}</code>. Config SHA-256 <code>{html.escape(catalog.get('config_sha256', '')[:16])}</code>. Results on synthetic data are not claims about real sky data.</footer>
</main></body></html>
"""
    out = out_dir / "index.html"
    out.write_text(page)
    return out
