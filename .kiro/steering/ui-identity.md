---
inclusion: fileMatch
fileMatchPattern: ["skeleton/web/**", "apps/*/web/**"]
---

# UI identity: the green-bar night ledger

Source images: 1986 continuous-form line-printer paper (green-bar), and a moonlit three-circle Venn diagram.

## Palette

| Token | Hex | Use |
|---|---|---|
| ink | `#0B1020` | Page ground (midnight). Never cream or beige |
| ink-2 | `#141B33` | Alternate green-bar band |
| phosphor | `#7CFFB2` | Rules, matched counts, focus rings |
| bone | `#EDEAE0` | Body text |
| amber | `#FFB347` | New findings tonight |
| moon | `#C9D3FF` | Venn circles outlines |
| blood | `#FF5A6E` | Only for a finding that persists more than 3 nights |

Contrast: every text/background pair meets WCAG 2.2 AA (4.5:1 for body text).

## Layout rules

- Findings are printout rows on alternating green-bar bands, never cards and never boxes with borders.
- Monospace for evidence values (`IBM Plex Mono`), a humanist sans for prose (`IBM Plex Sans`). Self-host the fonts.
- The Venn diagram is the main navigation: clicking a region filters the rows to that region.
- Each region is labelled by its plain meaning first. Its Halloween name follows as a small, quieter tag with its
  single-colour line glyph. No headline, count or button text depends on the Halloween name alone.
- Motion: a slow scan-line sweep on the header when a run completes. Respect `prefers-reduced-motion`.
- Every interactive element is reachable by keyboard and has a visible phosphor focus ring.
