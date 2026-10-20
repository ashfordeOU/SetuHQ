"""Statistical validation (S3): false-positive probabilities and the label exoplan may print.

**The rule.** A candidate is "validated (statistically)" only when TRICERATOPS (Giacalone et al. 2021,
doi:10.3847/1538-3881/abc6af) gives FPP < 0.015 and NFPP < 10⁻³ *and* a high-resolution imaging contrast curve was
used. Without a contrast curve the label is "not validated: no contrast curve", whatever the probabilities. exoplan
never calls its own results "confirmed": confirmation needs an independent measurement such as a mass (ATLAS E10).

**What runs.** TRICERATOPS 1.1.0 installs with pip (it pulls pytransit, numba, celerite, emcee and arviz), but it is
not offline-capable: ``triceratops.target()`` queries the TIC through MAST, a Gaia DR3 background population and a
TESSCut image on construction, and MAST's API was failing on 2026-10-19. So exoplan runs a **reduced FPP scheme** of
its own by default (:func:`reduced_fpp`), and :func:`run_triceratops` is an optional adapter (extra ``validate``)
for when TRICERATOPS and the archives can be reached. The reduced scheme can never produce "validated".

**The reduced scheme** (exoplan's, not a published method; every number in it is stated here):

Scenarios. TP, a planet transiting the target; EB, the target is an eclipsing binary at the detected period; EBx2P,
the target is an eclipsing binary at twice the period (primary and secondary alternate); NFP_i, an eclipse on a
resolved catalogued neighbour i. **Not modelled**: unresolved bound or background companions (HEB, BEB, planets on
companions). Bounding those is what a contrast curve and a stellar-population model are for, so the reduced FPP is a
lower bound on the full one, and the label says "not validated" for that reason too.

Likelihoods, from the S2 measurements (each closed-form):

* Secondary, from the all-phase search: the strongest dip s ± σ_s at any phase, in units of z = s/σ_s with σ_s
  scaled by the scan's noise (never below the nominal σ/√n, as in the secondary threshold). TP and EBx2P predict no secondary, so z is the largest dip of a white-noise scan:
  likelihood f₀(z), the simulated null density for that number of box positions (``null_cdf`` in
  docs/results/secondary_calibration.json, with an exponential (generalized Pareto, ξ = 0) tail fitted above its 99th percentile, so f₀
  is smooth and decreasing where only a few dozen simulated scans lie; modelling it as the largest of N_eff independent draws broke in the low
  tail and charged a planet for an unusually small dip). EB predicts a true secondary μ uniform in [0, Z], Z = δ/σ_s,
  so the largest dip is the larger of N(μ, 1) and the noise maximum: likelihood
  (1/Z) [F₀(z)(Φ(z) − Φ(z−Z)) + f₀(z)(G(z) − G(z−Z))] with G(u) = uΦ(u) + φ(u). Without the all-phase search, the
  phase-0.5 value is used with N(s; 0, σ_s), and so it is when the strongest dip is not periodic (one epoch
  carries 70% or more of it): a binary's secondary is in every epoch. (A planet's own occultation is taken as zero; it is tens of ppm at
  most for hot Jupiters in TESS.)
* The secondary likelihood assumes the scan is white noise. When it is not (robust spread outside 0.7–1.3, std
  over robust spread above 1.3, or a largest |excursion| beyond the white-noise 99.9% quantile for that number of
  positions), the FPP moved from 0.007 to 0.77 on pi Men c between plausible noise models, so no FPP or NFPP is
  given: the result reads "FPP not computed: secondary scan non-white (…)" with the numbers, and the spread of
  FPPs over noise models is kept in the evidence only. When it is white, the FPP is quoted at the robust spread
  with the robust-versus-std bracket beside it.
* Odd − even depth d ± σ_d: TP and EB predict 0, N(d; 0, σ_d); EBx2P predicts a difference anywhere in [−δ, δ],
  (1/2δ) ∫ N(d; x, σ_d) dx.
* Shape: when the transit fit is grazing, the binary scenarios gain exp(min(Δχ²_V, 50)/2), where Δχ²_V is how much
  worse the forced full transit fits (the V-shape test of transitfit.py); otherwise 1.
* Position: with a reliable difference-image centroid c (covariance C), each source s gets exp(−½ (c − s)ᵀ C⁻¹
  (c − s)); without one, every source gets 1 (no information). A neighbour that would need an eclipse deeper than
  100% gets 0.
* Light curve of a nearby-star scenario: a diluted eclipse on a neighbour leaves the same secondary, odd/even and
  shape evidence in the target's aperture, so NFP_i takes the prior-weighted mean of the TP, EB and EBx2P
  light-curve likelihoods. Only position (and the depth limit) separates the target from its neighbours.

Priors (illustrative, configurable): P(TP) = 0.75, P(EB) = 0.10, P(EBx2P) = 0.05, P(NFP) = 0.10 shared equally by
the neighbours not ruled out by depth. The 25% false-positive total follows Guerrero et al. 2021 (565 of 2,241 TOIs
were false positives after follow-up, doi:10.3847/1538-4365/abefe1); the split between scenarios is a choice, not a
measurement. FPP = 1 − P(TP | data); NFPP = Σ_i P(NFP_i | data).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm

FPP_VALIDATED = 0.015       # TRICERATOPS "validated" (Giacalone et al. 2021)
NFPP_VALIDATED = 1e-3
FPP_LIKELY_PLANET = 0.5     # "likely planet": FPP < 0.5 and NFPP < 1e-3
NFPP_LIKELY_NFP = 0.1       # "likely nearby false positive": NFPP > 0.1
V_SHAPE_CAP = 50.0

VALIDATED = "validated (statistically)"
NO_CONTRAST = "not validated: no contrast curve"
REDUCED_ONLY = "not validated: reduced FPP scheme, not TRICERATOPS"
NOT_VALIDATED = "not validated"
LABELS = (VALIDATED, NO_CONTRAST, REDUCED_ONLY, NOT_VALIDATED)
REDUCED_CLASS_SUFFIX = " (by number, reduced scheme)"


@dataclass(frozen=True)
class Priors:
    tp: float = 0.75
    eb: float = 0.10
    eb2p: float = 0.05
    nfp: float = 0.10
    source: str = ("illustrative: a 25% false-positive total (Guerrero et al. 2021, TOIs) split 10/5/10 between "
                   "EB, EBx2P and nearby stars by choice")


LIKELY_FP = "likely false positive"   # the reduced FPP above 0.5 on every detrending setting (not a TRICERATOPS class)
MAX_LOG10_ODDS_SPREAD = 1.0           # an FPP whose odds vary by more than a factor of 10 across settings is refused


def log_odds_spread(values) -> float:
    """max − min of log10(FPP / (1 − FPP)) over ``values`` (each clipped to [1e-12, 1 − 1e-12]): the stability test
    of the reduced FPP, on odds so that it treats 0.001 against 0.01 and 0.99 against 0.999 alike."""
    odds = [math.log10(p / (1.0 - p)) for p in (min(max(float(v), 1e-12), 1.0 - 1e-12) for v in values)]
    return max(odds) - min(odds)


def fpp_class(fpp: float | None, nfpp: float | None) -> str:
    """The TRICERATOPS classes (Giacalone et al. 2021) by number alone, without the contrast-curve rule."""
    if fpp is None or nfpp is None:
        return "undetermined"
    if nfpp > NFPP_LIKELY_NFP:
        return "likely nearby false positive"
    if fpp < FPP_VALIDATED and nfpp < NFPP_VALIDATED:
        return "meets the validation thresholds"
    if fpp < FPP_LIKELY_PLANET and nfpp < NFPP_VALIDATED:
        return "likely planet"
    return "undetermined"


def validation_label(fpp: float | None, nfpp: float | None, *, contrast_curve: bool, method: str) -> str:
    """The only label exoplan prints for a candidate's validation status (see the module docstring)."""
    if not contrast_curve:
        return NO_CONTRAST
    if method != "triceratops":
        return REDUCED_ONLY
    if fpp is not None and nfpp is not None and fpp < FPP_VALIDATED and nfpp < NFPP_VALIDATED:
        return VALIDATED
    return NOT_VALIDATED


