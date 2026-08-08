/* Raw records in, dashboard view models out.

   accounts/<id>/*.json is deliberately source shaped: member rows, a
   check-in log, Stripe charges, post insights, mailbox messages. None of it
   knows what a KPI is. This module is the part that would survive being
   pointed at a real Mindbody and a real Stripe, because it only ever reads
   fields an integration would actually give you.

   Nothing here invents a number it cannot compute. Where the demo's authored
   JSON claims something no raw feed could support ("saved 14 members last
   quarter", which needs a record of interventions nobody is keeping), this
   produces a different figure that the data does support.

   Everything is measured against account.as_of rather than the clock, so a
   committed fixture does not rot into a gym where nobody has trained in
   months. */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAY = 86400000

/* ---------- time, in the gym's timezone rather than the viewer's ---------- */

function clockFor(timeZone) {
  const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone })
  const timeFormat = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })

  // "2026-08-07", so date arithmetic happens on the gym's calendar days and
  // survives daylight saving without a hardcoded offset.
  const dayKey = (iso) => dayFormat.format(new Date(iso))
  const dayNumber = (iso) => Date.parse(`${dayKey(iso)}T00:00:00Z`) / DAY

  return {
    dayKey,
    dayNumber,
    // "6:12a", the way a person writes a time.
    time: (iso) =>
      timeFormat.format(new Date(iso)).replace(/\s?AM$/, 'a').replace(/\s?PM$/, 'p'),
    month: (iso) => {
      const [year, month] = dayKey(iso).split('-')
      return `${MONTHS[Number(month) - 1]} ${year}`
    },
  }
}

const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value))
const money = (cents) => Math.round(cents / 100)
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

function ago(days) {
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return `${days} days ago`
}

/* ---------- per-member behaviour, read out of the check-in log ---------- */

const bandOf = (risk) =>
  risk >= 75 ? 'high' : risk >= 50 ? 'medium' : risk >= 35 ? 'watch' : 'ok'

// Cancellation is a decision members make weeks after they stop showing up,
// so attendance is the only early warning the data actually contains.
//
// Taking the reference day as an argument rather than closing over "now" is
// what lets the overview plot how this number moved. A trend line under a KPI
// has to be the same measurement at an earlier date, not a proxy for it.
function scoreAt(history, refDay) {
  const { visitDays, joinedDay, failureDays } = history

  const last30 = visitDays.filter((day) => refDay - day >= 0 && refDay - day < 30).length
  const prior30 = visitDays.filter((day) => refDay - day >= 30 && refDay - day < 60).length
  const past = visitDays.filter((day) => day <= refDay)
  const lastVisitDays = past.length ? refDay - past[past.length - 1] : null
  const tenureDays = refDay - joinedDay

  // Consecutive weeks with at least one check-in, counting back. A long run
  // that has just ended is the loudest signal in the file.
  const weeks = new Set(past.map((day) => Math.floor((refDay - day) / 7)))
  let brokenStreak = 0
  if (!weeks.has(0)) {
    let probe = 1
    while (weeks.has(probe)) {
      brokenStreak += 1
      probe += 1
    }
  }

  // Someone who has not been in for months has an empty prior window too, so
  // a linear recency ramp that saturates at three weeks left the score
  // depending on the drop signal, and the drop signal gets *weaker* the longer
  // they have been gone. The result ranked a member missing 107 days below one
  // missing 36. This curve rises quickly and then keeps creeping, so absence
  // always ranks monotonically, and two empty windows means stopped rather
  // than halved.
  const drop = prior30 > 0 ? clamp((prior30 - last30) / prior30) : last30 === 0 ? 1 : 0
  const recency = lastVisitDays === null ? 1 : 1 - Math.exp(-lastVisitDays / 40)
  const failed = failureDays.find((day) => refDay - day >= 0 && refDay - day <= 45)

  // Both secondary signals are gated on the member having actually gone quiet.
  // A drop from thirty visits to twenty-two is training less, not leaving, and
  // being new is only a risk if you are also not turning up. Without these
  // gates the score flags the most committed members in the gym, which is
  // worse than flagging nobody.
  const quiet = clamp((8 - last30) / 8)
  const risk = Math.round(
    100 *
      clamp(
        recency * 0.9 +
          drop * quiet * 0.2 +
          (tenureDays < 90 && last30 < 6 ? 0.12 : 0) +
          (failed === undefined ? 0 : 0.15),
      ),
  )

  return { risk, band: bandOf(risk), last30, prior30, lastVisitDays, tenureDays, drop, brokenStreak, failedDay: failed }
}

