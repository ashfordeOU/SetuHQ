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


def _white_scan(**over):
    scan = dict(depth_ppm=30.0, sigma_ppm=10.0, snr=3.0, n_trials=200, scan_robust_sigma=1.0, scan_std_snr=1.05,
                max_brightening_snr=2.5, phase=0.3)
    scan.update(over)
    return scan


def test_all_phase_secondary_likelihood_closed_form():
    """With a white all-phase scan the no-secondary likelihood is the simulated null density f0 of the largest dip
    (in units of the noise scale), and the binary's is (1/Z)[F0(z)(Phi(z) - Phi(z-Z)) + f0(z)(G(z) - G(z-Z))]."""
    from exoplan.dvtests import null_cdf, null_pdf

    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(scan_robust_sigma=1.2, scan_std_snr=1.3))
    r = reduced_fpp(depth=1e-3, dv=dv)
    assert r.refused is None and r.fpp is not None
    ss = 10e-6 * 1.2
    z, big = 30e-6 / ss, 1e-3 / ss
    f0, c0 = null_pdf(z, 200), null_cdf(z, 200)
    g = lambda u: u * norm.cdf(u) + norm.pdf(u)  # noqa: E731
    f1 = (c0 * (norm.cdf(z) - norm.cdf(z - big)) + f0 * (g(z) - g(z - big))) / big
    assert r.evidence["secondary_bayes_factor_eb_vs_tp"] == pytest.approx(f1 / f0, rel=1e-9)
    lo, hi = r.evidence["fpp_bracket_robust_vs_std"]
    assert lo == pytest.approx(r.fpp) and hi is not None
    assert r.evidence["secondary_source"].startswith("all-phase")


def test_null_distribution_is_a_cdf():
    from exoplan.dvtests import null_cdf, null_pdf, white_quantiles

    assert null_cdf(0.0, 187) == 0.0 and null_cdf(12.0, 187) == pytest.approx(1.0, abs=1e-6)
    assert null_cdf(white_quantiles(187)["q_dip"], 187) == pytest.approx(0.999, abs=0.001)
    assert null_cdf(3.0, 400) < null_cdf(3.0, 25)          # more positions: a larger largest dip
    assert null_pdf(3.0, 187) > null_pdf(1.0, 187) > 0


@pytest.mark.parametrize("positions", [25, 73, 193, 409])
def test_null_tail_is_smooth_and_monotone(positions):
    """Above its 99th percentile the null is a fitted generalized Pareto tail: the CDF rises monotonically to 1, the
    density falls monotonically (the empirical one, from fewer than 40 scans beyond z = 5.1, did not), and the two
    pieces meet at the threshold without a jump."""
    from exoplan.dvtests import _null_tables, null_cdf, null_pdf

    z = np.arange(0.0, 12.0, 0.01)
    cdf = np.array([null_cdf(x, positions) for x in z])
    assert np.all(np.diff(cdf) >= -1e-12) and cdf[-1] > 0.99999
    _, pos, _, tails = _null_tables()
    u = float(np.interp(np.log(positions), np.log(pos), [t["u"] for t in tails]))
    above = np.arange(max(t["u"] for t in tails) + 0.01, 12.0, 0.05)
    pdf = np.array([null_pdf(x, positions) for x in above])
    assert np.all(np.diff(pdf) < 0)
    assert null_cdf(u + 1e-6, positions) - null_cdf(u - 1e-6, positions) < 1e-3
    assert 0.5 < null_pdf(u + 0.01, positions) / null_pdf(u - 0.11, positions) < 2.0


def test_clean_planets_with_low_peaks_get_a_low_fpp():
    """A clean 1000 ppm planet whose strongest dip elsewhere is unusually small (below 2.5 noise units) was charged for
    it by the old max-of-N_eff null (FPP up to 0.97, Bayes factor 263); with the simulated null it is not."""
    from exoplan.dvtests import extended_vet

    import sys
    sys.path.insert(0, "tests")
    from test_dvtests import DUR, P, T0, _curve, _transits

    low = []
    for seed in range(60):
        t, f, e = _curve(np.random.default_rng(7000 + seed), events=_transits(1000e-6))
        _, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
        s = m["secondary"]
        r = reduced_fpp(depth=1e-3, dv=m)
        if r.fpp is not None and s["snr"] / s["scan_robust_sigma"] < 2.5:
            low.append(r.fpp)
    assert len(low) >= 10
    assert max(low) < 0.05


