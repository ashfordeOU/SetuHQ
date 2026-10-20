# SetuHQ brand kit

Source-of-truth logo files for SetuHQ. Every file in this folder except this README is
written by `tools/gen_readme_assets.py` and checked by its `--check` step, so do not edit them
by hand: change the generator and regenerate.

```bash
python3 tools/gen_readme_assets.py          # rewrite docs/assets/brand/ and docs/assets/readme/
python3 tools/gen_readme_assets.py --check  # fail if any file differs from what it would write
```

## Layout

```
docs/assets/brand/
├── setuhq-logo-light.svg       # the lockup: Setu mark + wordmark, for light backgrounds
├── setuhq-logo-dark.svg        # the lockup, for dark backgrounds
├── setuhq-wordmark-light.svg   # the wordmark without the mark
├── setuhq-wordmark-dark.svg
├── setuhq-icon-black.svg       # app icon: the transit Q on #000, rounded square, 512 x 512
├── setuhq-icon-navy.svg        # app icon: the transit Q on #0A1226
├── setuhq-favicon.svg          # the transit Q, follows prefers-color-scheme
└── setuhq-social-card.svg      # 1200 x 630 Open Graph / social card
```

## Design

- **Mark.** The Setu mark, a flowing S of two paths with a dashed centre line: *setu*,
  Sanskrit for bridge. Taken unchanged from the Setu brand kit (`brand/svg/setu-mark.svg`,
  copied to `docs/assets/readme/brand/`) and cropped to its own bounding box.
- **"Setu".** Unbounded, weight 600, letter-spacing −1/64 em, in ink.
- **"HQ".** "H" is Unbounded 300 in blue. "Q" is drawn, not typed: a ring (the star) with the
  weight, height and overshoot of Unbounded 300's "O", a cyan planet dot 0.3 times the ring's
  radius crossing its face toward the upper left (a transit), and the Q's tail at the lower
  right in the ring's stroke. In the SVG it is three primitives: circle, circle, rounded line.
- **Every word is outlined.** No file loads a font, so the logo renders the same on GitHub, in
  mail clients and offline. The fonts (Unbounded, Geist, Geist Mono) are under the SIL Open
  Font License; their licences are in `tools/readme-fonts/`.

## Colours

| Token | Light backgrounds | Dark backgrounds |
|---|---|---|
| Ink ("Setu", the mark) | `#0A1226` | `#F5F5F7` |
| Blue ("H", the Q's ring and tail) | `#0071E3` | `#0A84FF` |
| Planet (the Q's dot) | `#64D2FF` | `#64D2FF` |
| Icon and card ground | `#000000` or `#0A1226` (navy) | |

## Usage rules

| Surface | File |
|---|---|
| README header, documentation | `setuhq-logo-light.svg` and `-dark.svg` in a `<picture>` with `prefers-color-scheme` |
| Small spaces, inline in text | `setuhq-wordmark-*.svg` |
| Browser tab | `setuhq-favicon.svg` |
| App launcher, avatar, social profile | `setuhq-icon-black.svg` or `setuhq-icon-navy.svg` |
| Link previews (Open Graph, X, LinkedIn) | `setuhq-social-card.svg`, rasterised to PNG where SVG is not accepted |

- Keep clear space around the lockup of at least the height of the "H" on every side.
- Do not recolour, stretch, rotate or outline the logo, re-set the wordmark in another
  typeface, or separate the planet from the Q.
- Use the light variant on light grounds and the dark variant on dark grounds; on photographs,
  put the logo on a solid panel.
- The transit Q may stand alone (icon, favicon); the wordmark never drops the Q's planet.

## Trade marks

"SetuHQ", "Setu" and the Setu mark are trade marks of Ashforde® OÜ. Forks must use another
name and another mark.
