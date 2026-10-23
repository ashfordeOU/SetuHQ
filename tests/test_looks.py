# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""setuhq.looks: a planet's look from measured values only, at the stated thresholds, with the showcase planets
pinned, and no look or caption that says "habitable"."""

import json
from pathlib import Path

import pytest

from setuhq import looks as L

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "docs/results/exoplanet_catalogue.json").read_text())
RJ, MJ = L.RJ_IN_RE, L.MJ_IN_ME


def test_composition_boundaries_by_radius_and_by_mass():
    by_r = {re_: L.look({"radius": re_ / RJ})["composition"] for re_ in (1.5999, 1.6, 3.999, 4.0, 9.999, 10.0)}
    assert list(by_r.values()) == ["rock", "envelope", "envelope", "neptune", "neptune", "giant"]
    by_m = [L.look({"mass": me / MJ})["composition"] for me in (1.99, 2, 9.99, 10, 49.9, 50)]
    assert by_m == ["rock", "ambiguous", "ambiguous", "neptune", "neptune", "giant"]
    assert L.look({"msini": 60 / MJ})["composition"] == "giant"  # a minimum mass is used when no true mass is stored


def test_band_boundaries():
    got = [L.band(t) for t in (199.9, 200, 349.9, 350, 999.9, 1000, 1999.9, 2000)]
    assert got == ["cold", "temperate", "temperate", "warm", "warm", "hot", "hot", "ultrahot"]
    assert L.band(None) is None


def test_earth_and_keplers_third_law():
    s = L.insolation(1.0, 5772, 1.0)
    assert s == pytest.approx(1.0, abs=1e-3) and L.teq_k(s) == pytest.approx(278.3, abs=0.05)
    i = L.find_planet(CAT, "pi Men c")
    P = CAT["planets"]
    a = L.kepler_a(P["smass"][i], P["period"][i])
    # The catalogue's own M★ and P give a 2.3% larger orbit than its stored a (0.06855 vs 0.06702 AU).
    assert a == pytest.approx(P["a"][i], rel=0.03)


@pytest.mark.parametrize("name,rp,teq,look", [
    ("pi Men c", 1.874, 1179, "envelope-hot"), ("WASP-126 b", 10.761, 1487, "giant-hot"), ("TOI-270 b", 1.247, 575, "rock-warm"),
    ("TOI-270 c", 2.330, 463, "envelope-warm"), ("TOI-270 d", 2.130, 372, "envelope-warm"), ("HD 15337 b", 1.770, 989, "envelope-warm"),
    ("HD 15337 c", 2.526, 645, "envelope-warm"), ("Kepler-9 b", 8.29, 721, "neptune-warm"), ("Kepler-9 c", 8.08, 573, "neptune-warm"),
    ("Kepler-9 d", 1.64, 1651, "envelope-hot")])
def test_the_showcase_looks(name, rp, teq, look):
    i = L.find_planet(CAT, name)
    lk = L.look(L.row(CAT, i))
    assert lk["rp_re"] == pytest.approx(rp, abs=0.006) and lk["teq"] == pytest.approx(teq, abs=1) and lk["name"] == look
    assert lk["teq_source"] == "computed" and lk["to_scale"]


def test_names_resolve_through_the_catalogues_alternatives():
    P = CAT["planets"]
    assert P["name"][L.find_planet(CAT, "HD 15337 b")] == "TOI-402 Ab"
    assert P["name"][L.find_planet(CAT, "HD 15337 c")] == "TOI-402 Ac"
    assert L.find_planet(CAT, "no such planet z") is None


def test_a_stored_teq_that_disagrees_is_named():
    cap = L.caption(L.row(CAT, L.find_planet(CAT, "HD 15337 b")))
    assert "the catalogue's stored value (3,109 K) differs" in cap and "Teq 989 K" in cap


def test_missing_inputs_say_so():
    none = L.look({})
    assert none["name"] is None and L.caption({}) == "No radius or mass stored, so no planet is drawn."
    mass_only = L.look({"mass": 5 / MJ, "teq": 500})
    assert mass_only["name"] == "ambiguous" and mass_only["to_scale"] is False and mass_only["teq_source"] == "stored"
    assert "not to scale" in " ".join(mass_only["reasons"])
    neutral = L.look({"radius": 1.0})
    assert neutral["band"] is None and neutral["neutral"] and "neutral colours" in " ".join(neutral["reasons"])


def test_seed_is_fnv1a_of_the_slug():
    assert L.seed("pi-men-c") == 4189685259 and L.seed("") == 0x811C9DC5


def test_every_look_is_reachable_and_nothing_says_habitable():
    reached = {L.look_name(c, b) for c in ("rock", "envelope", "neptune", "giant", "ambiguous")
               for b in ("cold", "temperate", "warm", "hot", "ultrahot")}
    assert reached == {k for k in L.LOOKS if not k.startswith("ref-")} and len(L.LOOKS) == 18
    assert "habitable" not in json.dumps(L.LOOKS).lower()
    P = CAT["planets"]
    for i in range(0, len(P["name"]), 7):
        assert "habitable" not in L.caption(L.row(CAT, i)).lower()
    # Oceans and continents only for Earth itself.
    assert [k for k, v in L.LOOKS.items() if v["clouds"]] == ["ref-earth"]


def test_star_colour_pins():
    for t, rgb in ((3532, (255, 201, 141)), (5175, (255, 233, 214)), (5772, (255, 241, 234)), (6421, (255, 248, 252)), (10000, (205, 217, 255))):
        assert L.teff_rgb(t) == rgb
    assert L.teff_rgb(500) == L.teff_rgb(1000) and L.teff_rgb(90000) == L.teff_rgb(40000)