function profileMembers(account, members, visits, charges, clock) {
  const asOfDay = clock.dayNumber(account.as_of)
  const plans = new Map(account.plans.map((plan) => [plan.id, plan]))

  const byMember = new Map(members.map((member) => [member.id, []]))
  for (const visit of visits) {
    byMember.get(visit.member_id)?.push(clock.dayNumber(visit.checked_in_at))
  }

  const failuresFor = new Map(members.map((member) => [member.id, []]))
  for (const charge of charges) {
    if (charge.status === 'failed') {
      failuresFor.get(charge.member_id)?.push(clock.dayNumber(charge.created_at))
    }
  }

  return members.map((member) => {
    const history = {
      visitDays: (byMember.get(member.id) || []).sort((a, b) => a - b),
      joinedDay: clock.dayNumber(member.joined_at),
      cancelledDay: member.cancelled_at ? clock.dayNumber(member.cancelled_at) : null,
      failureDays: (failuresFor.get(member.id) || []).sort((a, b) => a - b),
    }

    const now = scoreAt(history, asOfDay)
    const active = member.status === 'active'

    return {
      ...member,
      plan: plans.get(member.plan_id),
      name: `${member.first_name} ${member.last_name}`,
      initials: member.first_name[0] + member.last_name[0],
      history,
      last30: now.last30,
      prior30: now.prior30,
      lastVisitDays: now.lastVisitDays,
      tenureDays: now.tenureDays,
      brokenStreak: now.brokenStreak,
      risk: active ? now.risk : 0,
      band: active ? now.band : 'ok',
      signal: describeSignal(now, clock, asOfDay),
    }
  })
}

// Was this member on the roster, and flagged, on a given day? Used only for
// the trend line, so it answers both questions at once.
function flaggedOn(member, day) {
  if (member.history.joinedDay > day) return false
  if (member.history.cancelledDay !== null && member.history.cancelledDay <= day) return false
  const band = scoreAt(member.history, day).band
  return band === 'high' || band === 'medium'
}

// The dominant reason for the score, in the words an owner would use. Absence
// leads, because a declined card for someone who stopped coming two months ago
// is a symptom of the leaving, not the cause of it.
function describeSignal(
  { last30, prior30, lastVisitDays, drop, brokenStreak, failedDay },
  clock,
  asOfDay,
) {
  if (last30 === 0) {
    return lastVisitDays === null ? 'Never checked in' : `No visits in ${lastVisitDays} days`
  }
  if (failedDay !== undefined) {
    return `Card declined ${ago(asOfDay - failedDay).toLowerCase()}`
  }
  if (brokenStreak >= 4) return `${brokenStreak}-week streak broken`
  if (drop >= 0.3) return `Visits down ${Math.round(drop * 100)}%`
  if (last30 <= 2) return `Only ${plural(last30, 'visit')} in 30 days`
  if (prior30 && last30 < prior30) return `Down from ${prior30} to ${last30} visits`
  return 'Attendance steady'
}

/* ---------- month buckets, for the chart and the sparklines ---------- */

function monthWindows(account, clock, count) {
  const [year, month] = clock.dayKey(account.as_of).split('-').map(Number)
  const windows = []

  for (let back = count - 1; back >= 0; back -= 1) {
    const date = new Date(Date.UTC(year, month - 1 - back, 1))
    const endExclusive = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1))
    windows.push({
      label: MONTHS[date.getUTCMonth()],
      startDay: date.getTime() / DAY,
      endDay: endExclusive.getTime() / DAY,
    })
  }

  return windows
}