def _uniform_marginal(x: float, sigma: float, lo: float, hi: float) -> float:
    """(1/(hi − lo)) ∫_lo^hi N(x; m, σ) dm: the likelihood of x when its true value is uniform on [lo, hi]."""
    if hi <= lo or sigma <= 0:
        return 0.0
    return float((norm.cdf((hi - x) / sigma) - norm.cdf((lo - x) / sigma)) / (hi - lo))


def _gauss(x: float, sigma: float) -> float:
    return float(norm.pdf(x / sigma) / sigma) if sigma > 0 else 0.0


@dataclass
class FppResult:
    method: str
    fpp: float | None
    nfpp: float | None
    probabilities: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    priors: dict = field(default_factory=dict)
    not_modelled: tuple = ("unresolved bound companions (HEB, planet on a companion)",
                           "unresolved background stars (BEB, planet on a background star)")
    contrast_curve: str | None = None
    label: str = NO_CONTRAST
    fpp_class: str = "undetermined"
    notes: tuple = ()
    refused: str | None = None        # why no FPP was computed (the secondary scan is not white), else None

    def as_dict(self) -> dict:
        return {"method": self.method, "fpp": self.fpp, "nfpp": self.nfpp, "probabilities": self.probabilities,
                "evidence": self.evidence, "priors": self.priors, "not_modelled": list(self.not_modelled),
                "contrast_curve": self.contrast_curve, "label": self.label, "fpp_class": self.fpp_class,
                "notes": list(self.notes), "refused": self.refused}


