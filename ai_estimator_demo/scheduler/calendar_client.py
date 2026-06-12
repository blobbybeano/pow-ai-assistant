"""
Google Calendar API wrapper for PowWash Scheduler.

Authentication uses direct Google OAuth 2.0 — credentials are stored in
calendar_tokens.json after the user completes the in-app OAuth flow.
Falls back gracefully when not connected.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

logger = logging.getLogger(__name__)

# ── Service abbreviation map ──────────────────────────────────────────────────
_SERVICE_ABBREVS: dict[str, str] = {
    "gutter clean":          "G.C",
    "gutter cleaning":       "G.C",
    "gutter clearance":      "G.C",
    "gutter":                "G.C",
    "pressure wash":         "P.W",
    "pressure washing":      "P.W",
    "pressure clean":        "P.W",
    "pressure cleaning":     "P.W",
    "jet wash":              "J.W",
    "jet washing":           "J.W",
    "driveway clean":        "D.C",
    "driveway cleaning":     "D.C",
    "driveway wash":         "D.W",
    "softwash":              "S.W",
    "soft wash":             "S.W",
    "softwashing":           "S.W",
    "roof clean":            "R.C",
    "roof cleaning":         "R.C",
    "roof softwash":         "R.S",
    "window clean":          "W.C",
    "window cleaning":       "W.C",
    "fascia clean":          "F.C",
    "fascia cleaning":       "F.C",
    "conservatory clean":    "Con.C",
    "conservatory cleaning": "Con.C",
    "patio clean":           "Pat.C",
    "patio wash":            "Pat.W",
    "render clean":          "Rnd.C",
    "render cleaning":       "Rnd.C",
    "solar panel clean":     "SP.C",
    "solar clean":           "SP.C",
}


def _service_abbr(service: str) -> str:
    """Map a service name to a short abbreviation, e.g. 'Gutter Clean' → 'G.C'."""
    key = service.lower().strip()
    if key in _SERVICE_ABBREVS:
        return _SERVICE_ABBREVS[key]
    for k, v in _SERVICE_ABBREVS.items():
        if k in key:
            return v
    # Fallback: capitalised initials e.g. "Fascia Softwash" → "F.S"
    words = [w for w in re.split(r"\s+", service) if w]
    if len(words) >= 2:
        return ".".join(w[0].upper() for w in words[:3])
    return service[:4]


def _postcode_start(job_spec: dict) -> str:
    """Extract the outward postcode code (e.g. 'SW19') from postcode or address field."""
    for field in ("postcode", "address"):
        val = (job_spec.get(field) or "").strip().upper()
        if not val:
            continue
        m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", val)
        if m:
            return m.group(1)
    return ""

from pg_store import PersistentFile  # Postgres-backed persistence (survives Autoscale restarts)
CALENDAR_CONFIG_PATH = PersistentFile(Path(__file__).resolve().parent.parent / "calendar_config.json")
CALENDAR_TOKENS_PATH = PersistentFile(Path(__file__).resolve().parent.parent / "calendar_tokens.json")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_DEFAULT_CONFIG = {
    "calendarId": "",
    "businessTimezone": "Europe/London",
    # `end` is the SOFT target finish (aim to be done by 16:00). `overtimeEnd` is
    # the HARD cap — a job may finish in the 16:00–17:00 band when it lets us pack
    # the day instead of bumping it to a new day, but never past overtimeEnd.
    "workingHours": {"start": "08:00", "end": "16:00", "overtimeEnd": "17:00", "days": [1, 2, 3, 4, 5]},
    "holdTimeoutMinutes": 30,
    "travelBufferMinutes": 60,
    "eventFormat": {
        "titleTemplate": "{postcodeStart} {serviceAbbr} {customerName}",
        "descriptionTemplate": (
            "[notes]\n"
            "Notes: {notes}\n"
            "[/notes]\n"
            "\n"
            "[contact]\n"
            "Customer name: {customerName}\n"
            "Customer email address: {customerEmail}\n"
            "Customer contact number: {phone}\n"
            "[/contact]\n"
            "\n"
            "[invoice]\n"
            "{serviceLines}\n"
            "\n"
            "\u2b07Sales\u2b07\n"
            "\n"
            "[/invoice]\n"
            "PROCESS DRAFT (Y/N) ="
        ),
        "colorId": "2",
    },
}

HOLD_TITLE_PREFIX = "\U0001f7e1 HOLD \u2014 PowWash"


def business_tz_name() -> str:
    """Configured business timezone name (e.g. 'Europe/London'). Used for both
    slot computation and event creation so proposed times == booked times."""
    try:
        return load_config().get("businessTimezone", "Europe/London")
    except Exception:
        return "Europe/London"


def business_tz():
    """Return a tzinfo for the configured business timezone (falls back to UTC)."""
    name = business_tz_name()
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return timezone.utc

CALENDAR_CREDS_PATH = PersistentFile(Path(__file__).resolve().parent.parent / "calendar_credentials.json")


def load_credentials() -> dict:
    """Load OAuth credentials from file (falls back to empty dict)."""
    try:
        return json.loads(CALENDAR_CREDS_PATH.read_text())
    except Exception:
        return {}


def save_credentials(client_id: str, client_secret: str) -> None:
    CALENDAR_CREDS_PATH.write_text(json.dumps({
        "client_id": client_id,
        "client_secret": client_secret,
    }, indent=2))


def load_config() -> dict:
    try:
        raw = json.loads(CALENDAR_CONFIG_PATH.read_text())
        cfg = dict(_DEFAULT_CONFIG)
        cfg.update(raw)
        return cfg
    except Exception:
        return dict(_DEFAULT_CONFIG)


def save_config(patch: dict) -> dict:
    # NOTE: After calling this, _sync_knowledge_from_cal_config() in app.py
    # MUST be called to keep ai_agent_config.json in sync with these values.
    # Working hours, travel buffer, and hold timeout are mirrored in the AI
    # scheduling agent's knowledge document — see the SYNC RULE block in app.py.
    cfg = load_config()
    cfg.update(patch)
    CALENDAR_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return cfg


def load_tokens() -> dict:
    try:
        return json.loads(CALENDAR_TOKENS_PATH.read_text())
    except Exception:
        return {}


def save_tokens(tokens: dict) -> None:
    CALENDAR_TOKENS_PATH.write_text(json.dumps(tokens, indent=2))


def clear_tokens() -> None:
    try:
        CALENDAR_TOKENS_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _client_id() -> str:
    return (
        os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        or load_credentials().get("client_id", "")
    )


def _client_secret() -> str:
    return (
        os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        or load_credentials().get("client_secret", "")
    )


def _get_service():
    """
    Build and return an authorised Google Calendar API service.
    Uses locally stored OAuth2 tokens with automatic refresh.
    Never cache the returned service — tokens may refresh each call.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    tokens = load_tokens()
    if not tokens.get("refresh_token"):
        raise RuntimeError(
            "Google Calendar not connected. "
            "Click 'Connect Google Calendar' in the Calendar tab."
        )

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=_client_id(),
        client_secret=_client_secret(),
        scopes=SCOPES,
    )

    if not creds.valid:
        creds.refresh(Request())
        save_tokens({
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or tokens["refresh_token"],
            "token_uri": creds.token_uri,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        })

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def check_connection() -> dict:
    """Return connection status and basic calendar info."""
    if not _client_id() or not _client_secret():
        return {
            "connected": False,
            "reason": "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured.",
            "needsCredentials": True,
        }
    tokens = load_tokens()
    if not tokens.get("refresh_token"):
        return {"connected": False, "reason": "Not authorised yet. Click Connect Google Calendar."}
    cfg = load_config()
    try:
        service = _get_service()
        cal_id = cfg.get("calendarId") or "primary"
        cal = service.calendars().get(calendarId=cal_id).execute()
        return {
            "connected": True,
            "calendarId": cal_id,
            "calendarSummary": cal.get("summary", cal_id),
            "timeZone": cal.get("timeZone", "UTC"),
        }
    except Exception as exc:
        return {"connected": False, "reason": str(exc)}


