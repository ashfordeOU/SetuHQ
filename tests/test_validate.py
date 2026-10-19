"""S3: validation labels, the reduced FPP scheme (closed forms), the TRICERATOPS adapter (stubbed), and the rule that
exoplan never calls its results "confirmed"."""

import math
import re
import types

import numpy as np
import pytest
from scipy.stats import norm

from exoplan import validate
from exoplan.validate import (NO_CONTRAST, NOT_VALIDATED, REDUCED_ONLY, VALIDATED, Priors, fpp_class, reduced_fpp,
                              run_triceratops, validation_label)


def test_label_needs_triceratops_thresholds_and_a_contrast_curve():
    assert validation_label(0.001, 1e-5, contrast_curve=True, method="triceratops") == VALIDATED
    assert validation_label(0.001, 1e-5, contrast_curve=False, method="triceratops") == NO_CONTRAST
    assert validation_label(0.001, 1e-5, contrast_curve=True, method="exoplan reduced FPP") == REDUCED_ONLY
    assert validation_label(0.015, 1e-5, contrast_curve=True, method="triceratops") == NOT_VALIDATED   # strict <
    assert validation_label(0.001, 1e-3, contrast_curve=True, method="triceratops") == NOT_VALIDATED
    assert validation_label(None, None, contrast_curve=True, method="triceratops") == NOT_VALIDATED


def test_fpp_classes_follow_giacalone_2021():
    assert fpp_class(0.01, 1e-4) == "meets the validation thresholds"
    assert fpp_class(0.3, 1e-4) == "likely planet"
    assert fpp_class(0.3, 0.2) == "likely nearby false positive"
    assert fpp_class(0.3, 0.01) == "undetermined"
    assert fpp_class(None, None) == "undetermined"


def test_uniform_marginal_closed_form():
    # x well inside [0, d] with small sigma: the marginal tends to 1/d
    assert validate._uniform_marginal(0.5, 1e-3, 0.0, 1.0) == pytest.approx(1.0)
    # x at the edge: half of it
    assert validate._uniform_marginal(0.0, 1e-3, 0.0, 1.0) == pytest.approx(0.5)


def _dv(sec_depth, sec_sigma, odd, even, err):
    return {"secondary": {"phase_05": {"depth_ppm": sec_depth, "sigma_ppm": sec_sigma}},
            "odd_even_depth": {"odd_depth_ppm": odd, "even_depth_ppm": even, "odd_err_ppm": err, "even_err_ppm": err}}


def test_reduced_fpp_closed_form_without_neighbours():
    """No secondary (0 ± 10 ppm) and equal odd/even depths (diff 0 ± 14 ppm) for a 1000 ppm transit:
    BF_EB = (1/δ)∫N / N(0) and BF_EBx2P likewise; FPP follows from the priors."""
    depth = 1e-3
    r = reduced_fpp(depth=depth, dv=_dv(0.0, 10.0, 1000.0, 1000.0, 10.0))
    s, sd = 10e-6, math.hypot(10e-6, 10e-6)
    bf_eb = (0.5 / depth) / norm.pdf(0, scale=s)                       # half the uniform mass at the edge x = 0
    bf_2p = ((norm.cdf(depth / sd) - norm.cdf(-depth / sd)) / (2 * depth)) / norm.pdf(0, scale=sd)
    assert r.evidence["secondary_bayes_factor_eb_vs_tp"] == pytest.approx(bf_eb, rel=1e-6)
    assert r.evidence["odd_even_bayes_factor_eb2p_vs_tp"] == pytest.approx(bf_2p, rel=1e-6)
    p = Priors()
    fpp = (p.eb * bf_eb + p.eb2p * bf_2p) / (p.tp + p.eb * bf_eb + p.eb2p * bf_2p)
    assert r.fpp == pytest.approx(fpp, rel=1e-6)
    assert r.nfpp is None                                      # no neighbour table: NFPP unknown, not zero
    assert r.label == NO_CONTRAST and "NFPP unknown" in " ".join(r.notes)


