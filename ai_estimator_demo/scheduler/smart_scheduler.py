"""
PowWash Smart Scheduler.

Assigns jobs to engineers and scores available slots based on:
  - Region coverage (North / South), determined by geography (latitude boundary)
  - Priority order and fill-ahead rules
  - Job proximity (same-day grouping) using real postcode distances via postcodes.io
  - Route-aware scoring: insertion cost, cluster proximity, start/end-of-day bonuses

Distance approach:
  All postcodes use postcodes.io lat/lng + haversine distance.
  There is NO zone-based logic — SW19, Tooting (SW17), Croydon (CR0) are all
  treated as just coordinates and compared by km, which is what actually matters.

  Two grouping thresholds (both configurable in scheduling_rules.json):
    londonMaxGroupingKm  — normal day (default 20km, covers most of Greater London)
    northMaxGroupingKm   — normal day (default 60km, covers motorway ranges)
  Urgent/fill-slots mode raises these thresholds automatically.

Region boundary:
  Milton Keynes sits at ~52.0°N. Jobs below this latitude go to South engineers;
  jobs above go to North engineers. This correctly handles CR, SM, BR, TW, KT,
  HA, RM, IG, EN and all other Greater London postcodes.

Route-aware scoring (North engineer focus):
  The North engineer typically operates out of a home base (e.g. Stoke) and drives
  out to a city cluster (e.g. Birmingham or Manchester) for the day. The scorer:
    1. Calculates the cheapest insertion point in the current day's route
       (home → jobs → home) — prefers jobs that don't add a detour.
    2. Rewards jobs that sit BETWEEN home and the day's cluster centre
       (good for first or last slot of the day without extending the route).
    3. Gives a stronger bonus for jobs very close to home at end of day.
"""
import json
import logging
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from pg_store import PersistentFile  # Postgres-backed persistence (survives Autoscale restarts)
PROFILES_PATH = PersistentFile(Path(__file__).resolve().parent / "engineer_profiles.json")
RULES_PATH    = PersistentFile(Path(__file__).resolve().parent / "scheduling_rules.json")
PC_CACHE_PATH = PersistentFile(Path(__file__).resolve().parent / "postcode_cache.json")

# Geographic North/South boundary latitude (just south of Milton Keynes ~52.04°N)
BOUNDARY_LAT = 52.0

_DEFAULT_RULES = {
    "fillAheadDays": 5,
    "londonMaxGroupingKm": 20,
    "northMaxGroupingKm": 60,
    "londonUrgentGroupingKm": 35,
    "northUrgentGroupingKm": 90,
    "homeReturnBonus": True,
    "notes": (
        "Milton Keynes is the natural boundary between North and South engineers (~52°N). "
        "North engineer covers Manchester, Birmingham, Liverpool and the wider North. "
        "South engineers cover London and surrounding areas (including CR, SM, BR, TW, KT, etc). "
        "Priority 1 South engineer calendar should be filled at least fillAheadDays days ahead "
        "before offering the Priority 2 engineer. For urgent bookings, engineers can travel "
        "further (up to londonUrgentGroupingKm / northUrgentGroupingKm)."
    ),
}

_DEFAULT_PROFILES = [
    {
        "id": "eng-north",
        "name": "North Engineer",
        "homePostcode": "",
        "region": "north",
        "priority": 1,
        "fillAheadDays": 0,
        "active": True,
        "notes": "Covers Manchester, Birmingham, Liverpool and the wider North.",
        "calendarId": "",
    },
    {
        "id": "eng-south-1",
        "name": "South Engineer 1",
        "homePostcode": "",
        "region": "south",
        "priority": 1,
        "fillAheadDays": 5,
        "active": True,
        "notes": "Priority London engineer — fill calendar 5 days ahead before offering Engineer 2.",
        "calendarId": "",
    },
    {
        "id": "eng-south-2",
        "name": "South Engineer 2",
        "homePostcode": "",
        "region": "south",
        "priority": 2,
        "fillAheadDays": 0,
        "active": True,
        "notes": "Secondary London engineer.",
        "calendarId": "",
    },
]


# ── Data loading / saving ──────────────────────────────────────────────────

def load_profiles() -> list:
    try:
        return json.loads(PROFILES_PATH.read_text())
    except Exception:
        return list(_DEFAULT_PROFILES)


