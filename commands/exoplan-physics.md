---
description: Work out exoplanet physics with SetuHQ's Methods formulas (radial-velocity K, transit depth, microlensing A(u), habitable zone), via the exoplan MCP server
argument-hint: "[a question, e.g. 'K for a 1 MJ planet in 4 days around a 1.1 Msun star', 'depth of an Earth around an M dwarf']"
---

# Methods physics

Request: **$ARGUMENTS**

Use the `exoplan` MCP server's formula tools; do not do the arithmetic yourself:

- **`rv_semi_amplitude`**: K in m/s from period, planet mass (Jupiter masses), star mass (solar), e, sin i.
- **`transit_depth`**: the central-transit depth from Rp/R★ (or Rp in Earth radii and R★ in solar radii),
  geometric and, with the star's Teff, limb-darkened for TESS.
- **`microlensing_magnification`**: the point-lens A(u).
- **`habitable_zone`**: the four Kopparapu et al. 2014 edges in AU for a star's Teff and luminosity.

If a value the user needs is a real system's, look it up first (**`get_planet`**, **`get_star`**) and say it
came from the catalogue. Report the result with the equation and the honesty label the tool returns: these
are idealised formulas, not measurements, and a habitable-zone distance says nothing about habitability.
