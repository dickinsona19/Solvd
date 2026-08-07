/* The Gym Portal demo.

   Every number, row and message on the page comes from demo/data/*.json.
   This module's only jobs are turning that data into DOM and wiring the
   interactions, so tailoring the demo means editing JSON, not markup.

   Scope note: only behaviour that follows directly from the data lives
   here. The Smart Inbox is the one view with an AI layer behind it, and even
   that reads a file: ai/run.py does the thinking offline and writes
   demo/data/inbox-ai.json, so this module never calls a model. The churn and
   growth views still prescribe nothing. */

import portal from '../demo/data/portal.json'
import overviewData from '../demo/data/overview.json'
import growthData from '../demo/data/growth.json'
import churnData from '../demo/data/churn.json'
import inboxData from '../demo/data/inbox.json'
import inboxAi from '../demo/data/inbox-ai.json'
import membersData from '../demo/data/members.json'
import integrationsData from '../demo/data/integrations.json'

const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const SVG_NS = 'http://www.w3.org/2000/svg'

/* ---------- DOM helpers ----------
   Nodes are built rather than assembled from HTML strings, so copy with
   quotes and apostrophes in it can never break the markup. */

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue
    node.append(child)
  }
}

function h(tag, props, ...children) {
  const node = document.createElement(tag)
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined) continue
    if (key === 'class') node.className = value
    else if (key === 'text') node.textContent = value
    else node.setAttribute(key, value)
  }
  append(node, children)
  return node
}

function svgEl(tag, props, ...children) {
  const node = document.createElementNS(SVG_NS, tag)
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined) continue
    if (key === 'text') node.textContent = value
    else node.setAttribute(key, value)
  }
  append(node, children)
  return node
}

function icon(name, extra) {
  return svgEl(
    'svg',
    { class: extra ? `icon ${extra}` : 'icon', 'aria-hidden': 'true' },
    svgEl('use', { href: `#i-${name}` }),
  )
}

// Emphasis in data is marked with *asterisks*, so the JSON never has to
// carry HTML: "Payment received: *$149* from Priya Shah".
function richText(value) {
  const fragment = document.createDocumentFragment()
  String(value)
    .split('*')
    .forEach((part, index) => {
      if (!part) return
      fragment.append(index % 2 ? h('strong', { text: part }) : part)
    })
  return fragment
}

function pill(spec) {
  if (!spec) return null
  const { label, tone } = typeof spec === 'string' ? { label: spec } : spec
  return h('span', { class: tone ? `pill pill-${tone}` : 'pill', text: label })
}

function panel({ title, caption, aside } = {}, ...body) {
  const head =
    title || caption || aside
      ? h(
          'div',
          { class: 'panel-head' },
          h(
            'div',
            null,
            title ? h('h2', { text: title }) : null,
            caption ? h('p', { text: caption }) : null,
          ),
          typeof aside === 'string' ? pill(aside) : aside,
        )
      : null

  return h('div', { class: 'panel' }, head, ...body)
}

const format = (value, prefix = '') =>
  prefix + Number(value).toLocaleString('en-US')

/* ---------- data-driven pieces ---------- */

function kpiRow(kpis) {
  return h(
    'div',
    { class: 'kpi-row' },
    kpis.map((kpi) =>
      h(
        'div',
        { class: 'kpi' },
        h('p', { class: 'label-mono', text: kpi.label }),
        h('p', {
          class: 'kpi-val',
          'data-count': kpi.value,
          'data-prefix': kpi.prefix,
          text: format(kpi.value, kpi.prefix),
        }),
        h(
          'div',
          { class: 'kpi-foot' },
          kpi.delta
            ? h('span', {
                class: kpi.deltaTone === 'alert' ? 'delta is-alert' : 'delta',
                text: kpi.delta,
              })
            : null,
          kpi.spark ? sparkline(kpi.spark, kpi.deltaTone === 'alert') : null,
        ),
      ),
    ),
  )
}

