# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The anonymity lint: an aid for double-anonymous review, not a guarantee.

It scans proposal text for what commonly breaks anonymity and warns; it never edits, and a clean result does
not prove a text is anonymous (a human must read it). What it looks for:

* e-mail addresses, including obfuscated ones ("jane.doe [at] unige.ch"), and ORCID iDs;
* names the user gives (``--author-name``), in their usual variants: "Jane Doe", "J. Doe", "Doe, J.",
  "DOE J", "Jane Doe's", and the surname alone in a citation-like context ("Doe et al.", "Doe (2023)");
* institutions, case-insensitively: generic words ("university of ...", "institute", "observatory",
  "department of"), a modest built-in list of major institutions, and any the user gives (``--institution``);
* self-reference: "my"/"our" before a research noun ("my previous paper", "our earlier CHEOPS programme",
  "our 2023 study", "our work (Doe et al. 2023)", "our team"), "we have previously shown", "we are the team
  that discovered", "we discovered";
* titles before names, funding acknowledgements, links to personal pages;
* file names: e-mail addresses, ORCID iDs, institutions, the given names (surname, initials + surname), and
  initials-like tokens ("Doe_SJ").

Text is scanned paragraph by paragraph (lines joined), so a phrase wrapped over two lines is still caught. A PDF
is read with pypdf when it is installed (``pip install pypdf``); a PDF without extractable text, or any other
non-text file, is refused rather than reported clean.
"""

from __future__ import annotations

import re
from pathlib import Path

TODO = "[TO COMPLETE]"
NOT_A_GUARANTEE = ("The anonymity lint is an aid: it cannot guarantee anonymity. Read every document and file name "
                   "yourself before submission.")


class LintInputError(ValueError):
    """A file the lint cannot read as text (a binary, or a PDF without extractable text)."""


RESEARCH_NOUN = (r"(?:work|works|paper|papers|study|studies|article|articles|publication|publications|letter|"
                 r"programmes?|programs?|proposals?|campaigns?|surveys?|team|teams|group|groups|lab|labs|laboratory|"
                 r"institute|institution|university|department|collaboration|consortium|pipeline|code|software|"
                 r"tool|instrument|telescope|facility|thesis|students?|postdocs?|discovery|detection)")
SELF_REFERENCE = [
    # "my previous paper", "our earlier CHEOPS programme", "our 2023 study", "our own pipeline", "our team"
    rf"\b(?:my|our)\s+(?:[\w-]+\s+){{0,3}}?{RESEARCH_NOUN}\b",
    # results, observations, analysis: only with a past-tense marker ("our previous observations")
    r"\b(?:my|our)\s+(?:own\s+)?(?:previous|earlier|prior|past|published|recent|\d{4})\s+(?:results?|observations?|"
    r"analys[ie]s|measurements?|data|findings|fits?)\b",
    r"\b(?:we|I)\s+(?:have\s+|had\s+)?(?:previously|already|recently|earlier|first)\s+(?:\w+\s+)?(?:shown|showed|"
    r"demonstrated|published|reported|found|observed|detected|discovered|developed|led|proposed|measured)\b",
    r"\b(?:we|I)\s+(?:have\s+)?(?:shown|showed|demonstrated|published|reported)\s+(?:in|that)\b",
    r"\b(?:as\s+)?(?:we|I)\s+(?:showed|reported|argued|found)\s+(?:in|previously|earlier|before)\b",
    r"\bin\s+our\s+(?:previous|earlier|recent|own|\d{4})\b",
    r"\b(?:we|I)\s+(?:are|am|were|was)\s+(?:the|a|an|part\s+of\s+the|members?\s+of\s+the)\s+(?:[\w-]+\s+){0,2}?"
    r"(?:team|group|PIs?|Co-?Is?|developers?|authors?|members?|leads?|discoverers?)\b",
    r"\b(?:we|I)\s+(?:\w+\s+){0,2}?discovered\b",
]
INSTITUTION_WORDS = (r"\b(?:universit(?:y|ies|ät|at|é|e|à|a)|universidad|universidade|institute|institut|instituto|"
                     r"istituto|observatory|observatoire|observatorio|osservatorio|sternwarte|college|laboratory|"
                     r"laboratoire|department\s+of|dept\.|faculty\s+of|school\s+of\s+(?:physics|astronomy))")
MAJOR_INSTITUTIONS = (
    "ETH Zurich", "ETH Zürich", "ETH", "EPFL", "UniGE", "UNIGE", "UniBE", "Uni Bern", "Harvard", "MIT", "Caltech",
    "JPL", "Princeton", "Stanford", "Berkeley", "Yale", "Oxford", "Cambridge", "Leiden", "Max Planck", "Max-Planck",
    "MPIA", "MPE", "MPIfR", "CNRS", "CEA", "INAF", "CSIC", "IAC", "CfA", "STScI", "Goddard", "GSFC", "NASA Ames",
    "IPAC", "Carnegie", "Kavli", "Weizmann", "Niels Bohr", "Sorbonne", "KU Leuven", "Chalmers",
)
TITLES = r"\b(?:Dr|Prof|Professor|Mr|Ms|Mrs)\.?\s+[A-Z][a-z]+"
FUNDING = (r"\b(?:funded\s+by|funding\s+from|grant\s+(?:no\.?|number|agreement)|acknowledge[sd]?\s+(?:support|funding)|"
           r"ERC|NSF\s+grant|SNSF)\b")
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
EMAIL_OBFUSCATED = (
    # bracketed: "jane.doe [at] unige [dot] ch", "jdoe(at)unige.ch", "jane AT unige.ch"
    r"[A-Za-z0-9._%+-]+\s*(?:\[at\]|\(at\)|\{at\}|<at>|\s+AT\s+)\s*[A-Za-z0-9-]+"
    r"(?:\s*(?:\.|\[dot\]|\(dot\)|\s+dot\s+)\s*[A-Za-z0-9-]+)+"
    # plain "at": only "jane.doe at unige.ch" (a dotted local part and an unspaced domain), not prose
    r"|[A-Za-z0-9%+-]+[._][A-Za-z0-9._%+-]*\s+at\s+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
ORCID = r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"
PERSONAL_URL = (r"https?://(?:www\.)?(?:github\.com|gitlab\.com|orcid\.org|linkedin\.com|twitter\.com|x\.com|"
                r"scholar\.google\.[a-z.]+|researchgate\.net)/[^\s)>\]]+")
SOFTWARE_NAMES = (r"\bSetuHQ\b", r"\bAshforde\b")
# upper-case file-name tokens that are not initials: proposal and catalogue words
NOT_INITIALS = {"PDF", "ETC", "SFC", "RTL", "PHT", "GO", "GTO", "TAC", "DP", "TOI", "TIC", "HD", "GJ", "BD",
                "HIP", "KIC", "LHS", "HAT", "XO", "KOI", "EB", "AO", "EM", "CSV", "TXT", "MD", "LC", "JWST", "HST"}


# URLs of the public tools a proposal must cite (ESA's Target Checker lives at cheops.unige.ch): blanked before the
# scan, keeping offsets, so citing them does not read as naming an institution. Only these exact hosts.
OFFICIAL_URL = (r"https?://(?:cheops\.unige\.ch|dace\.unige\.ch|www\.cosmos\.esa\.int|cosmos\.esa\.int|"
                r"datalabs\.esa\.int|cheops-archive\.ssdc\.asi\.it|simbad\.cds\.unistra\.fr|mast\.stsci\.edu|"
                r"exoplanetarchive\.ipac\.caltech\.edu|arxiv\.org|doi\.org)(?:/[^\s)>\]]*)?")


def _mask_official_urls(text: str) -> str:
    return re.sub(OFFICIAL_URL, lambda m: " " * len(m.group(0)), text)


# ---------------------------------------------------------------- patterns from user input


def _name_parts(name: str) -> tuple[list[str], str] | None:
    """(given names, surname) from "Jane Doe", "Doe, Jane", "J. Doe" or "Doe"."""
    name = " ".join(name.replace("_", " ").split())
    if not name:
        return None
    if "," in name:
        last, first = (x.strip() for x in name.split(",", 1))
        return [g for g in re.split(r"[\s.]+", first) if g], last
    parts = name.split(" ")
    return [g.strip(".") for g in parts[:-1] if g.strip(".")], parts[-1]


def name_patterns(name: str) -> list[tuple[str, str]]:
    """(regex, description) for the usual written forms of one person's name (matched case-insensitively)."""
    parts = _name_parts(name)
    if not parts:
        return []
    given, last = parts
    L = re.escape(last)
    pats = [(rf"\b{re.escape(name.strip())}\b", "the name as given")]
    if given:
        g0 = re.escape(given[0][0])
        inits = r"\s*".join(rf"{re.escape(g[0])}\.?" for g in given)
        pats += [
            (rf"\b{re.escape(' '.join(given))}\s+{L}\b", "full name"),
            (rf"\b{inits}\s*{L}\b", "initials and surname"),
            (rf"\b{g0}\.?\s*(?:[A-Z]\.?\s*)?{L}\b", "initial and surname"),
            (rf"\b{L}\s*,\s*{inits}", "surname, initials"),
            (rf"\b{L}\s+{inits}(?:\s|$|,)", "surname initials"),
        ]
    pats += [
        (rf"\b{L}\s+et\s+al\b", "surname in a citation"),
        (rf"\b{L}\s*(?:\(|,)?\s*(?:19|20)\d\d\b", "surname in a citation"),
        (rf"\(\s*{L}\b", "surname in a citation"),
        (rf"\b{L}\s*(?:&|and)\s+[A-Z]", "surname in a citation"),
        (rf"\b{L}'s\b", "surname, possessive"),
    ]
    return pats