def test_reduced_fpp_eclipsing_binary_signatures():
    planet = reduced_fpp(depth=1e-3, dv=_dv(0.0, 10.0, 1000.0, 1000.0, 10.0))
    eb = reduced_fpp(depth=1e-3, dv=_dv(400.0, 10.0, 1000.0, 1000.0, 10.0))       # a 40σ secondary
    eb2p = reduced_fpp(depth=1e-3, dv=_dv(0.0, 10.0, 1300.0, 700.0, 10.0))        # odd/even differ by 42σ
    assert planet.fpp < 0.05
    assert eb.fpp > 0.999 and eb.probabilities["eb"] > 0.999
    assert eb2p.fpp > 0.999 and eb2p.probabilities["eb2p"] > 0.999
    vshape = reduced_fpp(depth=1e-3, dv=_dv(0.0, 10.0, 1000.0, 1000.0, 10.0), fit={"grazing": True, "v_shape_dchi2": 30})
    assert vshape.fpp > planet.fpp and vshape.evidence["v_shape_boost"] == pytest.approx(math.exp(15))


def _pixel(reliable, rows):
    return {"centroid": {"reliable": reliable}, "neighbours": {"stars": rows}}


def test_reduced_fpp_nearby_stars():
    rows = [{"id": "T", "needed_depth": 1e-3, "centroid_sigma": 0.5},
            {"id": "A", "needed_depth": 0.05, "centroid_sigma": 8.0},
            {"id": "B", "needed_depth": 3.0}]
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    r = reduced_fpp(depth=1e-3, dv=dv, pixel=_pixel(True, rows))
    assert "nfp:B" not in r.probabilities                      # ruled out: needs a depth above 100%
    assert r.nfpp == pytest.approx(r.probabilities["nfp:A"])
    # A takes the whole NFP prior (B is ruled out) and the target scenarios' mean light-curve likelihood, so against
    # all on-target scenarios together: (0.10 / 0.90) exp(-8²/2) / exp(-0.5²/2), in closed form
    on_target = r.probabilities["tp"] + r.probabilities["eb"] + r.probabilities["eb2p"]
    ratio = (0.10 / 0.90) * math.exp(-32.0) / math.exp(-0.125)
    assert r.probabilities["nfp:A"] / on_target == pytest.approx(ratio, rel=1e-9)
    assert r.nfpp < 1e-12
    # without a reliable centroid the neighbour keeps its prior share: NFPP is large and nothing can validate
    u = reduced_fpp(depth=1e-3, dv=dv, pixel=_pixel(False, rows))
    assert u.nfpp > 0.05 and not u.fpp_class.startswith("meets the validation thresholds")
    assert u.fpp_class.endswith("(by number, reduced scheme)")
    # the source on a neighbour
    rows_nb = [{"id": "T", "needed_depth": 1e-3, "centroid_sigma": 9.0}, {"id": "A", "needed_depth": 0.05, "centroid_sigma": 0.3}]
    nb = reduced_fpp(depth=1e-3, dv=dv, pixel=_pixel(True, rows_nb))
    assert nb.nfpp > 0.99 and nb.fpp_class == "likely nearby false positive (by number, reduced scheme)"


def test_reduced_scheme_never_validates_even_with_a_contrast_curve():
    rows = [{"id": "T", "needed_depth": 1e-3, "centroid_sigma": 0.0}]
    r = reduced_fpp(depth=1e-3, dv=_dv(0.0, 1.0, 1000.0, 1000.0, 1.0), pixel=_pixel(True, rows),
                    contrast_curve="curve.txt")
    assert r.fpp < 0.015 and r.nfpp < 1e-3
    assert r.label == REDUCED_ONLY


