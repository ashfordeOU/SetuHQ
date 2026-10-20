import pytest

from setuhq.discover import Target, Toi, match_toi, reclassify_catalog, toi_fields

# TOI-2669.01 on TIC 348835438 (CP), as published in the NASA Exoplanet Archive TOI table.
TOI_2669 = Toi(name="2669.01", period=6.2034960, tranmid=2459985.6041570, period_err=0.0000390,
               tranmid_err=0.005585, duration_hours=5.715, disposition="CP")
TARGET = Target(tic=348835438, toi_periods=[TOI_2669.period], toi_names=[TOI_2669.name], tois=[TOI_2669])


def test_dip_at_btjd_3711_33_is_toi_2669_not_a_new_candidate():
    # The feed entry that was labelled new_candidate: BLS period 5.07 d, 1.9 h long,
    # 1.9 h before predicted TOI-2669.01 epoch 117.
    entry = {"tic": 348835438, "t_center": 3711.3324126891403, "time_unit": "BTJD",
             "duration_hours": 1.8978896168991923, "period_days": 5.070022689848916}
    match = match_toi(entry, TARGET)
    assert match is not None and match["toi"] == "2669.01" and match["epoch"] == 117
    assert match["offset_hours"] == pytest.approx(-1.94, abs=0.02)
    assert toi_fields(entry, TARGET)["status"] == "known_toi"


def test_dip_off_every_toi_epoch_stays_new_even_with_a_matching_period():
    # BTJD 4073.33 sits about 2.1 d from the nearest TOI-2669.01 epoch.
    entry = {"tic": 348835438, "t_center": 4073.329416433498, "time_unit": "BTJD",
             "duration_hours": 4.45, "period_days": 2.0738}
    assert match_toi(entry, TARGET) is None
    assert match_toi(dict(entry, period_days=6.2035), TARGET) is None


def test_period_and_epoch_rule_and_double_period():
    # On the period (2P) and 1.5 h off an epoch with a 1 h dip: inside max(1 h, dur, TOI dur).
    t = 2985.6041570 + 100 * 6.2034960 + 4.0 / 24
    entry = {"t_center": t, "time_unit": "BTJD", "duration_hours": 1.0, "period_days": 2 * 6.2034960}
    match = match_toi(entry, TARGET)
    assert match["rule"] == "period and mid-time match" and match["offset_hours"] == pytest.approx(4.0, abs=0.01)
    assert match_toi(dict(entry, period_days=3.1), TARGET) is None


def test_reclassify_catalog_fixes_stored_status_and_stores_offset():
    catalog = {"candidates": [{"tic": 348835438, "t_center": 3711.3324, "time_unit": "BTJD",
                               "duration_hours": 1.9, "period_days": 5.07, "status": "new_candidate"}]}
    assert reclassify_catalog(catalog, {348835438: TARGET}) == 1
    (entry,) = catalog["candidates"]
    assert entry["status"] == "known_toi" and entry["toi_match"] == "2669.01"
    assert entry["toi_offset_hours"] == pytest.approx(-1.94, abs=0.02)

