"""S2 pixel-level vetting (pixel.py) on synthetic target pixel files, plus the offline readers of SPOC files."""

import math

import numpy as np
import pytest

from exoplan.pixel import (aperture_fraction, centroid_motion_test, detect_saturation, flux_weighted_centroid,
                           gaussian_psf, load_tpf, momentum_dumps, neighbour_table, offset_significance, parse_dv_xml,
                           pixel_vet, propagate_position, s3_prefix, synthetic_tpf, write_tpf_fits)

EPH = dict(period=3.0, t0=1001.5, duration=0.125)
TARGET = dict(x=5.2, y=5.4, flux=2e5)
FAINT = 10 ** (-0.4 * 3)          # a neighbour 3 magnitudes fainter


def _catalogue(stars, tmag0=8.0):
    return [dict(id=f"star{i}", x=s["x"], y=s["y"], tmag=tmag0 - 2.5 * math.log10(s["flux"] / stars[0]["flux"]))
            for i, s in enumerate(stars)]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_planet_on_target_gives_no_offset(seed):
    stars = [dict(TARGET, eclipse=1e-3), dict(x=7.2, y=5.4, flux=2e5 * FAINT)]
    tpf = synthetic_tpf(stars=stars, seed=seed, **EPH)
    r = pixel_vet(tpf, depth=1e-3, stars=_catalogue(stars), **EPH)
    c = r["centroid"]
    assert "centroid_offset" not in r["flags"] and c["reliable"]
    assert c["psf_target"]["sigma"] < 3.0
    assert c["psf_target"]["offset_total_px"] < 0.1
    # the target stays a possible source; the neighbour is excluded by the reliable centroid
    nb = r["neighbours"]["stars"]
    assert not nb[0]["ruled_out"] and nb[1]["ruled_out"]
    assert r["ghost"]["ghost_suspect"] is False


@pytest.mark.parametrize("dx,dy", [(1.5, 0.0), (1.4, 1.4), (0.0, -3.0)])
def test_blended_binary_on_a_neighbour_gives_a_significant_offset_and_is_localised(dx, dy):
    """ATLAS S2 acceptance: an injected neighbour EB at 1 to 3 px is localised within 0.2 px."""
    nb = dict(x=TARGET["x"] + dx, y=TARGET["y"] + dy, flux=2e5 * FAINT, eclipse=0.3)
    stars = [TARGET, nb]
    tpf = synthetic_tpf(stars=stars, seed=4, **EPH)
    share_nb = FAINT * aperture_fraction(tpf.shape, tpf.aperture, nb["x"], nb["y"], 1.0)
    depth = 0.3 * share_nb / (share_nb + aperture_fraction(tpf.shape, tpf.aperture, TARGET["x"], TARGET["y"], 1.0))
    r = pixel_vet(tpf, depth=depth, stars=_catalogue(stars), **EPH)
    c = r["centroid"]
    assert "centroid_offset" in r["flags"]
    assert c["psf_target"]["sigma"] > 5.0
    x, y = c["psf_control"]["diff"]
    assert math.hypot(x - nb["x"], y - nb["y"]) < 0.2
    assert c["psf_target"]["offset_arcsec"] == pytest.approx(math.hypot(dx, dy) * 21.0, abs=0.2 * 21.0)
    rows = r["neighbours"]["stars"]
    assert rows[0]["ruled_out"] and not rows[1]["ruled_out"]           # the target is excluded, the neighbour is not
    assert rows[1]["needed_depth"] == pytest.approx(0.3, rel=0.05)      # the needed depth is the injected eclipse
    assert r["motion"]["sigma"] > 5.0


def test_centroid_motion_source_offset_formula():
    """Delta phi = -delta phi (1 - D)/D points at a source 1 px away. The aperture truncates the source's PSF, so the
    distance is an underestimate (as the docstring says), but not by more than half."""
    nb = dict(x=TARGET["x"] + 1.0, y=TARGET["y"], flux=2e5 * FAINT, eclipse=0.3)
    tpf = synthetic_tpf(stars=[TARGET, nb], seed=7, **EPH)
    m = centroid_motion_test(tpf, **EPH)
    assert m["shift_px"][0] < 0                    # the light-weighted centroid moves away from the dimming star
    assert 0.5 < m["source_offset_px"][0] <= 1.05
    assert abs(m["source_offset_px"][1]) < 0.1


