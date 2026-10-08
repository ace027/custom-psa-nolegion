# Look and feel: themes and tokens

The staff app and the client portal share one design: a light theme (indigo accent) and a dark theme
(navy with a teal accent). It is colours, layout and components only; no behaviour changed.

## How themes work
- `frontend/src/index.css` holds all colour tokens. The pages use Tailwind's `slate`, `blue`, `red`,
  `amber`, `green` colour names; the two themes re-point those names (light in `@theme`, dark under
  `:root.dark`). So pages need no per-theme classes, and a new page that uses the usual classes is
  automatically correct in both themes.
- `blue-*` is the **accent** colour (indigo in light, teal in dark). To rebrand, change that one scale
  (and `--color-on-accent`, the text drawn on the accent).
- `bg-surface` is the card/input background. Do not use `bg-white`: it must stay white for text on
  buttons. `text-on-accent` is text on an accent-coloured button.
- `frontend/src/theme.ts` picks the theme: **Auto** (follows the operating system), **Light** or **Dark**.
  The toggle (sidebar for staff, header for the portal, sign-in cards) cycles through them and the choice
  is remembered in that browser only (`localStorage`, `psa-theme`). A tiny script in `index.html` applies it
  before first paint so dark mode does not flash white. If browser storage is blocked, Auto is used.
- Invoices, statements, quotes and every PDF/email stay light on purpose (they are printed and sent).

## Layout
- Staff: left sidebar (collapses to a **Menu** button on phones), content up to a readable width.
- Portal: header bar with the client's name, tabs, and (Devices) summary tiles plus a warranty coverage bar.
- The placeholder "E" / "P" mark and company name are text; there is no logo upload or branding setting
  (backlog).

## Adding to the UI
Reuse `Card`, `Button`, `StatTile`, `WarrantyBadge`, `inputCls` from `src/ui.tsx`. Status colours should
always be paired with text (never colour alone), as the badges are.