// Each sparkline scales to its own range, so the data is plain values.
function sparkline(values, isAlert) {
  const low = Math.min(...values)
  const span = Math.max(...values) - low || 1
  const step = values.length > 1 ? 100 / (values.length - 1) : 0
  const points = values
    .map((value, i) => `${(i * step).toFixed(1)},${(26 - ((value - low) / span) * 22).toFixed(1)}`)
    .join(' ')

  return svgEl(
    'svg',
    {
      class: isAlert ? 'spark is-alert' : 'spark',
      viewBox: '0 0 100 30',
      preserveAspectRatio: 'none',
      'aria-hidden': 'true',
    },
    svgEl('polyline', { 'vector-effect': 'non-scaling-stroke', points }),
  )
}

// Monthly values in, plotted line out. The JSON holds member counts, not
// SVG coordinates.
function chartPanel(chart) {
  const { min, max, months, series, prior } = chart
  const [left, right, top, bottom] = [40, 700, 30, 190]
  const step = months.length > 1 ? (right - left) / (months.length - 1) : 0
  const x = (i) => left + i * step
  const y = (value) => bottom - ((value - min) / (max - min)) * (bottom - top)
  const points = (values) =>
    values.map((value, i) => `${x(i).toFixed(1)},${y(value).toFixed(1)}`).join(' ')
  const gridValues = [max, Math.round((min + max) / 2), min]

  const figure = svgEl(
    'svg',
    {
      class: 'chart',
      viewBox: '0 0 740 224',
      role: 'img',
      'aria-label': chart.summary,
    },
    svgEl(
      'defs',
      null,
      svgEl(
        'linearGradient',
        { id: 'chart-fade', x1: '0', y1: '0', x2: '0', y2: '1' },
        svgEl('stop', { class: 'fade-top', offset: '0' }),
        svgEl('stop', { class: 'fade-bottom', offset: '1' }),
      ),
    ),
    gridValues.map((value) =>
      svgEl('line', { class: 'grid-line', x1: left, y1: y(value), x2: 716, y2: y(value) }),
    ),
    gridValues.map((value) =>
      svgEl('text', {
        class: 'axis',
        x: 32,
        y: y(value) + 4,
        'text-anchor': 'end',
        text: value,
      }),
    ),
    svgEl('path', {
      class: 'area',
      d: `M${points(series)} L${right},${bottom} L${left},${bottom} Z`,
    }),
    prior ? svgEl('polyline', { class: 'series-prior', points: points(prior) }) : null,
    svgEl('polyline', { class: 'series', points: points(series) }),
    svgEl('circle', {
      class: 'terminal',
      cx: x(series.length - 1),
      cy: y(series[series.length - 1]),
      r: 3.5,
    }),
    months.map((month, i) =>
      svgEl('text', { class: 'axis', x: x(i), y: 212, 'text-anchor': 'middle', text: month }),
    ),
  )

  const legend = h(
    'div',
    { class: 'legend' },
    h('span', null, h('i', null), chart.legend.series),
    chart.legend.prior ? h('span', null, h('i', { class: 'prior' }), chart.legend.prior) : null,
  )

  return panel(
    { title: chart.title, caption: chart.caption, aside: pill({ label: chart.badge, tone: 'signal' }) },
    h('div', { class: 'panel-body' }, figure),
    legend,
  )
}

function meter({ value, tone }) {
  return h(
    'span',
    { class: 'meter' },
    h(
      'span',
      { class: 'meter-track' },
      h('span', {
        class: tone === 'alert' ? 'meter-fill is-high' : 'meter-fill',
        style: `width: ${value}%`,
      }),
    ),
    h('span', { class: 'meter-val', text: value }),
  )
}

function cell(column, value) {
  switch (column.type) {
    case 'name': {
      const { name, sub } = typeof value === 'string' ? { name: value } : value
      return h('td', { class: 'name' }, name, sub ? h('span', { class: 'sub', text: sub }) : null)
    }
    case 'num': {
      const { value: text, highlight } =
        value !== null && typeof value === 'object' ? value : { value }
      return h('td', { class: highlight ? 'num lead-metric' : 'num', text })
    }
    case 'meter':
      return h('td', null, meter(value))
    case 'pill':
      return h('td', null, pill(value))
    default:
      return h('td', { text: value })
  }
}

