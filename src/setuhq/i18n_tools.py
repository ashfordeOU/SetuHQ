# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The catalogues' tooling and checks (``tools/i18n.py`` and tests/test_i18n.py).

* :func:`extract` reads every message from the code into ``locales/en.arb``: the calls ``t``, ``th`` and ``N_``
  in Python (id, English, ``note=`` the translator comment), ``T('id', 'English')`` in the pages' scripts, and
  each MCP tool's description (``mcp.tool.<name>``, from its docstring).
* :func:`sync` brings a translation file into shape: sorted as the source, every translation with its review
  status (``x-review``) and the hash of the English it translates (``x-source``); ids the source no longer has
  are dropped.
* :func:`check` runs the quality checks on every language: placeholders, plural forms, markup, glossary terms,
  brand names, the honesty rules and the caveats.
* :func:`coverage` and :func:`memory_tmx` report coverage and write the translation memory (TMX 1.4).
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from setuhq import i18n

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent
GLOSSARY_DIR = ROOT / "docs" / "i18n"
TMX_PATH = GLOSSARY_DIR / "memory.tmx"
REVIEW = ("machine", "reviewed")

# Every honesty caveat: present, current and not empty in every language, or the check fails (docs/TRANSLATING.md).
CAVEATS = {
    "honesty.attribution": ("Sentinels", "Probes", "Claude", "Anthropic"),
    "honesty.probes_only": ("Probes", "Sentinels"),
    "honesty.none_confirmed": (),
    "honesty.embargo": ("TOI",),
    "honesty.cheops_disclaimer": ("SetuHQ", "ESA", "CHEOPS"),
    "honesty.transients_aid": (),
    "honesty.tess_pointing": (),
    "honesty.unconfirmed": (),
    "honesty.footer": ("SetuHQ",),
    "label.real": (),
    "label.model": (),
    "label.art": (),
    "label.illustration": (),
    "label.speculative": (),
}
SHOWCASE_FIELDS = ("kind", "summary", "caveat", "why", "outcome")
# Words that never translate, wherever the English has them.
KEEP = ("SetuHQ", "Sentinel", "Probe", "TESS", "CHEOPS", "ESA", "NASA", "TOI", "Claude", "Anthropic", "MAST", "MCP")
# English that may make a claim: a translation may use its word for these only where the English does.
CLAIMS = {"discover": r"discover", "confirm": r"confirm"}


# ---------------------------------------------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------------------------------------------

_JS_T = re.compile(r"""(?<![\w$])TT?\('([\w.-]+)',\s*'((?:[^'\\]|\\.)*)'""")


def _js_unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name not in ("t", "th", "T", "N_", "span", "ispan") or len(node.args) < 2:
            continue
        a, b = node.args[0], node.args[1]
        if not (isinstance(a, ast.Constant) and isinstance(a.value, str) and isinstance(b, ast.Constant) and isinstance(b.value, str)):
            continue
        if not re.match(r"^[a-z][\w-]*(\.[\w-]+)+$", a.value):
            continue
        note = next((kw.value.value for kw in node.keywords if kw.arg == "note" and isinstance(kw.value, ast.Constant)), None)
        if note is None and len(node.args) > 2 and isinstance(node.args[2], ast.Constant) and isinstance(node.args[2].value, str):
            note = node.args[2].value
        yield a.value, b.value, note, node.lineno


def _tool_docs() -> dict[str, str]:
    """Every MCP tool's description (its docstring, as setuhq.mcp_server registers it), by name."""
    from setuhq.tools import TOOLS

    return {fn.__name__: inspect.cleandoc(fn.__doc__ or "") for fn, _ in TOOLS if fn.__doc__}


def page_text(site: Path | None = None) -> dict[str, tuple[str, list[str]]]:
    """The main pages' unkeyed prose (setuhq.i18n_auto), from the committed English site: {id: (template, paths)}."""
    from setuhq import i18n_auto
    from setuhq.site import MAIN_PATHS

    site = site or ROOT / "site"
    pages = {p: (site / p.strip("/") / "index.html").read_text(encoding="utf-8") for p in MAIN_PATHS
             if (site / p.strip("/") / "index.html").is_file()}
    return i18n_auto.harvest(pages)


def code_part(cat: dict) -> dict:
    """A catalogue without its page text (pg.*): what the code alone declares, which a check can compare."""
    return {k: v for k, v in cat.items() if not k.lstrip("@").startswith("pg.")}


