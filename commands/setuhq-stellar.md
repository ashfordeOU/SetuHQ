---
description: Look at a star beyond its planets with SetuHQ: flares, pulsations and public CHEOPS light curves, via the SetuHQ MCP server
argument-hint: "[a light curve or a target, e.g. 'flares in my CSV of AU Mic', 'pulsations of this light curve', 'CHEOPS visits of HR 10']"
---

# Stellar flares, pulsations and CHEOPS

Request: **$ARGUMENTS**

Use the `setuhq` MCP server's stellar tools; do not estimate from the plot yourself:

- **`find_flares`**: flares in a light curve (a CSV path in the data root, or time and flux arrays), with their
  morphology (simple or multi-component), equivalent duration and, when Teff and radius are given, energies. It
  also reports the flux-inverted null: how many 'flares' the method finds where no star makes them.
- **`pulsation_spectrum`**: the frequencies a light curve holds down to S/N 4, combination frequencies, the
  granulation background, numax and Δν for a solar-like oscillator, and a heuristic type.
- **`get_cheops_lightcurve`**: the public CHEOPS visits of a target, fetched once, detrended, with their
  programme, file key and credit line. It reaches the network; say so before calling it.

Report what the tools return with their labels: a flare or a frequency is *detected* at the significance stated,
never confirmed; a type is *likely* or a *candidate*; an energy rests on a 9000 K blackbody and the TIC values, or
is unavailable. Say each capability's validation status as the tool gives it. Anything from CHEOPS keeps ESA's
acknowledgement, the programme and visit ids, the credit line and the statement that SetuHQ is independent of
ESA and the CHEOPS mission. Do not post or send results anywhere without the user's explicit approval: stop and ask.
