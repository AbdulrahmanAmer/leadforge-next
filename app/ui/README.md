# The LeadForge window: screens

React and TypeScript with Vite. The screens talk to the engine only through `src/engine.ts`; the page
`docs/window-actions.md` maps every action to its engine command and lists what the engine lacks.

```
npm ci --ignore-scripts
npm run dev         # http://127.0.0.1:5183, on made-up data (src/engine.mock.ts)
npm run typecheck
npm test            # the mock engine's error paths
npm run build       # dist/, with the content security policy written into index.html
```

Inside the Tauri shell the screens use `src/engine.tauri.ts`. Anywhere else they use the mock, and the
address can ask for a state to look at:

```
?screen=campaign|run|results|people|data|keys|settings
&theme=light|dark  &accent=cobalt|brass|celadon|ember
&mock=done|empty|loading|error
&run=mid|done|fail      a run in progress, finished, or failed while reading websites
&plan=1                 New campaign with the form filled in and the plan asked for
&dialog=forget|suppress|purge|everything|about
```

## The look

The design farm's `quiet-porcelain` recipe (light) and its sibling `quiet-ink` (dark): palettes porcelain and
ink, depth `glass-still`, shape `capsule`, type `system`, at the farm's `comfortable` density. Ported as CSS
variables in `src/styles/tokens.css`; components keep the farm's structure and `ds-` class names
(`src/components/ui.tsx`, `src/styles/components.css`). Paint only: no `backdrop-filter`, no web font, no image.

## Rules that hold here

- No remote resource, no inline script, no `style` attribute, no `eval`. No link that opens a browser.
- No file or network access from the window. No send or outreach action.
- Mock data is made up: `.example` domains and Ofcom's drama phone ranges only.
- Dependencies at exact versions; `npm ci --ignore-scripts`.