function table({ columns, rows }) {
  return h(
    'div',
    { class: 'table-wrap' },
    h(
      'table',
      { class: 'data-table' },
      h(
        'thead',
        null,
        h(
          'tr',
          null,
          columns.map((column) =>
            h('th', {
              scope: 'col',
              class: column.type === 'num' ? 'num' : null,
              text: column.label,
            }),
          ),
        ),
      ),
      h(
        'tbody',
        null,
        rows.map((row) => h('tr', null, columns.map((column) => cell(column, row[column.key])))),
      ),
    ),
  )
}

function barList({ total, items }) {
  return h(
    'div',
    { class: 'panel-body bars' },
    items.map((item) =>
      h(
        'div',
        { class: 'bar-row' },
        h('span', { text: item.label }),
        h(
          'span',
          { class: 'bar-track' },
          h('span', { class: 'bar-fill', style: `width: ${((item.value / total) * 100).toFixed(1)}%` }),
        ),
        h('span', { class: 'num', text: item.value }),
      ),
    ),
  )
}

/* ---------- views ---------- */

function renderOverview(root) {
  root.append(
    kpiRow(overviewData.kpis),
    h(
      'div',
      { class: 'split' },
      chartPanel(overviewData.chart),
      h(
        'div',
        { class: 'col' },
        panel(
          {
            title: overviewData.attention.title,
            aside: pill(String(overviewData.attention.items.length)),
          },
          h(
            'div',
            { class: 'list' },
            overviewData.attention.items.map((item) =>
              h(
                'a',
                { href: `#${item.view}` },
                icon(item.icon, item.tone ? `is-${item.tone}` : null),
                h('span', { class: 'grow' }, h('strong', { text: item.title }), item.detail),
                icon('arrow'),
              ),
            ),
          ),
        ),
        panel(
          { title: overviewData.activity.title, caption: overviewData.activity.caption },
          h(
            'div',
            { class: 'list feed' },
            overviewData.activity.items.map((item) =>
              h(
                'div',
                null,
                h('span', { class: 'grow' }, richText(item.text)),
                h('span', { class: 'when', text: item.when }),
              ),
            ),
          ),
        ),
      ),
    ),
  )
}

function renderGrowth(root) {
  root.append(
    kpiRow(growthData.kpis),
    panel(
      {
        title: growthData.table.title,
        caption: growthData.table.caption,
        aside: pill(growthData.table.badge),
      },
      table(growthData.table),
    ),
    panel(
      { title: growthData.bars.title, caption: growthData.bars.caption },
      barList(growthData.bars),
    ),
  )
}

function renderChurn(root) {
  const spec = churnData.table
  root.append(
    churnData.note ? h('p', { class: 'view-note', text: churnData.note }) : null,
    kpiRow(churnData.kpis),
    panel(
      { title: spec.title, caption: spec.caption, aside: pill(spec.badge) },
      table(spec),
      spec.foot
        ? h('div', { class: 'panel-foot' }, h('p', { class: 'label-mono', text: spec.foot }))
        : null,
    ),
  )
}

function renderMembers(root) {
  const spec = membersData.table
  root.append(
    panel(
      {
        title: spec.title,
        caption: spec.caption,
        aside: pill(`Showing ${spec.rows.length}`),
      },
      table(spec),
    ),
  )
}

function renderIntegrations(root) {
  root.append(
    integrationsData.note ? h('p', { class: 'view-note', text: integrationsData.note }) : null,
    panel(
      {
        title: integrationsData.title,
        caption: `${integrationsData.items.filter((item) => item.live).length} connected`,
      },
      integrationsData.items.map((item) =>
        h(
          'div',
          { class: 'integration' },
          item.live ? h('span', { class: 'pulse' }) : null,
          h('span', { class: 'what' }, h('strong', { text: item.name }), h('p', { text: item.detail })),
          pill(item.status),
          item.action
            ? h('button', { class: 'btn btn-ghost btn-sm', type: 'button', text: item.action })
            : null,
        ),
      ),
    ),
  )
}

