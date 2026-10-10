# Dispatch board library spike (REQ-03)

Installed versions (frontend/package.json, React 19.3):

- react-big-calendar 1.20.0
- date-fns 4.4.0
- @date-fns/tz 1.5.0
- @types/react-big-calendar 1.16.3 (dev)

Checks:

- react-big-calendar `license` field: MIT
- peerDependencies: react `^16.14.0 || ^17 || ^18 || ^19`, react-dom `^16.14.0 || ^17 || ^18 || ^19`
- `npm install react-big-calendar date-fns @date-fns/tz` and `npm install -D @types/react-big-calendar`
  succeeded with no flags (no --legacy-peer-deps, no --force), no `overrides` key and no .npmrc.
- `src/scheduling/Spike.test.tsx` renders `withDragAndDrop(Calendar)` in jsdom with a day view and
  two resources and two events: both headers and titles render, `rbc-addons-dnd` is present, and
  console.error logged no Warning or Error.
- gzip size of the lazy-loaded calendar chunk (`npm run build`, vite 8.3.1, measured in 03-02):

  | Asset | Raw | gzip |
  |---|---|---|
  | `Dispatch-*.js` (lazy: page, dialogs, react-big-calendar, DnD addon, date-fns, @date-fns/tz) | 303.50 kB | 84.15 kB |
  | `Dispatch-*.css` (lazy: react-big-calendar and DnD CSS, dispatch.css) | 14.48 kB | 3.30 kB |
  | `index-*.js` (main) | 560.33 kB | 145.63 kB |
  | `index-*.css` (main) | 25.51 kB | 6.04 kB |

  `App.tsx` loads the page with `lazy(() => import("./pages/Dispatch"))`. `grep -c 'rbc-'` returns 0
  for the main JS and CSS assets and a nonzero count for both Dispatch assets, so react-big-calendar
  ships only in the lazy chunk. Vite's ">500 kB" warning refers to the main chunk, which this
  library does not contribute to.

Result: GO
