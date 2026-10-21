# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The anonymity lint: an aid for double-anonymous review, not a guarantee.

It scans proposal text for what commonly breaks anonymity and warns; it never edits, and a clean result does
not prove a text is anonymous (a human must read it). What it looks for:

* e-mail addresses, including obfuscated ones ("jane.doe [at] unige.ch", "jane.doe@ unige.ch"), and ORCID iDs;
* names the user gives (``--author-name``), in their usual variants: "Jane Doe", "J. Doe", "Doe, J.",
  "DOE J", "Jane Doe's", and the surname alone in a citation-like context ("Doe et al.", "Doe (2023)");
* institutions, case-insensitively and across hyphen joins ("IAA-CSIC"): generic words ("university of ...",
  "institute", "observatory", "department of"), a modest built-in list of major institutions, and any the
  user gives (``--institution``);
* self-reference: "my"/"our" before a research noun ("my previous paper", "our earlier CHEOPS programme",
  "our 2023 study", "our work (Doe et al. 2023)", "our team", "our tools"), "we have previously shown", "we are
  the team that discovered", "the code we developed"; and in the third person: "the authors' prior work", "the
  proposers' earlier programme", "this team", "Paper I of this series";
* titles before names, funding acknowledgements ("We thank the ... Foundation for support"), and personal pages
  (code hosts, ORCID, arxiv.org/a/ author pages, ``~user``, ``/profile/`` and similar paths on any host);
* file names: e-mail addresses, ORCID iDs, institutions, the given names (surname, initials + surname), and
  initials-like tokens ("Doe_SJ").

Before the scan, a copy of the text is normalised: NFKC (fullwidth and compatibility forms), format characters
(zero-width spaces, joiners, bidi marks) removed, and Cyrillic and Greek look-alikes folded to Latin. Findings
quote the original text and give its original line numbers. Text is scanned paragraph by paragraph (lines
joined), so a phrase wrapped over two lines is still caught.

The exact public tool pages a proposal must cite (the Target Checker, the ETC and the archive browser at
cheops.unige.ch), arXiv abstract pages and DOIs are masked for the institution and self-reference rules only;
the e-mail, name, title and personal-page rules always see the unmasked text.

A PDF is read with pypdf when it is installed (``pip install pypdf``): its page text, every string its
text-showing operators draw (pypdf's layout extraction can drop some), and its metadata (Author, Title, Subject,
Creator, Producer, Keywords). Images are counted and reported as not scanned. A PDF without extractable text,
or any other non-text file, is refused rather than reported clean.
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
                 r"tools?|instruments?|telescopes?|facility|thesis|students?|postdocs?|discovery|detection|"
                 r"method|methods|models?|packages?|ephemeris|light\s+curves?)")
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
    # third person: "the authors' prior work", "the proposers' earlier CHEOPS programme"
    rf"\b(?:the\s+)?(?:authors|proposers|applicants|investigators|PIs|team)['’]s?\s+(?:own\s+)?(?:[\w-]+\s+){{0,3}}?"
    rf"{RESEARCH_NOUN}\b",
    rf"\b(?:the\s+)?(?:author|proposer|applicant|investigator|PI|team)['’]s\s+(?:own\s+)?(?:[\w-]+\s+){{0,3}}?"
    rf"{RESEARCH_NOUN}\b",
    # "this team", "the present team", "by the proposing team"
    r"\b(?:this|the\s+present|the\s+proposing|the\s+same|our\s+own)\s+(?:team|group|collaboration|consortium)\b",
    # "Paper I of this series", "the first paper of this series"
    r"\b(?:Paper\s+[IVX]+|the\s+(?:first|second|third|previous)\s+paper)\s+(?:of|in)\s+(?:this|the\s+present|our)\s+"
    r"series\b",
    # "the code we developed", "a pipeline I wrote"
    r"\b(?:code|codes|pipeline|software|tool|tools|method|model|package|algorithm)\s+(?:that\s+|which\s+)?(?:we|I)\s+"
    r"(?:have\s+|had\s+)?(?:developed|wrote|written|built|created|published|released|designed)\b",
    # "I am the first author of ..."
    r"\b(?:I|we)\s+(?:am|are|was|were)\s+(?:the\s+)?(?:first|lead|corresponding|senior)\s+authors?\b",
]
INSTITUTION_WORDS = (r"\b(?:universit(?:y|ies|ät|at|é|e|à|a)|universidad|universidade|institute|institut|instituto|"
                     r"istituto|observatory|observatoire|observatorio|osservatorio|sternwarte|college|laboratory|"
                     r"laboratoire|department\s+of|dept\.|faculty\s+of|school\s+of\s+(?:physics|astronomy))")