/* ---------- inbox: sorting, messages, and the drafted reply ----------
   The agent in ai/ has already read every message and written what it made
   of it to demo/data/inbox-ai.json, keyed by thread id. Nothing here calls a
   model, so refreshing costs nothing. A thread with no cached entry still
   renders: it just gets an empty composer and sorts as low priority. */

const AI = inboxAi.results || {}
const RANK = { high: 0, medium: 1, low: 2 }

const aiFor = (thread) => AI[thread.id]
const rankOf = (thread) => RANK[aiFor(thread)?.sort.priority] ?? RANK.low

function categoryOf(thread) {
  const key = aiFor(thread)?.sort.category
  return key ? inboxData.ui.categories[key] || key : ''
}

// Each comparator falls through to age, so the order is total and the list
// cannot reshuffle between two renders of the same sort.
const SORTS = {
  priority: (a, b) => rankOf(a) - rankOf(b) || a.ageMinutes - b.ageMinutes,
  newest: (a, b) => a.ageMinutes - b.ageMinutes,
  category: (a, b) =>
    categoryOf(a).localeCompare(categoryOf(b)) ||
    rankOf(a) - rankOf(b) ||
    a.ageMinutes - b.ageMinutes,
}

let listHost = null
let detailHost = null
let openThread = ''
let sortMode = (inboxData.ui.sorts.find((s) => s.active) || inboxData.ui.sorts[0]).id
const replied = new Set()

function renderInbox(root) {
  listHost = h('div', { class: 'thread-list', 'aria-label': 'Member messages' })
  detailHost = h('div', { class: 'thread-detail' })

  const sorts = h(
    'div',
    {
      class: 'range',
      id: 'thread-sort',
      role: 'group',
      'aria-label': inboxData.ui.sortLabel,
    },
    inboxData.ui.sorts.map((option) =>
      h('button', {
        type: 'button',
        'data-sort': option.id,
        'aria-pressed': String(option.id === sortMode),
        text: option.label,
      }),
    ),
  )

  root.append(
    panel(
      {
        title: inboxData.title,
        caption: inboxData.caption,
        aside: h('div', { class: 'panel-tools' }, sorts, pill(inboxData.badge)),
      },
      h('div', { class: 'inbox' }, listHost, detailHost),
    ),
  )

  renderThreadList()
  renderThreadDetail()
}

function priorityTag(priority) {
  return h(
    'span',
    { class: `prio is-${priority}` },
    h('i', { 'aria-hidden': 'true' }),
    inboxData.ui.priorities[priority] || priority,
  )
}

function renderThreadList() {
  const threads = [...inboxData.threads].sort(SORTS[sortMode] || SORTS.newest)
  if (!threads.some((thread) => thread.id === openThread)) {
    openThread = threads[0]?.id || ''
  }

  listHost.replaceChildren(
    ...threads.map((thread) => {
      const on = thread.id === openThread
      const sorted = aiFor(thread)?.sort

      return h(
        'button',
        {
          class: on ? 'thread is-on' : 'thread',
          type: 'button',
          'data-thread': thread.id,
          'aria-current': on ? 'true' : null,
        },
        h(
          'span',
          { class: 'thread-top' },
          h('span', { class: 'thread-who', text: thread.name }),
          h('span', { class: 'thread-when', text: thread.when }),
        ),
        h('span', { class: 'thread-subject', text: thread.subject }),
        h(
          'span',
          { class: 'thread-tags' },
          replied.has(thread.id)
            ? pill({ label: inboxData.ui.replied, tone: 'signal' })
            : pill(categoryOf(thread) || thread.status),
          sorted ? priorityTag(sorted.priority) : null,
        ),
      )
    }),
  )
}

// Why the message landed where it did in the list. The owner gets to
// disagree with the sort, which means they have to be able to see it.
function sortNote(sorted) {
  return h(
    'div',
    { class: sorted.needs_human ? 'sort-note is-flagged' : 'sort-note' },
    icon(sorted.needs_human ? 'alert' : 'check'),
    h(
      'span',
      null,
      h('strong', { text: sorted.summary }),
      h('span', { text: sorted.reasoning }),
    ),
  )
}