WHITE_RS = (0.7, 1.3)      # the scan's robust spread must lie here (white noise gives ~1)
WHITE_STD_RATIO = 1.3      # and its standard deviation over its robust spread at most this (white: ~1.05)


def scan_whiteness(scan: dict) -> dict | None:
    """Whether the all-phase secondary scan looks like white noise, which the reduced FPP's secondary likelihood
    assumes: robust spread in [0.7, 1.3], std/robust ≤ 1.3, and largest |excursion|/robust no larger than the
    white-noise 99.9% quantile for that number of positions (:data:`exoplan.dvtests.SECONDARY_TABLE`)."""
    from exoplan.dvtests import white_quantiles

    rs, sd, n = scan.get("scan_robust_sigma"), scan.get("scan_std_snr"), scan.get("n_trials")
    if not rs or sd is None or not n:
        return None
    q = white_quantiles(n)
    excursion = max(scan["snr"], scan.get("max_brightening_snr") or 0.0) / rs
    checks = {"robust_spread": rs, "std_over_robust": sd / rs, "max_excursion_over_robust": excursion,
              "white_q_abs_999": q["q_abs"], "positions": n, "n_eff": q["n_eff"]}
    reasons = []
    if not WHITE_RS[0] <= rs <= WHITE_RS[1]:
        reasons.append(f"robust spread {rs:.2f} outside {WHITE_RS[0]}-{WHITE_RS[1]}")
    if sd / rs > WHITE_STD_RATIO:
        reasons.append(f"std/robust {sd / rs:.2f} > {WHITE_STD_RATIO}")
    if excursion > q["q_abs"]:
        reasons.append(f"largest |excursion| {excursion:.2f} robust spreads > white 99.9% {q['q_abs']:.2f}")
    checks["white"] = not reasons
    checks["reasons"] = reasons
    return checks


