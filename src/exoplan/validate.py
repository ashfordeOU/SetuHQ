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

* Secondary, from the all-phase search: the strongest dip s ± σ_s at any phase, with σ_s scaled by the scan's
  robust spread. TP and EBx2P predict no secondary, so s is the largest of N_eff noise excursions, N_eff simulated
  for that number of box positions (:data:`exoplan.dvtests.SECONDARY_TABLE`; about 1.5–1.8 times the positions):
  likelihood N_eff φ(z) Φ(z)^(N_eff−1)/σ_s with z = s/σ_s. EB predicts a secondary
  anywhere between 0 and the primary depth δ: (1/δ) ∫₀^δ N(s; x, σ_s) dx. Without the all-phase search, the
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
                priors: Priors = Priors(), contrast_curve: str | None = None) -> FppResult:
    """The reduced FPP of one candidate from its S2 results.

    ``depth`` is the fractional transit depth; ``dv`` is ``candidate.metrics["dv"]`` (the all-phase secondary scan,
    or the phase-0.5 value, and the odd/even depths); ``fit`` the transit fit (grazing, v_shape_dchi2); ``pixel`` the
    pixel report (neighbour table and centroid). Missing evidence contributes a likelihood ratio of 1 and is listed
    in ``notes``. When the all-phase scan is not white (:func:`scan_whiteness`), no FPP or NFPP is given: the
    result says "FPP not computed" with the numbers, and the range of FPPs under other noise models is kept in
    ``evidence["fpp_sensitivity"]`` only.
    """
    from exoplan.dvtests import white_quantiles

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

    def secondary_like(widen: float):
        """(L_TP = L_EBx2P, L_EB) of the secondary measurement with the noise scaled by ``widen``."""
        if use_peak:
            n_eff = white_quantiles(scan["n_trials"])["n_eff"]
            s, ss = scan["depth_ppm"] * 1e-6, scan["sigma_ppm"] * 1e-6 * widen
            z = s / ss
            return float(n_eff * norm.pdf(z) * norm.cdf(z) ** (n_eff - 1.0) / ss), _uniform_marginal(s, ss, 0.0, depth)
        if sec05 and sec05.get("sigma_ppm"):
            s, ss = sec05["depth_ppm"] * 1e-6, sec05["sigma_ppm"] * 1e-6 * widen
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

    def posterior(widen: float):
        like = dict(base)
        sl = secondary_like(widen)
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
    if all_phase:
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
    result.fpp_class = refused if refused else fpp_class(fpp, nfpp) + REDUCED_CLASS_SUFFIX
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