// Active on a given day means joined by then and not yet cancelled. Counting
// it this way means the chart is a fact about the roster rather than a
// snapshot someone typed in.
function activeOn(members, day, clock) {
  let count = 0
  for (const member of members) {
    if (clock.dayNumber(member.joined_at) > day) continue
    if (member.cancelled_at && clock.dayNumber(member.cancelled_at) <= day) continue
    count += 1
  }
  return count
}

/* ---------- views ---------- */

function deriveOverview(ctx) {
  const { members, charges, messages, account, clock, asOfDay } = ctx

  const active = members.filter((member) => member.status === 'active')
  // High and medium only, so this agrees with the count Churn Radar puts in
  // its badge. The watchlist is a separate, quieter tier.
  const flagged = active.filter(
    (member) => member.band === 'high' || member.band === 'medium',
  )
  const highRisk = active
    .filter((member) => member.band === 'high')
    .sort((a, b) => b.risk - a.risk)
  const newMembers = active.filter((member) => member.tenureDays <= 30)
  const fromInstagram = newMembers.filter(
    (member) => member.acquisition.channel === 'instagram',
  ).length

  const months = monthWindows(account, clock, 8)
  const memberSpark = months.map((window) => activeOn(members, window.endDay - 1, clock))

  // Trailing 30 day windows rather than calendar months. Members bill on
  // their signup anniversary, so the current calendar month is always part
  // way through collecting and reporting it would show a third of the real
  // figure and a catastrophic decline every time the month turned over.
  const revenueWindow = (offsetDays) => {
    let cents = 0
    for (const charge of charges) {
      if (charge.status !== 'succeeded') continue
      const age = asOfDay - clock.dayNumber(charge.created_at)
      if (age >= offsetDays && age < offsetDays + 30) cents += charge.amount_cents
    }
    return money(cents)
  }

  const revenueTrail = [7, 6, 5, 4, 3, 2, 1, 0].map((back) => revenueWindow(back * 30))

  const joinsByMonth = months.map(
    (window) =>
      members.filter((member) => {
        const day = clock.dayNumber(member.joined_at)
        return day >= window.startDay && day < window.endDay
      }).length,
  )

  // The same flagged count, scored 60 and 30 days ago. Three points rather
  // than eight because the score compares two consecutive 30 day windows, so
  // the earliest point already needs 120 days of check-in log and there is no
  // honest way to reach further back than the log goes.
  const riskTrail = [60, 30, 0].map(
    (back) => members.filter((member) => flaggedOn(member, asOfDay - back)).length,
  )

  const revenue = revenueTrail[revenueTrail.length - 1]
  const priorRevenue = revenueTrail[revenueTrail.length - 2] || revenue
  const revenueDelta = priorRevenue
    ? (((revenue - priorRevenue) / priorRevenue) * 100).toFixed(1)
    : '0.0'

  const chartMonths = monthWindows(account, clock, 12)
  const series = chartMonths.map((window) => activeOn(members, window.endDay - 1, clock))
  const prior = chartMonths.map((window) =>
    activeOn(members, window.endDay - 1 - 365, clock),
  )
  const low = Math.min(...prior, ...series)
  const high = Math.max(...series)
  const last = series[series.length - 1]
  const priorLast = prior[prior.length - 1]
  const yoy = priorLast ? (((last - priorLast) / priorLast) * 100).toFixed(1) : null

  const unread = messages.filter((message) => message.labels.includes('UNREAD'))
  const oldest = unread.reduce(
    (worst, message) => Math.max(worst, asOfDay - clock.dayNumber(message.received_at)),
    0,
  )
  const expiring = account.integrations.find(
    (item) =>
      item.expires_at && clock.dayNumber(item.expires_at) - asOfDay <= 14,
  )

  const attention = []
  if (highRisk.length) {
    attention.push({
      icon: 'alert',
      tone: 'alert',
      title: `${plural(highRisk.length, 'member')} at high churn risk`,
      detail: highRisk
        .slice(0, 2)
        .map((member) => `${member.first_name} ${member.last_name[0]}.`)
        .join(' and ') + `, ${highRisk[0].lastVisitDays}+ days out`,
      view: 'churn',
    })
  }
  if (unread.length) {
    attention.push({
      icon: 'inbox',
      title: `${plural(unread.length, 'message')} unanswered`,
      detail: oldest
        ? `The oldest has been waiting ${plural(oldest, 'day')}`
        : 'All arrived today',
      view: 'inbox',
    })
  }
  if (expiring) {
    attention.push({
      icon: 'plug',
      title: `${expiring.name.split(',')[0]} token expires in ${
        clock.dayNumber(expiring.expires_at) - asOfDay
      } days`,
      detail: 'Reconnect to keep attribution running',
      view: 'integrations',
    })
  }

  return {
    kpis: [
      {
        label: 'Active members',
        value: active.length,
        delta: `+${joinsByMonth[joinsByMonth.length - 1]} this month`,
        spark: memberSpark,
      },
      {
        label: 'Revenue, 30d',
        value: revenue,
        prefix: '$',
        delta: `${revenueDelta >= 0 ? '+' : ''}${revenueDelta}% vs prior 30`,
        spark: revenueTrail,
      },
      {
        label: 'New members, 30d',
        value: newMembers.length,
        delta: `${fromInstagram} from Instagram`,
        spark: joinsByMonth,
      },
      {
        label: 'Flagged at risk',
        value: flagged.length,
        delta: `${highRisk.length} high risk`,
        deltaTone: 'alert',
        spark: riskTrail,
      },
    ],

    chart: {
      title: 'Active members',
      caption: 'Rolling 12 months, end of month',
      badge: yoy ? `${yoy > 0 ? '+' : ''}${yoy}% YoY` : 'Rolling 12 months',
      min: Math.max(0, Math.floor((low - 10) / 10) * 10),
      max: Math.ceil((high + 10) / 10) * 10,
      months: chartMonths.map((window) => window.label),
      series,
      prior,
      legend: { series: 'This year', prior: 'Same period last year' },
      summary: `Active members went from ${series[0]} to ${last} over twelve months`,
    },

    attention: { title: 'Needs your attention', items: attention },
    activity: deriveActivity(ctx),
  }
}