def extract(pages: bool = True) -> dict:
    """The source catalogue as the code declares it (an ARB dict), with the committed site's page text (pg.*) when
    ``pages``. Raises on an id given two different texts."""
    found: dict[str, tuple[str, str | None, str]] = {}

    def add(mid: str, en: str, note: str | None, where: str):
        if mid in found and found[mid][0] != en:
            raise ValueError(f"{mid}: two English texts ({found[mid][2]} and {where})")
        if mid not in found or (note and not found[mid][1]):
            found[mid] = (en, note or (found[mid][1] if mid in found else None), found.get(mid, (None, None, where))[2])

    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name in ("i18n.py", "i18n_tools.py", "i18n_cli.py"):
            continue
        for mid, en, note, line in _calls(path):
            add(mid, en, note, f"{rel}:{line}")
        text = path.read_text(encoding="utf-8")
        for m in _JS_T.finditer(text):
            add(m.group(1), _js_unescape(m.group(2)), None, f"{rel}:{text.count(chr(10), 0, m.start()) + 1}")
    showcase = ROOT / "docs" / "results" / "showcase.json"
    if showcase.is_file():  # the worked examples' editorial lines (data, but prose a reader sees on the home page)
        for r in json.loads(showcase.read_text(encoding="utf-8")).get("runs") or []:
            for field in SHOWCASE_FIELDS:
                if r.get(field):
                    add(f"showcase.{r['run']}.{field}", r[field], f"The worked example {r.get('star') or r['run']}: its {field}, "
                        "from docs/results/showcase.json.", "docs/results/showcase.json")
    from setuhq.i18n_cli import messages as cli_messages

    for mid, en in cli_messages().items():
        add(mid, en, "A help text of the setuhq command line. Option names, metavariables, %(...)s and code stay as written."
            if not mid.startswith("cli.argparse.") else "One of argparse's own words; keep every %(...)s and %s.", "src/setuhq/cli.py")
    for name, doc in _tool_docs().items():
        add(f"mcp.tool.{name}", doc, f"The MCP tool {name}'s description, read by AI assistants and people choosing a tool.",
            "src/setuhq/tools.py")
    if pages:
        for mid, (tpl, paths) in page_text().items():
            more = f" and {len(paths) - 3} more" if len(paths) > 3 else ""
            add(mid, tpl, "Text on the page " + ", ".join(paths[:3]) + more + ". Keep every {nN} (a number from the page) "
                "and every tag with its attributes; code, file names and commands stay as written.", "site" + paths[0])
    drawn = ROOT / "src" / "setuhq" / "locales" / "js-templates.json"
    if drawn.is_file():  # what the scripts draw (tools/i18n_harvest.mjs)
        for mid, d in json.loads(drawn.read_text(encoding="utf-8")).items():
            add(mid, d["en"], "Text a script draws on " + ", ".join(d["pages"][:3]) + ". Keep every {nN} (a number) and {sN} (a name) "
                "and every tag with its attributes; code, file names and commands stay as written.", "tools/i18n_harvest.mjs")
    out: dict = {"@@locale": "en", "@@x-generated-by": "tools/i18n.py extract (do not edit by hand)"}
    for mid in sorted(found):
        en, note, where = found[mid]
        i18n.parse(en)  # every message must parse
        meta: dict = {"x-file": where.split(":")[0]}
        if note:
            meta["description"] = note
        args = sorted(i18n.arguments(en))
        if args:
            meta["placeholders"] = {a: {} for a in args}
        out[mid] = en
        out["@" + mid] = meta
    return out


def dumps(cat: dict) -> str:
    return json.dumps(cat, ensure_ascii=False, indent=1) + "\n"


def sync(lang: str, src: dict | None = None, *, review: str = "machine") -> dict:
    """``lang``'s catalogue in shape against the source: ordered as it, each translation's ``x-review`` (kept, or
    ``review`` for a new one) and ``x-source`` (kept while the English is unchanged; set for a new one)."""
    src = src or i18n.raw_catalogue(i18n.SOURCE)
    old = i18n.raw_catalogue(lang)
    out: dict = {"@@locale": lang, "@@x-source-locale": "en"}
    for mid, en in src.items():
        if mid.startswith("@"):
            continue
        tr = old.get(mid)
        if not isinstance(tr, str) or not tr.strip():
            continue
        meta = dict(old.get("@" + mid) or {})
        meta.setdefault("x-review", review)
        meta.setdefault("x-source", i18n.source_hash(en))
        out[mid] = tr
        out["@" + mid] = {k: meta[k] for k in ("x-review", "x-source", "x-note") if k in meta}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------