def save_profiles(profiles: list) -> None:
    PROFILES_PATH.write_text(json.dumps(profiles, indent=2))


def load_rules() -> dict:
    try:
        raw = json.loads(RULES_PATH.read_text())
        return {**_DEFAULT_RULES, **raw}
    except Exception:
        return dict(_DEFAULT_RULES)


def save_rules(patch: dict) -> dict:
    rules = load_rules()
    rules.update(patch)
    RULES_PATH.write_text(json.dumps(rules, indent=2))
    return rules


# ── Postcode / coordinate utilities ───────────────────────────────────────

def _load_pc_cache() -> dict:
    try:
        return json.loads(PC_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_pc_cache(cache: dict) -> None:
    try:
        PC_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def postcode_to_latlng(postcode: str) -> Optional[tuple]:
    """
    Convert a UK postcode to (lat, lng) using the free postcodes.io API.
    Results are cached locally — no API key needed.

    Accepts both full postcodes (SW19 1AA) and outward codes (SW19, CR0, M1).
    Tries /postcodes/{postcode} first; falls back to /outcodes/{outcode} for
    outward-code-only inputs (e.g. when engineer enters just 'SW12' or 'M14').
    """
    if not postcode:
        return None
    clean = re.sub(r"\s+", "", postcode.upper().strip())
    cache = _load_pc_cache()
    if clean in cache:
        c = cache[clean]
        return tuple(c) if c else None

    def _fetch(url: str) -> Optional[list]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PowWash/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read())
            if data.get("status") == 200 and data.get("result"):
                r = data["result"]
                return [r["latitude"], r["longitude"]]
        except Exception as exc:
            logger.debug("postcodes.io request failed (%s): %s", url, exc)
        return None

    # Try full-postcode endpoint first
    coords = _fetch(f"https://api.postcodes.io/postcodes/{urllib.parse.quote(clean)}")

    # If that fails, try the outcode endpoint (works for SW19, CR0, M1, etc.)
    if coords is None:
        coords = _fetch(f"https://api.postcodes.io/outcodes/{urllib.parse.quote(clean)}")

    cache[clean] = coords
    _save_pc_cache(cache)
    return tuple(coords) if coords else None


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in km between two lat/lng points."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def postcode_distance_km(pc1: str, pc2: str) -> Optional[float]:
    """Return straight-line km between two postcodes, or None if either can't be geocoded."""
    c1 = postcode_to_latlng(pc1)
    c2 = postcode_to_latlng(pc2)
    if c1 and c2:
        return haversine(*c1, *c2)
    return None


def is_south_of_boundary(postcode: str, boundary_lat: float = BOUNDARY_LAT) -> Optional[bool]:
    """
    Return True if the postcode is geographically south of the boundary latitude,
    False if north, None if we can't determine (geocode failed).
    Default boundary: ~52.0°N (just south of Milton Keynes).
    """
    coords = postcode_to_latlng(postcode)
    if coords is None:
        return None
    return coords[0] < boundary_lat


def postcode_area(postcode: str) -> str:
    """Return the outward area code, e.g. 'SW1A 1AA' → 'SW', 'CR0 2AA' → 'CR'."""
    m = re.match(r"^([A-Z]{1,2})", postcode.upper().strip())
    return m.group(1) if m else ""


# ── Job grouping ────────────────────────────────────────────────────────────

def jobs_groupable(
    postcode1: str,
    postcode2: str,
    max_km: float = 20,
) -> bool:
    """
    True if two job locations are close enough to schedule on the same day.

    Uses real postcode coordinates (postcodes.io) and straight-line distance
    for everything — both London/South and North.  The max_km threshold differs:
      - South/London: typically ~20km (covers Greater London comfortably)
      - North: typically ~60km (covers motorway ranges)

    The caller passes the appropriate max_km based on which engineer/region is being scored.
    If either postcode can't be geocoded, we allow the grouping (fail open).
    """
    if not postcode1 or not postcode2:
        return True
    dist = postcode_distance_km(postcode1, postcode2)
    if dist is None:
        return True  # can't measure, allow
    return dist <= max_km


# ── Engineer eligibility ────────────────────────────────────────────────────

def _job_is_south(job_postcode: str) -> Optional[bool]:
    """
    True  = job is in the South (below boundary lat) → South engineers
    False = job is in the North (above boundary lat) → North engineer
    None  = unknown (geocode failed) → all engineers eligible
    """
    return is_south_of_boundary(job_postcode)