MAJOR_INSTITUTIONS = (
    "ETH Zurich", "ETH Zürich", "ETH", "EPFL", "UniGE", "UNIGE", "UniBE", "Uni Bern", "Harvard", "MIT", "Caltech",
    "JPL", "Princeton", "Stanford", "Berkeley", "Yale", "Oxford", "Cambridge", "Leiden", "Max Planck", "Max-Planck",
    "MPIA", "MPE", "MPIfR", "CNRS", "CEA", "INAF", "CSIC", "IAC", "CfA", "STScI", "Goddard", "GSFC", "NASA Ames",
    "IPAC", "Carnegie", "Kavli", "Weizmann", "Niels Bohr", "Sorbonne", "KU Leuven", "Chalmers",
    "OCA", "IAA", "IAP", "LAM", "IPAG", "UCL", "DTU", "IoA", "IAS", "IRAP", "MPS", "LESIA", "SRON", "DLR",
)
TITLES = r"\b(?:Dr|Prof|Professor|Mr|Ms|Mrs)\.?\s+[A-Z][a-z]+"
FUNDING = (r"\b(?:funded\s+by|funding\s+from|grant\s+(?:no\.?|number|agreement)|acknowledge[sd]?\s+(?:support|funding)|"
           r"ERC|NSF\s+grant|SNSF)\b"
           # "We thank the Swiss National Science Foundation for support"
           r"|\b(?:we|I)\s+(?:thank|acknowledge|are\s+grateful\s+to|gratefully\s+acknowledge)\b[^.]{0,120}?"
           r"\b(?:Foundation|Agency|Council|Fund|Ministry|Grant|Fellowship|for\s+(?:financial\s+)?support)\b")
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
EMAIL_OBFUSCATED = (
    # bracketed: "jane.doe [at] unige [dot] ch", "jdoe(at)unige.ch", "jane AT unige.ch"
    r"[A-Za-z0-9._%+-]+\s*(?:\[at\]|\(at\)|\{at\}|<at>|\s+AT\s+)\s*[A-Za-z0-9-]+"
    r"(?:\s*(?:\.|\[dot\]|\(dot\)|\s+dot\s+)\s*[A-Za-z0-9-]+)+"
    # plain "at": only "jane.doe at unige.ch" (a dotted local part and an unspaced domain), not prose
    r"|[A-Za-z0-9%+-]+[._][A-Za-z0-9._%+-]*\s+at\s+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"
    # an "@" with spaces around it: "jane.doe@ unige.ch"
    r"|[A-Za-z0-9._%+-]+(?:\s+@\s*|@\s+)[A-Za-z0-9-]+(?:\s*\.\s*[A-Za-z0-9-]+)*\s*\.\s*[A-Za-z]{2,}\b")
ORCID = r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"
PERSONAL_URL = (r"https?://(?:www\.)?(?:github\.com|gitlab\.com|orcid\.org|linkedin\.com|twitter\.com|x\.com|"
                r"scholar\.google\.[a-z.]+|researchgate\.net)/[^\s)>\]]+"
                # author pages and personal directories on any host: arxiv.org/a/..., /~user, /profile/, /people/
                r"|(?:https?://)?(?:www\.)?arxiv\.org/a/[^\s)>\]]+"
                r"|(?:https?://)?[\w.-]+\.[a-z]{2,}(?:/[^\s)>\]]*)?/(?:~[\w.-]+|(?:profile|people|staff|members|user|"
                r"users|homepage|personal)/[\w.-]+)[^\s)>\]]*")
