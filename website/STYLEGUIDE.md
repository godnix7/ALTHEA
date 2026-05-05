# Design System — Color Palette

## Light Theme

- Off-white background: `#F8F8F8`
- Beige surfaces (chat bar, toggles): `#F5F5DC`
- Beige border: `#E2E2C8`
- Beige active state: `#E6E6C7`
- Text: `#1A1A1A` (primary), `#484848` (secondary)
- Muted text: `#666`
- Shadows: `rgba(0,0,0,0.08)` to `rgba(0,0,0,0.12)`

## Dark Theme

- Page background: `#1A1A1A`
- Panel background: `rgba(30,30,30,0.95)`
- Text: `#FFFFFF`
- Composer: `#2A2A2A`
- Composer border: `#444`
- Toggle (default): `#444`, active `#5B9BD5`

## Usage Notes

- Chat composer uses beige background with subtle shadow to increase depth without harsh contrast.
- Toggles in light theme use beige fill; active uses a slightly darker beige.
- In dark theme, toggles keep original dark styles for contrast.
- Primary background across pages uses off-white to ensure calm, consistent tone.

## Accessibility

- Text `#1A1A1A` on off-white `#F8F8F8` achieves AA/AAA contrast.
- Secondary text `#484848` on beige `#F5F5DC` meets WCAG AA for body text.
- Maintain minimum contrast ratio of 4.5:1 for body text and 3:1 for UI components.