def _region_matches(eng: dict, job_south: Optional[bool]) -> bool:
    """True if the engineer's region covers a job in this part of the country."""
    region = eng.get("region", "both").lower()
    if job_south is True and region == "north":
        return False
    if job_south is False and region == "south":
        return False
    return True


def _has_calendar(eng: dict) -> bool:
    """An engineer can only be booked if a specific Google Calendar is linked."""
    return bool((eng.get("calendarId") or "").strip())


def get_eligible_engineers(job_postcode: str) -> list:
    """
    Return BOOKABLE engineers eligible for this job, sorted by priority.

    An engineer is bookable only if:
      - they are active (ticked on), AND
      - they have a specific calendar linked (calendarId set), AND
      - their region covers the job.

    Region matching:
      job_is_south=True  → 'south' and 'both' engineers
      job_is_south=False → 'north' and 'both' engineers
      job_is_south=None  → all regions (geocode failed, don't exclude on region)
    """
    profiles = load_profiles()
    job_south = _job_is_south(job_postcode) if job_postcode else None

    eligible = []
    for eng in profiles:
        if not eng.get("active", True):
            continue
        if not _has_calendar(eng):
            # No calendar linked → never auto-booked (avoids the old shared-calendar
            # fallback that caused engineers to double-book the same diary).
            continue
        if not _region_matches(eng, job_south):
            continue
        eligible.append(eng)

    eligible.sort(key=lambda e: (e.get("priority", 99), e.get("name", "")))
    return eligible


def get_coverage_status(job_postcode: str) -> dict:
    """
    Classify region-covering engineers into bookable vs blocked for this job.

    Returns:
      {
        "eligible": [<bookable engineer dicts>],   # active + calendar linked
        "blocked":  [                              # cover the area but can't be booked
          {"id", "name", "region", "reasons": ["disabled" | "no calendar linked"]}
        ],
      }

    A coverage gap exists when `eligible` is empty but `blocked` is not — i.e. the
    only engineers covering the requested area are unticked or have no calendar.
    """
    profiles = load_profiles()
    job_south = _job_is_south(job_postcode) if job_postcode else None

    eligible, blocked = [], []
    for eng in profiles:
        if not _region_matches(eng, job_south):
            continue
        inactive = not eng.get("active", True)
        no_cal   = not _has_calendar(eng)
        if inactive or no_cal:
            reasons = []
            if inactive:
                reasons.append("disabled")
            if no_cal:
                reasons.append("no calendar linked")
            blocked.append({
                "id":      eng.get("id"),
                "name":    eng.get("name", "Engineer"),
                "region":  eng.get("region", "both"),
                "reasons": reasons,
            })
        else:
            eligible.append(eng)

    eligible.sort(key=lambda e: (e.get("priority", 99), e.get("name", "")))
    return {"eligible": eligible, "blocked": blocked}


# ── Slot scoring helpers ─────────────────────────────────────────────────────

def _grouping_km(region: str, urgent: bool, rules: dict) -> float:
    """Return the appropriate max grouping distance for this region and urgency."""
    if region == "north":
        return rules.get("northUrgentGroupingKm", 90) if urgent else rules.get("northMaxGroupingKm", 60)
    return rules.get("londonUrgentGroupingKm", 35) if urgent else rules.get("londonMaxGroupingKm", 20)


def _postcode_centroid(postcodes: list) -> Optional[tuple]:
    """
    Return the geographic centroid (mean lat, mean lng) of a list of postcodes.
    Silently skips any that can't be geocoded.
    """
    lats, lngs = [], []
    for pc in postcodes:
        coords = postcode_to_latlng(pc)
        if coords:
            lats.append(coords[0])
            lngs.append(coords[1])
    if not lats:
        return None
    return (sum(lats) / len(lats), sum(lngs) / len(lngs))