def institution_patterns(extra=()) -> list[str]:
    return [INSTITUTION_WORDS] + [r"(?<![\w-])" + re.escape(i).replace(r"\ ", r"[\s-]+") + r"(?![\w-])"
                                  for i in (*MAJOR_INSTITUTIONS, *extra) if i and i.strip()]


# ---------------------------------------------------------------- text


def paragraphs(text: str):
    """(first line number, paragraph with its newlines turned into spaces) for each blank-line-separated block;
    offsets are kept, so a match's line is the first line plus the newlines before it."""
    line = 1
    for block in re.split(r"(\n[ \t]*\n)", text):
        if block.startswith("\n") and not block.strip():
            line += block.count("\n")
            continue
        yield line, block
        line += block.count("\n")


def lint_text(text: str, *, author_names=(), institutions=(), file: str = "") -> list[dict]:
    """Anonymity findings in one text: level (warn or info), rule, line number, the matched excerpt."""
    rules = [("email", EMAIL, "warn", 0), ("email-obfuscated", EMAIL_OBFUSCATED, "warn", 0), ("orcid", ORCID, "warn", 0),
             ("self-reference", "|".join(f"(?:{p})" for p in SELF_REFERENCE), "warn", re.I),
             ("title-and-name", TITLES, "warn", 0), ("funding", FUNDING, "warn", re.I),
             ("personal-url", PERSONAL_URL, "warn", re.I)]
    rules += [("institution", p, "warn", re.I) for p in institution_patterns(institutions)]
    for n in author_names:
        rules += [(f"author-name ({what})", p, "warn", re.I) for p, what in name_patterns(n)]
    findings, seen = [], set()
    for start, para in paragraphs(text):
        flat = _mask_official_urls(para.replace("\n", " "))
        for rule, pattern, level, flags in rules:
            for m in re.finditer(pattern, flat, flags):
                line = start + para[:m.start()].count("\n")
                key = (rule.split(" ")[0], line, m.start())
                if key in seen:
                    continue
                seen.add(key)
                findings.append({"level": level, "rule": rule, "file": file, "line": line,
                                 "match": " ".join(m.group(0).split())})
        for pattern in SOFTWARE_NAMES:
            for m in re.finditer(pattern, flat):
                findings.append({"level": "info", "rule": "names-software", "file": file,
                                 "line": start + para[:m.start()].count("\n"), "match": m.group(0),
                                 "note": "Citing public software is fine; if you develop it, cite it neutrally."})
        for m in re.finditer(re.escape(TODO), flat):
            findings.append({"level": "info", "rule": "unfinished", "file": file,
                             "line": start + para[:m.start()].count("\n"), "match": TODO})
    return sorted(findings, key=lambda f: (f["line"], f["rule"]))