def test_flux_weighted_centroid_error_propagation_closed_form():
    image = np.array([[0.0, 0.0], [1.0, 3.0]])
    err = np.full((2, 2), 0.1)
    xc, yc, cov = flux_weighted_centroid(image, err, np.ones((2, 2), bool))
    assert xc == pytest.approx(0.75) and yc == pytest.approx(5 / 4 * 0.8)
    # var(xc) = sum((x_i - xc)^2 s^2) / F^2 = (2*0.75^2 + 2*0.25^2) * 0.01 / 16
    assert cov[0, 0] == pytest.approx((2 * 0.75 ** 2 + 2 * 0.25 ** 2) * 0.01 / 16)


def test_offset_significance_closed_form():
    r = offset_significance(0.3, 0.4, np.eye(2) * 0.01)
    assert r["chi2"] == pytest.approx(25.0)
    assert r["p_value"] == pytest.approx(math.exp(-12.5))
    assert r["sigma"] > 4.5


def test_gaussian_psf_is_normalised_and_centred():
    img = gaussian_psf((21, 21), 10.3, 9.6, 1.0)
    assert img.sum() == pytest.approx(1.0, abs=1e-6)
    rows, cols = np.indices(img.shape)
    assert (img * cols).sum() == pytest.approx(10.3, abs=1e-4)
    assert (img * rows).sum() == pytest.approx(9.6, abs=1e-4)


def test_saturated_target_is_flagged_and_its_centroid_not_trusted():
    stars = [dict(TARGET, flux=2e7, eclipse=1e-3)]   # peak pixel ~3e6 e/s against a 3e5 well
    tpf = synthetic_tpf(stars=stars, seed=1, saturate_at=3e5, **EPH)
    assert detect_saturation(tpf.flux[0])["saturated"]
    r = pixel_vet(tpf, depth=1e-3, **EPH)
    assert "saturated" in r["flags"] and "centroid_unreliable" in r["flags"]
    assert "centroid_offset" not in r["flags"]
    clean = synthetic_tpf(stars=[dict(TARGET, eclipse=1e-3)], seed=1, **EPH)
    assert not detect_saturation(clean.flux[0])["saturated"]


def test_neighbour_table_closed_form():
    """Two equal stars fully inside the aperture: each must eclipse twice the observed depth. A star 10 mag fainter
    would need more than 100% and is ruled out; delta_mag_limit = -2.5 log10(depth)."""
    tpf = synthetic_tpf(stars=[dict(x=5.0, y=5.0, flux=1e5)], shape=(11, 11), seed=0, **EPH)
    tpf.aperture[:] = True
    stars = [dict(id="a", x=5.0, y=5.0, tmag=10.0), dict(id="b", x=5.5, y=5.0, tmag=10.0),
             dict(id="c", x=5.0, y=5.5, tmag=20.0)]
    t = neighbour_table(tpf, stars, depth=0.01)
    a, b, c = t["stars"]
    assert a["needed_depth"] == pytest.approx(0.01 * (2 + 1e-4), rel=1e-3)
    assert b["needed_depth"] == pytest.approx(a["needed_depth"], rel=1e-3)
    assert c["ruled_out"] and "100%" in c["ruled_out_by"][0]
    assert t["delta_mag_limit"] == pytest.approx(5.0)
    # PDCSAP depth is crowding-corrected: the aperture depth is depth x CROWDSAP
    assert neighbour_table(tpf, stars, depth=0.01, crowdsap=0.5)["depth_aperture"] == pytest.approx(0.005)


def test_ghost_halo_dimming_is_suspect():
    tpf = synthetic_tpf(stars=[TARGET], seed=2, halo_dim=0.01, **EPH)
    r = pixel_vet(tpf, depth=1e-4, **EPH)
    assert r["ghost"]["ghost_suspect"] and "ghost_suspect" in r["flags"]


