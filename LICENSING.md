<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# Licensing

SetuHQ is **dual-licensed**. You may use its code under **either** the open licence
(AGPL-3.0-only) **or** a **commercial licence** from Ashforde OÜ. Pick the one that fits how you
intend to use it. SetuHQ's own data, benchmark, leaderboard data and paper are under
**CC BY 4.0**.

> This document explains the model in plain language. It is a guide, not legal advice, and it
> does not modify the licences themselves. The binding terms are in [`LICENSE`](LICENSE) (the
> GNU AGPL-3.0), in the [CC BY 4.0 legal code](https://creativecommons.org/licenses/by/4.0/legalcode)
> and in any commercial agreement you sign with Ashforde OÜ. If they ever conflict with this
> page, those documents govern.

---

## Option A: open source, GNU AGPL-3.0-only

The default. The full text is in [`LICENSE`](LICENSE). In short, the AGPL lets you use, study,
modify and redistribute SetuHQ for free, **provided** that:

- if you **distribute** SetuHQ or a derivative, you make the **complete corresponding source**
  available under the AGPL; and
- if you let users interact with a **modified** SetuHQ **over a network** (the AGPL's
  distinguishing clause, §13: for example a hosted copy of the app, the MCP server or the
  pipeline behind a web form), you must offer **those users** the corresponding source of your
  modified version under the AGPL.

AGPL is an [OSI-approved open-source licence](https://opensource.org/license/agpl-v3) and strong
copyleft. It is the right choice for research, teaching, citizen science, open-source projects,
internal evaluation, and anyone happy to keep their own derivative open.

## Option B: commercial licence, from Ashforde OÜ

If the AGPL does not suit you, Ashforde OÜ will license the same code under commercial terms.
This is the right choice when you want to:

- **embed SetuHQ in a proprietary or closed-source product** (a smart-telescope app, an
  education product, a hosted service) without releasing your own source;
- **offer a network service** built on a modified SetuHQ **without** the §13
  source-disclosure obligation;
- integrate SetuHQ into a larger system whose other parts cannot be AGPL; or
- obtain a warranty, indemnity or support terms, which the AGPL explicitly disclaims.

A commercial licence removes the copyleft obligations for your use, on agreed terms.
**Contact: [contact@ashforde.org](mailto:contact@ashforde.org).**

## Data, benchmark, leaderboard data and paper: CC BY 4.0

What SetuHQ itself measured and wrote is licensed under the
[Creative Commons Attribution 4.0 International licence](https://creativecommons.org/licenses/by/4.0/)
(SPDX: `CC-BY-4.0`):

- the results under [`docs/results/`](docs/results/) that SetuHQ computed (validation,
  benchmarks, calibration, vetting, feed-rule and sweep checks);
- the frozen real-TOI benchmark's design and scored outputs, and the leaderboard data under
  [`docs/leaderboard/`](docs/leaderboard/) (its submissions, inputs and scored tables);
- the sweep records and catalogue under [`docs/sweep/`](docs/sweep/) and the search feed under
  [`docs/discoveries/`](docs/discoveries/);
- the stored run [`runs/tess-pi-men-s1/`](runs/tess-pi-men-s1/) (its candidates, classifications
  and manifest);
- the methods paper, [`docs/paper/`](docs/paper/).

You may share and adapt them for any purpose, commercial included, provided you give credit
("SetuHQ, Ashforde OÜ", with a link to https://setuhq.com or the repository), link the licence and
say what you changed. `docs/results/`, `docs/leaderboard/`, `docs/sweep/`, `docs/discoveries/`
and `docs/paper/` each carry a short `LICENSE.md` that says so (the stored run is covered by this
page, so that its folder stays exactly as the run wrote it), and
`docs/leaderboard/leaderboard.json` states `"license": "CC-BY-4.0"`.

**Third-party data keeps its own terms.** Where a file holds or derives from someone else's
data (the exoplanet.eu catalogue, NASA MAST and NASA Exoplanet Archive tables, the Claret 2017
limb-darkening table, the WASP-39 b JWST spectrum), CC BY 4.0 covers only SetuHQ's own
contribution, and the source's terms and requested acknowledgements apply to the rest. They are
listed in [`NOTICE`](NOTICE).

**CHEOPS data are excluded.** CHEOPS light curves, and every output derived from them (the CHEOPS
parts of `docs/results/stellar_validation.*`, the test excerpt `tests/data/cheops_gj65_excerpt.json`,
and anything `setuhq cheops` or the `get_cheops_lightcurve` tool produces), stay under ESA's terms:
data in the ESA Space Science Archives are distributed under the **CC BY-NC 3.0 IGO** licence, and any
commercial use, including use that indirectly generates financial gain, needs ESA's **prior
authorisation** ([data.licences@esa.int](mailto:data.licences@esa.int); ESDC terms and conditions).
CC BY 4.0 does not apply to them, and **neither the commercial licence nor SetuHQ Pro covers
them**: a hosted, Pro or other commercial use of CHEOPS data through SetuHQ needs ESA's
authorisation first. Every CHEOPS-derived output carries ESA's acknowledgement, the programme and
visit ids, the credit line "Credit: ESA, <proposal PI>" and SetuHQ's statement that it is not
affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission or the CHEOPS
Consortium ([`docs/STELLAR.md`](docs/STELLAR.md)).

**The `[cheops]` extra installs `dace-query`, which is licensed GPL-3.0.** It is optional, not
shipped with SetuHQ and not needed for anything else; it is compatible with the AGPL-3.0 option,
and a commercial licensee who installs it takes on its GPL-3.0 terms for that package.

---

## Why dual-license this way

The goal is to be **publicly verifiable**, so anyone can run and audit the search, the vetting
and the benchmark, **without** letting someone fork the engine, close it and ship a proprietary
competitor that gives nothing back. The AGPL's network copyleft achieves that: a closed or hosted
derivative must come back to open source, or take a commercial licence from us. The open
benchmark, the leaderboard and the paper are under CC BY 4.0 so that anyone, including other
pipelines and AI providers, can use and cite them freely.

## What is **not** covered by the dual licence

- **SetuHQ Pro** and any other proprietary overlay are separate, closed-source products under
  their own commercial terms. None is built yet (see [`docs/PRO.md`](docs/PRO.md)); none is part
  of this repository or offered under the AGPL.
- **Fonts.** Geist, Geist Mono and Unbounded are under the SIL Open Font License 1.1; their
  licence texts ship beside each copy of the fonts (see [`NOTICE`](NOTICE)).
- **Third-party data,** as above and in [`NOTICE`](NOTICE).
- **Dependencies** keep their own licences. They are installed by pip and are not part of
  this repository.
- **Trademarks.** "SetuHQ", "Setu" and the Setu mark are trademarks of Ashforde OÜ. Neither
  licence grants rights to the name or the marks; forks and derivative distributions must use a
  different name. See [`TRADEMARKS.md`](TRADEMARKS.md).

## Contributions

Contributions are accepted under the [Contributor Licence Agreement](CLA.md), which licenses
your contribution under the AGPL **and** grants Ashforde OÜ the right to include it in the
commercially licensed edition, so the dual licence keeps working. You keep the copyright in your
contribution. See [`CONTRIBUTING.md`](CONTRIBUTING.md#licence-and-the-cla).

## The licence before this release

Before its public release the code was published privately as `exoplan` under the MIT licence.
Every commit in that history was made by Ashforde OÜ's own account, so the change to
AGPL-3.0-only (or a commercial licence) is the copyright owner's decision. A copy of the code
someone received under MIT before the change keeps that grant for that copy.

## Questions

Licensing questions, commercial terms and "which option applies to us?":
**[contact@ashforde.org](mailto:contact@ashforde.org)**.