# ---------------------------------------------------------------- file names


def lint_filenames(paths, *, author_names=(), institutions=()) -> list[dict]:
    """File names must be anonymous too: no e-mail, ORCID iD, institution, given name or initials in them."""
    out = []
    for p in paths:
        name = Path(p).name
        stem = Path(p).stem if Path(p).suffix else name
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", stem) if t]
        joined = "".join(tokens).lower()
        hits = [(m.group(0), "e-mail") for m in re.finditer(EMAIL, name)]
        hits += [(m.group(0), "ORCID iD") for m in re.finditer(ORCID, name)]
        spaced = " ".join(tokens)
        for pat in institution_patterns(institutions):
            hits += [(m.group(0), "institution") for m in re.finditer(pat, spaced, re.I)]
        for n in author_names:
            parts = _name_parts(n)
            if not parts:
                continue
            given, last = parts
            last_l = re.sub(r"[^a-z0-9]", "", last.lower())
            inits = "".join(g[0].lower() for g in given)
            forms = {last_l + "".join(g.lower() for g in given), "".join(g.lower() for g in given) + last_l}
            if inits:
                forms |= {inits + last_l, last_l + inits, inits[0] + last_l, last_l + inits[0]}
            if any(t.lower() == last_l for t in tokens) or any(f and f in joined for f in forms if len(f) > len(last_l)):
                hits.append((n, "author name"))
        hits += [(t, "looks like initials") for t in tokens if re.fullmatch(r"[A-Z]{2,3}", t)
                 and t not in NOT_INITIALS]
        out += [{"level": "warn", "rule": f"file-name ({why})", "file": name, "line": 0, "match": h} for h, why in hits]
    return out


