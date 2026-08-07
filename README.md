# SOLVD — getsolvd.io

Static site for SOLVD, a two-person software firm in Charlotte, NC, and its
flagship product, The Gym Portal. Three pages, no client framework: all copy
ships in the initial HTML so crawlers and link previews get the full page with
JS disabled.

Color, type, voice, and motion rules live in [DESIGN.md](DESIGN.md). Read it
before changing anything visual, but see "Loose ends" below first, because parts
of it describe an implementation that was never built.

## Stack

- [Vite](https://vite.dev/) as a static multi-page bundler
- Hand-written HTML and CSS, tokens as custom properties
- Vanilla ES modules, used only for progressive enhancement
- [oxlint](https://oxc.rs/docs/guide/usage/linter)
- Archivo, Geist, and Geist Mono, loaded from Google Fonts in each page head

No React, no Tailwind, no runtime dependencies. `package.json` has exactly two
devDependencies, and that is deliberate.

## Getting started

```bash
npm install
npm run dev
```

Then open the printed local URL (defaults to http://localhost:5173).

## Scripts

| Command           | Description                  |
| ----------------- | ---------------------------- |
| `npm run dev`     | Start local dev server       |
| `npm run build`   | Production build to `dist/`  |
| `npm run lint`    | Run oxlint                   |
| `npm run preview` | Preview the production build |

## Pages

| Route      | Source               | Job                                                       |
| ---------- | -------------------- | --------------------------------------------------------- |
| `/`        | `index.html`         | The Gym Portal sales page: hero, pricing, proof, FAQ, form |
| `/custom/` | `custom/index.html`  | Custom builds and technical partnerships                  |
| `/demo/`   | `demo/index.html`    | Interactive product demo on sample data, `noindex`         |

Every page needs an entry in `rollupOptions.input` in `vite.config.js` or it
will not be built.

## Structure

```
index.html            # /
custom/index.html     # /custom/
demo/
  index.html          # /demo/ — a shell: the icon sprite and the containers JS fills
  data/               # every number, row and message in the demo, as JSON
    portal.json       #   gym, user, date ranges, and the view list that builds the nav
    overview.json     #   KPIs, the members chart series, attention list, activity feed
    growth.json       #   KPIs, post attribution table, channel breakdown
    churn.json        #   KPIs and the flagged-members table
    inbox.json        #   member messages and the reply composer's labels
    members.json      #   the roster table
    integrations.json #   connection list and sync status
src/
  site.css            # tokens + every marketing-page style. All three pages load it
  site.js             # brand intro, hero portal tilt, scroll reveals, stat count-ups
  demo.css            # the demo app shell only. Loads after site.css and reuses its tokens
  demo.js             # renders demo/data into DOM, plus routing and interactions
public/               # served from the root: favicons, OG image, wordmark, photo, robots, sitemap
vite.config.js        # the three build inputs
DESIGN.md             # color, type, voice, motion
```

`site.js` is loaded by `/` and `/custom/`. `/demo/` loads `demo.js` instead.

## Conventions

- **Tokens, not hex values.** Everything is a custom property in `:root` at the
  top of `src/site.css`: `--void`, `--panel`, `--line`, `--ink`, `--body`,
  `--muted`, `--signal`. `src/demo.css` adds one warm `--alert` hue, used only
  for churn risk and negative deltas, because a product needs a negative state
  the marketing pages never do.
- **Progressive enhancement is a hard rule.** Both scripts are optional. With JS
  off, every page renders complete and static: the intro overlay never mounts,
  reveals stay visible, and stats show their final values. Keep it that way.
  `/demo/` is the one exception: it renders its views from JSON at runtime, so
  it needs JS and says so in a `<noscript>` notice.
- **Motion lives in one place.** Each stylesheet ends with a motion layer gated
  on `prefers-reduced-motion: no-preference`, plus (on the marketing pages) an
  `html.js` class that JS only adds when it can actually run the reveals.
- **Accent budget.** Roughly one use of `--signal` per section, often zero. If
  you add color somewhere, remove it somewhere else. See DESIGN.md §2 and §3.

## The demo, and where its data comes from

Every number, row, and message lives in `demo/data/*.json`. There is no API and
no database: the JSON is imported at build time and rendered into the DOM by
`src/demo.js`, so tailoring the demo means editing JSON, never markup.

- **To change what the demo shows,** edit the JSON. `demo/index.html` is only a
  shell (icon sprite, return pill, and the containers the renderer fills), and
  the views are built on first visit.
- **Values, not coordinates.** The members chart holds twelve monthly counts
  plus a `min`/`max`; `demo.js` maps those to SVG geometry. Sparklines are plain
  arrays and auto-scale to their own range. Bar widths come from `value / total`.
- **Adding a view** means adding an entry to `views` in `portal.json` (which
  builds the nav, the route, and the container) and a renderer in `demo.js`.
- **Emphasis in copy** is marked with `*asterisks*`, so no JSON field ever has
  to carry HTML: `"Payment received: *$149* from Priya Shah"`.
- **Nodes, not HTML strings.** The renderer builds elements and sets
  `textContent`, so copy containing quotes or apostrophes cannot break markup.
- **Interactions are in-memory.** Sending a reply and the date-range control
  change local state only and reset on reload. The range buttons do not
  re-filter the data.

Only behaviour that reads directly out of the data is implemented. The AI layer
is deliberately not built yet: drafted replies, confidence scoring, suggested
CRM actions, and recommended retention actions are all absent, and the churn
table reports risk scores and signals without prescribing what to do about
them.

The gym, the members, and every figure are invented. The page labels itself
"Sample data" in the return pill and is `noindex`.

## Before launch

- The form `action` in `index.html` is still `https://formspree.io/f/REPLACE_ME`.
  Point it at a real endpoint.
- Confirm the LinkedIn URL in the footer of `/` and `/custom/`.
- `public/sitemap.xml` lists `/` and `/custom/` only. `/demo/` is excluded on
  purpose, since it is sample data.

## Loose ends

- **DESIGN.md is partly aspirational.** It is the v3 "The Thread" design doc,
  written when this site was going to be React plus Framer Motion. Its color,
  type, voice, spacing, and motion rules still hold and match `src/site.css`.
  Ignore its React and Tailwind implementation notes, the `src/index.css`
  `@theme` block, and the page-level thread SVG system, none of which exist.
- `.oxlintrc.json` still enables React plugin rules. Harmless, but there is no
  React here.
- `public/icons.svg`, `public/brand-banner.png`, and `public/solvd-icon.svg` are
  unreferenced.