_TAGS = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>")


def markup(msg: str) -> tuple[Counter, str | None]:
    """The tags of a message (name and attributes) and the first nesting error, if any."""
    tags, stack, err = Counter(), [], None
    for m in _TAGS.finditer(msg):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3) or "", m.group(4)
        if name == "wbr":  # a line-break opportunity a language adds (Japanese and Chinese phrases), not markup
            continue
        if closing:
            if not stack or stack[-1] != name:
                err = err or f"</{name}> does not close an open element"
            else:
                stack.pop()
            continue
        tags[(name, " ".join(sorted(re.findall(r"[^\s=]+(?:=(?:\"[^\"]*\"|'[^']*'|\S+))?", attrs.strip()))))] += 1
        if not selfclose and name not in i18n.VOID:
            stack.append(name)
    if stack:
        err = err or f"<{stack[-1]}> is not closed"
    stray = re.sub(r"<[^<>]*>", "", msg)
    if "<" in stray or ">" in stray.replace("&gt;", ""):
        err = err or "a stray < or >"
    return tags, err


def glossary(lang: str) -> dict:
    p = GLOSSARY_DIR / f"glossary.{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"terms": [], "claims": {}}


def check_message(lang: str, mid: str, en: str, tr: str, gl: dict | None = None) -> list[str]:
    """Every problem with one translation."""
    probs = []
    try:
        i18n.parse(tr)
    except i18n.MessageError as e:
        return [f"{lang} {mid}: does not parse ({e})"]
    a_en, a_tr = i18n.arguments(en), i18n.arguments(tr)
    if a_en != a_tr:
        probs.append(f"{lang} {mid}: placeholders {sorted(a_tr)} differ from the English {sorted(a_en)}")
    need = set(i18n.PLURAL_CATEGORIES[lang])
    en_plurals = {name for name, _ in i18n.plural_branches(en)}
    tr_plurals = dict()
    for name, keys in i18n.plural_branches(tr):
        cats = {k for k in keys if not k.startswith("=")}
        if not need <= cats:
            probs.append(f"{lang} {mid}: plural {name} lacks {sorted(need - cats)}")
        if cats - need:
            probs.append(f"{lang} {mid}: plural {name} has forms {sorted(cats - need)} that {lang} does not use")
        tr_plurals[name] = cats
    if len(need) > 1:
        for name in en_plurals - set(tr_plurals):
            probs.append(f"{lang} {mid}: the English plural {name} is not a plural here")
    pf = re.compile(r"%\(\w+\)[sdr]|%[sdr%]")
    if sorted(pf.findall(en)) != sorted(pf.findall(tr)):
        probs.append(f"{lang} {mid}: printf placeholders {sorted(pf.findall(tr))} differ from the English {sorted(pf.findall(en))}")
    t_en, e_en = markup(en)
    t_tr, e_tr = markup(tr)
    if e_en:  # the English holds a literal < or > (a placeholder such as <name>, or n > 0): the same ones
        if Counter(re.findall(r"[<>]", en)) != Counter(re.findall(r"[<>]", tr)):
            probs.append(f"{lang} {mid}: its < and > differ from the English")
    elif e_tr:
        probs.append(f"{lang} {mid}: broken markup ({e_tr})")
    elif t_en != t_tr:
        probs.append(f"{lang} {mid}: markup differs from the English ({sorted((t_tr - t_en) + (t_en - t_tr))})")
    for word in KEEP:
        n_en = len(re.findall(rf"(?<![A-Za-z]){re.escape(word)}", en))
        if n_en and not re.search(rf"(?<![A-Za-z]){re.escape(word)}", tr):
            probs.append(f"{lang} {mid}: '{word}' must stay as written")
    gl = gl if gl is not None else glossary(lang)
    code = re.compile(r"``.*?``|<code>.*?</code>|[!-~]*[A-Za-z0-9_][._/][A-Za-z0-9_][!-~]*|(?<!\w)'[^'\s][^']*'(?!\w)")  # code, file names and quoted values are not prose
    plain_en = code.sub(" ", re.sub(r"<(?!/?code>)[^>]+>", " ", en))
    plain_tr = code.sub(" ", re.sub(r"<(?!/?code>)[^>]+>", " ", tr))
    for term in gl.get("terms", []):
        if re.search(term["en"], plain_en, re.I) and not re.search(term["target"], plain_tr, re.I):
            probs.append(f"{lang} {mid}: glossary term '{term['term_en']}' should read '{term['term']}'")
    for claim, pat in (gl.get("claims") or {}).items():
        if re.search(pat, plain_tr, re.I) and not re.search(CLAIMS[claim], plain_en, re.I):
            probs.append(f"{lang} {mid}: says '{claim}' where the English does not")
    if mid in CAVEATS:
        for word in CAVEATS[mid]:
            if word not in tr:
                probs.append(f"{lang} {mid}: the caveat must keep '{word}'")
        if mid == "honesty.embargo" and re.search(r"\d", tr):
            probs.append(f"{lang} {mid}: the embargo line holds a number")
    return probs


