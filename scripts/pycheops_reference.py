#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""pycheops' decorrelation of one public CHEOPS visit, as the reference for scripts/stellar_validation.py
(item cheops_pycheops). Run it in pycheops' own environment, not SetuHQ's: pycheops 1.1.27 pins numpy 1.24
(Python 3.11):

    uv venv -p 3.11 pyc && VIRTUAL_ENV=pyc uv pip install pycheops "dace-query==3.0.2"
    XDG_CONFIG_HOME=<dir with pycheops.cfg> pyc/bin/python scripts/pycheops_reference.py CH_PR100018_TG035201_V0300 \
        cache/pycheops_ref/ref_CH_PR100018_TG035201_V0300.json

pycheops downloads the visit's public DRP archive from DACE into its own cache (delete the .tgz afterwards; it is
large), reads the DEFAULT aperture with the contamination subtracted and high points kept, and decorrelates with
the 15 terms below. The output holds the decorrelated light curve and pycheops' input, for the comparison only;
it stays in the cache and is never committed.
"""
import contextlib
import io
import json
import os
import sys

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import pycheops  # noqa: E402
from pycheops import Dataset  # noqa: E402

TERMS = dict(dfdt=True, d2fdt2=True, dfdx=True, dfdy=True, d2fdx2=True, d2fdy2=True, d2fdxdy=True, dfdsinphi=True,
             dfdcosphi=True, dfdsin2phi=True, dfdcos2phi=True, dfdsin3phi=True, dfdcos3phi=True, dfdbg=True, dfdcontam=True)

if __name__ == "__main__":
    fk, out = sys.argv[1], sys.argv[2]
    d = Dataset(fk)
    with contextlib.redirect_stdout(io.StringIO()):
        t, f, e = d.get_lightcurve(aperture="DEFAULT", decontaminate=True, reject_highpoints=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ff, ee = d.decorr(**TERMS)
    tt = np.array(d.lc["time"])
    json.dump({"file_key": fk, "pycheops_version": pycheops.__version__, "terms": sorted(TERMS),
               "bjd_ref": float(d.lc["bjd_ref"]), "time": tt.tolist(), "flux_decorrelated": np.asarray(ff).tolist(),
               "time_raw": np.asarray(t).tolist(), "flux_raw": np.asarray(f).tolist(), "log": buf.getvalue()[-3000:]},
              open(out, "w"))
    print("ok", len(tt))