def _route_insertion_cost(
    job_postcode: str,
    existing_postcodes: list,
    home: str,
) -> Optional[float]:
    """
    Calculate the minimum extra kilometres added by inserting job_postcode
    into the current day's round-trip route: home → [existing jobs] → home.

    Tries every possible insertion position and returns the cheapest one.
    Returns None if coordinates are unavailable for key stops.

    Examples (Stoke = home):
      Existing: [Birmingham B1]
        Route: Stoke → B1 → Stoke = ~80km
        Insert Lichfield WS13 (on the way back):
          Stoke → B1 → WS13 → Stoke ≈ 87km  → insertion cost ≈ +7km   ✓
        Insert Manchester M1 (major detour):
          cheapest: Stoke → M1 → B1 → Stoke ≈ 240km  → insertion cost ≈ +160km  ✗
    """
    all_stops = [home] + existing_postcodes + [home]

    def _dist(a: str, b: str) -> Optional[float]:
        return postcode_distance_km(a, b)

    def _route_km(stops: list) -> Optional[float]:
        total = 0.0
        for i in range(len(stops) - 1):
            d = _dist(stops[i], stops[i + 1])
            if d is None:
                return None
            total += d
        return total

    current_km = _route_km(all_stops)
    if current_km is None:
        return None

    best_extra = float("inf")
    for i in range(1, len(all_stops)):
        candidate = all_stops[:i] + [job_postcode] + all_stops[i:]
        new_km = _route_km(candidate)
        if new_km is not None:
            extra = new_km - current_km
            if extra < best_extra:
                best_extra = extra

    return best_extra if best_extra != float("inf") else None


# ── Main slot scorer ─────────────────────────────────────────────────────────

def score_slot_for_engineer(
    engineer: dict,
    job_postcode: str,
    existing_day_jobs: list,
    rules: dict | None = None,
    urgent: bool = False,
) -> float:
    """
    Score how suitable this engineer + day is for the new job. Higher = better.

    Scoring factors
    ───────────────
    Priority bonus
        P1 = +23, P2 = +11, P3+ = 0

    Grouping bonus (+40 or +10)
        +40 if new job is within max_km of any existing job today.
        +10 partial credit if distance can't be measured.

    Route insertion bonus (+0 → +50)
        Calculates the extra km cost of inserting this job into the round-trip
        home → [existing jobs] → home.  A job that fits on the way out or back
        (e.g. Lichfield on the way home from Birmingham) costs very little.
        Bonus = max(0, 50 − insertion_cost_km × 1.2)
        → 0 extra km  = +50  (job is perfectly on the route)
        → 20 extra km = +26  (slight detour, still worthwhile)
        → 42 extra km =  +0  (major detour, no route bonus)

    "Between home and cluster" bonus (+20)
        If the new job is closer to home than the day's geographic cluster centre,
        it sits on the return leg of the route — ideal for a first or last slot.

    Near-home first-slot bonus (+20)
        First job of the day and within near_home_km of home.

    Near-home last-slot bonus (+35)
        New job is closer to home than the current last-booked job
        AND within near_home_km of home.
        (Prioritised over first-slot — user preference: "especially the end")

    near_home_km: 20 for North engineers, 15 for South/both.
    """
    if rules is None:
        rules = load_rules()

    score = 50.0
    priority = engineer.get("priority", 99)
    score += max(0.0, 35.0 - priority * 12.0)

    home   = (engineer.get("homePostcode") or "").strip()
    region = engineer.get("region", "both").lower()
    max_km = _grouping_km(region, urgent, rules)
    near_home_km = 20.0 if region == "north" else 15.0

    if not job_postcode:
        return score

    # ── Grouping bonus / ungroupable penalty ───────────────────────────────
    existing_postcodes: list[str] = []
    grouped_with_existing = False

    for ej in existing_day_jobs:
        ep = (ej.get("address") or ej.get("postcode") or "").strip()
        if not ep:
            continue
        existing_postcodes.append(ep)
        dist = postcode_distance_km(job_postcode, ep)
        if dist is not None and dist <= max_km:
            score += 40
            grouped_with_existing = True
            break
        elif dist is None:
            # Can't measure → partial credit, treat as loosely grouped
            score += 10
            grouped_with_existing = True

    # Penalty: if there ARE existing jobs but this one doesn't cluster with any
    # of them, it should strongly prefer a fresh empty day over hijacking this one.
    if existing_postcodes and not grouped_with_existing:
        score -= 25

    if not rules.get("homeReturnBonus", True) or not home:
        return score

    home_to_job = postcode_distance_km(job_postcode, home)

    # ── Route insertion bonus (most impactful for North/route-day scheduling) ─
    if existing_postcodes:
        insertion_cost = _route_insertion_cost(job_postcode, existing_postcodes, home)
        if insertion_cost is not None:
            route_bonus = max(0.0, 50.0 - insertion_cost * 1.2)
            score += route_bonus

        # "Between home and cluster" bonus ─────────────────────────────────
        # Job must be:
        #   a) closer to home than the cluster centre, AND
        #   b) in the SAME DIRECTION as the cluster (dot-product > 0)
        # This prevents a job in the opposite direction (e.g. Manchester on a
        # Birmingham day when home is Stoke) from claiming the return-leg bonus.
        centroid = _postcode_centroid(existing_postcodes)
        home_coords = postcode_to_latlng(home)
        job_coords  = postcode_to_latlng(job_postcode)
        if centroid and home_coords and job_coords and home_to_job is not None:
            dist_home_to_cluster = haversine(
                home_coords[0], home_coords[1],
                centroid[0], centroid[1],
            )
            # Direction check via dot product of vectors (home→cluster) · (home→job)
            v_cluster = (centroid[0] - home_coords[0], centroid[1] - home_coords[1])
            v_job     = (job_coords[0] - home_coords[0], job_coords[1] - home_coords[1])
            dot       = v_cluster[0] * v_job[0] + v_cluster[1] * v_job[1]
            same_direction = dot > 0

            if same_direction and home_to_job < dist_home_to_cluster:
                score += 20  # job is on the route between home and the day's cluster

    # ── Home proximity bonuses ──────────────────────────────────────────────
    if not existing_day_jobs:
        # First job of the day — bonus if close to home
        if home_to_job is not None and home_to_job <= near_home_km:
            score += 20
    else:
        # Last-slot bonus — new job closer to home than the current last job
        # AND within near_home_km so it genuinely feels like "on the way home".
        # Only applies when the job also clusters (or is on the right route leg).
        last_ep = next(
            (
                (ej.get("address") or ej.get("postcode") or "").strip()
                for ej in reversed(existing_day_jobs)
                if (ej.get("address") or ej.get("postcode") or "").strip()
            ),
            None,
        )
        if last_ep and home_to_job is not None and grouped_with_existing:
            last_home_dist = postcode_distance_km(last_ep, home)
            is_closer_to_home = last_home_dist is None or home_to_job <= last_home_dist
            is_near_home = home_to_job <= near_home_km
            if is_closer_to_home:
                # Bigger bonus (+35) if also near home; smaller (+15) if just directionally closer
                score += 35 if is_near_home else 15

    return score