def check(langs=None) -> list[str]:
    """Every problem in every translation (and the caveats each language must have)."""
    src = i18n.raw_catalogue(i18n.SOURCE)
    probs = []
    for c in CAVEATS:
        if c not in src:
            probs.append(f"en {c}: the caveat is missing from the source")
    for lang in langs or i18n.TRANSLATIONS:
        raw = i18n.raw_catalogue(lang)
        usable = i18n.messages(lang)
        gl = glossary(lang)
        for mid, tr in raw.items():
            if mid.startswith("@"):
                continue
            if mid not in src:
                probs.append(f"{lang} {mid}: not in the source catalogue")
                continue
            meta = raw.get("@" + mid) or {}
            if meta.get("x-review") not in REVIEW:
                probs.append(f"{lang} {mid}: review status {meta.get('x-review')!r} is not one of {REVIEW}")
            if not isinstance(tr, str):
                probs.append(f"{lang} {mid}: not a string")
                continue
            probs += check_message(lang, mid, src[mid], tr, gl)
        for c in CAVEATS:
            if not (usable.get(c) or "").strip():
                probs.append(f"{lang} {c}: the caveat is missing, empty or stale")
    return probs


def coverage() -> dict[str, dict]:
    """Per language: messages translated and current, stale, machine and reviewed, of the source's total."""
    src = {k for k in i18n.raw_catalogue(i18n.SOURCE) if not k.startswith("@")}
    out = {}
    for lang in i18n.TRANSLATIONS:
        raw = i18n.raw_catalogue(lang)
        usable = i18n.messages(lang)
        review = Counter((raw.get("@" + k) or {}).get("x-review") for k in usable)
        stale = sum(1 for k in raw if not k.startswith("@") and k in src and k not in usable and str(raw[k]).strip())
        out[lang] = {"total": len(src), "translated": len(usable), "stale": stale, "machine": review.get("machine", 0),
                     "reviewed": review.get("reviewed", 0), "percent": round(100 * len(usable) / len(src), 1) if src else 100.0}
    return out


def page_english(site: str | Path, lang: str) -> list[tuple[int, str, str]]:
    """The English left on ``lang``'s pages of a built site: (characters, page, text) for each keyed element whose
    message has no usable translation and each block of page text (setuhq.i18n_auto) still as on the English page."""
    from setuhq import i18n_auto

    site = Path(site)
    usable = i18n.messages(lang)
    english = set(i18n_auto.harvest({p: (site / p.strip("/") / "index.html").read_text(encoding="utf-8")
                                     for p in _main_paths() if (site / p.strip("/") / "index.html").is_file()}))
    out = []
    for p in sorted((site / lang).rglob("index.html")) if (site / lang).is_dir() else []:
        src = p.read_text(encoding="utf-8")
        page = "/" + p.parent.relative_to(site).as_posix() + "/"
        for _kind, s, e, tpl, _args in i18n_auto.blocks(src):
            if i18n_auto.message_id(tpl) in english:
                out.append((_textlen(src[s:e]), page, _plain_text(src[s:e])))
        body = src[src.find("<body"):]
        for m in i18n._TAG.finditer(body):
            k = re.search(r'data-i18n="([^"]+)"', m.group(2) or "")
            if k and k.group(1) not in usable:
                end = i18n._close(body, m.group(1), m.end())
                if end > 0 and _textlen(body[m.end():end]):
                    out.append((_textlen(body[m.end():end]), page, _plain_text(body[m.end():end])))
    return sorted(out, reverse=True)


