"""Generate the raw data for a test account.

The point of this file is that its output is deliberately *not* dashboard
shaped. It emits the kind of records the portal would really pull from
Mindbody, Stripe, the Meta API and a mailbox: snake_case fields, opaque ids,
UTC timestamps, nulls, cancelled rows, failed charges. Turning that into KPIs,
chart series and churn scores is src/derive.js's job, which is the whole point
of having it.

Output is deterministic: same seed, same bytes. Reshape the gym by editing the
knobs below and re-running.

    python accounts/generate.py
    python accounts/generate.py --account test --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Everything is generated relative to this date rather than today, so the
# dashboard shows the same numbers next month. Real raw data would carry real
# timestamps; a committed fixture cannot, or it silently rots into a gym where
# nobody has checked in for six months.
AS_OF = date(2026, 8, 7)

# Late evening, because the fixture contains a full day of check-ins and the
# 5:30pm class cannot appear in a feed that syncs at breakfast.
AS_OF_HOUR, AS_OF_MINUTE = 20, 45

VISIT_WEEKS = 20  # how much check-in history to emit

# The revenue sparkline plots eight trailing 30 day windows, so it reaches 240
# days back. Ten months of billing covers that with room to spare; eight left
# the oldest point half empty and drew a cliff that was never there.
CHARGE_MONTHS = 10

# A gym is a revolving door, and modelling it as one is what makes the derived
# numbers hang together. Members arrive at a steady rate across JOIN_SPAN and
# each gets an exponential lifetime, so the roster churns instead of only ever
# growing. Without the churn you have to choose between a believable growth
# rate and having enough recent signups for Growth to attribute; with it you
# get roughly 9 joins a month, ~120 active, and a sane year over year.
TOTAL_MEMBERS = 300
JOIN_SPAN = 1050
MEAN_LIFETIME = 480

GYM = {
    "name": "Northside Barbell",
    "short_name": "Northside",
    "city": "Durham, NC",
    "timezone": "America/New_York",
    "support_email": "front@northsidebarbell.com",
}

PLANS = [
    {"id": "plan_unlimited", "name": "Unlimited", "price_cents": 15900, "visits_per_week": None},
    {"id": "plan_3x", "name": "3x / week", "price_cents": 12900, "visits_per_week": 3},
    {"id": "plan_open", "name": "Open gym", "price_cents": 8900, "visits_per_week": None},
]

CLASS_SLOTS = [
    {"id": "slot_0600", "label": "Strength 6:00a", "weekdays": [0, 1, 2, 3, 4], "hour": 6},
    {"id": "slot_0915", "label": "Strength 9:15a", "weekdays": [0, 2, 4], "hour": 9},
    {"id": "slot_1730", "label": "Strength 5:30p", "weekdays": [0, 1, 2, 3, 4], "hour": 17},
    {"id": "slot_1900", "label": "Barbell club 7:00p", "weekdays": [1, 3], "hour": 19},
    {"id": "slot_sat", "label": "Saturday 9:00a", "weekdays": [5], "hour": 9},
]

FIRST_NAMES = [
    "Alicia", "Marcus", "Danielle", "Tom", "Priya", "Jordan", "Kayla", "Devon",
    "Sam", "Rosa", "Ethan", "Nadia", "Curtis", "Bianca", "Omar", "Hannah",
    "Trevor", "Leah", "Andre", "Simone", "Colin", "Maya", "Derek", "Ingrid",
    "Felix", "Tasha", "Reid", "Naomi", "Victor", "Clara", "Jonah", "Elise",
    "Damon", "Yara", "Pete", "Greta", "Luis", "Mira", "Wesley", "June",
]

LAST_NAMES = [
    "Grant", "Terry", "Wu", "Alvarez", "Shah", "Miles", "Reyes", "Ward",
    "Okafor", "Delgado", "Boone", "Haddad", "Pace", "Ferrer", "Nassar",
    "Whitfield", "Lund", "Barrera", "Coleman", "Nakamura", "Ellis", "Rourke",
    "Vance", "Holm", "Amari", "Bright", "Sowell", "Kaur", "Mendes", "Quinn",
]


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def at(day: date, hour: int, minute: int) -> datetime:
    """A local wall-clock time, emitted as UTC the way an API would.

    Durham is UTC-4 in August, and pinning the offset keeps the fixture stable
    rather than depending on the machine's tzdata.
    """
    naive = datetime.combine(day, time(hour, minute))
    return naive.replace(tzinfo=timezone(timedelta(hours=-4)))


def month_starts(end: date, count: int) -> list[date]:
    months, cursor = [], end.replace(day=1)
    for _ in range(count):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(months))


def build_members(rng: random.Random) -> list[dict]:
    """Members joining over roughly three years, some of whom left.

    Each gets a hidden `_habit` and `_fade`: how often they train and whether
    they are drifting. Nothing downstream sees those, they only shape the
    check-in log, which is the only evidence the dashboard gets.
    """
    members, used = [], set()
    total = TOTAL_MEMBERS

    for index in range(total):
        while True:
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            if (first, last) not in used:
                used.add((first, last))
                break

        # Joins are spread across the span by index with a jitter, not drawn
        # independently. Independent draws let a seed land on two signups in
        # the last month, which makes a growing gym look dead through no fault
        # of the dashboard. The exponent tilts the rate gently towards the
        # present so the roster grows instead of sitting at steady state.
        fraction = (total - index - rng.random()) / total
        days_ago = int(JOIN_SPAN * fraction**1.08)
        joined = AS_OF - timedelta(days=days_ago)

        plan = rng.choices(PLANS, weights=[6, 3, 2])[0]

        channel = rng.choices(
            ["instagram", "referral", "walk_in", "facebook", "tiktok"],
            weights=[8, 5, 4, 2, 1],
        )[0]

        # Anyone whose lifetime ran out before today has already left. Nobody
        # quits in their first month, which keeps the fixture free of members
        # who joined and cancelled in the same fortnight.
        lifetime = max(30, rng.expovariate(1 / MEAN_LIFETIME))
        cancelled_at = None
        status = "active"
        if lifetime < days_ago:
            cancelled_at = (joined + timedelta(days=int(lifetime))).isoformat()
            status = "cancelled"

        habit = rng.choice([1.0, 1.6, 2.2, 2.6, 3.2, 3.6])

        # Drifting is a matter of degree, not a flag. A depth near 0.4 is
        # someone coming half as often as they used to; above 1.3 they have
        # effectively stopped. Making this continuous is what gives the churn
        # scores a gradient instead of a cliff between "fine" and "gone".
        fade = rng.uniform(0.35, 1.7) if rng.random() < 0.16 else 0.0

        # And they start drifting at different times. When everyone declines
        # from the same week, the count of quiet members climbs steadily from
        # nothing to a crisis, which is an artefact of the fixture rather than
        # anything about the gym.
        fade_start = rng.randint(2, 13)

        members.append(
            {
                "id": f"mbr_{index + 1001:04d}",
                "first_name": first,
                "last_name": last,
                "email": f"{first.lower()}.{last.lower()}@example.com",
                "phone": f"+1919{rng.randint(2000000, 9999999)}",
                "plan_id": plan["id"],
                "status": status,
                "joined_at": joined.isoformat(),
                "cancelled_at": cancelled_at,
                "acquisition": {"channel": channel, "post_id": None, "claim_id": None},
                "_habit": habit,
                "_fade": fade,
                "_fade_start": fade_start,
            }
        )

    return members


def build_visits(rng: random.Random, members: list[dict]) -> list[dict]:
    """A check-in log. This is the only record of whether anyone shows up."""
    visits: list[dict] = []
    start = AS_OF - timedelta(weeks=VISIT_WEEKS)
    counter = 0

    for member in members:
        joined = date.fromisoformat(member["joined_at"])
        left = date.fromisoformat(member["cancelled_at"]) if member["cancelled_at"] else None

        day = start
        while day <= AS_OF:
            week_index = (day - start).days // 7

            if day < joined or (left and day >= left):
                day += timedelta(days=1)
                continue

            rate = member["_habit"]
            if member["_fade"]:
                # Once they start drifting they taper off over about six
                # weeks, scaled by how badly. That decline is the only thing
                # in the data the churn score has to notice.
                weeks_in = week_index - member["_fade_start"]
                if weeks_in > 0:
                    rate *= max(0.0, 1.0 - (weeks_in / 6.0) * member["_fade"])

            slots = [s for s in CLASS_SLOTS if day.weekday() in s["weekdays"]]
            if slots and rng.random() < rate / len(CLASS_SLOTS) * 1.15:
                slot = rng.choice(slots)
                counter += 1
                visits.append(
                    {
                        "id": f"chk_{counter:05d}",
                        "member_id": member["id"],
                        "class_slot_id": slot["id"],
                        "checked_in_at": iso(
                            at(day, slot["hour"], rng.choice([1, 3, 4, 7, 12]))
                        ),
                        "source": "front_desk" if rng.random() < 0.2 else "app",
                    }
                )

            day += timedelta(days=1)

    visits.sort(key=lambda visit: visit["checked_in_at"])
    return visits


def build_charges(rng: random.Random, members: list[dict]) -> list[dict]:
    """Stripe-shaped charges, including the failures that matter."""
    prices = {plan["id"]: plan["price_cents"] for plan in PLANS}
    names = {plan["id"]: plan["name"] for plan in PLANS}
    charges: list[dict] = []
    counter = 0

    for month in month_starts(AS_OF, CHARGE_MONTHS):
        for member in members:
            joined = date.fromisoformat(member["joined_at"])
            left = date.fromisoformat(member["cancelled_at"]) if member["cancelled_at"] else None

            # Members bill on their signup anniversary, not all on the 1st.
            # That is how subscription billing actually behaves, and it means
            # payments land throughout the month instead of in one spike.
            billed = month.replace(day=min(joined.day, 28))
            if billed < joined or billed > AS_OF or (left and left <= billed):
                continue

            counter += 1
            status = "succeeded"
            roll = rng.random()
            if roll < 0.025:
                status = "failed"
            elif roll < 0.035:
                status = "refunded"

            charges.append(
                {
                    "id": f"ch_{counter:05d}",
                    "member_id": member["id"],
                    "amount_cents": prices[member["plan_id"]],
                    "currency": "usd",
                    "status": status,
                    "description": f"{names[member['plan_id']]} monthly",
                    "created_at": iso(at(billed, 9, rng.randint(1, 55))),
                    "failure_code": "card_declined" if status == "failed" else None,
                }
            )

    return charges


POSTS = [
    {
        "caption": "PR Friday: Simone pulls 315 for the first time",
        "channel": "instagram",
        "days_ago": 27,
        "reach": 38400,
        "clicks": 902,
        "spend_cents": 12000,
    },
    {
        "caption": "Meet the 6am crew",
        "channel": "instagram",
        "days_ago": 35,
        "reach": 21100,
        "clicks": 588,
        "spend_cents": 0,
    },
    {
        "caption": "Marcus dropped 40 lbs in a year. Here is what he actually did",
        "channel": "instagram",
        "days_ago": 20,
        "reach": 29700,
        "clicks": 813,
        "spend_cents": 9000,
    },
    {
        "caption": "Barbell club, Tuesday 7pm, all levels",
        "channel": "instagram",
        "days_ago": 16,
        "reach": 17500,
        "clicks": 366,
        "spend_cents": 0,
    },
    {
        "caption": "Free week giveaway, tag a friend",
        "channel": "facebook",
        "days_ago": 31,
        "reach": 11400,
        "clicks": 494,
        "spend_cents": 15000,
    },
    {
        "caption": "Saturday 9am is our beginner class. No experience needed",
        "channel": "instagram",
        "days_ago": 12,
        "reach": 9200,
        "clicks": 205,
        "spend_cents": 0,
    },
    {
        "caption": "Gym tour: 6,000 sq ft, 14 platforms",
        "channel": "tiktok",
        "days_ago": 23,
        "reach": 26300,
        "clicks": 271,
        "spend_cents": 0,
    },
]


def build_posts_and_claims(rng: random.Random, members: list[dict]):
    """Post insights plus the free-pass funnel that links them to signups.

    Attribution is a join the dashboard has to make: a claim carries a post id
    and, if it worked, a member id. Nothing here says "9 members from this
    post", which is exactly the number Growth has to work out.
    """
    posts, claims = [], []

    # Only recent members acquired through a channel we post on can be
    # attributed. Pooled per channel, because drawing from one shared queue
    # and discarding whoever came from the wrong channel silently threw away
    # most of the candidates and left Growth attributing almost nobody.
    pools = {"instagram": [], "facebook": [], "tiktok": []}
    for member in members:
        channel = member["acquisition"]["channel"]
        if channel not in pools:
            continue
        if (AS_OF - date.fromisoformat(member["joined_at"])).days <= 90:
            pools[channel].append(member)
    for queue in pools.values():
        rng.shuffle(queue)

    for index, spec in enumerate(POSTS):
        published = AS_OF - timedelta(days=spec["days_ago"])
        post_id = f"post_{2200 + index * 7}"
        posts.append(
            {
                "id": post_id,
                "channel": spec["channel"],
                "permalink": f"https://example.com/{spec['channel']}/{post_id}",
                "caption": spec["caption"],
                "published_at": iso(at(published, 7, 30)),
                "insights": {
                    "reach": spec["reach"],
                    "link_clicks": spec["clicks"],
                },
                "spend_cents": spec["spend_cents"],
            }
        )

        # Bigger posts pull more pass claims, and a minority convert.
        claim_count = max(3, round(spec["clicks"] / 26))
        for _ in range(claim_count):
            claimed = published + timedelta(days=rng.randint(0, 5))
            if claimed > AS_OF:
                claimed = AS_OF

            converted = None
            redeemed = None
            if rng.random() < 0.42:
                redeemed = iso(at(claimed + timedelta(days=rng.randint(1, 6)), 18, 0))
                queue = pools.get(spec["channel"])
                if rng.random() < 0.55 and queue:
                    converted = queue.pop()["id"]

            claim_id = f"claim_{len(claims) + 4001}"
            if converted:
                for member in members:
                    if member["id"] == converted:
                        member["acquisition"]["post_id"] = post_id
                        member["acquisition"]["claim_id"] = claim_id

            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            claims.append(
                {
                    "id": claim_id,
                    "post_id": post_id,
                    "name": f"{first} {last}",
                    "email": f"{first.lower()}{rng.randint(11, 99)}@example.com",
                    "claimed_at": iso(at(claimed, 12, rng.randint(0, 58))),
                    "redeemed_at": redeemed,
                    "converted_member_id": converted,
                }
            )

    return posts, claims


# Hand-written, because generated prose reads like generated prose and these
# are the strings a human actually looks at. Senders are described by persona
# rather than by name: the roster is generated, so a hardcoded name would not
# exist in it, and binding by persona is what keeps the inbox agreeing with
# the churn radar. Someone writing "I haven't been in for weeks" should be a
# member the check-in log actually shows drifting.
MESSAGES = [
    {
        "persona": "quiet",
        "subject": "Freeze my membership for September?",
        "body": "Hey! I'm on the road for work almost all of September and won't be able to get in. Can I freeze instead of cancelling? I'd rather not lose the rate I'm on.",
        "hours_ago": 2,
    },
    {
        "persona": "lead",
        "from_name": "Curtis Boone",
        "subject": "free pass from the beginner post",
        "body": "Saw the Saturday 9am post and grabbed the free pass. I've never touched a barbell, is that class actually okay for someone starting from zero?",
        "hours_ago": 3,
    },
    {
        "persona": "regular",
        "subject": "Switching to the 6am",
        "body": "My hours changed and 5:30 doesn't work anymore. Can I move to the 6am starting next week?",
        "hours_ago": 21,
    },
    {
        "persona": "regular",
        "subject": "charged twice this month",
        "body": "I show two charges from you this month. Can you check? Happy to keep the membership, just want the extra one back.",
        "hours_ago": 26,
    },
    {
        "persona": "quiet",
        "subject": "cancelling at the end of the month",
        "body": "I want to cancel at the end of the month. Work has been brutal and I haven't been in for weeks, so I'm paying for nothing right now.",
        "hours_ago": 44,
    },
    {
        "persona": "quiet",
        "subject": "childcare during the morning classes?",
        "body": "Is there any childcare in the mornings? That's genuinely the only thing stopping me from coming back.",
        "hours_ago": 51,
    },
    {
        "persona": "regular",
        "subject": "shoulder is bugging me",
        "body": "Tweaked my shoulder overhead pressing on Tuesday. Should I skip the barbell club this week or is there something I can do instead?",
        "hours_ago": 68,
    },
    {
        "persona": "regular",
        "subject": "Bringing a friend Saturday",
        "body": "Can I bring my sister to the Saturday class? She's visiting from Raleigh and wants to try it.",
        "hours_ago": 73,
    },
]


def build_messages(members: list[dict], visits: list[dict]) -> list[dict]:
    """Mailbox-shaped email. Most senders are members, one is a stranger."""
    recent = {}
    cutoff = AS_OF - timedelta(days=30)
    for visit in visits:
        day = date.fromisoformat(visit["checked_in_at"][:10])
        if day >= cutoff:
            recent[visit["member_id"]] = recent.get(visit["member_id"], 0) + 1

    # Established members only, so "I haven't been in for weeks" is not coming
    # from somebody who joined last Tuesday.
    settled = [
        member
        for member in members
        if member["status"] == "active"
        and (AS_OF - date.fromisoformat(member["joined_at"])).days > 90
    ]
    settled.sort(key=lambda member: recent.get(member["id"], 0))

    pools = {"quiet": list(settled[:12]), "regular": list(reversed(settled[-12:]))}
    now = at(AS_OF, AS_OF_HOUR, AS_OF_MINUTE - 5)
    messages = []

    for index, spec in enumerate(MESSAGES):
        member = pools[spec["persona"]].pop(0) if spec["persona"] in pools else None

        if member:
            name = f"{member['first_name']} {member['last_name']}"
            email = member["email"]
        else:
            name = spec["from_name"]
            email = f"{name.split()[0].lower()}{index}@example.com"

        received = now - timedelta(hours=spec["hours_ago"])
        messages.append(
            {
                "id": f"msg_{9100 + index}",
                "thread_id": f"thr_{9100 + index}",
                "from": {"name": name, "email": email},
                "to": GYM["support_email"],
                "subject": spec["subject"],
                "body_text": spec["body"],
                "received_at": iso(received),
                "labels": ["INBOX", "UNREAD"],
                "member_id": member["id"] if member else None,
            }
        )

    return messages


def build_account() -> dict:
    return {
        "id": "test",
        "as_of": iso(at(AS_OF, AS_OF_HOUR, AS_OF_MINUTE)),
        "gym": GYM,
        "owner": {"name": "Ray Whitfield", "email": "ray@northsidebarbell.com", "role": "Owner"},
        "plans": PLANS,
        "class_slots": CLASS_SLOTS,
        "integrations": [
            {
                "id": "mindbody",
                "name": "Mindbody",
                "scope": "Members, bookings, billing history",
                "status": "connected",
                "last_sync_at": iso(at(AS_OF, AS_OF_HOUR, AS_OF_MINUTE - 6)),
                "expires_at": None,
            },
            {
                "id": "instagram",
                "name": "Instagram, via the Meta API",
                "scope": "Posts, reach, link clicks, free pass claims",
                "status": "connected",
                "last_sync_at": iso(at(AS_OF, AS_OF_HOUR - 1, 12)),
                "expires_at": iso(at(AS_OF + timedelta(days=9), 7, 40)),
            },
            {
                "id": "gmail",
                "name": "Member inbox, Google Workspace",
                "scope": "Reads member email so replies live in one place",
                "status": "connected",
                "last_sync_at": iso(at(AS_OF, AS_OF_HOUR, AS_OF_MINUTE - 3)),
                "expires_at": None,
            },
            {
                "id": "stripe",
                "name": "Stripe",
                "scope": "Payments, refunds, failed charge recovery",
                "status": "connected",
                "last_sync_at": iso(at(AS_OF, AS_OF_HOUR - 2, 30)),
                "expires_at": None,
            },
            {
                "id": "zen_planner",
                "name": "Zen Planner",
                "scope": "Available if you migrate from Mindbody",
                "status": "not_connected",
                "last_sync_at": None,
                "expires_at": None,
            },
        ],
    }


def write(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    rows = len(payload) if isinstance(payload, list) else 1
    size = path.stat().st_size / 1024
    print(f"  {path.name:<18} {rows:>5} record(s)  {size:>7.1f} kB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="test")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = HERE / args.account
    out.mkdir(parents=True, exist_ok=True)

    members = build_members(rng)
    visits = build_visits(rng, members)
    charges = build_charges(rng, members)
    posts, claims = build_posts_and_claims(rng, members)
    messages = build_messages(members, visits)

    # The habit knobs shaped the check-in log and must not leak into the
    # output: the dashboard has to infer behaviour from visits alone.
    for member in members:
        member.pop("_habit", None)
        member.pop("_fade", None)
        member.pop("_fade_start", None)

    print(f"accounts/{args.account} (seed {args.seed}, as of {AS_OF})")
    write(out / "account.json", build_account())
    write(out / "members.json", members)
    write(out / "visits.json", visits)
    write(out / "charges.json", charges)
    write(out / "posts.json", posts)
    write(out / "pass_claims.json", claims)
    write(out / "messages.json", messages)

    active = sum(1 for m in members if m["status"] == "active")
    print(f"  {active} active of {len(members)} members, {len(visits)} check-ins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
