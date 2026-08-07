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

The Smart Inbox agent in `ai/` is Python and LangGraph, but it is a build-time
tool, not part of the site. It runs on your machine, writes a JSON file, and
ships nothing to the browser. See "The Smart Inbox agent" below.

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
    inbox.json        #   member messages, the ui labels, and the sort options
    inbox-ai.json     #   what the agent made of each message. Generated, see below
    members.json      #   the roster table
    integrations.json #   connection list and sync status
src/
  site.css            # tokens + every marketing-page style. All three pages load it
  site.js             # brand intro, hero portal tilt, scroll reveals, stat count-ups
  demo.css            # the demo app shell only. Loads after site.css and reuses its tokens
  demo.js             # renders demo/data into DOM, plus routing and interactions
ai/                   # the Smart Inbox agent. Runs offline, ships nothing to the browser
  graph.py            #   the LangGraph: sort, then route to a drafter per category
  prompts.py          #   gym facts, what the agent may promise, and the voice rules
  run.py              #   the runner and the cache. Writes demo/data/inbox-ai.json
  requirements.txt    #   langgraph, langchain-openai, pydantic, python-dotenv
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

Outside the Smart Inbox, only behaviour that reads directly out of the data is
implemented. The churn table reports risk scores and signals without
prescribing what to do about them, and Growth attributes members to posts
without recommending the next one. Those stay unbuilt on purpose.

The gym, the members, and every figure are invented. The page labels itself
"Sample data" in the return pill and is `noindex`.

## The Smart Inbox agent

The inbox is the one view with a model behind it. It sorts each message into a
category and a priority, then drafts a reply the owner can edit and send.

**It runs offline, not in the browser.** A static site cannot hold an API key,
and paying for a model call every time someone refreshes a demo would be
absurd. So `ai/run.py` does the work on your machine and writes
`demo/data/inbox-ai.json`; `src/demo.js` imports that file like any other data.
The browser never talks to OpenAI, and the key never leaves `.env`.

```bash
python -m venv ai/.venv
ai/.venv/Scripts/python -m pip install -r ai/requirements.txt   # Windows
python ai/run.py
```

`.env` needs `OPENAI_API_KEY`. Copy `.env.example` to start. Both passes run on
`gpt-5.6-luna`; override either with `SOLVD_SORT_MODEL` or `SOLVD_DRAFT_MODEL`,
for instance to sort on something cheaper than you draft on.

### The graph

```
START -> sort -> draft_billing | draft_membership | draft_schedule
                 draft_lead    | draft_facilities | draft_other    -> END
```

`sort` assigns `category`, `priority`, `needs_human`, `confidence` and a
one-line summary. A conditional edge then routes to the drafter for that
category, each with its own prompt, because a duplicate charge and a
cancellation are not the same kind of reply. Drafting never runs without a
sort, so an email costs two calls at most.

Everything the agent knows or may promise is in `ai/prompts.py`: the gym's
hours, plans and classes, plus a policy block listing exactly what it can
commit to unaided (freezes to 60 days, one plan change a cycle, refunding a
duplicate charge). Anything outside that list has to be escalated rather than
invented, which is what `needs_human` is for. Changing gym policy is a text
edit in that file.

### One call per email, ever

Each email is fingerprinted from its own content plus the models and prompts
that produced its result. A matching fingerprint means the answer is already
cached and the email is skipped, so re-running is free and idempotent.
Editing the message, or editing `prompts.py`, changes the fingerprint and
re-runs just what it affects. Results for deleted emails are pruned.

```bash
python ai/run.py --list    # report what is cached and what is stale, call nothing
python ai/run.py --only kayla-freeze
python ai/run.py --force   # ignore the cache
```

Every thread in `inbox.json` therefore needs a stable `id`: it is the cache
key, and `run.py` refuses to start without one. `demo.js` keys open and
replied state off the same id, since sorting makes array position meaningless.

### What the demo shows

Category and priority appear on each row, and the sort control offers priority,
newest, or category. Open a message and you also get the sort rationale, the
drafted reply pre-filled and editable, the one system change sending it would
commit to, and a "Read this one first" flag when `needs_human` is set. A thread
with no cached entry still renders: it sorts as low priority and gets an empty
composer.

## Before launch

- The form `action` in `index.html` is still `https://formspree.io/f/REPLACE_ME`.
  Point it at a real endpoint.
- Confirm the LinkedIn URL in the footer of `/` and `/custom/`.
- `public/sitemap.xml` lists `/` and `/custom/` only. `/demo/` is excluded on
  purpose, since it is sample data.

## Loose ends

- **The drafts read a little stiff in places.** They are real output and they
  are accurate, but the model is more formal than the voice rules ask for, and
  it likes typographic apostrophes. Worth another pass at `REPLY_RULES` in
  `ai/prompts.py` before this goes in front of a gym owner.
- **DESIGN.md is partly aspirational.** It is the v3 "The Thread" design doc,
  written when this site was going to be React plus Framer Motion. Its color,
  type, voice, spacing, and motion rules still hold and match `src/site.css`.
  Ignore its React and Tailwind implementation notes, the `src/index.css`
  `@theme` block, and the page-level thread SVG system, none of which exist.
- `.oxlintrc.json` still enables React plugin rules. Harmless, but there is no
  React here.
- `public/icons.svg`, `public/brand-banner.png`, and `public/solvd-icon.svg` are
  unreferenced.
