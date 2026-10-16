"""Live-archive tests. These are skipped by default and run with: pytest -m network"""

import pytest

from exoplan.loaders import load_tess


@pytest.mark.network
def test_tess_spoc_download_for_pi_men_sector_1():
    curves = load_tess("TIC 261136679", sectors=[1])
    assert len(curves) == 1
    lc = curves[0]
    assert lc.mission == "TESS"
    assert lc.provenance["sector"] == 1
    assert len(lc) > 10_000
