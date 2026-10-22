<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Quick-start notebook

[`examples/quickstart.ipynb`](../examples/quickstart.ipynb) walks through the run stored in the repository,
`runs/tess-pi-men-s1` (TESS sector 1 of pi Men), **offline**: it loads the run's candidates, shows the data
behind the Docket, runs a Probe on a stored light curve and calls an MCP tool as a plain Python function.
Nothing is downloaded and no AI provider is called. Every SetuHQ output is a candidate, never a
confirmation.

In a checkout:

```bash
pip install -e ".[mcp]" jupyterlab
jupyter lab examples/quickstart.ipynb
```

In Google Colab (its first cell clones the repository and installs it, so this path needs the network):

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ashfordeOU/SetuHQ/blob/main/examples/quickstart.ipynb)

`https://colab.research.google.com/github/ashfordeOU/SetuHQ/blob/main/examples/quickstart.ipynb`

The notebook is committed with its outputs cleared, and `tests/test_quickstart_notebook.py` runs its code
cells in order, offline, on every test run.