// The feed is a merge of four raw streams on one timeline. Emphasis is marked
// with *asterisks*, which is what the renderer expects.
function deriveActivity(ctx) {
  const { members, visits, charges, posts, clock, asOfDay } = ctx
  const byId = new Map(members.map((member) => [member.id, member]))
  const postCaptions = new Map(posts.map((post) => [post.id, post.caption]))
  const slots = new Map(ctx.account.class_slots.map((slot) => [slot.id, slot.label]))
  const events = []

  for (const member of members) {
    if (asOfDay - clock.dayNumber(member.joined_at) > 3) continue
    const caption = postCaptions.get(member.acquisition.post_id)
    events.push({
      kind: 'signup',
      at: `${member.joined_at}T12:00:00Z`,
      text: caption
        ? `New member signed: *${member.name}* from "${caption.slice(0, 28)}"`
        : `New member signed: *${member.name}*`,
    })
  }

  for (const visit of visits.slice(-60)) {
    if (asOfDay - clock.dayNumber(visit.checked_in_at) > 0) continue
    const member = byId.get(visit.member_id)
    if (!member) continue
    events.push({
      kind: 'checkin',
      at: visit.checked_in_at,
      text: `*${member.name}* checked in to ${slots.get(visit.class_slot_id)}`,
    })
  }

  for (const charge of charges) {
    if (asOfDay - clock.dayNumber(charge.created_at) > 1) continue
    const member = byId.get(charge.member_id)
    if (!member) continue
    events.push({
      kind: 'charge',
      at: charge.created_at,
      text:
        charge.status === 'failed'
          ? `Card declined for *${member.name}*`
          : `Payment received: *$${money(charge.amount_cents)}* from ${member.name}`,
    })
  }

  events.sort((a, b) => Date.parse(b.at) - Date.parse(a.at))

  // Strict recency makes this six rows of whichever class just finished,
  // because an evening session check-ins twenty people at once. Cap check-ins
  // so signups and payments can surface, then put the selection back in time
  // order.
  const checkins = events.filter((event) => event.kind === 'checkin')
  const rest = events.filter((event) => event.kind !== 'checkin')
  const items = [...checkins.slice(0, 3), ...rest.slice(0, 3)]
  if (items.length < 6) items.push(...checkins.slice(3, 3 + (6 - items.length)))

  return {
    title: 'Live activity',
    caption: 'Today',
    items: items
      .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
      .map((event) => ({ text: event.text, when: clock.time(event.at) })),
  }
}

