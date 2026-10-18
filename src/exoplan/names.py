"""Display names for the reviewer panel: the Sentinels and the Probes.

The Claude reviewers are shown as Sentinels ("Sentinel · Volunteer", "Sentinel · Skeptic") and the
deterministic simulated reviewers as Probes ("Probe · Sensitive", "Probe · Typical", "Probe · Cautious").
Only what the pages show changes: reviewer ids stay as they are in every data file, CSV, JSON and URL,
and the pages keep each id beside its name (a tooltip or small mono text) so it can be traced.
"""

from __future__ import annotations

SENTINEL_KINDS = ("claude", "claude_code")
PROBE_KINDS = ("simulated",)

# The attribution, word for word, on the Panel page and in the Docket's provenance.
ATTRIBUTION = "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors."

_PREFIXES = {"sentinel": ("claude-",), "probe": ("volunteer-", "sim-", "probe-")}


def role(kind: str | None) -> str | None:
    """'sentinel' for a Claude reviewer, 'probe' for a simulated one, None otherwise."""
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


def reviewer_names(kinds: dict[str, str]) -> dict[str, dict]:
    """For the pages: each reviewer id with its display name, lane label and role."""
    return {rid: {"id": rid, "name": display_name(rid, k), "short": short_name(rid, k), "role": role(k) or "other"}
            for rid, k in kinds.items()}