# ---------------------------------------------------------------- files


def read_text_for_lint(path: Path) -> str:
    """The text of a file to lint: UTF-8 text, or a PDF's extracted text. Anything else is refused."""
    raw = Path(path).read_bytes()
    if raw[:5] == b"%PDF-" or Path(path).suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise LintInputError(f"{Path(path).name}: a PDF, and pypdf is not installed (pip install pypdf); "
                                 "lint the source text instead. Not reported as clean.") from None
        import io

        try:
            text = "\n\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages)
        except Exception as exc:  # noqa: BLE001 (any parse failure is a refusal, never a clean result)
            raise LintInputError(f"{Path(path).name}: the PDF could not be read ({type(exc).__name__}); "
                                 "lint the source text instead.") from None
        if len(text.strip()) < 20:
            raise LintInputError(f"{Path(path).name}: the PDF has no extractable text (outlined fonts or images); "
                                 "lint the source text instead. Not reported as clean.")
        return text
    if b"\x00" in raw[:4096]:
        raise LintInputError(f"{Path(path).name}: not a text file; lint the source text instead.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise LintInputError(f"{Path(path).name}: not UTF-8 text; lint the source text instead.") from None


def lint_files(paths, *, author_names=(), institutions=()) -> list[dict]:
    """Lint the file names and the text of each file. Raises :class:`LintInputError` for a file it cannot read."""
    findings = lint_filenames(paths, author_names=author_names, institutions=institutions)
    for p in paths:
        findings += lint_text(read_text_for_lint(Path(p)), author_names=author_names, institutions=institutions,
                              file=Path(p).name)
    return findings


def format_findings(findings: list[dict]) -> str:
    lines = []
    for f in findings:
        lines.append(f"{f['level'].upper():4s} {f['file']}:{f['line']} {f['rule']}: {f['match']!r}"
                     + (f" ({f['note']})" if f.get("note") else ""))
    n = sum(f["level"] == "warn" for f in findings)
    lines.append(f"anonymity lint: {n} warning(s), {len(findings) - n} note(s)" if findings
                 else "anonymity lint: no findings")
    return "\n".join(lines + [NOT_A_GUARANTEE])