function deriveGrowth(ctx) {
  const { members, posts, claims, clock, asOfDay } = ctx

  // 90 days, because a post keeps converting for weeks after it is published
  // and a 30 day window credits almost none of it.
  const WINDOW = 90
  const recent = posts.filter(
    (post) => asOfDay - clock.dayNumber(post.published_at) <= WINDOW,
  )
  const claimsByPost = new Map(recent.map((post) => [post.id, []]))
  for (const claim of claims) claimsByPost.get(claim.post_id)?.push(claim)

  const attributed = members.filter(
    (member) => member.acquisition.post_id && member.tenureDays <= WINDOW,
  )
  const convertedByPost = new Map(recent.map((post) => [post.id, 0]))
  for (const member of attributed) {
    if (convertedByPost.has(member.acquisition.post_id)) {
      convertedByPost.set(
        member.acquisition.post_id,
        convertedByPost.get(member.acquisition.post_id) + 1,
      )
    }
  }

  const rows = recent
    .map((post) => {
      const postClaims = claimsByPost.get(post.id) || []
      const converted = convertedByPost.get(post.id) || 0
      const spend = money(post.spend_cents)
      const channel = post.channel === 'tiktok' ? 'TikTok' : titleCase(post.channel)
      return {
        post: {
          name: post.caption,
          sub: `${channel} · ${clock.month(post.published_at)}`,
        },
        channel,
        reach: post.insights.reach.toLocaleString('en-US'),
        clicks: post.insights.link_clicks.toLocaleString('en-US'),
        passes: String(postClaims.length),
        members: String(converted),
        // A post with no ad spend has no cost per member, and printing $0
        // would read as free customers rather than organic reach.
        cost: spend === 0 ? 'Organic' : converted ? `$${Math.round(spend / converted)}` : `$${spend}`,
        _converted: converted,
      }
    })
    .sort((a, b) => b._converted - a._converted)

  const best = rows[0]
  if (best) {
    best.members = { value: best.members, highlight: true }
    if (best.cost !== 'Organic') best.cost = { value: best.cost, highlight: true }
  }
  for (const row of rows) delete row._converted

  const totalSpend = recent.reduce((sum, post) => sum + money(post.spend_cents), 0)
  const totalReach = recent.reduce((sum, post) => sum + post.insights.reach, 0)
  const allClaims = recent.flatMap((post) => claimsByPost.get(post.id) || [])
  const redeemed = allClaims.filter((claim) => claim.redeemed_at).length

  const byChannel = new Map()
  for (const member of attributed) {
    const channel = member.acquisition.channel
    byChannel.set(channel, (byChannel.get(channel) || 0) + 1)
  }

  return {
    kpis: [
      {
        label: 'Cost per member',
        value: attributed.length ? Math.round(totalSpend / attributed.length) : 0,
        prefix: '$',
        delta: `$${totalSpend.toLocaleString('en-US')} spent, blended`,
      },
      {
        label: 'Attributed members',
        value: attributed.length,
        delta: `From ${plural(recent.length, 'tracked post')}`,
      },
      {
        label: 'Free passes claimed',
        value: allClaims.length,
        delta: allClaims.length
          ? `${Math.round((redeemed / allClaims.length) * 100)}% redeemed`
          : 'None yet',
      },
      {
        label: 'Total reach',
        value: totalReach,
        delta: `Across ${plural(recent.length, 'post')}`,
      },
    ],

    table: {
      title: 'Post attribution',
      caption: 'Reach to link click to free pass to signed member',
      badge: `Last ${WINDOW} days`,
      columns: [
        { key: 'post', label: 'Post', type: 'name' },
        { key: 'channel', label: 'Channel' },
        { key: 'reach', label: 'Reach', type: 'num' },
        { key: 'clicks', label: 'Clicks', type: 'num' },
        { key: 'passes', label: 'Passes', type: 'num' },
        { key: 'members', label: 'Members', type: 'num' },
        { key: 'cost', label: 'Cost / member', type: 'num' },
      ],
      rows,
    },

    bars: {
      title: 'Members by channel',
      caption: `${plural(attributed.length, 'signed member')}, attributed to a post`,
      total: attributed.length || 1,
      items: [...byChannel.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([channel, value]) => ({
          label: channel === 'tiktok' ? 'TikTok' : titleCase(channel),
          value,
        })),
    },
  }
}