def list_calendars() -> list:
    """List all calendars the user has access to."""
    service = _get_service()
    result = service.calendarList().list().execute()
    return [
        {"id": c["id"], "summary": c.get("summary", c["id"]), "primary": c.get("primary", False)}
        for c in result.get("items", [])
    ]


def get_events(calendar_id: str, time_min: datetime, time_max: datetime) -> list:
    """Fetch events in a time window."""
    service = _get_service()

    # Google's events.list requires RFC3339 timestamps WITH a timezone offset.
    # A naive datetime serialises without one and triggers a 400 Bad Request, so
    # coerce any naive bound into the business timezone before sending.
    def _ensure_tz(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=business_tz())
        return dt

    resp = service.events().list(
        calendarId=calendar_id,
        timeMin=_ensure_tz(time_min).isoformat(),
        timeMax=_ensure_tz(time_max).isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return resp.get("items", [])


def find_free_slots(
    calendar_id: str,
    target_date: datetime,
    duration_mins: int,
    working_hours: dict | None = None,
    travel_buffer_mins: int = 20,
    events: list | None = None,
) -> list:
    """
    Return a list of free slot dicts {start, end, startLabel, endLabel}
    for the given date, respecting working hours and existing events.

    If `events` is provided (pre-fetched for a wider window), it is used directly
    instead of making a Google Calendar API call — this lets callers compute slots
    for many days from a single events fetch. Events outside the day window are
    harmlessly ignored by the overlap check.
    """
    # Only hit storage for config when the caller hasn't supplied working hours.
    # _fetch_calendar_context calls this once per day per engineer with
    # working_hours already provided, so reading config here would mean dozens of
    # redundant Postgres reads per request (and connection exhaustion under load).
    wh = working_hours
    if wh is None:
        wh = load_config().get("workingHours", _DEFAULT_CONFIG["workingHours"])

    start_h, start_m = (int(x) for x in wh["start"].split(":"))
    end_h, end_m = (int(x) for x in wh["end"].split(":"))

    day_start = target_date.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    # SOFT end = the target finish (aim to be done by here). HARD end = overtime cap.
    # Jobs may fit in the soft→hard band to pack a busy day, but never past the cap.
    soft_end = target_date.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    ot = wh.get("overtimeEnd")
    if ot:
        oh, om = (int(x) for x in ot.split(":"))
        day_end = target_date.replace(hour=oh, minute=om, second=0, microsecond=0)
    else:
        day_end = soft_end

    # ── Never offer slots in the past ────────────────────────────────────────
    # For "today", the working-hours start (e.g. 08:00) is in the past if it's
    # already the afternoon. Advance day_start to now + a minimum lead buffer so
    # we only ever suggest genuinely bookable future times.
    _MIN_LEAD = timedelta(hours=2)
    _now = datetime.now(day_start.tzinfo) if day_start.tzinfo else datetime.now()
    _earliest = _now + _MIN_LEAD
    if day_start < _earliest:
        day_start = _earliest
        # round up to the next 15-minute boundary for a clean slot time
        _rem = day_start.minute % 15
        if _rem or day_start.second or day_start.microsecond:
            day_start = (day_start + timedelta(minutes=(15 - _rem))).replace(
                second=0, microsecond=0
            )
        else:
            day_start = day_start.replace(second=0, microsecond=0)

    # If the (advanced) start is now past the end of the working day, no slots today
    if day_start + timedelta(minutes=duration_mins) > day_end:
        return []

    if events is None:
        events = get_events(calendar_id, day_start, day_end)

    # Match every event's tz-awareness to the day window before comparing.
    # Calendar events can come back timezone-aware (Google timed events) OR
    # naive (events written without an offset). Comparing a naive datetime to an
    # aware one raises TypeError, which previously bubbled up and silently wiped
    # an engineer's ENTIRE availability for every day. Coerce to the window's tz.
    _win_tz = day_start.tzinfo

    def _coerce(dt: datetime) -> datetime:
        if dt.tzinfo is None and _win_tz is not None:
            return dt.replace(tzinfo=_win_tz)
        if dt.tzinfo is not None and _win_tz is None:
            return dt.replace(tzinfo=None)
        return dt

    _win_date = day_start.date()
    busy = []
    for ev in events:
        ev_start_raw = (ev.get("start") or {}).get("dateTime")
        ev_end_raw = (ev.get("end") or {}).get("dateTime")
        if ev_start_raw and ev_end_raw:
            # Timed event
            try:
                ev_start = _coerce(datetime.fromisoformat(ev_start_raw))
                ev_end = _coerce(datetime.fromisoformat(ev_end_raw))
            except (ValueError, TypeError):
                continue
            busy.append((
                ev_start - timedelta(minutes=travel_buffer_mins),
                ev_end + timedelta(minutes=travel_buffer_mins),
            ))
            continue

        # All-day event (Google returns start.date/end.date; end is EXCLUSIVE).
        # Holidays/OOO blockers must mark the whole working day busy or the
        # scheduler would over-offer slots on days the engineer is unavailable.
        ev_start_date = (ev.get("start") or {}).get("date")
        ev_end_date = (ev.get("end") or {}).get("date")
        if ev_start_date and ev_end_date:
            try:
                sd = datetime.fromisoformat(ev_start_date).date()
                ed = datetime.fromisoformat(ev_end_date).date()
            except (ValueError, TypeError):
                continue
            if sd <= _win_date < ed:
                busy.append((day_start, day_end))
    busy.sort(key=lambda x: x[0])

    slots = []
    cursor = day_start
    slot_delta = timedelta(minutes=duration_mins)
    buf_delta = timedelta(minutes=travel_buffer_mins)

    while cursor + slot_delta <= day_end:
        slot_end = cursor + slot_delta
        blocked = any(b_start < slot_end and b_end > cursor for b_start, b_end in busy)
        if not blocked:
            slots.append({
                "start": cursor.isoformat(),
                "end": slot_end.isoformat(),
                "startLabel": cursor.strftime("%H:%M"),
                "endLabel": slot_end.strftime("%H:%M"),
                # True when the job finishes after the soft target end (the
                # 16:00–17:00 overtime band) — used sparingly to pack busy days.
                "overtime": slot_end > soft_end,
            })
            cursor = slot_end + buf_delta
        else:
            cursor += timedelta(minutes=15)

    return slots


def list_events(calendar_id: str, time_min, time_max) -> list:
    """
    Return all events in a calendar between time_min and time_max (datetime objects).
    Used by the AI scheduling agent to see existing bookings when reasoning about routes.
    """
    try:
        service = _get_service()
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        ).execute()
        return result.get("items", [])
    except Exception as exc:
        logger.warning("list_events failed for %s: %s", calendar_id, exc)
        return []