def test_momentum_dump_during_transit():
    tpf = synthetic_tpf(stars=[dict(TARGET, eclipse=1e-3)], seed=3, dumps=(1001.52, 1003.0), **EPH)
    m = momentum_dumps(tpf, **EPH)
    assert m["n_dumps"] == 2
    assert [e["epoch"] for e in m["epochs_with_dump"]] == [0]
    assert "momentum_dump" in pixel_vet(tpf, depth=1e-3, **EPH)["flags"]


def test_tpf_fits_round_trip(tmp_path):
    """load_tpf reads a file in the SPOC layout: PIXELS table, APERTURE image (bit 2), WCS and CROWDSAP."""
    stars = [TARGET, dict(x=6.7, y=5.4, flux=2e5 * FAINT, eclipse=0.3)]
    tpf = synthetic_tpf(stars=stars, seed=5, **EPH)
    path = write_tpf_fits(tpf, tmp_path / "tess-s0001-0000000000000001-0120-s_tp.fits",
                          extra_header={"CROWDSAP": 0.97, "FLFRCSAP": 0.9})
    back = load_tpf(path)
    assert back.flux.shape == tpf.flux.shape
    assert np.array_equal(back.aperture, tpf.aperture)
    assert back.header["crowdsap"] == pytest.approx(0.97)
    assert back.target_position() == pytest.approx((TARGET["x"], TARGET["y"]), abs=1e-6)
    assert back.pixel_scale_arcsec() == pytest.approx(21.0, rel=1e-6)
    assert len(back.provenance["file_sha256"]) == 64
    assert "centroid_offset" in pixel_vet(back, depth=0.005, **EPH)["flags"]


def test_proper_motion_propagation():
    ra, dec = propagate_position(84.0, -80.0, 311.0, 1049.0, years=18.6)
    assert (dec + 80.0) * 3600 == pytest.approx(1.049 * 18.6, rel=1e-9)
    assert (ra - 84.0) * 3600 * math.cos(math.radians(-80.0)) == pytest.approx(0.311 * 18.6, rel=1e-9)
    assert propagate_position(84.0, -80.0, None, None, years=10) == (84.0, -80.0)


def test_s3_prefix_matches_the_spoc_layout():
    assert s3_prefix(261136679, 1) == "tess/public/tid/s0001/0000/0002/6113/6679/"


DV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dv:dvTargetResults ticId="261136679" xmlns:dv="http://www.nasa.gov/2018/TESS/DV">
  <dv:planetResults planetNumber="1" toiId="144.01">
    <dv:binaryDiscriminationResults>
      <dv:oddEvenTransitDepthComparisonStatistic value="0.2015297" significance="0.65348893"/>
    </dv:binaryDiscriminationResults>
    <dv:differenceImageResults numberOfTransits="4" sector="1">
      <dv:qualityMetric attempted="true" valid="true" value="0.57559127"/>
      <dv:ticCentroidOffsets>
        <dv:rowOffset value="-2.0745318" uncertainty="0.005257394"/>
        <dv:columnOffset value="0.023864495" uncertainty="0.010823628"/>
        <dv:skyOffset value="40.459084" uncertainty="0.082314506"/>
      </dv:ticCentroidOffsets>
    </dv:differenceImageResults>
  </dv:planetResults>
</dv:dvTargetResults>
"""


def test_parse_dv_xml(tmp_path):
    """Values from SPOC's DV report for pi Men (TOI 144.01, sector 1), trimmed to the elements read."""
    path = tmp_path / "dvr.xml"
    path.write_text(DV_XML)
    (row,) = parse_dv_xml(path)
    assert row["toi"] == "144.01" and row["quality"] == pytest.approx(0.5756, abs=1e-4)
    assert row["ticCentroidOffsets"]["skyOffset"]["value"] == pytest.approx(40.459, abs=1e-3)
    assert row["odd_even"]["significance"] == pytest.approx(0.6535, abs=1e-4)