def rank_engineers_for_job(
    job_postcode: str,
    existing_jobs_by_engineer: dict | None = None,
    urgent: bool = False,
) -> list:
    """
    Return [{engineer, score, distanceKm, reason}, ...] sorted best-first.

    existing_jobs_by_engineer: {engineer_id: [job_spec, ...]} for jobs already
    booked on the target day.  job_spec items should have 'address' or 'postcode'.
    urgent: if True, uses larger grouping radius to help fill gaps in the calendar.
    """
    if existing_jobs_by_engineer is None:
        existing_jobs_by_engineer = {}
    rules   = load_rules()
    eligible = get_eligible_engineers(job_postcode)
    ranked  = []

    for eng in eligible:
        day_jobs = existing_jobs_by_engineer.get(eng["id"], [])
        score    = score_slot_for_engineer(eng, job_postcode, day_jobs, rules, urgent)

        # Build a human-readable reason string
        reasons = []
        if eng.get("priority", 99) == 1:
            reasons.append("priority engineer")
        if day_jobs:
            # Find closest existing job distance for the reason text
            best_dist = None
            for ej in day_jobs:
                ep = (ej.get("address") or ej.get("postcode") or "").strip()
                if ep:
                    d = postcode_distance_km(job_postcode, ep)
                    if d is not None and (best_dist is None or d < best_dist):
                        best_dist = d
            if best_dist is not None:
                reasons.append(f"nearest existing job ~{best_dist:.0f}km away")
            else:
                reasons.append(f"{len(day_jobs)} job(s) already that day")
        else:
            reasons.append("open day")
        if urgent:
            reasons.append("urgent — extended range")

        ranked.append({
            "engineer": eng,
            "score":    round(score, 1),
            "reason":   ", ".join(reasons),
        })

    ranked.sort(key=lambda x: -x["score"])
    return ranked
