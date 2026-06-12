"""
Google Maps Distance Matrix client for PowWash Smart Scheduler.

Provides real driving-time and distance data between UK postcodes.
Falls back to haversine straight-line distance when no API key is configured,
with a clearly-labelled caveat so the scheduling agent knows to treat it as approximate.

Setup:
  Set GOOGLE_MAPS_API_KEY in your environment (or via the Scheduling Agent UI).
  Without a key, the system still works but uses crow-flies estimates.
"""
import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from .smart_scheduler import postcode_to_latlng, haversine

logger = logging.getLogger(__name__)

from pg_store import PersistentFile  # Postgres-backed persistence (survives Autoscale restarts)
_CONFIG_PATH = PersistentFile(Path(__file__).resolve().parent / "maps_config.json")

# ── Config helpers ──────────────────────────────────────────────────────────

def _load_maps_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_maps_config(cfg: dict) -> None:
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_maps_api_key() -> Optional[str]:
    """
    Return the Google Maps API key.
    Priority: environment variable → saved config file.
    """
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if key:
        return key
    return _load_maps_config().get("apiKey") or None


def save_maps_api_key(key: str) -> None:
    cfg = _load_maps_config()
    cfg["apiKey"] = key.strip()
    _save_maps_config(cfg)


# ── Driving time lookup ──────────────────────────────────────────────────────

def get_driving_time(origin: str, destination: str, depart_time=None) -> dict:
    """
    Return driving time and distance between two UK postcodes.

    Args:
        depart_time: optional time-of-day for traffic-aware routing. Accepts a
            datetime, an ISO-8601 string, or epoch seconds. When given (and in
            the future), Google returns duration_in_traffic for that departure
            time so morning-rush vs midday routing differs realistically. Past
            times are coerced to "now" (Google rejects past departure times).

    Returns:
        {
          "durationMins": 35,            # traffic-adjusted when depart_time given
          "durationStaticMins": 28,      # free-flow duration (no traffic)
          "distanceKm": 28.4,
          "trafficAware": True|False,
          "departTime": "2026-06-10T09:00:00+01:00" | None,
          "source": "google_maps" | "haversine_estimate",
          "caveat": None | "Straight-line estimate ..."
        }

    The 'source' field lets the scheduling agent know how reliable the data is.
    """
    api_key = get_maps_api_key()

    if api_key:
        result = _google_maps_driving(origin, destination, api_key, depart_time)
        if result:
            return result

    # Fallback: haversine with an upscaling factor (driving ≈ 1.35× crow-flies for UK)
    return _haversine_estimate(origin, destination)


def _to_departure_epoch(depart_time) -> tuple[Optional[int], Optional[str]]:
    """
    Normalise a depart_time (datetime | ISO str | epoch int) to (epoch_secs, iso).
    Google's Distance Matrix requires departure_time to be now or in the future,
    so any past time is clamped to now. Returns (None, None) if unparseable.
    """
    if depart_time is None:
        return None, None
    import time as _time
    from datetime import datetime as _dt, timezone as _tz
    try:
        if isinstance(depart_time, (int, float)):
            dt = _dt.fromtimestamp(float(depart_time), tz=_tz.utc)
        elif isinstance(depart_time, str):
            s = depart_time.strip().replace("Z", "+00:00")
            dt = _dt.fromisoformat(s)
        elif isinstance(depart_time, _dt):
            dt = depart_time
        else:
            return None, None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        epoch = int(dt.timestamp())
        now   = int(_time.time())
        if epoch < now:           # Google rejects past departures → use now
            epoch = now
        return epoch, dt.isoformat()
    except Exception:
        return None, None


def _google_maps_driving(origin: str, dest: str, api_key: str, depart_time=None) -> Optional[dict]:
    try:
        depart_epoch, depart_iso = _to_departure_epoch(depart_time)
        query = {
            "origins":      origin,
            "destinations": dest,
            "key":          api_key,
            "mode":         "driving",
            "region":       "gb",
            "units":        "metric",
        }
        if depart_epoch is not None:
            # departure_time triggers traffic-aware duration_in_traffic in the response
            query["departure_time"] = depart_epoch
            query["traffic_model"]  = "best_guess"
        params = urllib.parse.urlencode(query)
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "PowWash/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        if data.get("status") != "OK":
            logger.warning("Maps API status: %s", data.get("status"))
            return None

        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            logger.warning("Maps element status: %s", element.get("status"))
            return None

        static_secs   = element["duration"]["value"]
        distance_m    = element["distance"]["value"]
        # duration_in_traffic is only present when departure_time was supplied
        traffic       = element.get("duration_in_traffic")
        traffic_aware = bool(traffic) and depart_epoch is not None
        duration_secs = traffic["value"] if traffic_aware else static_secs
        return {
            "durationMins":       round(duration_secs / 60),
            "durationStaticMins": round(static_secs / 60),
            "distanceKm":         round(distance_m / 1000, 1),
            "trafficAware":       traffic_aware,
            "departTime":         depart_iso if traffic_aware else None,
            "source":             "google_maps",
            "caveat":             None,
        }
    except Exception as exc:
        logger.warning("Google Maps API call failed (%s → %s): %s", origin, dest, exc)
        return None


def _haversine_estimate(origin: str, dest: str) -> dict:
    c1 = postcode_to_latlng(origin)
    c2 = postcode_to_latlng(dest)
    if c1 and c2:
        km       = haversine(c1[0], c1[1], c2[0], c2[1])
        road_km  = round(km * 1.35, 1)   # typical UK road-to-crow ratio
        mins     = round(road_km / 0.8)  # ~50km/h average inc. urban
        return {
            "durationMins": mins,
            "distanceKm":   road_km,
            "source":       "haversine_estimate",
            "caveat":       (
                "Straight-line estimate × 1.35 — connect Google Maps for accurate "
                "driving times (essential for city routing where roads, bridges, and "
                "one-way systems add significant time)."
            ),
        }
    return {
        "durationMins": None,
        "distanceKm":   None,
        "source":       "unavailable",
        "caveat":       f"Could not geocode one or both postcodes ({origin}, {dest}).",
    }


def get_maps_status() -> dict:
    """Returns Maps connection status for the UI."""
    key = get_maps_api_key()
    if not key:
        return {"connected": False, "source": "haversine_estimate"}
    # Quick validation check
    test = _google_maps_driving("SW1A 1AA", "EC1A 1BB", key)
    if test:
        return {"connected": True, "source": "google_maps"}
    return {"connected": False, "source": "haversine_estimate", "error": "API key rejected by Google"}