const titleCase = (value) =>
  value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ')

function deriveChurn(ctx) {
  const active = ctx.members.filter((member) => member.status === 'active')
  const bands = {
    high: active.filter((member) => member.band === 'high'),
    medium: active.filter((member) => member.band === 'medium'),
    watch: active.filter((member) => member.band === 'watch'),
  }

  const atRisk = [...bands.high, ...bands.medium].sort((a, b) => b.risk - a.risk)
  const exposure = atRisk.reduce((sum, member) => sum + money(member.plan.price_cents), 0)

  return {
    note: 'Scored from the check-in log: how long since they came in, and whether they are coming less than they used to. Names, not averages, so you know who to walk over to.',

    kpis: [
      {
        label: 'High risk',
        value: bands.high.length,
        delta: 'Act this week',
        deltaTone: 'alert',
      },
      { label: 'Medium risk', value: bands.medium.length, delta: 'Worth a check-in' },
      { label: 'Watchlist', value: bands.watch.length, delta: 'Monitoring only' },
      {
        label: 'Revenue at risk',
        value: exposure,
        prefix: '$',
        delta: 'Monthly, if all of them left',
        deltaTone: 'alert',
      },
    ],

    table: {
      title: 'Flagged this week',
      caption: 'Ranked by risk score, recomputed on every sync',
      badge: { label: `${atRisk.length} flagged`, tone: 'alert' },
      columns: [
        { key: 'member', label: 'Member', type: 'name' },
        { key: 'risk', label: 'Risk', type: 'meter' },
        { key: 'lastVisit', label: 'Last visit' },
        { key: 'visits', label: 'Visits / 30d', type: 'num' },
        { key: 'signal', label: 'Signal' },
      ],
      rows: atRisk.map((member) => ({
        member: {
          name: member.name,
          sub: `${member.plan.name} · $${money(member.plan.price_cents)}/mo`,
        },
        risk: { value: member.risk, tone: member.band === 'high' ? 'alert' : null },
        lastVisit: member.lastVisitDays === null ? 'Never' : ago(member.lastVisitDays),
        visits: String(member.last30),
        signal: member.signal,
      })),
      foot: `Keeping two of them pays for the portal`,
    },
  }
}