def reduced_fpp(*, depth: float, dv: dict | None, fit: dict | None = None, pixel: dict | None = None,
                priors: Priors = Priors(), contrast_curve: str | None = None,
                variants: list[dict] | None = None) -> FppResult:
    """The reduced FPP of one candidate from its S2 results.

    ``depth`` is the fractional transit depth; ``dv`` is ``candidate.metrics["dv"]`` (the all-phase secondary scan,
    or the phase-0.5 value, and the odd/even depths); ``fit`` the transit fit (grazing, v_shape_dchi2); ``pixel`` the
    pixel report (neighbour table and centroid). Missing evidence contributes a likelihood ratio of 1 and is listed
    in ``notes``.

    With ``variants`` (the same all-phase scan on other detrending settings, :func:`exoplan.pipeline.secondary_variants`)
    the FPP is computed on every setting under two noise models (the scan's robust spread and its plain std). The FPP
    given is the median over settings at the robust spread, with the full range beside it. When every setting gives
    more than 0.5 the class is "likely false positive" whatever the spread; otherwise none is given when the odds
    FPP/(1 − FPP) vary by more than a factor of 10 across the range (:func:`log_odds_spread`), and the class is stated
    only when both ends of the range fall in the same class ("undetermined" when it straddles 0.015 or 0.5). Without ``variants``, a single scan must pass the white-noise gate (:func:`scan_whiteness`)
    or no FPP is given; the FPPs under other noise models are kept in ``evidence["fpp_sensitivity"]`` only.
    """
    notes = []
    dv = dv or {}
    fit = fit or {}
    base = {"tp": 1.0, "eb": 1.0, "eb2p": 1.0}
    evidence: dict = {}
    oe = dv.get("odd_even_depth")
    if oe and oe.get("odd_err_ppm") and oe.get("even_err_ppm"):
        d = (oe["odd_depth_ppm"] - oe["even_depth_ppm"]) * 1e-6
        sd = math.hypot(oe["odd_err_ppm"], oe["even_err_ppm"]) * 1e-6
        l0, l2 = _gauss(d, sd), _uniform_marginal(d, sd, -depth, depth)
        base["tp"] *= l0
        base["eb"] *= l0
        base["eb2p"] *= l2
        evidence["odd_even_bayes_factor_eb2p_vs_tp"] = l2 / l0 if l0 > 0 else math.inf
    else:
        notes.append("no odd/even depth measurement")
    if fit.get("grazing") and fit.get("v_shape_dchi2") is not None:
        boost = math.exp(min(max(float(fit["v_shape_dchi2"]), 0.0), V_SHAPE_CAP) / 2.0)
        base["eb"] *= boost
        base["eb2p"] *= boost
        evidence["v_shape_boost"] = boost
    elif not fit:
        notes.append("no transit fit (shape not used)")

    scan = dv.get("secondary") or {}
    sec05 = scan.get("phase_05")
    all_phase = bool(scan.get("sigma_ppm") and scan.get("n_trials") and scan.get("scan_robust_sigma"))
    # An eclipsing binary's secondary is in every epoch. When the strongest dip is not (S2's periodicity test: two or
    # more epochs, none carrying 70% or more), it is not evidence for one, and the phase-0.5 measurement (the
    # circular-orbit secondary) carries the secondary likelihood instead.
    use_peak = all_phase and scan.get("periodic", True)

    def secondary_like(widen: float, sc: dict | None = None):
        """(L_TP = L_EBx2P, L_EB) of the secondary measurement of scan ``sc`` (default: the main scan) with the noise
        scaled by ``widen``."""
        sc = scan if sc is None else sc
        peak = bool(sc.get("sigma_ppm") and sc.get("n_trials")) and sc.get("periodic", True)
        p05 = sc.get("phase_05")
        if peak:
            # In units of z = largest dip / noise scale: the null density f0 is simulated (null_pdf); a binary's
            # secondary is a true dip mu ~ U[0, Z] (Z the primary depth in the same units) seen with unit noise,
            # and the largest dip is then the larger of that and the noise maximum, whose density is
            # phi(z - mu) F0(z) + Phi(z - mu) f0(z); averaged over mu in closed form, with G(u) = u Phi(u) + phi(u).
            from exoplan.dvtests import null_cdf, null_pdf

            n = sc["n_trials"]
            ss = sc["sigma_ppm"] * 1e-6 * widen
            z = sc["depth_ppm"] * 1e-6 / ss
            big_z = max(depth / ss, 1e-9)
            f0, cdf0 = null_pdf(z, n), null_cdf(z, n)
            g = lambda u: u * norm.cdf(u) + norm.pdf(u)  # noqa: E731
            f1 = (cdf0 * (norm.cdf(z) - norm.cdf(z - big_z)) + f0 * (g(z) - g(z - big_z))) / big_z
            return f0, max(f1, 1e-300)
        if p05 and p05.get("sigma_ppm"):
            s, ss = p05["depth_ppm"] * 1e-6, p05["sigma_ppm"] * 1e-6 * widen
            return _gauss(s, ss), _uniform_marginal(s, ss, 0.0, depth)
        return None

    # Positions: the target and every catalogued neighbour.
    nb_rows = ((pixel or {}).get("neighbours") or {}).get("stars") or []
    centroid = (pixel or {}).get("centroid") or {}
    reliable = bool(centroid.get("reliable"))
    if not nb_rows:
        notes.append("no neighbour table: nearby-star scenarios not evaluated (NFPP unknown)")
    if nb_rows and not reliable:
        notes.append("no reliable difference-image centroid: positions carry no information")
    marginal = [r for r in nb_rows[1:] if r.get("marginal")]
    if marginal:
        notes.append(f"{len(marginal)} neighbour(s) excluded only marginally (within 3σ of the Tmag uncertainty "
                     "of reaching the depth)")
    target_pos = 1.0
    if reliable and nb_rows:
        sig_t = nb_rows[0].get("centroid_sigma")
        target_pos = math.exp(-0.5 * sig_t ** 2) if sig_t is not None else 1.0
    nfp_like = []
    possible = [r for r in nb_rows[1:] if r.get("needed_depth", math.inf) <= 1.0]
    for r in nb_rows[1:]:
        if r.get("needed_depth", math.inf) > 1.0:
            continue
        pos = 1.0
        if reliable and r.get("centroid_sigma") is not None:
            pos = math.exp(-0.5 * r["centroid_sigma"] ** 2)
        nfp_like.append((r.get("id"), pos))

    def posterior(widen: float, sc: dict | None = None):
        like = dict(base)
        # The noise scale never drops below the nominal σ/√n, as in the secondary threshold (assess_secondary): a
        # scan spread below white noise (detrending suppresses noise on the box's time-scale; 0.56 on some clean
        # planets) made a 2.7σ dip read as 4.8 and refused the FPP of clean planets as unstable.
        sl = secondary_like(max(widen, 1.0), sc)
        if sl is not None:
            l0, leb = sl
            like["tp"] *= l0
            like["eb2p"] *= l0
            like["eb"] *= leb
        weights = {"tp": priors.tp * like["tp"] * target_pos, "eb": priors.eb * like["eb"] * target_pos,
                   "eb2p": priors.eb2p * like["eb2p"] * target_pos}
        per_nfp = priors.nfp / len(possible) if possible else 0.0
        on_target = priors.tp + priors.eb + priors.eb2p
        lc_mean = (priors.tp * like["tp"] + priors.eb * like["eb"] + priors.eb2p * like["eb2p"]) / on_target
        for star, pos in nfp_like:
            if pos > 0:
                weights[f"nfp:{star}"] = per_nfp * pos * lc_mean
        total = sum(weights.values())
        probs = {k: (v / total if total > 0 else None) for k, v in weights.items()}
        fpp = 1.0 - probs["tp"] if probs.get("tp") is not None else None
        nfpp = sum(v for k, v in probs.items() if k.startswith("nfp:") and v is not None) if nb_rows else None
        return fpp, nfpp, probs, sl

    method = "exoplan reduced FPP"
    refused = None
    stable_class = None
    if all_phase and variants:
        settings = [dict(scan, window_scale=1.0, mask_t14="default")] + [v for v in variants if v.get("scan_robust_sigma")]
        rows, white = [], 0
        for sc in settings:
            g = scan_whiteness(sc)
            white += bool(g and g["white"])
            rs = sc["scan_robust_sigma"]
            for model, w in (("robust spread", rs), ("std", sc.get("scan_std_snr") or rs)):
                rows.append({"window_scale": sc.get("window_scale"), "mask_t14": sc.get("mask_t14"), "noise": model,
                             "fpp": posterior(max(w, 1e-9), sc)[0], "white": bool(g and g["white"])})
        values = [r["fpp"] for r in rows if r["fpp"] is not None]
        central = sorted(r["fpp"] for r in rows if r["noise"] == "robust spread" and r["fpp"] is not None)
        evidence["secondary_source"] = (
            f"all-phase search (phase {scan.get('phase', float('nan')):.3f})" if use_peak else
            f"phase 0.5 (the strongest dip, at phase {scan.get('phase', float('nan')):.3f}, is not periodic: "
            f"{(scan.get('max_epoch_share') or 0) * 100:.0f}% from one epoch)")
        _, nfpp, probs, sl = posterior(scan["scan_robust_sigma"])
        lo, hi = (min(values), max(values)) if values else (None, None)
        fpp = central[len(central) // 2] if central else None
        evidence["fpp_stability"] = {"n_settings": len(settings), "white_settings": white, "range": [lo, hi],
                                     "median_robust": fpp, "rows": rows}
        if sl is not None:
            evidence["secondary_bayes_factor_eb_vs_tp"] = sl[1] / sl[0] if sl[0] > 0 else math.inf
        spread = log_odds_spread(values) if values else None
        evidence["fpp_stability"]["log10_odds_spread"] = spread
        if lo is not None and lo > FPP_LIKELY_PLANET:
            # Every setting puts the FPP above 0.5: the class is the same whatever the setting, however far apart
            # the numbers are (an obvious binary's FPP runs from 0.98 to 1 - 1e-10, a factor of 10^8 in odds).
            stable_class = (f"{LIKELY_FP if not (nfpp is not None and nfpp > NFPP_LIKELY_NFP) else fpp_class(fpp, nfpp)}"
                            f"{REDUCED_CLASS_SUFFIX}: FPP above {FPP_LIKELY_PLANET:g} on every one of {len(settings)} "
                            f"detrending settings × 2 noise models (range {lo:.3g}–{hi:.3g})")
        elif lo is None or spread > MAX_LOG10_ODDS_SPREAD:
            refused = (f"FPP not computed: unstable across {len(settings)} detrending settings and two noise models "
                       f"(range {lo:.3g}–{hi:.3g}, more than a factor of 10 in odds)" if lo is not None else
                       "FPP not computed: no setting gave one")
            fpp = nfpp = None
            probs = {}
        else:
            span = f"FPP ≈ {fpp:.2g}, range {lo:.3g}–{hi:.3g} over {len(settings)} detrending settings × 2 noise models"
            crossed = [t for t in (FPP_VALIDATED, FPP_LIKELY_PLANET) if lo < t <= hi]
            stable_class = (f"undetermined{REDUCED_CLASS_SUFFIX}: {span} straddles the FPP threshold "
                            f"{', '.join(f'{t:g}' for t in crossed)}" if crossed else
                            f"{fpp_class(fpp, nfpp)}{REDUCED_CLASS_SUFFIX}: {span}")
    elif all_phase:
        gate = scan_whiteness(scan)
        evidence["scan_whiteness"] = gate
        evidence["secondary_source"] = (
            f"all-phase search (phase {scan.get('phase', float('nan')):.3f})" if use_peak else
            f"phase 0.5 (the strongest dip, at phase {scan.get('phase', float('nan')):.3f}, is not periodic: "
            f"{(scan.get('max_epoch_share') or 0) * 100:.0f}% from one epoch)")
        rs, sd_ratio = gate["robust_spread"], gate["std_over_robust"]
        models = {"robust spread": rs, "std": rs * sd_ratio, "nominal (white, σ/√n)": 1.0}
        outs = {name: posterior(max(w, 1e-9))[0] for name, w in models.items()}
        values = [v for v in outs.values() if v is not None]
        evidence["fpp_sensitivity"] = {"by_noise_model": outs,
                                       "range": [min(values), max(values)] if values else None}
        if not gate["white"]:
            refused = "FPP not computed: secondary scan non-white (" + "; ".join(gate["reasons"]) + ")"
            fpp = nfpp = None
            probs = {}
        else:
            fpp, nfpp, probs, sl = posterior(rs)
            evidence["fpp_bracket_robust_vs_std"] = [outs["robust spread"], outs["std"]]
            evidence["secondary_bayes_factor_eb_vs_tp"] = sl[1] / sl[0] if sl[0] > 0 else math.inf
    else:
        fpp, nfpp, probs, sl = posterior(1.0)
        if sl is not None:
            evidence["secondary_source"] = "phase 0.5"
            evidence["secondary_bayes_factor_eb_vs_tp"] = sl[1] / sl[0] if sl[0] > 0 else math.inf
        else:
            notes.append("no secondary measurement")
    if refused:
        notes.append(refused)
    result = FppResult(method=method, fpp=fpp, nfpp=nfpp, probabilities=probs, evidence=evidence,
                       priors={"tp": priors.tp, "eb": priors.eb, "eb2p": priors.eb2p, "nfp": priors.nfp,
                               "source": priors.source}, contrast_curve=contrast_curve, notes=tuple(notes))
    result.label = validation_label(fpp, nfpp, contrast_curve=bool(contrast_curve), method=method)
    result.fpp_class = refused if refused else (stable_class or fpp_class(fpp, nfpp) + REDUCED_CLASS_SUFFIX)
    result.refused = refused
    return result


def run_triceratops(*, tic: int, sectors, time, flux, flux_err: float, period: float, t0: float, depth: float,
                    contrast_curve: str | None = None, filt: str = "TESS", n_draws: int = 1_000_000, runs: int = 5,
                    apertures=None, module=None) -> FppResult:
    """FPP and NFPP from TRICERATOPS (optional; ``pip install 'exoplan[validate]'``), mean and scatter over ``runs``
    Monte Carlo runs, as ATLAS S3 asks. Needs the network: TRICERATOPS queries the TIC, Gaia and TESSCut itself.
    ``time`` is BTJD; it is folded on (``period``, ``t0``) into days from mid-transit for TRICERATOPS. ``depth``
    is fractional. ``module`` replaces the import (for tests)."""
    if module is None:
        from triceratops import triceratops as module  # noqa: PLC0415

    target = module.target(ID=int(tic), sectors=np.asarray(list(sectors)))
    target.calc_depths(tdepth=float(depth), all_ap_pixels=apertures)
    phase = (np.asarray(time, float) - t0 + 0.5 * period) % period - 0.5 * period
    order = np.argsort(phase)
    fpps, nfpps = [], []
    for _ in range(int(runs)):
        target.calc_probs(time=phase[order], flux_0=np.asarray(flux, float)[order], flux_err_0=float(flux_err),
                          P_orb=float(period), contrast_curve_file=contrast_curve, filt=filt, N=int(n_draws), verbose=0)
        fpps.append(float(target.FPP))
        nfpps.append(float(target.NFPP))
    fpp, nfpp = float(np.mean(fpps)), float(np.mean(nfpps))
    version = getattr(module, "__version__", None)
    try:
        from importlib import metadata

        version = version or metadata.version("triceratops")
    except Exception:  # noqa: BLE001
        pass
    result = FppResult(method="triceratops", fpp=fpp, nfpp=nfpp,
                       probabilities={"fpp_runs": fpps, "nfpp_runs": nfpps,
                                      "fpp_scatter": float(np.std(fpps)), "nfpp_scatter": float(np.std(nfpps))},
                       evidence={"triceratops_version": version, "runs": int(runs), "n_draws": int(n_draws)},
                       not_modelled=(), contrast_curve=contrast_curve)
    result.label = validation_label(fpp, nfpp, contrast_curve=bool(contrast_curve), method="triceratops")
    result.fpp_class = fpp_class(fpp, nfpp)
    return result
