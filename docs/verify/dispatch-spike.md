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
- gzip size of the lazy-loaded calendar chunk (`npx vite build`): measured in 03-02

Result: GO