function deriveMembers(ctx) {
  const roster = ctx.members
    .filter((member) => member.status === 'active')
    .sort((a, b) => (a.lastVisitDays ?? 999) - (b.lastVisitDays ?? 999))

  const status = (member) => {
    if (member.band === 'high' || member.band === 'medium') {
      return { label: 'At risk', tone: 'alert' }
    }
    if (member.tenureDays <= 30) return { label: 'New', tone: 'signal' }
    if (member.band === 'watch') return { label: 'Watch' }
    return { label: 'Active' }
  }

  return {
    table: {
      title: 'Member roster',
      caption: `${roster.length} active, synced from Mindbody`,
      columns: [
        { key: 'member', label: 'Member', type: 'name' },
        { key: 'plan', label: 'Plan' },
        { key: 'joined', label: 'Joined' },
        { key: 'lastVisit', label: 'Last visit' },
        { key: 'visits', label: 'Visits / 30d', type: 'num' },
        { key: 'status', label: 'Status', type: 'pill' },
      ],
      rows: roster.map((member) => ({
        member: { name: member.name, sub: member.email },
        plan: member.plan.name,
        joined: ctx.clock.month(`${member.joined_at}T12:00:00Z`),
        lastVisit: member.lastVisitDays === null ? 'Never' : ago(member.lastVisitDays),
        visits: String(member.last30),
        status: status(member),
      })),
    },
  }
}

function deriveIntegrations(ctx) {
  const { account, clock, asOfDay } = ctx

  const statusFor = (item) => {
    if (item.status !== 'connected') return { label: 'Not connected' }
    if (item.expires_at) {
      const days = clock.dayNumber(item.expires_at) - asOfDay
      if (days <= 30) return { label: `Token expires in ${days}d`, tone: 'alert' }
    }
    const hours = Math.round((Date.parse(account.as_of) - Date.parse(item.last_sync_at)) / 36e5)
    return {
      label: hours < 1 ? 'Synced just now' : `Synced ${plural(hours, 'hour')} ago`,
      tone: 'signal',
    }
  }

  return {
    note: 'Read access only. You never hand over passwords, and member data is used to run your portal and nothing else.',
    title: 'Connections',
    items: account.integrations.map((item) => {
      const status = statusFor(item)
      return {
        name: item.name,
        detail: item.scope,
        live: item.status === 'connected',
        status,
        action: status.tone === 'alert' ? 'Reconnect' : null,
      }
    }),
  }
}

// Product copy, not tenant data, so it lives here rather than in a gym's
// folder. The demo keeps its own copy of these strings in demo/data.
const INBOX_UI = {
  replyLabel: 'Your reply',
  replyPlaceholder: 'Write a reply, or leave it for later.',
  send: 'Send reply',
  approve: 'Approve and send',
  sent: 'Sent to {name}.',
  replied: 'Replied',
  draftLabel: 'Drafted reply',
  draftNote: "Drafted from this member's record. Edit anything before it goes out.",
  actionLabel: 'Commits to',
  confidenceLabel: 'confidence',
  needsHuman: 'Read this one first',
  sortLabel: 'Sort',
  sorts: [
    { id: 'priority', label: 'Priority', active: true },
    { id: 'newest', label: 'Newest' },
    { id: 'category', label: 'Category' },
  ],
  categories: {
    billing: 'Billing',
    membership: 'Membership',
    schedule: 'Scheduling',
    lead: 'New lead',
    facilities: 'Facilities',
    other: 'Other',
  },
  priorities: { high: 'High', medium: 'Medium', low: 'Low' },
}