SOFTWARE_NAMES = (r"\bSetuHQ\b", r"\bAshforde\b")
# upper-case file-name tokens that are not initials: proposal and catalogue words
NOT_INITIALS = {"PDF", "ETC", "SFC", "RTL", "PHT", "GO", "GTO", "TAC", "DP", "TOI", "TIC", "HD", "GJ", "BD",
                "HIP", "KIC", "LHS", "HAT", "XO", "KOI", "EB", "AO", "EM", "CSV", "TXT", "MD", "LC", "JWST", "HST"}


# The exact public tool pages a proposal must cite (ESA's Target Checker, ETC and archive browser live at
# cheops.unige.ch), arXiv abstracts and DOIs: blanked before the institution and self-reference rules, keeping
# offsets, so citing them does not read as naming an institution. Nothing else on those hosts is masked (an
# author page, a ~user or /profile/ path stays visible), and the e-mail, name and personal-URL rules always run
# on the unmasked text.
OFFICIAL_URL = (r"https?://cheops\.unige\.ch/(?:pht2/search-reserved-targets|pht2/exposure-time-calculator|"
                r"archive_browser)/?(?=[\s)>\],;]|\.(?:\s|$)|$)"
                r"|https?://(?:www\.)?arxiv\.org/abs/(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?=[\s)>\],;]|\.(?:\s|$)|$)"
                r"|https?://(?:dx\.)?doi\.org/10\.\d{4,9}/[-._;()/:A-Za-z0-9]+?(?=[\s)>\],;]|\.(?:\s|$)|$)")


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
    # word edges are letters and digits only, so hyphen joins ("IAA-CSIC") are still caught
    return [INSTITUTION_WORDS] + [r"(?<![A-Za-z0-9])" + re.escape(i).replace(r"\ ", r"[\s-]+") + r"(?![A-Za-z0-9])"
                                  for i in (*MAJOR_INSTITUTIONS, *extra) if i and i.strip()]


# ---------------------------------------------------------------- text

# Cyrillic and Greek letters that look like Latin ones, folded before the scan (the scan only; the report quotes
# the original text).
CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t",
    "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ь": "b",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "У": "Y", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W",
    "α": "a", "ο": "o", "ν": "v", "ρ": "p", "ι": "i", "κ": "k", "τ": "t", "υ": "u", "χ": "x", "ε": "e",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})


def normalise_for_scan(text: str) -> tuple[str, list[int]]:
    """The text as the rules see it, and for each of its characters the index of the original character: NFKC
    (fullwidth and compatibility forms), format characters (category Cf: zero-width spaces, joiners, bidi marks)
    removed, Cyrillic and Greek look-alikes folded to Latin. Newlines are kept, so lines map back exactly."""
    import unicodedata

    out, where = [], []
    for i, ch in enumerate(text):
        if unicodedata.category(ch) == "Cf":
            continue
        for c in unicodedata.normalize("NFKC", ch).translate(CONFUSABLES):
            if unicodedata.category(c) == "Cf":
                continue
            out.append(c)
            where.append(i)
    return "".join(out), where


def paragraphs(text: str):
    """(start offset, paragraph) for each blank-line-separated block of ``text``."""
    pos = 0
    for block in re.split(r"(\n[ \t]*\n)", text):
        if not (block.startswith("\n") and not block.strip()):
            yield pos, block
        pos += len(block)


# Rules that must see the text unmasked (the official-URL mask must never hide an address, a name or a page).
UNMASKED_RULES = ("email", "email-obfuscated", "orcid", "personal-url", "title-and-name", "author-name")