def list_holds(calendar_id: str = None, days_ahead: int = 30) -> list:
    """Return all active HOLD events (powwash_hold=true) in the next days_ahead days."""
    cfg = load_config()
    if calendar_id is None:
        calendar_id = cfg.get("calendarId")
    if not calendar_id:
        return []

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)

    try:
        service = _get_service()
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
            privateExtendedProperty="powwash_hold=true",
        ).execute()
        items = result.get("items", [])
    except Exception as exc:
        logger.warning("list_holds failed: %s", exc)
        return []

    holds = []
    for ev in items:
        priv = ev.get("extendedProperties", {}).get("private", {})
        if priv.get("powwash_hold") != "true":
            continue

        start_str   = ev.get("start", {}).get("dateTime", "")
        end_str     = ev.get("end",   {}).get("dateTime", "")
        created_str = ev.get("created", "")

        hours_until = None
        if start_str:
            try:
                slot_start  = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                hours_until = (slot_start - now).total_seconds() / 3600
            except Exception:
                pass

        age_minutes = None
        if created_str:
            try:
                created     = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                age_minutes = (now - created).total_seconds() / 60
            except Exception:
                pass

        job_spec = {}
        try:
            job_spec = json.loads(priv.get("powwash_job", "{}"))
        except Exception:
            pass

        holds.append({
            "eventId":    ev["id"],
            "title":      ev.get("summary", "Hold"),
            "start":      start_str,
            "end":        end_str,
            "created":    created_str,
            "ageMinutes": round(age_minutes) if age_minutes is not None else None,
            "hoursUntil": round(hours_until, 1) if hours_until is not None else None,
            "customer":   job_spec.get("customerName", ""),
            "service":    job_spec.get("service", ""),
            "calendarId": calendar_id,
        })

    return holds