function deriveInbox(ctx) {
  const { messages, members, account, clock, asOfDay } = ctx
  const byId = new Map(members.map((member) => [member.id, member]))
  const unread = messages.filter((message) => message.labels.includes('UNREAD'))

  const threads = messages
    .slice()
    .sort((a, b) => Date.parse(b.received_at) - Date.parse(a.received_at))
    .map((message) => {
      const member = message.member_id ? byId.get(message.member_id) : null
      const days = asOfDay - clock.dayNumber(message.received_at)

      return {
        // The message id is the AI cache key, so it has to be stable and
        // come from the source rather than from list position.
        id: message.id,
        name: message.from.name,
        initials: message.from.name
          .split(' ')
          .map((part) => part[0])
          .join('')
          .slice(0, 2),
        when: days === 0 ? clock.time(message.received_at) : ago(days),
        receivedAt: `${days === 0 ? 'Today' : ago(days)}, ${clock.time(message.received_at)}`,
        ageMinutes: Math.round((Date.parse(account.as_of) - Date.parse(message.received_at)) / 60000),
        status: member ? { label: 'Member' } : { label: 'Lead', tone: 'signal' },
        meta: member
          ? `Member since ${clock.month(`${member.joined_at}T12:00:00Z`)} · ${
              member.plan.name
            } · $${money(member.plan.price_cents)}/mo`
          : `New lead · ${message.from.email}`,
        risk:
          member && member.risk >= 50
            ? { label: `Churn risk ${member.risk}`, tone: 'alert' }
            : null,
        subject: message.subject,
        message: message.body_text,
      }
    })

  return {
    title: 'Member inbox',
    caption: `${plural(unread.length, 'message')} waiting on a reply`,
    badge: { label: `${unread.length} unanswered`, tone: 'alert' },
    ui: INBOX_UI,
    threads,
  }
}

function derivePortal(ctx, overview, churn, inbox) {
  const { account, members } = ctx
  const active = members.filter((member) => member.status === 'active').length
  const flagged = churn.table.rows.length
  const unread = inbox.threads.length

  return {
    product: 'The Gym Portal',
    name: account.gym.name,
    initials: account.gym.name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .slice(0, 2),
    members: `${active} members`,
    navLabel: 'Portal',
    sync: `Synced ${plural(
      Math.max(1, Math.round((Date.parse(account.as_of) - Date.parse(account.integrations[0].last_sync_at)) / 60000)),
      'min',
    )} ago`,
    searchPlaceholder: 'Search this view',
    ranges: [{ label: '7D' }, { label: '30D', active: true }, { label: '90D' }],
    user: {
      name: account.owner.name,
      initials: account.owner.name
        .split(' ')
        .map((part) => part[0])
        .join('')
        .slice(0, 2),
      role: account.owner.role,
    },
    views: [
      { id: 'overview', label: 'Overview', icon: 'overview', title: 'Overview', eyebrow: account.gym.name },
      { id: 'growth', label: 'Growth', icon: 'growth', title: 'Growth', eyebrow: 'Post to signed member' },
      {
        id: 'churn',
        label: 'Churn Radar',
        icon: 'churn',
        title: 'Churn Radar',
        eyebrow: 'Retention',
        badge: { value: flagged, tone: 'alert' },
      },
      {
        id: 'inbox',
        label: 'Smart Inbox',
        icon: 'inbox',
        title: 'Smart Inbox',
        eyebrow: 'Member email',
        badge: { value: unread },
      },
      { id: 'members', label: 'Members', icon: 'members', title: 'Members', eyebrow: 'Roster' },
      { id: 'integrations', label: 'Integrations', icon: 'plug', title: 'Integrations', eyebrow: 'Data sources' },
    ],
  }
}

/* ---------- entry point ---------- */

export function deriveBundle(raw) {
  const { account, members, visits, charges, posts, pass_claims: claims, messages, inboxAi } = raw
  const clock = clockFor(account.gym.timezone)

  const ctx = {
    account,
    clock,
    asOfDay: clock.dayNumber(account.as_of),
    members: profileMembers(account, members, visits, charges, clock),
    visits,
    charges,
    posts,
    claims,
    messages,
  }

  const overview = deriveOverview(ctx)
  const growth = deriveGrowth(ctx)
  const churn = deriveChurn(ctx)
  const membersView = deriveMembers(ctx)
  const integrations = deriveIntegrations(ctx)
  const inbox = deriveInbox(ctx)

  return {
    portal: derivePortal(ctx, overview, churn, inbox),
    overview,
    growth,
    churn,
    members: membersView,
    integrations,
    inbox,
    inboxAi,
  }
}
