# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Render a subject as a plain PNG, the way a reviewer sees it.

The image has no markers, no pipeline output and no target name. The only
text is the axis labels. Y limits come from the 0.5th and 99.5th percentiles
so that a few outliers do not flatten the plot.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from setuhq.subjects import Subject


def render_subject(subject: Subject, path: str | Path, *, dpi: int = 110) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(10, 4))
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    axis.plot(subject.time, subject.flux, ".", ms=1.6, color="#1f1f1f", rasterized=False)
    low, high = np.percentile(subject.flux, [0.5, 99.5])
    pad = 0.1 * (high - low) if high > low else 1e-4
    axis.set_ylim(low - pad, high + pad)
    axis.set_xlim(subject.start, subject.end)
    axis.set_xlabel(f"Time ({subject.time_unit})")
    axis.set_ylabel("Relative brightness")
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=dpi, format="png")
    return path