def page_coverage(site: str | Path) -> dict[str, float]:
    """Per language: the share of the visible text of its pages (under /<lang>/, main content and header, by
    characters) that is not English left in place (``page_english``)."""
    site = Path(site)
    out = {}
    for lang in i18n.TRANSLATIONS:
        total = 0
        for p in sorted((site / lang).rglob("index.html")) if (site / lang).is_dir() else []:
            s = re.sub(r"<(script|style|svg|template)\b.*?</\1>", "", p.read_text(encoding="utf-8"), flags=re.S | re.I)
            total += _textlen(s[s.find("<body"):])
        left = sum(n for n, _p, _t in page_english(site, lang))
        out[lang] = round(100 * (1 - left / total), 1) if total else 0.0
    return out


def _main_paths():
    from setuhq.site import MAIN_PATHS

    return MAIN_PATHS


def _plain_text(s: str) -> str:
    import html as h

    return re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _textlen(s: str) -> int:
    import html as h

    return len(re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", s))).strip())


_HEAD = re.compile(r'<(h[1-4])\b[^>]*>|<[a-z]+\b[^>]*\bclass="[^"]*\blead-h\b[^"]*"[^>]*>')
_PHRASE_LANGS = ("ja", "zh-Hans")


def heading_ids(site: str | Path) -> set[str]:
    """The messages that are (or are in) a heading on the main pages of a built English site: keyed ones by id, page
    text (setuhq.i18n_auto) by its template's id."""
    from setuhq import i18n_auto

    site, out = Path(site), set()
    for path in _main_paths():
        f = site / path.strip("/") / "index.html"
        if not f.is_file():
            continue
        src = f.read_text(encoding="utf-8")
        for m in _HEAD.finditer(src):
            end = src.find("</" + (m.group(1) or "div"), m.end())
            out.update(re.findall(r'data-i18n="([^"]+)"', src[m.start():end]))
        for kind, s, _e, tpl, _args in i18n_auto.blocks(src):
            if kind == "html" and _HEAD.match(src, src.rfind("<", 0, s)):
                out.add(i18n_auto.message_id(tpl))
    return out


def phrases(text: str, lang: str) -> str:
    """``text`` (a message: markup, {arguments}) with <wbr> between its phrases, where a line may break in a
    heading set with word-break: keep-all (Japanese by BudouX's phrases, Chinese by jieba's words and the glossary's
    terms). Needs the budoux and jieba packages (tools only, never the site)."""
    if lang == "ja":
        import budoux

        cut = budoux.load_default_japanese_parser().parse
    else:
        import jieba

        jieba.setLogLevel(60)
        for term in {t.get("term", "") for t in glossary(lang).get("terms", [])} | {"凌星", "光变曲线", "系外行星", "假阳性", "候选体"}:
            if re.search(r"[\u4e00-\u9fff]", term):
                jieba.add_word(term)

        def cut(s):  # a lone particle or punctuation stays with the word before it
            out = []
            for w in jieba.cut(s):
                if out and (len(w) == 1 and w in "的了中和与及或吗呢吧，。、：；！？）」』”" or not re.search(r"[\u4e00-\u9fff]", w)):
                    out[-1] += w
                else:
                    out.append(w)
            return out
    terms = sorted({t.get("term", "") for t in glossary(lang).get("terms", [])} | {"光度曲線", "光变曲线", "系外惑星", "系外行星"}, key=len, reverse=True)

    def one(p):
        w = "<wbr>".join(x for x in cut(p) if x)
        for term in terms:  # never inside a glossary term
            if len(term) > 1 and re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", term):
                w = re.sub("(?:<wbr>)?".join(map(re.escape, term)), term, w)
        return re.sub(r"<wbr>(?=\s|$)|(?<=\s)<wbr>|^<wbr>", "", w)

    text = text.replace("<wbr>", "")
    parts = re.split(r"(<[^>]*>|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", text)
    return "".join(p if p.startswith(("<", "{")) or not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", p) else one(p) for p in parts)


def add_phrases(site: str | Path) -> dict[str, int]:
    """<wbr> in every Japanese and Chinese heading message (``heading_ids``): the catalogues rewritten in place."""
    ids, done = heading_ids(site), {}
    for lang in _PHRASE_LANGS:
        raw = i18n.raw_catalogue(lang)
        n = 0
        for mid in ids:
            v = raw.get(mid)
            if isinstance(v, str) and (w := phrases(v, lang)) != v:
                raw[mid], n = w, n + 1
        i18n.catalogue_path(lang).write_text(dumps(raw), encoding="utf-8")
        done[lang] = n
    i18n.reload()
    return done


def memory_tmx() -> str:
    """The translation memory: every current translation with its English, as TMX 1.4 (Weblate and other tools
    import it), each unit with its id and review status."""
    src = i18n.raw_catalogue(i18n.SOURCE)
    units = []
    for mid in (k for k in src if not k.startswith("@")):
        tuvs = [f'<tuv xml:lang="en"><seg>{xml_escape(src[mid])}</seg></tuv>']
        for lang in i18n.TRANSLATIONS:
            raw = i18n.raw_catalogue(lang)
            tr = i18n.messages(lang).get(mid)
            if tr:
                rv = (raw.get("@" + mid) or {}).get("x-review", "machine")
                tuvs.append(f'<tuv xml:lang="{lang}"><prop type="x-review">{rv}</prop><seg>{xml_escape(tr)}</seg></tuv>')
        units.append(f'<tu tuid="{xml_escape(mid)}">' + "".join(tuvs) + "</tu>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4"><header creationtool="setuhq tools/i18n.py" '
            'creationtoolversion="1" segtype="block" o-tmf="ARB" adminlang="en" srclang="en" datatype="html"/><body>\n'
            + "\n".join(units) + "\n</body></tmx>\n")


def tool_description(name: str, doc: str) -> str:
    """An MCP tool's description in the current language (its docstring as written, in English)."""
    if i18n.current() == i18n.SOURCE:
        return (doc or "").strip()
    return i18n.messages(i18n.current()).get(f"mcp.tool.{name}") or (doc or "").strip()


def cleandoc(doc: str) -> str:
    return inspect.cleandoc(doc or "")


def _norm(s: str) -> str:
    import html as h

    return re.sub(r"\s+", " ", h.unescape(h.unescape(s))).strip()


def keyed_mismatches(src: str, where: str = "") -> list[str]:
    """Every keyed element whose English content is not its message formatted with its arguments: a key put on the
    wrong text, or a message that drifted from what the code writes. Also every key the source does not have."""
    en = i18n.messages(i18n.SOURCE)
    probs = []
    for m in i18n._TAG.finditer(src):
        raw = m.group(2) or ""
        if "data-i18n" not in raw:
            continue
        a = dict(i18n._attrs(raw))
        args = {}
        if a.get("data-i18n-args"):
            args = json.loads(i18n._html.unescape(a["data-i18n-args"]))
        args = {x: v for x, v in args.items() if not x.endswith("@")}
        for spec in (a.get("data-i18n-attr") or "").split("|"):
            if not spec:
                continue
            name, _, mid = spec.partition(":")
            if mid not in en:
                probs.append(f"{where}: {mid} is not in the source catalogue")
            elif name in a and _norm(i18n.format_message(en[mid], args, "en")) != _norm(a[name] or ""):
                probs.append(f"{where}: {mid} ({name}) reads {a[name]!r}, the message gives {i18n.format_message(en[mid], args, 'en')!r}")
        mid = a.get("data-i18n")
        if not mid:
            continue
        if mid not in en:
            probs.append(f"{where}: {mid} is not in the source catalogue")
            continue
        end = i18n._close(src, m.group(1), m.end())
        if end < 0 or m.group(3):
            continue
        have, want = _norm(src[m.end():end]), _norm(i18n.format_message(en[mid], args, "en", html=True))
        if have != want:
            probs.append(f"{where}: {mid} reads {have[:120]!r}, the message gives {want[:120]!r}")
    return probs


def site_mismatches(site: str | Path, limit: int | None = None) -> list[str]:
    """keyed_mismatches over every English page of a built site (and its shared views and chrome)."""
    site = Path(site)
    langs = set(i18n.TRANSLATIONS)
    files = [p for p in sorted(site.rglob("*.html")) if p.relative_to(site).parts[0] not in langs]
    probs = []
    for p in files[:limit]:
        probs += keyed_mismatches(p.read_text(encoding="utf-8"), p.relative_to(site).as_posix())
    return probs