@pytest.mark.parametrize("over, reason", [
    (dict(scan_robust_sigma=2.0, scan_std_snr=2.2), "robust spread"),
    (dict(scan_robust_sigma=1.0, scan_std_snr=1.6), "std/robust"),
    (dict(scan_robust_sigma=1.0, scan_std_snr=1.05, max_brightening_snr=8.8), "excursion"),
])
def test_a_non_white_scan_refuses_the_fpp(over, reason):
    """No point estimate when the secondary scan is not white: the FPP, NFPP and class say so with the numbers, the
    range over noise models is kept as evidence only, and the label stays 'not validated: no contrast curve'."""
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(**over))
    rows = [{"id": "T", "needed_depth": 1e-3}]
    r = reduced_fpp(depth=1e-3, dv=dv, pixel={"centroid": {"reliable": False}, "neighbours": {"stars": rows}})
    assert r.fpp is None and r.nfpp is None
    assert r.refused.startswith("FPP not computed: secondary scan non-white") and reason in r.refused
    assert r.fpp_class == r.refused and r.label == NO_CONTRAST
    lo, hi = r.evidence["fpp_sensitivity"]["range"]
    assert 0 <= lo <= hi <= 1
    from exoplan.exofop import exclusion

    row = {"passed": True, "flags": "", "period_days": 5.0, "n_transits": 3, "fit": {"period_days": 5.0},
           "metrics": {"validation": r.as_dict()}}
    assert exclusion(row).startswith("S3 not evaluated: FPP not computed")


def test_a_non_periodic_peak_is_not_secondary_evidence():
    """A strongest dip carried by one epoch is not what a binary's secondary looks like (it is in every epoch): the
    secondary likelihood then uses the phase-0.5 measurement."""
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(depth_ppm=60.0, snr=4.8, periodic=False, max_epoch_share=0.84))
    r = reduced_fpp(depth=1e-3, dv=dv)
    assert r.evidence["secondary_source"].startswith("phase 0.5")
    s, ss = 0.0, 10e-6
    l0 = norm.pdf(s / ss) / ss
    leb = validate._uniform_marginal(s, ss, 0.0, 1e-3)
    assert r.evidence["secondary_bayes_factor_eb_vs_tp"] == pytest.approx(leb / l0, rel=1e-9)


def _variants(depths):
    return [dict(_white_scan(depth_ppm=d, snr=d / 10.0), window_scale=w, mask_t14=m)
            for d, (w, m) in zip(depths, ((0.75, 1.0), (0.75, 2.0), (1.5, 1.0), (1.5, 2.0)))]


def test_fpp_across_detrending_settings():
    """With variant scans the FPP is the median over settings, with its range over settings and two noise models; the
    class is stated only when both ends of the range fall in the same class."""
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(depth_ppm=25.0, snr=2.5))
    stable = reduced_fpp(depth=1e-3, dv=dv, variants=_variants([24.0, 26.0, 25.0, 27.0]))
    st = stable.evidence["fpp_stability"]
    assert st["n_settings"] == 5 and len(st["rows"]) == 10
    lo, hi = st["range"]
    assert lo <= stable.fpp <= hi and hi / lo < 10
    assert "FPP ≈" in stable.fpp_class and "straddles" not in stable.fpp_class
    assert stable.label == NO_CONTRAST


def test_an_unstable_fpp_is_refused_and_a_straddling_one_has_no_class():
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(depth_ppm=25.0, snr=2.5))
    wild = reduced_fpp(depth=1e-3, dv=dv, variants=_variants([25.0, 90.0, 25.0, 25.0]))
    assert wild.fpp is None and wild.refused.startswith("FPP not computed: unstable across 5 detrending settings")
    # secondary dips of 35 and 40 ppm give FPPs of about 0.009 and 0.020: stable, but straddling 0.015
    dv["secondary"] = _white_scan(depth_ppm=35.0, snr=3.5)
    straddle = reduced_fpp(depth=1e-3, dv=dv, variants=_variants([40.0, 35.0, 40.0, 35.0]))
    lo, hi = straddle.evidence["fpp_stability"]["range"]
    assert lo < 0.015 < hi and straddle.fpp is not None
    assert straddle.fpp_class.startswith("undetermined") and "straddles the FPP threshold 0.015" in straddle.fpp_class


def test_a_sub_white_spread_never_raises_the_secondary_significance():
    """The FPP's noise scale is floored at the nominal σ/√n, as the secondary threshold is: a variant whose scan spread
    is 0.56 gives the same FPP as one at 1.0, so it cannot make the stability range look unstable."""
    dv = _dv(0.0, 10.0, 1000.0, 1000.0, 10.0)
    dv["secondary"].update(_white_scan(depth_ppm=27.0, snr=2.7))
    narrow = [dict(v, scan_robust_sigma=0.56, scan_std_snr=0.6) for v in _variants([27.0, 27.0, 27.0, 27.0])]
    a = reduced_fpp(depth=1e-3, dv=dv, variants=narrow)
    b = reduced_fpp(depth=1e-3, dv=dv, variants=_variants([27.0, 27.0, 27.0, 27.0]))
    assert a.fpp == pytest.approx(b.fpp, rel=1e-9) and a.refused is None
    rows = a.evidence["fpp_stability"]["rows"]
    floored = [r["fpp"] for r in rows if r["window_scale"] != 1.0]   # every variant row sits at the nominal σ
    assert max(floored) == pytest.approx(min(floored), rel=1e-9)
