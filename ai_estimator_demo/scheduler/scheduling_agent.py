"""
PowWash Scheduling Agent.

Given a job spec (service type, address, estimated duration),
this agent:
  1. Asks Google Calendar for free slots on a target date
  2. Optionally ranks them by travel efficiency (future: Google Maps)
  3. Creates a HOLD event on the best slot
  4. Can confirm (convert hold → real booking) or release the hold

The agent is intentionally decoupled from the conversation AI —
it only deals with logistics, not customer communication.
"""
import json
import logging
from datetime import datetime, timezone

from . import calendar_client as _cc

logger = logging.getLogger(__name__)


def find_slots(
    target_date_str: str,
    duration_mins: int,
    calendar_id: str | None = None,
) -> dict:
    """
    Find available slots for a job.

    Args:
        target_date_str: ISO date string, e.g. "2026-06-10"
        duration_mins: estimated job length in minutes
        calendar_id: Google Calendar ID (uses config default if None)

    Returns:
        {"slots": [...], "date": "...", "durationMins": N}
    """
    cfg = _cc.load_config()
    cal_id = calendar_id or cfg.get("calendarId") or "primary"
    travel_buf = cfg.get("travelBufferMinutes", 20)

    target_date = datetime.fromisoformat(target_date_str).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    slots = _cc.find_free_slots(
        calendar_id=cal_id,
        target_date=target_date,
        duration_mins=duration_mins,
        travel_buffer_mins=travel_buf,
    )

    return {
        "slots": slots,
        "date": target_date_str,
        "durationMins": duration_mins,
        "calendarId": cal_id,
    }


def create_hold(job_spec: dict, slot: dict, calendar_id: str | None = None) -> dict:
    """
    Place a HOLD event on the calendar.

    Args:
        job_spec: dict with customerName, service, phone, address, price,
                  durationMins, notes
        slot: {start, end, startLabel, endLabel} from find_slots()
        calendar_id: override calendar (uses config if None)

    Returns:
        {"ok": True, "eventId": "...", "slot": {...}, "calendarId": "..."}
    """
    cfg = _cc.load_config()
    cal_id = calendar_id or cfg.get("calendarId") or "primary"

    event_body = _cc.build_hold_event(job_spec, slot, cfg)
    event = _cc.create_event(cal_id, event_body)

    logger.info("Hold created: %s on %s (%s)", event["id"], cal_id, slot)
    return {
        "ok": True,
        "eventId": event["id"],
        "eventHtmlLink": event.get("htmlLink", ""),
        "slot": slot,
        "calendarId": cal_id,
    }


def confirm_booking(
    job_spec: dict,
    slot: dict,
    event_id: str,
    calendar_id: str | None = None,
) -> dict:
    """
    Convert a HOLD into a confirmed booking event.

    Args:
        job_spec: full job details
        slot: the slot dict (same as used for the hold)
        event_id: Google Calendar event ID of the hold to update
        calendar_id: override calendar

    Returns:
        {"ok": True, "eventId": "...", "htmlLink": "..."}
    """
    cfg = _cc.load_config()
    cal_id = calendar_id or cfg.get("calendarId") or "primary"

    event_body = _cc.build_booking_event(job_spec, slot, cfg)
    event = _cc.update_event(cal_id, event_id, event_body)

    logger.info("Booking confirmed: event %s on %s", event_id, cal_id)
    return {
        "ok": True,
        "eventId": event["id"],
        "htmlLink": event.get("htmlLink", ""),
        "calendarId": cal_id,
    }


def release_hold(event_id: str, calendar_id: str | None = None) -> dict:
    """
    Delete a HOLD event (customer declined or timed out).
    """
    cfg = _cc.load_config()
    cal_id = calendar_id or cfg.get("calendarId") or "primary"
    success = _cc.delete_event(cal_id, event_id)
    return {"ok": success, "eventId": event_id, "calendarId": cal_id}
