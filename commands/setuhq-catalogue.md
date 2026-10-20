---
description: Look up a known exoplanet or host star in SetuHQ's stored catalogue (as stored, with its source), via the SetuHQ MCP server
argument-hint: "[a planet or star name, a TIC id, or a filter, e.g. 'pi Men', 'transiting planets', 'TIC 261136679']"
---

# Look up the catalogue

Request: **$ARGUMENTS**

Do this:

1. Call **`search_catalogue`** with the name (or part of it, or a TIC id) and, if the user asks for one,
   a `method` (transit, rv, imaging, microlensing, astrometry, timing).
2. For one planet call **`get_planet`** with its exact name; for a star and all its planets **`get_star`**.
3. Report the stored values with their units (the result's honesty labels give them). A missing value is
   "not stored", never a guess. Name the catalogue's source and fetch date from the provenance.
4. SetuHQ did not discover these planets; it catalogues them. Say so if the user might think otherwise.