function composer(thread, entry, ui) {
  const draft = entry?.draft

  return h(
    'div',
    { class: draft ? 'reply has-draft' : 'reply' },
    draft
      ? h(
          'div',
          { class: 'draft-head' },
          h('p', { class: 'label-mono', text: ui.draftLabel }),
          h(
            'span',
            { class: 'draft-meta' },
            entry.sort.needs_human ? pill({ label: ui.needsHuman, tone: 'alert' }) : null,
            h('span', {
              class: 'draft-conf',
              text: `${draft.confidence} ${ui.confidenceLabel}`,
            }),
          ),
        )
      : h('label', { class: 'label-mono', for: 'reply-body', text: ui.replyLabel }),
    h('textarea', {
      id: 'reply-body',
      rows: draft ? '7' : '4',
      placeholder: ui.replyPlaceholder,
      'aria-label': draft ? ui.draftLabel : ui.replyLabel,
      text: draft ? draft.reply : null,
    }),
    draft
      ? h(
          'p',
          { class: 'draft-action' },
          h('span', { class: 'label-mono', text: ui.actionLabel }),
          h('strong', { text: draft.action }),
        )
      : null,
    h(
      'div',
      { class: 'reply-foot' },
      h('button', {
        class: 'btn btn-signal btn-sm',
        type: 'button',
        'data-send': '',
        text: draft ? ui.approve : ui.send,
      }),
      draft ? h('p', { class: 'draft-note', text: ui.draftNote }) : null,
    ),
  )
}

function renderThreadDetail() {
  if (!detailHost) return

  const thread = inboxData.threads.find((item) => item.id === openThread)
  if (!thread) return

  const ui = inboxData.ui
  const entry = aiFor(thread)

  detailHost.replaceChildren(
    h(
      'div',
      { class: 'member-card' },
      h('span', { class: 'avatar', text: thread.initials }),
      h(
        'span',
        { class: 'who' },
        h('h3', { text: thread.name }),
        h('span', { class: 'meta', text: thread.meta }),
      ),
      pill(thread.risk),
    ),
    h(
      'div',
      { class: 'message' },
      h(
        'div',
        { class: 'message-head' },
        h('strong', { text: thread.subject }),
        h('span', { class: 'thread-when', text: thread.receivedAt }),
      ),
      h('p', { text: thread.message }),
    ),
    entry ? sortNote(entry.sort) : null,
    replied.has(thread.id)
      ? h(
          'div',
          { class: 'reply' },
          h(
            'p',
            { class: 'sent-note' },
            icon('check'),
            ui.sent.replace('{name}', thread.name.split(' ')[0]),
          ),
        )
      : composer(thread, entry, ui),
  )
}

/* ---------- shell ---------- */

function renderShell() {
  document.getElementById('product-label').textContent = portal.product
  document.getElementById('gym-mark').textContent = portal.initials
  document.getElementById('gym-name').prepend(portal.name)
  document.getElementById('gym-members').textContent = portal.members
  document.getElementById('user-initials').textContent = portal.user.initials
  document.getElementById('user-name').textContent = portal.user.name
  document.getElementById('user-role').textContent = portal.user.role
  document.getElementById('sync-label').textContent = portal.sync
  document.getElementById('portal-search').placeholder = portal.searchPlaceholder

  const nav = document.getElementById('rail-nav')
  nav.append(h('p', { class: 'label-mono', text: portal.navLabel }))
  for (const view of portal.views) {
    nav.append(
      h(
        'a',
        { class: 'nav-item', href: `#${view.id}`, 'data-view': view.id },
        icon(view.icon),
        view.label,
        view.badge
          ? h('span', {
              class: view.badge.tone === 'alert' ? 'nav-count is-alert' : 'nav-count',
              text: view.badge.value,
            })
          : null,
      ),
    )
  }

  const range = document.getElementById('range')
  for (const item of portal.ranges) {
    range.append(
      h('button', {
        type: 'button',
        'aria-pressed': String(Boolean(item.active)),
        text: item.label,
      }),
    )
  }

  const host = document.getElementById('views')
  for (const view of portal.views) {
    host.append(
      h(
        'section',
        { class: 'view', 'data-view': view.id, 'aria-label': view.title },
        h('div', { class: 'view-inner' }),
      ),
    )
  }
}