class _StubTarget:
    """Records what the adapter passes to TRICERATOPS; returns fixed probabilities that vary by run."""

    calls = []

    def __init__(self, ID, sectors):
        self.ID, self.sectors, self.n = ID, sectors, 0
        _StubTarget.calls.append(("init", ID, list(sectors)))

    def calc_depths(self, tdepth, all_ap_pixels=None):
        _StubTarget.calls.append(("depths", tdepth))

    def calc_probs(self, time, flux_0, flux_err_0, P_orb, contrast_curve_file=None, filt="TESS", N=0, verbose=1):
        assert np.all(np.diff(time) >= 0) and abs(time).max() <= 0.5 * P_orb
        _StubTarget.calls.append(("probs", P_orb, contrast_curve_file, N))
        self.n += 1
        self.FPP, self.NFPP = 0.010 + 0.001 * self.n, 1e-4


def test_triceratops_adapter_contract():
    stub = types.SimpleNamespace(target=_StubTarget, __version__="stub")
    t = np.linspace(1325.0, 1350.0, 500)
    r = run_triceratops(tic=261136679, sectors=[1], time=t, flux=np.ones(500), flux_err=1e-4, period=6.268,
                        t0=1338.04, depth=3e-4, contrast_curve="speckle.txt", runs=3, n_draws=1000, module=stub)
    assert _StubTarget.calls[0] == ("init", 261136679, [1]) and _StubTarget.calls[1] == ("depths", 3e-4)
    assert [c for c in _StubTarget.calls if c[0] == "probs"] == [("probs", 6.268, "speckle.txt", 1000)] * 3
    assert r.fpp == pytest.approx(0.012) and r.probabilities["fpp_scatter"] == pytest.approx(np.std([0.011, 0.012, 0.013]))
    assert r.label == VALIDATED and r.method == "triceratops"
    r2 = run_triceratops(tic=1, sectors=[1], time=t, flux=np.ones(500), flux_err=1e-4, period=6.268, t0=1338.04,
                         depth=3e-4, runs=1, module=stub)
    assert r2.label == NO_CONTRAST


def test_no_output_calls_a_candidate_confirmed(tmp_path):
    """Language guard (ATLAS S3, K4): no validation label, and no candidate row of a run, uses "confirmed"."""
    for label in validate.LABELS:
        assert "confirm" not in label.lower()
    from exoplan.config import RunConfig
    from exoplan.lightcurve import LightCurve
    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers.simulated import SimulatedVolunteer

    rng = np.random.default_rng(2)
    time = np.arange(0.0, 13.0, 10 / 1440)
    flux = 1 + rng.normal(0, 3e-4, time.size)
    for k in range(4):
        flux -= 2000e-6 * (np.abs(time - (1.5 + 3.0 * k)) < 0.1)
    lc = LightCurve(target="TIC 9", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 3e-4),
                    provenance={"sector": 1, "time_unit": "BTJD"})
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    run_pipeline(RunConfig(name="g", subject_days=13.0, min_points=100, fap_trials=0), [lc], reviewers, tmp_path / "r")
    text = (tmp_path / "r" / "candidates.json").read_text() + (tmp_path / "r" / "candidates.csv").read_text()
    assert "validation_label" in text and NO_CONTRAST in text
    assert not re.search(r"\bconfirmed\b", text, re.I)


def test_all_phase_secondary_likelihood_closed_form():
    """With the all-phase search, TP's likelihood is the density of the largest of N_eff noise excursions,
    N_eff phi(z) Phi(z)^(N_eff - 1) / sigma, with sigma widened by the scan's robust spread."""
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(depth_ppm=30.0, sigma_ppm=10.0, n_trials=200, scan_robust_sigma=1.5, phase=0.3)
    r = reduced_fpp(depth=1e-3, dv=dv)
    ss, n_eff = 15e-6, 50.0
    z = 30e-6 / ss
    l0 = n_eff * norm.pdf(z) * norm.cdf(z) ** (n_eff - 1) / ss
    leb = validate._uniform_marginal(30e-6, ss, 0.0, 1e-3)
    assert r.evidence["secondary_bayes_factor_eb_vs_tp"] == pytest.approx(leb / l0, rel=1e-9)
    assert r.evidence["secondary_source"].startswith("all-phase")
    # a 2-sigma "secondary" among 50 independent positions is what noise gives: it barely moves the odds
    assert r.evidence["secondary_bayes_factor_eb_vs_tp"] < 3
