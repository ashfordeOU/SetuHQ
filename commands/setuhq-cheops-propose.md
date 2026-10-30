---
description: Prepare (never submit) a CHEOPS Guest Observers proposal for a target - rules check, target status, estimates, anonymised drafts and ESA's checklist - via the SetuHQ MCP server
argument-hint: "[target and plan, e.g. 'TOI-1987, regular, 30 orbits' or 'WASP-12 eclipse, large programme, April 2027']"
---

# A CHEOPS proposal preparation pack

Request: **$ARGUMENTS**

SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission
or the CHEOPS Consortium. It does not replace ESA's Target Checker, Visibility Tool, Exposure Time Calculator,
Scheduling Feasibility Checker or the Policies & Procedures document; the official call and tools govern.

Do this:

1. Call **`cheops_proposal_pack`** with the target, a new plain `run_name`, the programme type (`regular`,
   `large` or `fasttrack`), the orbits and cycle if given, and the event depth and duration if the user knows
   them. It writes a new `runs/propose/<run_name>` and nothing else.
2. Report the rules check first: errors (orbit limits, the April/October rule for Large programmes, a passed
   deadline) and the next deadline in Paris time with the earliest start.
3. Report the target status as found: on the public Reserved Target List or not, already observed or not
   (public visit ids), the coordinate source, and the Sun-constraint screen. Say plainly that ESA's Target
   Checker and Mission Archive are definitive.
4. Give the precision and orbit numbers as estimates only, and tell the user to confirm them with ESA's Exposure
   Time Calculator, Visibility Tool and Scheduling Feasibility Checker.
5. Any SetuHQ evidence is a candidate, not a discovery and not a confirmation.
6. Never submit, log in or fill in anything on ESA systems; the user does that through PHT1 themselves.
