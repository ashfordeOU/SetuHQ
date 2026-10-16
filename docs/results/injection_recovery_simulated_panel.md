# Injection recovery: deterministic panel (no Claude)

Panel: volunteer-sensitive, volunteer-typical, volunteer-cautious

Weights: volunteer-cautious=0.633, volunteer-sensitive=0.667, volunteer-typical=0.667

Completeness is the fraction of injected transits recovered as a vetted candidate, with the consensus centred within half a transit duration of the injection.

| depth (ppm) | duration (h) | subjects | recovered | completeness |
|---:|---:|---:|---:|---:|
| 300 | 1.0 | 20 | 0 | 0.00 |
| 300 | 2.0 | 20 | 0 | 0.00 |
| 300 | 4.0 | 20 | 0 | 0.00 |
| 1000 | 1.0 | 20 | 1 | 0.05 |
| 1000 | 2.0 | 20 | 12 | 0.60 |
| 1000 | 4.0 | 20 | 18 | 0.90 |
| 3000 | 1.0 | 20 | 20 | 1.00 |
| 3000 | 2.0 | 20 | 19 | 0.95 |
| 3000 | 4.0 | 20 | 20 | 1.00 |

False positives: 0.000 vetted candidates per empty subject (40 empty subjects).