def create_event(calendar_id: str, event_body: dict) -> dict:
    service = _get_service()
    return service.events().insert(calendarId=calendar_id, body=event_body).execute()


def update_event(calendar_id: str, event_id: str, event_body: dict) -> dict:
    service = _get_service()
    return service.events().update(
        calendarId=calendar_id, eventId=event_id, body=event_body
    ).execute()


def delete_event(calendar_id: str, event_id: str) -> bool:
    try:
        service = _get_service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except Exception as exc:
        logger.warning("delete_event failed: %s", exc)
        return False


def build_hold_event(job_spec: dict, slot: dict, cfg: dict | None = None, is_ai: bool = True) -> dict:
    if cfg is None:
        cfg = load_config()
    customer = job_spec.get("customerName", "Customer")
    service_name = job_spec.get("service", "Cleaning")
    if isinstance(service_name, list):
        service_name = ", ".join(service_name)
    service_lines = _build_service_lines(job_spec)

    # Build title using the same template as confirmed bookings
    fmt = cfg.get("eventFormat", _DEFAULT_CONFIG["eventFormat"])
    title_tmpl = fmt.get("titleTemplate", "{postcodeStart} {serviceAbbr} {customerName}")
    fields = {k: job_spec.get(k, "") for k in
        ["customerName", "customerEmail", "service", "phone", "address", "price", "notes"]}
    if isinstance(fields["service"], list):
        fields["service"] = ", ".join(fields["service"])
    fields["serviceLines"]  = service_lines
    fields["serviceAbbr"]   = _service_abbr(service_name)
    fields["postcodeStart"] = _postcode_start(job_spec)
    try:
        title = "Prov_" + title_tmpl.format(**fields)
    except KeyError:
        title = f"Prov_{fields['postcodeStart']} {fields['serviceAbbr']} {customer}".strip()
    if is_ai:
        title = "*AI* " + title

    return {
        "summary": title,
        "description": (
            f"\u23f3 Awaiting customer confirmation.\n\n"
            f"[notes]\n"
            f"Notes: {job_spec.get('notes', '')}\n"
            f"[/notes]\n\n"
            f"[contact]\n"
            f"Customer name: {customer}\n"
            f"Customer email address: {job_spec.get('customerEmail', '')}\n"
            f"Customer contact number: {job_spec.get('phone', '')}\n"
            f"[/contact]\n\n"
            f"[invoice]\n"
            f"{service_lines}\n\n"
            f"\u2b07Sales\u2b07\n\n"
            f"[/invoice]\n"
            f"PROCESS DRAFT (Y/N) ="
        ),
        "start": {"dateTime": slot["start"], "timeZone": business_tz_name()},
        "end": {"dateTime": slot["end"], "timeZone": business_tz_name()},
        "colorId": "5",
        "extendedProperties": {
            "private": {
                "powwash_hold": "true",
                "powwash_job": json.dumps(job_spec),
            }
        },
    }


