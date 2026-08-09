# SOLVD — getsolvd.io

Website and live portal for SOLVD, a two-person software firm in Charlotte, NC,
and its flagship product, The Gym Portal. The frontend has no client framework:
marketing copy ships in the initial HTML and the dashboard uses vanilla ES
modules. A FastAPI service now owns authentication, live email ingestion,
durable inbox state, and server-side OpenAI calls.

Color, type, voice, and motion rules live in [DESIGN.md](DESIGN.md). Read it
before changing anything visual, but see "Loose ends" below first, because parts
of it describe an implementation that was never built.

## Stack

- [Vite](https://vite.dev/) as a static multi-page bundler
- Hand-written HTML and CSS, tokens as custom properties
- Vanilla ES modules, used only for progressive enhancement
- [oxlint](https://oxc.rs/docs/guide/usage/linter)
- FastAPI, SQLAlchemy, and Postgres for the live portal service
- LangGraph and OpenAI's Responses API for Smart Inbox classification/drafting
- Archivo, Geist, and Geist Mono, loaded from Google Fonts in each page head

No React and no Tailwind. The Python backend and model code never ship to the
browser, and the OpenAI key remains server-side.

## Getting started

```bash
npm install
npm run build
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn server.app:app --reload
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

| Route      | Source              | Job                                                        |
| ---------- | ------------------- | ---------------------------------------------------------- |
| `/`        | `index.html`        | The Gym Portal sales page: hero, pricing, proof, FAQ, form  |
| `/custom/` | `custom/index.html` | Custom builds and technical partnerships                   |
| `/demo/`   | `demo/index.html`   | Product demo on hand-written sample data, `noindex`         |
| `/login/`  | `login/index.html`  | Client sign in through the authenticated portal API         |
| `/app/`    | `app/index.html`    | Authorized dashboard with a live, polling Smart Inbox       |

Every page needs an entry in `rollupOptions.input` in `vite.config.js` or it
will not be built.

`/demo/` and `/app/` are the same dashboard. They differ only in where the
numbers come from, which is what `data-portal` on the `<body>` selects.

## Structure

```
index.html            # /
custom/index.html     # /custom/
login/index.html      # /login/
app/index.html        # /app/  — same shell as the demo, data-portal="account"
demo/
  index.html          # /demo/ — a shell: just the containers JS fills
  data/               # every number, row and message in the demo, as JSON
    portal.json       #   gym, user, date ranges, and the view list that builds the nav
    overview.json     #   KPIs, the members chart series, attention list, activity feed
    growth.json       #   KPIs, post attribution table, channel breakdown
    churn.json        #   KPIs and the flagged-members table
    inbox.json        #   member messages, the ui labels, and the sort options
    inbox-ai.json     #   what the agent made of each message. Generated, see below
    members.json      #   the roster table
    integrations.json #   connection list and sync status
accounts/
  generate.py         # seeded generator. Rewrites test/ from scratch, deterministically
  test/               # raw records for the 'test' account, in integration shape
    account.json      #   gym, owner, connections, and the as-of date everything is scored against
    members.json      #   one row per member ever: plan, price, joined, cancelled, acquisition
    visits.json       #   ~6k check-ins. The only source for every risk score
    charges.json      #   ten months of billing, including failures
    posts.json        #   social posts with reach and clicks
    pass_claims.json  #   free-pass claims, some of which converted
    messages.json     #   member email, addressed from real rows in members.json
    inbox-ai.json     #   seeded account drafts used to bootstrap local development
src/
  site.css            # tokens + every marketing-page style. /, /custom/ and /login/ load it
  site.js             # brand intro, hero portal tilt, scroll reveals, stat count-ups
  portal.css          # the dashboard shell only. Loads after site.css and reuses its tokens
  portal.js           # renders a data bundle into DOM, plus routing and interactions
  derive.js           # raw records -> the view models portal.js renders. /app/ only
  icons.js            # the SVG sprite, injected by JS so both dashboards share one copy
  api.js              # authenticated browser requests to the portal service
  session.js          # stores and validates the short-lived signed session
  login.js            # the /login/ form
ai/                   # the Smart Inbox graph, also usable as an offline generator
  model.py            #   ChatOpenAI wired to OpenAI's Responses API
  graph.py            #   the LangGraph: sort, then route to a drafter per category
  prompts.py          #   gym facts, what the agent may promise, and the voice rules
  run.py              #   the runner and the cache. Writes demo/data/inbox-ai.json
  requirements.txt    #   langgraph, langchain-openai, pydantic, python-dotenv
server/               # FastAPI auth, inbox persistence, ingestion, and AI workers
tests/                # policy, auth, parser, and API tests (no paid model calls)
requirements.txt      # complete API service dependency set
render.yaml           # Render API service + Postgres Blueprint
DEPLOYMENT.md          # exact live deployment and mailbox setup
public/               # served from the root: favicons, OG image, wordmark, photo, robots, sitemap
vite.config.js        # the five build inputs
DESIGN.md             # color, type, voice, motion
```

`site.js` is loaded by `/` and `/custom/`. `/demo/` and `/app/` load
`portal.js` instead. `/login/` loads `login.js`.

## Conventions

- **Tokens, not hex values.** Everything is a custom property in `:root` at the
  top of `src/site.css`: `--void`, `--panel`, `--line`, `--ink`, `--body`,
  `--muted`, `--signal`. `src/portal.css` adds one warm `--alert` hue, used only
  for churn risk and negative deltas, because a product needs a negative state
  the marketing pages never do.
- **Progressive enhancement is a hard rule.** Both scripts are optional. With JS
  off, every marketing page renders complete and static: the intro overlay
  never mounts, reveals stay visible, and stats show their final values. Keep it
  that way. The dashboards are the exception: `/demo/` and `/app/` build their
  views from data at runtime, so they need JS and say so in a `<noscript>`
  notice.
- **Motion lives in one place.** Each stylesheet ends with a motion layer gated
  on `prefers-reduced-motion: no-preference`, plus (on the marketing pages) an
  `html.js` class that JS only adds when it can actually run the reveals.
- **Accent budget.** Roughly one use of `--signal` per section, often zero. If
  you add color somewhere, remove it somewhere else. See DESIGN.md §2 and §3.

## The dashboard, and where its data comes from

One renderer, `src/portal.js`, draws both dashboards. It never reaches for a
file directly: it is handed a bundle of view models, and `data-portal` on the
`<body>` decides who assembles that bundle.

| `data-portal` | Route    | Bundle                                                          |
| ------------- | -------- | --------------------------------------------------------------- |
| `demo`        | `/demo/` | `demo/data/*.json`, frozen walkthrough, no API calls             |
| `account`     | `/app/`  | `accounts/<id>/*.json` raw records, run through `src/derive.js`   |

Both paths are lazy: `import.meta.glob` keeps each account's records out of the
demo's bundle and vice versa. There is no API and no database anywhere.

### Shared rules

- **Values, not coordinates.** The members chart holds twelve monthly counts
  plus a `min`/`max`; `portal.js` maps those to SVG geometry. Sparklines are
  plain arrays and auto-scale to their own range. Bar widths are `value / total`.
- **Adding a view** means adding an entry to `views` in the portal model (which
  builds the nav, the route, and the container) and a renderer in `portal.js`.
- **Emphasis in copy** is marked with `*asterisks*`, so no field ever has to
  carry HTML: `"Payment received: *$149* from Priya Shah"`.
- **Nodes, not HTML strings.** The renderer builds elements and sets
  `textContent`, so copy containing quotes or apostrophes cannot break markup.
- **Interactions.** View switching, search, and inbox sort are client-side
  only. On `/app/`, sending a reply flips in-memory state and resets on
  reload. On `/demo/`, drafts are read-only and send is disabled. The range
  buttons never re-filter the data.

### The demo: frozen sample JSON

Every number, row, and message in `/demo/` lives in `demo/data/*.json`, already
shaped the way the renderer wants it. Those files are loaded only on the demo
route as same-origin static assets — never OpenAI, never a backend, and never
run through `derive.js`. Smart Inbox drafts are the committed cache in
`demo/data/inbox-ai.json` from an offline `ai/run.py` pass. Drafts are
read-only, send is disabled, and KPI count-ups are skipped so nothing on the
page looks like a live sync.

Tailoring the demo means editing JSON, never markup. The gym, the members, and
every figure are invented; the page labels itself "Sample data" in the return
pill and is `noindex`.

### The client portal: authorized records, derived at runtime

`/app/` requests an authorized account bundle from the FastAPI service.
`accounts/test/` remains the seeded integration-shaped fixture behind that
service: snake_case keys, ISO timestamps, foreign keys, nulls, and cancelled
members. `src/derive.js` turns the authorized raw bundle into every KPI, chart
series, churn score, and attribution figure. The browser no longer imports
tenant files directly.

A few consequences worth knowing:

- **`visits.json` is the only input to risk.** Recency is a decaying curve
  rather than a threshold, so a member missing 100 days always outranks one
  missing 40. Frequency drop, tenure, and failed charges adjust from there. The
  bands are just cutoffs on that score.
- **Trailing windows, not calendar months.** Revenue compares the last 30 days
  against the previous 30, because a calendar month is a partial number for all
  but one day of it.
- **Everything is scored against `account.as_of`,** not the wall clock, so the
  dashboard reads the same in a year as it does today.
- **The counts agree across views by construction.** The flagged KPI on Overview
  and the churn table are the same list, filtered once.

To reshape the test gym, edit the constants at the top of `accounts/generate.py`
and re-run it. It is seeded, so the output is byte-identical between runs and
belongs in the commit alongside the script:

```bash
python accounts/generate.py
```

Outside the Smart Inbox, only behaviour that reads directly out of the data is
implemented. The churn table reports risk scores and signals without
prescribing what to do about them, and Growth attributes members to posts
without recommending the next one. Those stay unbuilt on purpose.

## Authentication

`/login/` posts credentials to `POST /api/v1/session`. The server compares them
against environment-held secrets and issues a signed, expiring token. Every
account and inbox endpoint verifies that token before returning data. The
browser never receives the password, signing secret, mailbox credential,
webhook secret, or OpenAI key.

The service is intentionally single-tenant today. Supporting multiple gyms
requires an account table with per-account password hashes and ownership rules,
not additional credentials embedded in frontend code.

## The Smart Inbox agent

The inbox is the one view with a model behind it. It sorts each message into a
category and a priority, then drafts a reply the owner can edit and send.

The demo remains frozen: `ai/run.py` writes `demo/data/inbox-ai.json` and the
browser reads that committed sample cache. The signed-in portal is live. With
no mailbox credentials, the production API ingests `accounts/test/messages.json`
and runs its actionable messages through OpenAI once. Postgres deduplication
keeps unchanged messages from being billed again after a restart. When complete
IMAP credentials are added, `SOLVD_EMAIL_SOURCE=auto` switches to mailbox
polling; authenticated webhook ingestion remains available in either setup.
The portal polls draft status every ten seconds. The browser talks only to the
SOLVD API, never directly to OpenAI.

```bash
python -m venv ai/.venv
ai/.venv/Scripts/python -m pip install -r ai/requirements.txt   # Windows
python ai/run.py
```

The live service and offline runner need `OPENAI_API_KEY`. Copy `.env.example`
to start. Both model passes run on
`gpt-5.6-luna` through OpenAI's **Responses API** (`use_responses_api=True` in
`ai/model.py`), not Chat Completions. Override either model with
`SOLVD_SORT_MODEL` or `SOLVD_DRAFT_MODEL`, for instance to sort on something
cheaper than you draft on.

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

The live agent builds gym facts and policy from the authorized account fixture;
`ai/prompts.py` supplies the reusable prompt templates and offline-runner
defaults. Anything outside the allowed policy is escalated instead of invented,
which is what `needs_human` is for.

### When the live service calls OpenAI

Every email is keyed by provider Message-ID and fingerprinted from the content
that affects the reply. Duplicate deliveries and unchanged messages reuse the
stored result. Before any model call, `server/email_policy.py` rejects read or
non-inbox mail, spam/trash/sent/draft labels, automated senders, auto-responses,
mailing lists, messages from the gym, empty bodies, and acknowledgement-only
replies. Ambiguous human mail is processed because missing a member request is
worse than drafting one extra response. An owner can explicitly request a
draft for anything the prefilter skipped or retry a failed call.

The offline demo runner retains its prompt-and-model fingerprint cache:

```bash
python ai/run.py --list    # report what is cached and what is stale, call nothing
python ai/run.py --only kayla-freeze
python ai/run.py --force   # ignore the cache
```

Every thread in `inbox.json` therefore needs a stable `id`: it is the cache
key, and `run.py` refuses to start without one. `portal.js` keys open and
replied state off the same id, since sorting makes array position meaningless.

### What the inbox shows

Category and priority appear on each row, and the sort control offers priority,
newest, or category. Open a message and you also get the sort rationale, the
drafted reply pre-filled and editable, the one system change sending it would
commit to, and a "Read this one first" flag when `needs_human` is set. A thread
with no cached entry still renders: it sorts as low priority and gets an empty
composer.

In `/app/`, queued messages show a drafting state, ready results fill the
composer and suggested action, and skipped or failed messages expose an
explicit **Draft with AI** control.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Render, Postgres, CORS, mailbox, webhook,
and static-site configuration.

## Before launch

- The form `action` in `index.html` is still `https://formspree.io/f/REPLACE_ME`.
  Point it at a real endpoint.
- Confirm the LinkedIn URL in the footer of `/` and `/custom/`.
- `public/sitemap.xml` lists `/` and `/custom/` only. `/demo/` is excluded on
  purpose, since it is sample data.
- Replace the single-tenant environment login with a real account store before
  onboarding multiple gyms.

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
