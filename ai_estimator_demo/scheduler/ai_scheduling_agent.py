"""
PowWash AI Scheduling Agent.

A GPT-4 powered agent that reasons about the best available slots for a new job.
Completely decoupled from the customer-facing AI — this agent only deals with
logistics: calendar availability, driving times, engineer routing.

Architecture
────────────
  1. Gather context: engineer profiles, scheduling rules, agent instructions,
     Google Calendar events for the next N days, driving times via Maps API.
  2. Format everything as a structured prompt.
  3. Ask GPT-4 to reason and return 2–3 slot recommendations with plain-English
     explanations.
  4. Return structured recommendations to the caller (customer AI or UI).

The customer AI receives the recommendations and presents them conversationally.
It does not do any calendar reasoning itself.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from pg_store import PersistentFile  # Postgres-backed persistence (survives Autoscale restarts)
_AGENT_CONFIG_PATH = PersistentFile(Path(__file__).resolve().parent / "ai_agent_config.json")

# ── Agent config (natural language instructions + settings) ──────────────────

def load_agent_config() -> dict:
    """Load the AI scheduling agent configuration."""
    defaults = {
        "instructions": (
            "You are a smart scheduling assistant for PowWash, an exterior cleaning company.\n"
            "Your job is to find the best 2–3 available slots for a new cleaning job, "
            "taking into account travel time, existing bookings, and engineer routing.\n\n"
            "Key principles:\n"
            "- Group jobs in the same area on the same day where possible.\n"
            "- Minimise total travel time for each engineer.\n"
            "- Respect engineer priority rules (fill Priority 1 calendars first).\n"
            "- For the North engineer, keep jobs within a sensible driving radius "
            "and avoid mixing city clusters (e.g. don't mix Birmingham and Manchester on the same day).\n"
            "- Prefer slots where a near-home job can be done first or last in the day.\n"
            "- Always be honest about travel-time accuracy: if driving times are "
            "estimates (not Google Maps), say so.\n"
        ),
        "maxDaysAhead": 21,
        "preferredWorkingHours": {"start": "08:00", "end": "18:00"},
        "defaultJobDurationMins": 120,
    }
    try:
        saved = json.loads(_AGENT_CONFIG_PATH.read_text())
        return {**defaults, **saved}
    except Exception:
        return defaults


def save_agent_config(cfg: dict) -> dict:
    existing = load_agent_config()
    merged = {**existing, **cfg}
    _AGENT_CONFIG_PATH.write_text(json.dumps(merged, indent=2))
    return merged


# ── Job duration resolution ──────────────────────────────────────────────────
import re as _dur_re

_DUR_TEXT_RE = _dur_re.compile(
    r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b", _dur_re.IGNORECASE
)


def parse_duration_mins(text: str) -> Optional[int]:
    """Extract an explicit job-time estimate from free text (e.g. owner advice
    'this will take 3 hours', customer 'about 90 minutes'). Returns minutes or
    None. Picks the LARGEST match so a phrase like 'around 2-3 hours' resolves
    to the longer, safer estimate. Ignores tiny values that are clearly not job
    lengths (< 30 min)."""
    if not text:
        return None
    best = None
    for num, unit in _DUR_TEXT_RE.findall(text):
        try:
            val = float(num)
        except ValueError:
            continue
        u = unit.lower()
        mins = val * 60 if u.startswith(("hour", "hr", "h")) else val
        mins = int(round(mins))
        if mins < 30 or mins > 600:  # sanity bounds — a real exterior-clean job
            continue
        if best is None or mins > best:
            best = mins
    return best


def duration_for_service(service_type: str, cfg: dict | None = None) -> int:
    """Resolve a realistic job duration (minutes) for a service description.
    Matches any configured service keyword found in the text (longest keyword
    wins, so 'gutter clean' → gutter not a generic default). Falls back to
    defaultJobDurationMins when no keyword matches."""
    if cfg is None:
        cfg = load_agent_config()
    default = int(cfg.get("defaultJobDurationMins", 120))
    table = cfg.get("serviceDurationsMins") or {}
    if not service_type or not table:
        return default
    s = service_type.lower()
    best_kw, best_val = "", None
    for kw, mins in table.items():
        if kw.lower() in s and len(kw) > len(best_kw):
            best_kw, best_val = kw, int(mins)
    return best_val if best_val is not None else default


def resolve_job_duration(service_type: str, notes: str = "",
                         cfg: dict | None = None) -> int:
    """Best job duration: an EXPLICIT time stated in notes/advice wins
    (owner's quote feedback 'allow 3 hours'); otherwise the per-service
    default."""
    explicit = parse_duration_mins(notes or "")
    if explicit is not None:
        return explicit
    return duration_for_service(service_type, cfg)


# ── Recommendation engine ────────────────────────────────────────────────────

_TIME_PREF_RE = re.compile(
    r"\b(morning|afternoon|evening|midday|noon|lunch|asap|earliest|first thing|"
    r"\d{1,2}\s*(?:am|pm)|\d{1,2}[:.]\d{2})\b",
    re.IGNORECASE,
)


def _real_slot_index(context: dict) -> dict:
    """{engineer_name_lower: [ {start,end,label}, ... ]} of REAL free slots,
    chronologically sorted, taken from the calendar context."""
    idx: dict[str, list] = {}
    days = (context.get("calendarData") or {}).get("days", {}) or {}
    for _date, info in days.items():
        for eng, slots in (info.get("engineers") or {}).items():
            idx.setdefault(eng.lower(), []).extend(slots or [])
    for k in idx:
        idx[k].sort(key=lambda s: s.get("start", ""))
    return idx


def _slot_minutes(iso: str):
    try:
        return int(iso[11:13]) * 60 + int(iso[14:16])
    except Exception:
        return None


def _reconcile_recommendations(recs: list, context: dict,
                               customer_notes: str = "") -> list:
    """Make recommendations trustworthy:

    1. SNAP every rec to a REAL free slot for that engineer (the LLM sometimes
       fabricates a time that isn't actually free — e.g. one running past the
       16:00 close). Drops recs whose engineer has no real availability.
    2. FILL FROM THE FRONT: when the customer states no time-of-day preference,
       use the deterministic earliest-first (cluster-aware) ordering so the
       diary packs gap-free instead of leaving silly mid-day gaps.
    """
    idx = _real_slot_index(context)
    if not idx:
        return recs

    fixed = []
    for r in recs:
        eng = (r.get("engineer") or "").lower()
        ekey = next(
            (k for k in idx
             if k == eng or k in eng or eng in k
             or (eng and k.split() and k.split()[0] in eng)),
            None,
        )
        if not ekey or not idx[ekey]:
            continue
        slots = idx[ekey]
        want = (r.get("rawSlot") or {}).get("start") or ""
        chosen = next((s for s in slots if s["start"] == want), None)
        if not chosen:
            wm = _slot_minutes(want)
            same_day = [s for s in slots if s["start"][:10] == want[:10]]
            pool = same_day or slots
            if wm is None:
                chosen = pool[0]
            else:
                chosen = min(pool, key=lambda s: abs((_slot_minutes(s["start"]) or 0) - wm))
        r["rawSlot"] = {"start": chosen["start"], "end": chosen["end"]}
        r["timeSlot"] = chosen.get("label", r.get("timeSlot", ""))
        fixed.append(r)

    # De-dup by (engineer, start)
    seen, uniq = set(), []
    for r in fixed:
        key = ((r.get("engineer") or "").lower(), (r.get("rawSlot") or {}).get("start"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    fixed = uniq

    # No explicit time preference → FILL FROM THE FRONT, but only within the
    # engineer + day the agent already chose (preserving its geographic
    # routing). Pull each option's start to the earliest free slot on that
    # engineer's chosen day so the diary packs without silly mid-day gaps.
    if not _TIME_PREF_RE.search(customer_notes or ""):
        for r in fixed:
            eng = (r.get("engineer") or "").lower()
            ekey = next(
                (k for k in idx
                 if k == eng or k in eng or eng in k
                 or (eng and k.split() and k.split()[0] in eng)),
                None,
            )
            if not ekey:
                continue
            day = ((r.get("rawSlot") or {}).get("start") or "")[:10]
            same_day = [s for s in idx[ekey] if s["start"][:10] == day]
            if same_day:
                earliest = same_day[0]
                r["rawSlot"] = {"start": earliest["start"], "end": earliest["end"]}
                r["timeSlot"] = earliest.get("label", r.get("timeSlot", ""))

        # Re-de-dup IN PLACE (rank-1/2 on the same engineer+day may now collapse
        # to the same slot). Preserve the agent's original option order so its
        # cross-engineer geographic routing is never reshuffled.
        seen2, uniq2 = set(), []
        for r in fixed:
            key = ((r.get("engineer") or "").lower(), (r.get("rawSlot") or {}).get("start"))
            if key in seen2:
                continue
            seen2.add(key)
            uniq2.append(r)
        fixed = uniq2

    for i, r in enumerate(fixed, start=1):
        r["rank"] = i
    # If reconciliation dropped everything (e.g. no recommended engineer matched
    # a real free slot) never leak the LLM's possibly-fabricated times — fall
    # back to deterministic REAL-slot recommendations instead.
    return fixed or _fallback_recommendations(context)


def recommend_slots(
    job_postcode: str,
    service_type: str,
    duration_mins: Optional[int] = None,
    customer_notes: str = "",
    target_date: Optional[str] = None,
) -> dict:
    """
    Ask the AI scheduling agent to recommend the best slots for a new job.

    Args:
        job_postcode:   The job location (e.g. "B1 1AA" or "B1")
        service_type:   Service description (e.g. "driveway clean", "render wash")
        duration_mins:  Estimated job duration (defaults to config value)
        customer_notes: Any timing preferences from the customer
        target_date:    ISO date string if customer wants a specific date

    Returns:
        {
          "ok": True,
          "recommendations": [
            {
              "rank": 1,
              "engineer": "Dan",
              "date": "Monday 9 June",
              "timeSlot": "09:00 – 11:00",
              "travelNote": "Joins a Birmingham day — 8km from previous job",
              "reasoning": "Best route efficiency. Dan already has a job in B4 that morning...",
              "rawSlot": {...}
            },
            ...
          ],
          "agentReasoning": "Full reasoning text...",
          "mapsSource": "google_maps" | "haversine_estimate",
          "caveat": None | "..."
        }
    """
    import anthropic
    import re as _re

    cfg = load_agent_config()
    # Per-job duration: caller override > explicit time in notes (owner quote
    # feedback / customer) > per-service default. This is what makes different
    # services book as different-sized events instead of a flat 2h block.
    dur = duration_mins or resolve_job_duration(service_type, customer_notes, cfg)

    # ── Gather context ──────────────────────────────────────────────────────
    context = _build_context(job_postcode, service_type, dur, customer_notes, target_date, cfg)

    # ── Coverage gap: the only engineers covering this area are unticked or have
    #    no calendar linked. Do NOT invent a booking — flag for a human and stop. ─
    blocked = context.get("blockedEngineers", [])
    if not context.get("eligibleEngineers") and blocked:
        logger.info(
            "Coverage gap for %s — blocked engineers: %s",
            job_postcode, ", ".join(b.get("name", "?") for b in blocked),
        )
        return {
            "ok": True,
            "recommendations": [],
            "coverageGap": True,
            "blockedEngineers": blocked,
            "jobPostcode": job_postcode,
            "agentReasoning": "",
        }

    # ── Build prompt ────────────────────────────────────────────────────────
    system_prompt = cfg.get("instructions", "")
    user_prompt   = _build_user_prompt(context)

    # ── Call Claude ─────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2500,
            temperature=0,
            system=(
                system_prompt
                + "\n\n"
                  "ARCHITECTURE: You are the logistics AI. You do NOT speak to the customer directly. "
                  "The customer liaison AI agent handles all customer communication. "
                  "When you need to flag uncertainties (e.g. unclear job duration, missing details), "
                  "write them as notes in the 'caveat' field addressed to the liaison AI — "
                  "e.g. 'Liaison AI should confirm actual duration with customer before booking.' "
                  "Never phrase caveats as if you are speaking to the customer yourself.\n\n"
                  "IMPORTANT: Respond with valid JSON only. "
                  "No markdown code fences, no explanation outside the JSON object."
            ),
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip any accidental markdown fences
        raw = _re.sub(r"^```(?:json)?\s*", "", raw)
        raw = _re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        recommendations = parsed.get("recommendations", []) or []
        agent_reasoning = parsed.get("reasoning", "")

        # ── Reliability guardrail ───────────────────────────────────────────
        # Slot picking is deterministic, but the LLM occasionally returns an
        # empty recommendations list even when the calendar has real free slots
        # (intermittent refusal / over-cautious reasoning). Never let that
        # surface as a false "no availability" — fall back to the real slots.
        if not recommendations:
            fb = _fallback_recommendations(context)
            if fb:
                logger.info(
                    "Scheduling agent returned no recommendations for %s — "
                    "using deterministic fallback (%d slots).",
                    context.get("jobPostcode"), len(fb),
                )
                recommendations = fb
                agent_reasoning = (
                    agent_reasoning
                    or "Auto-selected the earliest available slots matching the request."
                )

        # Snap to REAL free slots + fill-from-front when no time preference.
        recommendations = _reconcile_recommendations(
            recommendations, context, customer_notes
        )

        return {
            "ok": True,
            "recommendations": recommendations,
            "agentReasoning":  agent_reasoning,
            "mapsSource":      context.get("mapsSource", "haversine_estimate"),
            "caveat":          context.get("mapsCaveat"),
        }
    except Exception as exc:
        logger.error("Scheduling agent Claude call failed: %s", exc)
        # Even on a hard failure (bad JSON, API error), still offer real slots
        # rather than going silent when the calendar clearly has availability.
        fb = _fallback_recommendations(context)
        if fb:
            logger.info("Falling back to deterministic slots after agent error.")
            return {
                "ok": True,
                "recommendations": fb,
                "agentReasoning": "Auto-selected the earliest available slots matching the request.",
                "mapsSource":     context.get("mapsSource", "haversine_estimate"),
                "caveat":         context.get("mapsCaveat"),
            }
        return {
            "ok": False,
            "error": str(exc),
            "recommendations": [],
            "agentReasoning": "",
        }


def _fallback_recommendations(context: dict, limit: int = 3) -> list:
    """
    Build recommendations deterministically from the real free slots in the
    calendar context. Used when the LLM returns nothing. Honours the customer's
    target date when one is set, and prefers days/engineers that already have a
    nearby job (clustering) so routing stays tight.
    """
    cal_days = (context.get("calendarData") or {}).get("days", {}) or {}
    existing = (context.get("calendarData") or {}).get("existing_jobs", {}) or {}
    target   = context.get("targetDate")

    # Flatten to (date_str, engineer, slot) tuples.
    flat = []
    for date_str in sorted(cal_days.keys()):
        for eng_name, slots in (cal_days[date_str].get("engineers", {}) or {}).items():
            for s in slots:
                flat.append((date_str, eng_name, s))
    if not flat:
        return []

    # Prefer the requested date if it has any slots; otherwise use all upcoming.
    if target:
        same_day = [t for t in flat if t[0] == target]
        if same_day:
            flat = same_day

    # Clustering hint: rank days that already have a booking first.
    def sort_key(t):
        date_str, eng_name, slot = t
        has_cluster = 0 if existing.get(date_str) else 1
        return (has_cluster, date_str, slot.get("start", ""))
    flat.sort(key=sort_key)

    from datetime import datetime as _dt
    out = []
    for rank, (date_str, eng_name, slot) in enumerate(flat[:limit], start=1):
        try:
            date_label = _dt.fromisoformat(date_str).strftime("%A %d %B %Y")
        except Exception:
            date_label = date_str
        cluster = " (clusters with an existing job nearby)" if existing.get(date_str) else ""
        out.append({
            "rank": rank,
            "engineer": eng_name,
            "date": date_label,
            "timeSlot": slot.get("label", ""),
            "travelNote": f"Auto-selected from {eng_name}'s real availability{cluster}.",
            "reasoning": "Deterministic fallback: earliest real free slot matching the request.",
            "rawSlot": {"start": slot.get("start"), "end": slot.get("end")},
        })
    return out


# ── Context builder ──────────────────────────────────────────────────────────

def _build_context(
    job_postcode: str,
    service_type: str,
    duration_mins: int,
    customer_notes: str,
    target_date: Optional[str],
    cfg: dict,
) -> dict:
    """Gather all data the agent needs to reason about slots."""
    from .smart_scheduler import get_coverage_status, load_rules
    from .maps_client import get_driving_time, get_maps_api_key

    rules    = load_rules()
    coverage = get_coverage_status(job_postcode)
    eligible = coverage["eligible"]
    blocked  = coverage["blocked"]

    # Calendar events for next N days
    days_ahead = cfg.get("maxDaysAhead", 21)
    calendar_data = _fetch_calendar_context(eligible, days_ahead, duration_mins)

    # Driving times from job location to any existing same-day job postcodes
    driving_times = {}
    maps_source   = "haversine_estimate"
    maps_caveat   = None
    maps_key      = get_maps_api_key()

    for day_key, jobs in calendar_data.get("existing_jobs", {}).items():
        for j in jobs:
            ep = (j.get("postcode") or j.get("address") or "").strip()
            if ep and ep != job_postcode:
                # Use the existing job's start time so the driving estimate reflects
                # traffic at that time of day (morning rush vs midday vs evening).
                depart = j.get("start") or None
                result = get_driving_time(job_postcode, ep, depart_time=depart)
                driving_times[f"{job_postcode}→{ep}"] = result
                if result.get("source") == "google_maps":
                    maps_source = "google_maps"
                if result.get("caveat") and not maps_caveat:
                    maps_caveat = result["caveat"]

    # Working hours for the PROMPT must match the ones used to GENERATE real slots
    # (calendar_client config: soft `end` 16:00 + hard `overtimeEnd` 17:00), or the
    # model is told 08:00–18:00 while the slots stop at 16:00/17:00 — a contradiction.
    # Prefer the calendar config; fall back to the agent config only if unavailable.
    wh = cfg.get("preferredWorkingHours", {"start": "08:00", "end": "18:00"})
    try:
        from . import calendar_client as _cc_wh
        _cal_wh = _cc_wh.load_config().get("workingHours")
        if _cal_wh:
            wh = _cal_wh
    except Exception:
        pass

    return {
        "jobPostcode":    job_postcode,
        "serviceType":    service_type,
        "durationMins":   duration_mins,
        "customerNotes":  customer_notes,
        "targetDate":     target_date,
        "eligibleEngineers": eligible,
        "blockedEngineers":  blocked,
        "schedulingRules":   rules,
        "calendarData":      calendar_data,
        "workingHours":      wh,
        "drivingTimes":      driving_times,
        "mapsSource":        maps_source,
        "mapsCaveat":        maps_caveat,
        "hasMapsKey":        bool(maps_key),
    }


def _fetch_calendar_context(engineers: list, days_ahead: int, duration_mins: int = 120) -> dict:
    """
    Fetch calendar events for each engineer for the next N days.
    Returns a structured summary safe to embed in a prompt.
    """
    try:
        from . import calendar_client as _cc
        config = _cc.load_config()
    except Exception:
        return {"available": False, "reason": "Google Calendar not configured"}

    # Work entirely in the business timezone (e.g. Europe/London) so slot labels
    # and bookings reflect true local working hours — not UTC (which is 1h off in
    # BST). create_event also books in this same tz, so proposed == booked time.
    tz   = _cc.business_tz()
    now  = datetime.now(tz)
    days = {}
    existing_jobs: dict[str, list] = {}

    duration    = duration_mins or 120
    buffer_mins = config.get("travelBufferMinutes", 20)
    working_hrs = config.get("workingHours") or config.get("preferredWorkingHours")

    # Build the working-day structure (Mon–Fri only; weekends are not bookable)
    for i in range(days_ahead):
        day = now + timedelta(days=i)
        if day.weekday() >= 5:   # 5=Sat, 6=Sun
            continue
        date_str = day.strftime("%Y-%m-%d")
        days[date_str] = {"weekday": day.strftime("%A"), "engineers": {}}

    for eng in engineers:
        cal_id   = eng.get("calendarId") or config.get("calendarId") or "primary"
        eng_name = eng.get("name", "Engineer")
        try:
            # ONE events fetch for the whole window, reused for every day below
            events = _cc.list_events(cal_id, now, now + timedelta(days=days_ahead)) or []

            # Real free slots per working day (past times already excluded by
            # find_free_slots). Pass pre-fetched events so we don't re-hit the API.
            for date_str, day_info in days.items():
                target = datetime.fromisoformat(date_str).replace(
                    hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
                )
                slots = _cc.find_free_slots(
                    calendar_id=cal_id,
                    target_date=target,
                    duration_mins=duration,
                    working_hours=working_hrs,
                    travel_buffer_mins=buffer_mins,
                    events=events,
                )
                if slots:
                    day_info["engineers"][eng_name] = [
                        {
                            "start": s["start"],
                            "end":   s["end"],
                            "label": f"{s['startLabel']} – {s['endLabel']}",
                            "overtime": s.get("overtime", False),
                        }
                        for s in slots
                    ]

            # Existing bookings for routing/grouping context
            for event in events:
                start = event.get("start", {}).get("dateTime", "")
                if start:
                    date_key = start[:10]
                    existing_jobs.setdefault(date_key, [])
                    location = event.get("location", "")
                    postcode = _extract_postcode(location)
                    existing_jobs[date_key].append({
                        "engineer":   eng_name,
                        "engineerId": eng.get("id"),
                        "title":      event.get("summary", ""),
                        "start":      start,
                        "location":   location,
                        "postcode":   postcode,
                    })
        except Exception as exc:
            logger.debug("Calendar fetch for %s failed: %s", eng.get("name"), exc)

    return {
        "available": True,
        "days": days,
        "existing_jobs": existing_jobs,
        "daysAhead": days_ahead,
    }


def _extract_postcode(text: str) -> str:
    """Extract a UK postcode from a text string if present."""
    import re
    match = re.search(
        r"\b([A-Z]{1,2}[0-9][0-9A-Z]?\s?[0-9][A-Z]{2})\b",
        (text or "").upper(),
    )
    return match.group(1) if match else ""


# ── Prompt builder ───────────────────────────────────────────────────────────

def _build_user_prompt(ctx: dict) -> str:
    engineers_summary = []
    for e in ctx.get("eligibleEngineers", []):
        engineers_summary.append(
            f"  - {e['name']} (Priority {e.get('priority',1)}, "
            f"region: {e.get('region','both')}, home: {e.get('homePostcode','unknown')})"
        )

    existing_summary = []
    for date_str, jobs in sorted(ctx.get("calendarData", {}).get("existing_jobs", {}).items()):
        from datetime import datetime
        try:
            wd = datetime.fromisoformat(date_str).strftime("%A %d %b")
        except Exception:
            wd = date_str
        for j in jobs:
            loc = f" at {j['location']}" if j.get("location") else ""
            pc  = f" [{j['postcode']}]" if j.get("postcode") else ""
            existing_summary.append(f"  {wd}: {j['engineer']} — {j['title']}{loc}{pc}")

    # Real, bookable free slots per day per engineer (past times already excluded).
    # The agent MUST choose only from these — it must never invent a start time.
    avail_summary = []
    _cal_days = ctx.get("calendarData", {}).get("days", {})
    for date_str in sorted(_cal_days.keys()):
        day_info = _cal_days[date_str]
        eng_slots = day_info.get("engineers", {})
        if not eng_slots:
            continue
        from datetime import datetime as _dt2
        try:
            wd_label = _dt2.fromisoformat(date_str).strftime("%A %d %b %Y")
        except Exception:
            wd_label = f"{day_info.get('weekday','')} {date_str}"
        for eng_name, slots in eng_slots.items():
            labels = ", ".join(
                (s["label"] + " (OVERTIME)") if s.get("overtime") else s["label"]
                for s in slots[:8]
            )
            avail_summary.append(f"  {wd_label} — {eng_name}: {labels}")

    driving_summary = []
    for pair, result in ctx.get("drivingTimes", {}).items():
        if result.get("durationMins") is not None:
            source_flag = "" if result["source"] == "google_maps" else " (estimate)"
            traffic_flag = ""
            if result.get("trafficAware"):
                static_mins = result.get("durationStaticMins")
                if static_mins is not None and static_mins != result["durationMins"]:
                    traffic_flag = f" (incl. traffic at job time; {static_mins} mins off-peak)"
                else:
                    traffic_flag = " (incl. traffic at job time)"
            driving_summary.append(
                f"  {pair}: {result['durationMins']} mins, {result['distanceKm']}km{source_flag}{traffic_flag}"
            )

    maps_note = (
        "IMPORTANT: Driving times are ESTIMATES based on straight-line distance × 1.35. "
        "They are NOT accurate for city routing. Flag this clearly in your recommendations."
        if not ctx.get("hasMapsKey")
        else "Driving times provided by Google Maps (accurate)."
    )

    target_note = ""
    has_preference = False
    if ctx.get("targetDate"):
        target_note = f"\nCustomer preference: {ctx['targetDate']}"
        has_preference = True
    if ctx.get("customerNotes"):
        target_note += f"\nCustomer notes / availability: {ctx['customerNotes']}"
        has_preference = True
    if has_preference:
        target_note += (
            "\n\nPREFERENCE MATCHING RULE: The customer has stated a preferred day or time. "
            "Rank your recommendations to match this preference first. If an exact match is available, "
            "put it as rank 1. If not, find the closest alternative (nearest day, closest time) and "
            "explain in the reasoning why the exact preference wasn't available."
            "\n\nAVAILABILITY-WINDOW RULE: If the note describes when the customer is or isn't "
            "available (e.g. 'back from the school run by 8:15', 'not before 9', 'only mornings', "
            "'after 2pm'), NEVER offer a slot that starts before they are free. Pick the next sensible "
            "slot at or after that time — e.g. if they are free from 8:15, a 08:00 start is wrong; offer "
            "a later morning slot instead. There is usually travel-buffer slack in the day to absorb a "
            "slightly later start, so honour their constraint rather than forcing the earliest slot."
        )

    rules = ctx.get("schedulingRules", {})
    wh    = ctx.get("workingHours", {"start": "08:00", "end": "18:00"})
    wh_start = wh.get("start", "08:00")
    wh_end   = wh.get("end",   "18:00")

    from datetime import datetime as _dt, timedelta as _td
    _now      = _dt.now()
    today_str = _now.strftime("%A %d %B %Y")

    # Pre-compute the next 21 days so the LLM never has to guess day-of-week
    _day_calendar = "\n".join(
        f"  {(_now + _td(days=i)).strftime('%Y-%m-%d')} = {(_now + _td(days=i)).strftime('%A')}"
        for i in range(21)
    )

    return f"""TODAY'S DATE: {today_str}
All slot recommendations MUST be on or after today's date and in {_now.year}. Do not suggest dates in the past, in a different year, or more than 14 days ahead unless no earlier slots are available.
CRITICAL: Every "date" field in your JSON response MUST include the full 4-digit year (e.g. "Tuesday 9 June {_now.year}"). Never omit the year.
CRITICAL: Use the calendar below for correct day-of-week — do NOT compute day names from memory:

CORRECT DAY-OF-WEEK FOR UPCOMING DATES:
{_day_calendar}

NEW JOB REQUEST
===============
Location (postcode): {ctx['jobPostcode']}
Service: {ctx['serviceType']}
Estimated duration: {ctx['durationMins']} minutes{target_note}

WORKING WINDOW (STRICT — slots must fall within these times)
=============================================================
Working hours: {wh_start} – {wh_end}, Monday–Friday
Earliest a job may START: {wh_start}
TARGET finish (aim for this): {wh_end}
Latest a job may END (overtime cap, use sparingly): {wh.get('overtimeEnd', wh_end)}
Travel buffer between consecutive jobs on the SAME day: {rules.get('travelBufferMinutes', 20) if hasattr(rules.get('travelBufferMinutes', 20), '__int__') else 20} mins

REAL AVAILABLE SLOTS (CHOOSE ONLY FROM THESE — already filtered to future, in-hours, conflict-free)
Listed in chronological order — EARLIEST dates first.
=====================================================================================================
{chr(10).join(avail_summary) if avail_summary else "  No bookable slots found in the window (calendar may not be connected, or the diary is full)."}

ABSOLUTE RULE — DO NOT INVENT TIMES:
Every slot you recommend MUST be copied exactly from the REAL AVAILABLE SLOTS list above.
Never make up a start time, never default to {wh_start}, never offer a time that is not in that list.
These slots are already guaranteed to be in the future, within working hours, and free of conflicts.
Each recommendation is a SEPARATE OPTION on a DIFFERENT DAY for the same single job — they are
alternatives, not a sequence. If the list is empty, return an empty "recommendations" array and
explain in the reasoning that no slots are currently available.

ELIGIBLE ENGINEERS
==================
{chr(10).join(engineers_summary) if engineers_summary else "  None found for this region"}

SCHEDULING RULES
================
- Fill-ahead days (P1 must be booked this far ahead before offering P2): {rules.get('fillAheadDays', 5)}
- South/London max grouping radius: {rules.get('londonMaxGroupingKm', 20)}km
- North max grouping radius: {rules.get('northMaxGroupingKm', 60)}km

EXISTING CALENDAR BOOKINGS (next {ctx.get('calendarData',{}).get('daysAhead', 21)} days)
==================
{chr(10).join(existing_summary) if existing_summary else "  No existing bookings found (calendar may not be connected)"}

DRIVING TIMES TO EXISTING JOBS
================================
{chr(10).join(driving_summary) if driving_summary else "  No existing jobs nearby to compare"}
{maps_note}

YOUR TASK
=========
Identify the 2–3 best available slots for this job.

#1 PRIORITY — FILL THE DIARY FROM THE FRONT (EARLIEST FIRST):
Offer the SOONEST available dates. Work down the chronological list from the top.
A completely empty earlier weekday is BETTER than a later day — never skip an
earlier available day in favour of a later one. The goal is to keep the team's
week full by booking the nearest open slots before pushing work further out.
Rank 1 should normally be the earliest workable slot.

Grouping/route efficiency is a TIE-BREAKER, not a reason to push the job later:
- If two days are close together (e.g. Tuesday vs Wednesday) and the LATER one
  groups with an existing nearby job, you may prefer it ONLY when the time saved
  is significant. A day or more of extra delay is NOT worth a small travel saving.
- Never recommend a later day over an earlier EMPTY day just to cluster jobs
  unless the customer specifically asked for that later day.

PACK EACH DAY — DON'T LEAVE EARLY FINISHES:
Jobs do NOT have to slot together like a perfect jigsaw, but the aim is full days.
Prefer filling the remaining gaps of a part-booked EARLIER day (even an afternoon
slot) over opening a brand-new later day — a slot at 14:00 today beats 08:00
tomorrow. The standard target is to be FINISHED BY 16:00.

OVERTIME SLOTS (marked "(OVERTIME)" — these finish between 16:00 and 17:00):
- Treat overtime as a last resort to AVOID pushing a job onto a new day. If a
  normal (≤16:00) slot exists earlier or on the same day, always prefer it.
- Finishing by ~16:30 is fine occasionally; a full 17:00 finish should be rare
  (think no more than once a fortnight) and rarer still for the North engineer.
- Only reach for an overtime slot when the alternative is leaving the day
  under-filled and bumping the customer further out.

After earliest-availability, then consider:
1. Which nearby days have existing jobs (good for grouping, less travel)?
2. For the North engineer: does this job fit a sensible route from their home base?
3. Are there days where this job would be a first or last slot near the engineer's home?
4. Priority rules: is the P1 engineer's calendar filled ahead before offering P2?
5. ALL proposed slots must respect the working window above. Start times for each day are independent — do NOT offset them based on other recommendations.

(If the customer stated a preferred day/time, the PREFERENCE MATCHING RULE above
overrides earliest-first — match their preference at rank 1.)

Return a JSON object in exactly this format:
{{
  "reasoning": "2–3 paragraph explanation of your thinking",
  "recommendations": [
    {{
      "rank": 1,
      "engineer": "engineer name",
      "date": "Monday 9 June 2026",
      "timeSlot": "10:00 – 12:00",
      "travelNote": "brief travel context (e.g. '8km from existing B4 job')",
      "reasoning": "why this is a good slot",
      "confidence": "high|medium|low",
      "caveat": "any caveats or items for the liaison AI to verify with the customer",
      "rawSlot": {{
        "start": "2026-06-09T10:00:00",
        "end": "2026-06-09T12:00:00"
      }}
    }}
  ]
}}

IMPORTANT: rawSlot must use ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
"""