def _norm_price(p) -> str:
    """Normalise a price to a single leading £, preserving any +VAT note.
    Prevents the '££' that appears when the source value already includes a £."""
    s = str(p or "").strip()
    if not s:
        return ""
    s = s.lstrip("\u00a3 ").strip()   # drop any existing £ sign(s)/spaces
    return f"\u00a3{s}" if s else ""


def _title_service(s) -> str:
    """Sentence-case a service name: 'back patio clean' → 'Back patio clean'."""
    s = str(s or "").strip()
    return s[:1].upper() + s[1:] if s else ""


def _build_service_lines(job_spec: dict) -> str:
    """One 'Service £Price+VAT' line per service — capitalised, single £, and
    one line per service when several are booked (e.g. front + back patio).
    Handles list or scalar service/price values."""
    services = job_spec.get("service", "")
    prices   = job_spec.get("price", "")
    if isinstance(services, list):
        price_list = prices if isinstance(prices, list) else [prices] * len(services)
        return "\n".join(
            f"{_title_service(s)} {_norm_price(p)}".strip()
            for s, p in zip(services, price_list)
        )
    if isinstance(prices, list):
        return "\n".join(f"{_title_service(services)} {_norm_price(p)}".strip() for p in prices)
    return f"{_title_service(services)} {_norm_price(prices)}".strip()


def build_booking_event(job_spec: dict, slot: dict, cfg: dict | None = None, is_ai: bool = True) -> dict:
    if cfg is None:
        cfg = load_config()
    fmt = cfg.get("eventFormat", _DEFAULT_CONFIG["eventFormat"])
    fields = {k: job_spec.get(k, "") for k in
        ["customerName", "customerEmail", "service", "phone", "address", "price", "notes"]}
    if isinstance(fields["service"], list):
        fields["service"] = ", ".join(fields["service"])
    fields["serviceLines"]   = _build_service_lines(job_spec)
    fields["serviceAbbr"]    = _service_abbr(fields["service"])
    fields["postcodeStart"]  = _postcode_start(job_spec)
    title = fmt["titleTemplate"].format(**fields)
    if is_ai:
        title = "*AI* " + title
    description = fmt["descriptionTemplate"].format(**fields)
    # Location must include the postcode so the engineer can navigate. The address
    # field often omits it (postcode is captured separately), so append it unless
    # it is already present in the address text.
    _addr = (job_spec.get("address") or "").strip().rstrip(",")
    _pc = (job_spec.get("postcode") or "").strip()
    if _pc and _pc.replace(" ", "").upper() not in _addr.replace(" ", "").upper():
        location = f"{_addr}, {_pc}".strip().lstrip(",").strip() if _addr else _pc
    else:
        location = _addr
    return {
        "summary": title,
        "description": description,
        "location": location,
        "start": {"dateTime": slot["start"], "timeZone": business_tz_name()},
        "end": {"dateTime": slot["end"], "timeZone": business_tz_name()},
        "colorId": fmt.get("colorId", "2"),
        "extendedProperties": {
            "private": {
                "powwash_booking": "true",
                "powwash_job": json.dumps(job_spec),
            }
        },
    }
