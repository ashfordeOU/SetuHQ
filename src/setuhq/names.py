# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Display names for the reviewer panel: the Sentinels and the Probes.

The AI reviewers are shown as Sentinels ("Sentinel · Volunteer", "Sentinel · Skeptic") whatever their
provider (the provider and model are shown beside the name, never in it), and the
deterministic simulated reviewers as Probes ("Probe · Sensitive", "Probe · Typical", "Probe · Cautious").
Only what the pages show changes: reviewer ids stay as they are in every data file, CSV, JSON and URL,
and the pages keep each id beside its name (a tooltip or small mono text) so it can be traced.
"""

from __future__ import annotations

# Every Sentinel config type. Claude (Anthropic) is the default; the others are supported and labelled.
SENTINEL_KINDS = ("claude", "claude_code", "openai", "gemini", "openai_compatible")
PROBE_KINDS = ("simulated",)

# The attribution, word for word, on the Panel page and in the Docket's provenance.
ATTRIBUTION = ("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. "
               "Probes are deterministic matched-filter detectors.")

# Who runs each Sentinel kind: the provider tag shown beside a Sentinel's name.
PROVIDER_BY_KIND = {
    "claude": "Claude (Anthropic API)",
    "claude_code": "Claude (Claude Code CLI)",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "openai_compatible": "OpenAI-compatible endpoint",
}

# Id prefixes dropped from a display name: claude-skeptic, gpt-skeptic and gemini-skeptic are all "Sentinel · Skeptic".
_PREFIXES = {"sentinel": ("claude-", "sentinel-", "gpt-", "openai-", "gemini-", "compat-", "local-", "ollama-"),
             "probe": ("volunteer-", "sim-", "probe-")}


# SetuHQ was called exoplan before its public release, and records stored then (sweep credits, run notes) say so.
# Pages show the current name; the records are left as stored (they are hashed).
LEGACY_NAME = "exoplan"


def public_name(name: str) -> str:
    """A contributor or tool name as a page shows it: the old project name becomes SetuHQ."""
    return "SetuHQ" if str(name).strip().lower() == LEGACY_NAME else str(name)


def public_text(text: str) -> str:
    """Stored prose (a validation note) as a page shows it: the old name and its source paths read as today's."""
    import re

    text = text.replace("src/exoplan/", "src/setuhq/")
    text = re.sub(r"(['`])exoplan (?=[a-z])", r"\1setuhq ", text)  # a quoted command: 'exoplan calibrate'
    return re.sub(r"\bexoplan\b", "SetuHQ", text)


def provider_label(kind: str | None) -> str | None:
    """'OpenAI' for an openai Sentinel, 'Claude (Claude Code CLI)' for claude_code; None for a Probe."""
    return PROVIDER_BY_KIND.get(kind or "")


def role(kind: str | None) -> str | None:
    """'sentinel' for a Sentinel (an AI reviewer on any provider), 'probe' for a simulated one, None otherwise."""
    if kind in SENTINEL_KINDS:
        return "sentinel"
    if kind in PROBE_KINDS:
        return "probe"
    return None


def _tail(rid: str, which: str) -> str:
    for p in _PREFIXES[which]:
        if rid.startswith(p) and len(rid) > len(p):
            rid = rid[len(p):]
            break
    return " ".join(w.capitalize() for w in rid.replace("_", "-").split("-") if w)


def display_name(rid: str, kind: str | None) -> str:
    """'Sentinel · Volunteer' for claude-volunteer, 'Probe · Sensitive' for volunteer-sensitive; else the id."""
    r = role(kind)
    if r is None:
        return rid
    return f"{'Sentinel' if r == 'sentinel' else 'Probe'} · {_tail(rid, r)}"


def short_name(rid: str, kind: str | None) -> str:
    """The transit strip's lane label: 'SEN Volunteer', 'PRB Sensitive'; else the id."""
    r = role(kind)
    if r is None:
        return rid
    return f"{'SEN' if r == 'sentinel' else 'PRB'} {_tail(rid, r)}"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def panel_phrase(n_sentinels: int, n_probes: int, n_other: int = 0) -> str:
    """'2 Sentinels and 3 Probes' (Sentinels first), with any other kind counted after."""
    parts = [plural(n_sentinels, "Sentinel") if n_sentinels else "", plural(n_probes, "Probe") if n_probes else "",
             f"{n_other} other" if n_other else ""]
    parts = [p for p in parts if p]
    if not parts:
        return "no reviewers"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def reviewer_provenance(manifest: dict) -> dict[str, dict]:
    """Each Sentinel's provider, model and calibration status, from a run manifest, for the pages.

    The model is the one the provider reported when the manifest has it (``models_reported``), else
    the configured one. A run written before providers were recorded gives each Claude Sentinel its
    kind's provider and the model as "not recorded".
    """
    out = {}
    for r in manifest.get("reviewers") or []:
        if r.get("kind") not in SENTINEL_KINDS:
            continue
        reported = r.get("models_reported") or []
        out[r["id"]] = {
            "provider_label": r.get("provider_label") or PROVIDER_BY_KIND.get(r["kind"], r["kind"]),
            "model": ", ".join(reported) if reported else (r.get("model") or "model not recorded"),
            "model_reported": bool(reported),
            "calibration": r.get("calibration"),
        }
    return out


def reviewer_names(kinds: dict[str, str]) -> dict[str, dict]:
    """For the pages: each reviewer id with its display name, lane label and role."""
    return {rid: {"id": rid, "name": display_name(rid, k), "short": short_name(rid, k), "role": role(k) or "other",
                  "provider": provider_label(k)}
            for rid, k in kinds.items()}


# A dip's status from its vetting outcome: only a dip that passed vetting is a candidate. A rejected dip is never
# called one; a flagged dip is open (waiting for review). (class, tag word, full phrase.) A search-feed entry passed
# vetting to enter the feed (discover.py), so its statuses count as candidates.
DIP_STATE = {"passed": ("cand", "candidate", "candidate, unconfirmed"),
             "flagged": ("open", "flagged", "flagged for review, open"),
             "rejected": ("rej", "rejected", "rejected by vetting, not a candidate")}
FEED_STATUSES = ("new_candidate", "known_toi")


def dip_state(outcome: str | None) -> tuple[str, str, str]:
    return DIP_STATE.get("passed" if outcome in FEED_STATUSES else outcome or "", DIP_STATE["flagged"])


def dip_count(outcomes: list[str | None]) -> str:
    """"7 dips (5 candidates, 1 flagged, 1 rejected)": a count that never calls a rejected dip a candidate."""
    words = [dip_state(o)[1] for o in outcomes]
    n, parts = len(words), []
    for w, one, many in (("candidate", "candidate", "candidates"), ("flagged", "flagged", "flagged"), ("rejected", "rejected", "rejected")):
        k = words.count(w)
        if k:
            parts.append(f"{k} {one if k == 1 else many}")
    return f"{n} dip{'' if n == 1 else 's'}" + (f" ({', '.join(parts)})" if parts else "")