def lint_text(text: str, *, author_names=(), institutions=(), file: str = "") -> list[dict]:
    """Anonymity findings in one text: level (warn or info), rule, original line number, the matched excerpt.
    The scan runs on a normalised copy (see :func:`normalise_for_scan`); lines refer to the original text."""
    import bisect

    rules = [("email", EMAIL, "warn", 0), ("email-obfuscated", EMAIL_OBFUSCATED, "warn", 0), ("orcid", ORCID, "warn", 0),
             ("self-reference", "|".join(f"(?:{p})" for p in SELF_REFERENCE), "warn", re.I),
             ("title-and-name", TITLES, "warn", 0), ("funding", FUNDING, "warn", re.I),
             ("personal-url", PERSONAL_URL, "warn", re.I)]
    rules += [("institution", p, "warn", re.I) for p in institution_patterns(institutions)]
    for n in author_names:
        rules += [(f"author-name ({what})", p, "warn", re.I) for p, what in name_patterns(n)]
    norm, where = normalise_for_scan(text)
    newlines = [i for i, c in enumerate(text) if c == "\n"]

    def line_of(pos_in_norm: int) -> int:
        orig = where[min(pos_in_norm, len(where) - 1)] if where else 0
        return bisect.bisect_left(newlines, orig) + 1

    def excerpt(a: int, b: int) -> str:
        if not where:
            return ""
        return " ".join(text[where[a]:where[max(a, b - 1)] + 1].split())

    findings, seen = [], set()
    for start, para in paragraphs(norm):
        plain = para.replace("\n", " ")
        masked = re.sub(OFFICIAL_URL, lambda m: " " * len(m.group(0)), plain)
        for rule, pattern, level, flags in rules:
            hay = plain if rule.split(" ")[0] in UNMASKED_RULES else masked
            for m in re.finditer(pattern, hay, flags):
                a = start + m.start()
                key = (rule.split(" ")[0], a)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({"level": level, "rule": rule, "file": file, "line": line_of(a),
                                 "match": excerpt(a, start + m.end())})
        for pattern in SOFTWARE_NAMES:
            for m in re.finditer(pattern, plain):
                findings.append({"level": "info", "rule": "names-software", "file": file,
                                 "line": line_of(start + m.start()), "match": m.group(0),
                                 "note": "Citing public software is fine; if you develop it, cite it neutrally."})
        for m in re.finditer(re.escape(TODO), plain):
            findings.append({"level": "info", "rule": "unfinished", "file": file,
                             "line": line_of(start + m.start()), "match": TODO})
    if norm != text:
        n = sum(1 for a, b in zip(norm, text) if a != b) or abs(len(norm) - len(text))
        findings.append({"level": "info", "rule": "normalised", "file": file, "line": 0, "match": f"{n} character(s)",
                         "note": "Look-alike, fullwidth or invisible characters were normalised before the scan."})
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


PDF_METADATA_KEYS = ("/Author", "/Title", "/Subject", "/Creator", "/Producer", "/Keywords")


def images_note(n: int) -> str:
    return f"{n} image{'s' if n != 1 else ''} not scanned (text in images cannot be checked)"


def _pdf_operator_strings(reader) -> list[str]:
    """Every string drawn by a text-showing operator (Tj, TJ, ', ") on every page, decoded as well as pypdf can
    without the font's encoding (simple fonts come out readable; CID fonts may not)."""
    from pypdf.generic import ContentStream

    out = []
    for page in reader.pages:
        contents = page.get_contents()
        if contents is None:
            continue
        for operands, op in ContentStream(contents, reader).operations:
            if op in (b"Tj", b"'", b'"'):
                items = operands[-1:]
            elif op == b"TJ":
                items = [x for x in (operands[0] if operands else []) if not isinstance(x, (int, float))]
            else:
                continue
            parts = []
            for x in items:
                if isinstance(x, bytes):
                    parts.append(x.decode("latin-1", errors="replace"))
                elif hasattr(x, "get_original_bytes"):
                    parts.append(str(x))
                elif isinstance(x, str):
                    parts.append(x)
            t = "".join(parts).strip()
            if t:
                out.append(t)
    return out