/* ---------- routing ---------- */

const RENDERERS = {
  overview: renderOverview,
  growth: renderGrowth,
  churn: renderChurn,
  inbox: renderInbox,
  members: renderMembers,
  integrations: renderIntegrations,
}

const VIEWS = new Map(portal.views.map((view) => [view.id, view]))
const DEFAULT_VIEW = portal.views[0].id
const built = new Set()

let currentView = ''

// Re-running the entrance animation needs a forced reflow between
// removing and re-adding the class.
function restartAnimation(el) {
  el.classList.remove('is-in')
  void el.offsetWidth
  el.classList.add('is-in')
}

function activate(name) {
  const next = VIEWS.has(name) ? name : DEFAULT_VIEW
  if (next === currentView) return
  currentView = next

  for (const section of document.querySelectorAll('.view')) {
    const on = section.dataset.view === next
    section.hidden = !on
    if (!on) continue

    if (!built.has(next)) {
      built.add(next)
      RENDERERS[next](section.firstElementChild)
    }
    if (!reduce) restartAnimation(section)
    countUp(section)
  }

  for (const item of document.querySelectorAll('.nav-item')) {
    const on = item.dataset.view === next
    item.classList.toggle('is-on', on)
    if (on) item.setAttribute('aria-current', 'page')
    else item.removeAttribute('aria-current')
  }

  const view = VIEWS.get(next)
  document.getElementById('view-title').textContent = view.title
  document.getElementById('view-eyebrow').textContent = view.eyebrow
  document.getElementById('views').scrollTop = 0

  const search = document.getElementById('portal-search')
  if (search.value) {
    search.value = ''
    filter('')
  }
}

// Views answer to the hash, so the rail links, the in-page shortcuts and
// the back button all route through one path.
window.addEventListener('hashchange', () => activate(window.location.hash.slice(1)))

/* ---------- count-ups ---------- */

const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4)

function countUp(root) {
  if (reduce) return

  for (const el of root.querySelectorAll('[data-count]')) {
    if (el.dataset.counted) continue
    el.dataset.counted = '1'

    const end = Number(el.dataset.count)
    const prefix = el.dataset.prefix || ''
    const duration = 900
    const start = performance.now()

    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration)
      el.textContent = format(Math.round(end * easeOutQuart(progress)), prefix)
      if (progress < 1) requestAnimationFrame(tick)
    }

    requestAnimationFrame(tick)
  }
}

/* ---------- search ---------- */

// Filters whatever the active view lists: table rows or messages.
function filter(query) {
  const view = document.querySelector(`.view[data-view="${currentView}"]`)
  if (!view) return

  for (const row of view.querySelectorAll('.data-table tbody tr, .thread')) {
    row.hidden = !row.textContent.toLowerCase().includes(query)
  }
}

/* ---------- interactions ---------- */

function wireInteractions() {
  document.getElementById('portal-search').addEventListener('input', (event) => {
    filter(event.target.value.trim().toLowerCase())
  })

  document.getElementById('range').addEventListener('click', (event) => {
    const button = event.target.closest('button')
    if (!button) return
    for (const other of document.querySelectorAll('#range button')) {
      other.setAttribute('aria-pressed', String(other === button))
    }
  })

  // Delegated, because views are rendered on first visit and the thread
  // list is rebuilt every time the sort changes.
  document.getElementById('views').addEventListener('click', (event) => {
    const thread = event.target.closest('.thread')
    if (thread) {
      openThread = thread.dataset.thread
      renderThreadList()
      renderThreadDetail()
      return
    }

    const sortButton = event.target.closest('[data-sort]')
    if (sortButton) {
      sortMode = sortButton.dataset.sort
      for (const other of document.querySelectorAll('#thread-sort button')) {
        other.setAttribute('aria-pressed', String(other === sortButton))
      }
      renderThreadList()
      return
    }

    if (event.target.closest('[data-send]')) {
      replied.add(openThread)
      renderThreadList()
      renderThreadDetail()
    }
  })
}

/* ---------- boot ---------- */

renderShell()
wireInteractions()
activate(window.location.hash.slice(1))
