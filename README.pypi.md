<!-- The package page on PyPI (pyproject.toml: readme). PyPI does not rewrite relative paths, so every link and
     image here is absolute, pinned to the main branch. The full README is README.md on GitHub. Keep this page free
     of benchmark numbers: they live in the repository, where they are regenerated from the committed results.
     The next line is the ownership marker the official MCP registry reads; it must equal "name" in server.json. -->
<!-- mcp-name: io.github.ashfordeOU/setuhq -->

<p align="center">
  <img src="https://raw.githubusercontent.com/ashfordeOU/SetuHQ/main/docs/assets/brand/setuhq-logo-light.svg" alt="SetuHQ: the Setu mark beside the wordmark SetuHQ, whose Q is a star with a planet crossing its face" width="360">
</p>

<p align="center">
  <strong>SetuHQ · <em>the bridge</em></strong><br>
  The open exoplanet observatory: from public sky data to reviewed, explained candidates.
</p>

SetuHQ is an open, reproducible transit search of public NASA TESS light curves. A reviewer panel of
AI **Sentinels** (Claude by default; other providers supported and labelled) and deterministic
matched-filter **Probes** marks every dip in blind-coded light curves, the way Planet Hunters volunteers
do. The pipeline then vets each dip, fits a limb-darkened transit model and bounds its false-alarm
probability. Every candidate keeps its provenance: data hash, config hash, code fingerprint and every
reviewer's marks.

**Every SetuHQ output is a candidate, never a confirmation.** Follow-up observations decide what is a
planet.

## Install

```bash
pip install setuhq                 # the setuhq command
pip install "setuhq[mcp]"          # plus the setuhq-mcp server for AI assistants
pip install "setuhq[tess,mcp]"     # plus TESS downloads through lightkurve
```

Python 3.10 or later. The stored runs, the frozen real-TOI benchmark, the leaderboard, the site and the
reference tables the pipeline reads (limb-darkening coefficients, the secondary-eclipse calibration) are
data, not code, so they are not in the package. The package alone gives the commands, the MCP server and
the tools that need no stored data (BLS vetting, the false-alarm probability, the Methods physics). To run
the pipeline or the transit fit, reproduce the results, or point the MCP tools at the stored runs, install
from a checkout of the repository (`pip install -e ".[mcp]"`) and set `SETUHQ_ROOT` to it.

```bash
git clone https://github.com/ashfordeOU/SetuHQ
SETUHQ_ROOT=$PWD/SetuHQ setuhq-mcp --list-tools
```

## Use

```bash
setuhq --help                                   # every command
setuhq run configs/tess_pi_men_s1.toml --out runs/tess-pi-men-s1
setuhq docket runs/tess-pi-men-s1 --out site/docket --title "pi Men (TESS sector 1)"
setuhq-mcp                                      # the MCP server over stdio
```

The [quick-start notebook](https://github.com/ashfordeOU/SetuHQ/blob/main/examples/quickstart.ipynb)
walks through the stored pi Men run offline: the candidates, the docket data, a Probe on a stored light
curve and an MCP tool called as a plain function.

## The MCP server

`setuhq-mcp` lets an AI assistant run SetuHQ's own code and read its stored results instead of guessing
them: the exoplanet catalogue, a run's candidates with full provenance, BLS search and vetting, the
transit fit, the bounded false-alarm probability and the Methods physics. Every answer carries its
provenance and honesty labels. The server runs on your computer; nothing is sent to Ashforde OÜ. Set-up
for each client is in
[docs/MCP-INSTALL.md](https://github.com/ashfordeOU/SetuHQ/blob/main/docs/MCP-INSTALL.md).

## Learn more

- **The full README, the evidence and the benchmark:** <https://github.com/ashfordeOU/SetuHQ>
- **The app:** <https://setuhq.com>
- **Changelog:** [CHANGELOG.md](https://github.com/ashfordeOU/SetuHQ/blob/main/CHANGELOG.md)
- **Cite:** [CITATION.cff](https://github.com/ashfordeOU/SetuHQ/blob/main/CITATION.cff)
- **Security:** [SECURITY.md](https://github.com/ashfordeOU/SetuHQ/blob/main/SECURITY.md)

## Licence

The code is under the **GNU AGPL-3.0-only**, or under a **commercial licence** from Ashforde OÜ
([contact@ashforde.org](mailto:contact@ashforde.org)) for use the AGPL does not suit. SetuHQ's own data,
benchmark, leaderboard data and paper are under **CC BY 4.0**. See
[LICENSING.md](https://github.com/ashfordeOU/SetuHQ/blob/main/LICENSING.md). "SetuHQ" and the Setu mark
are trademarks of Ashforde OÜ
([TRADEMARKS.md](https://github.com/ashfordeOU/SetuHQ/blob/main/TRADEMARKS.md)).