def read_pdf_for_lint(path: Path) -> tuple[str, str, int]:
    """(page text, metadata as text, number of images) of a PDF, read with pypdf. Refused (LintInputError) when
    pypdf is missing or the file cannot be read; the caller refuses a PDF without page text."""
    import io

    try:
        from pypdf import PdfReader
    except ImportError:
        raise LintInputError(f"{Path(path).name}: a PDF, and pypdf is not installed (pip install pypdf); "
                             "lint the source text instead. Not reported as clean.") from None
    try:
        reader = PdfReader(io.BytesIO(Path(path).read_bytes()))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        # pypdf's layout extraction can drop strings (a caption after a drawn path, for one): add every string a
        # text-showing operator draws that the extraction missed.
        seen = " ".join(text.split())
        missed = [t for t in _pdf_operator_strings(reader) if " ".join(t.split()) not in seen]
        if missed:
            text = "\n\n".join([text, *missed])
        n_images = 0
        for page in reader.pages:
            try:
                n_images += len(page.images)
            except Exception:  # noqa: BLE001 (an unreadable image still counts as unscanned)
                n_images += 1
        meta = reader.metadata or {}
        meta_text = "\n\n".join(f"{k[1:]}: {meta.get(k)}" for k in PDF_METADATA_KEYS if meta.get(k))
    except LintInputError:
        raise
    except Exception as exc:  # noqa: BLE001 (any parse failure is a refusal, never a clean result)
        raise LintInputError(f"{Path(path).name}: the PDF could not be read ({type(exc).__name__}); "
                             "lint the source text instead.") from None
    return text, meta_text, n_images


def read_text_for_lint(path: Path) -> str:
    """The text of a file to lint: UTF-8 text, or a PDF's extracted page text. Anything else is refused."""
    raw = Path(path).read_bytes()
    if raw[:5] == b"%PDF-" or Path(path).suffix.lower() == ".pdf":
        text, _, n_images = read_pdf_for_lint(path)
        if len(text.strip()) < 20:
            raise LintInputError(f"{Path(path).name}: the PDF has no extractable text (outlined fonts or images"
                                 + (f"; {images_note(n_images)}" if n_images else "")
                                 + "); lint the source text instead. Not reported as clean.")
        return text
    if b"\x00" in raw[:4096]:
        raise LintInputError(f"{Path(path).name}: not a text file; lint the source text instead.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise LintInputError(f"{Path(path).name}: not UTF-8 text; lint the source text instead.") from None


def lint_files(paths, *, author_names=(), institutions=()) -> list[dict]:
    """Lint the file names and the text of each file; for a PDF also its metadata (Author, Title, Subject, Creator,
    Producer, Keywords), with a note of the images that were not scanned. Raises :class:`LintInputError` for a file
    it cannot read as text."""
    findings = lint_filenames(paths, author_names=author_names, institutions=institutions)
    for p in paths:
        p = Path(p)
        findings += lint_text(read_text_for_lint(p), author_names=author_names, institutions=institutions, file=p.name)
        if p.read_bytes()[:5] == b"%PDF-" or p.suffix.lower() == ".pdf":
            _, meta_text, n_images = read_pdf_for_lint(p)
            if meta_text:
                for f in lint_text(meta_text, author_names=author_names, institutions=institutions,
                                   file=f"{p.name} (metadata)"):
                    if f["rule"] != "normalised":
                        findings.append(f | {"line": 0})
                flat = normalise_for_scan(meta_text)[0]
                for n in author_names:  # in metadata, a surname alone is enough ("Doe CHEOPS proposal")
                    parts = _name_parts(n)
                    if parts and re.search(rf"\b{re.escape(parts[1])}\b", flat, re.I):
                        findings.append({"level": "warn", "rule": "author-name (surname in PDF metadata)",
                                         "file": f"{p.name} (metadata)", "line": 0, "match": parts[1]})
            if n_images:
                findings.append({"level": "info", "rule": "images", "file": p.name, "line": 0,
                                 "match": images_note(n_images)})
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
