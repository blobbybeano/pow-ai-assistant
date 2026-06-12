import base64
import json
import logging
import os
import random
import re
import secrets
import sys
import queue
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - handled at runtime
    Anthropic = None  # type: ignore

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

try:
    from pillow_heif import register_heif_opener  # type: ignore

    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    register_heif_opener = None  # type: ignore

import yaml

APP_ROOT   = Path(__file__).resolve().parent
# Allow imports from workspace root (e.g. conversation_store, auto_responder)
_workspace_root = str(APP_ROOT.parent)
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

# Postgres-backed persistence: dynamic data (users, settings, conversations,
# push subscriptions, AI config) is stored in the database so it survives
# deploys/restarts on Replit Autoscale's ephemeral filesystem. Falls back to
# plain files automatically when DATABASE_URL is not set.
from pg_store import PersistentFile

USERS_PATH = PersistentFile(APP_ROOT / "users.json")
CONFIG_PATH = APP_ROOT / "config" / "defaults.yaml"
TMP_DIR = APP_ROOT / "tmp"
TMP_DIR.mkdir(exist_ok=True, parents=True)

load_dotenv(APP_ROOT / ".env")
load_dotenv()  # fallback to repo root

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_estimator_demo")


ESTIMATE_JSON_SCHEMA = {
    "name": "powwash_estimate",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "service": {"type": "string"},
            "area_estimate_m2": {"type": "number", "minimum": 0},
            "condition": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "dirt_level": {"type": "string"},
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["dirt_level", "issues"],
            },
            "missing_sections": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "needs_more_photos": {"type": "boolean"},
            "next_request": {"type": ["string", "null"]},
            "notes": {"type": "string", "default": ""},
            "summary": {"type": "string"},
        },
        "required": [
            "service",
            "area_estimate_m2",
            "condition",
            "missing_sections",
            "confidence",
            "needs_more_photos",
            "next_request",
            "notes",
            "summary",
        ],
    },
}

ESTIMATE_TOOL = {
    "name": "submit_estimate",
    "description": (
        "Submit a structured exterior cleaning estimate based on the property photos and description. "
        "Always call this tool with your assessment."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Type of cleaning service (e.g. driveway, roof, patio)"},
            "area_estimate_m2": {"type": "number", "minimum": 0, "description": "Estimated area in square metres"},
            "condition": {
                "type": "object",
                "properties": {
                    "dirt_level": {"type": "string", "description": "light, medium, or heavy"},
                    "issues": {"type": "array", "items": {"type": "string"}, "description": "List of specific issues e.g. oil_stains, algae"},
                },
                "required": ["dirt_level", "issues"],
            },
            "missing_sections": {"type": "array", "items": {"type": "string"}, "description": "Parts of property not visible"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Confidence score 0-1"},
            "needs_more_photos": {"type": "boolean"},
            "next_request": {"type": "string", "description": "Internal note: what photos or info are still needed (used for tracking only, NOT shown to customer)"},
            "notes": {"type": "string", "description": "Any additional notes"},
            "summary": {"type": "string", "description": "The actual reply message sent to the customer — written as a warm, friendly WhatsApp message from the business owner. Follow the communication style guide exactly. Include the price, be conversational and human. Never sound robotic or like a form output."},
        },
        "required": ["service", "area_estimate_m2", "condition", "missing_sections", "confidence", "needs_more_photos", "next_request", "notes", "summary"],
    },
}

CLAUDE_MAIN_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_FAST_MODEL = "claude-haiku-4-5-20251001"


def load_defaults() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ParameterStore:
    def __init__(self, defaults: Dict[str, Any]):
        self.defaults = defaults
        self.state = self._initial_state(defaults)

    def _initial_state(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        preset_key = next(iter(defaults.get("service_presets", {})), "driveway")
        preset = defaults.get("service_presets", {}).get(preset_key, {})
        return {
            "system_prompt": defaults.get("system_prompt", ""),
            "service_preset": preset_key,
            "service_focus": preset.get("focus", ""),
            "pricing": defaults.get("pricing", {}).copy(),
            "coverage_policy": defaults.get("coverage_policy", {}).copy(),
            "response_format": defaults.get("response_format", "json"),
            "limits": defaults.get("limits", {}).copy(),
        }

    def get(self) -> Dict[str, Any]:
        return self.state

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "service_preset" in payload:
            key = payload["service_preset"]
            preset = self.defaults.get("service_presets", {}).get(key)
            if preset:
                self.state["service_preset"] = key
                self.state["service_focus"] = preset.get("focus", "")
        if "system_prompt" in payload:
            self.state["system_prompt"] = payload["system_prompt"]
        if "pricing" in payload and isinstance(payload["pricing"], dict):
            self.state["pricing"].update(payload["pricing"])
        if "coverage_policy" in payload and isinstance(payload["coverage_policy"], dict):
            self.state["coverage_policy"].update(payload["coverage_policy"])
        if "response_format" in payload:
            self.state["response_format"] = payload["response_format"]
        if "limits" in payload and isinstance(payload["limits"], dict):
            self.state["limits"].update(payload["limits"])
        return self.state

    def preset_options(self) -> Dict[str, Any]:
        return self.defaults.get("service_presets", {})


class SessionState:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get(self, session_id: str) -> Dict[str, Any]:
        return self.sessions.setdefault(session_id, {"photo_requests": 0, "history": []})

    def increment_photo_requests(self, session_id: str) -> None:
        session = self.get(session_id)
        session["photo_requests"] = session.get("photo_requests", 0) + 1

    def append_history(self, session_id: str, customer_msg: str, ai_reply: str) -> None:
        session = self.get(session_id)
        history = session.setdefault("history", [])
        if customer_msg:
            history.append({"role": "customer", "text": customer_msg})
        history.append({"role": "powwash", "text": ai_reply})
        # Keep last 20 turns to avoid token bloat
        session["history"] = history[-20:]

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        return self.get(session_id).get("history", [])


class PricingEngine:
    def __init__(self, params: ParameterStore):
        self.params = params

    def compute_price(self, estimate: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        pricing = self.params.get().get("pricing", {})
        base = float(pricing.get("base_callout", 0))
        rate = float(pricing.get("rate_per_m2", 0))
        area = float(estimate.get("area_estimate_m2") or 0)
        modifiers_cfg = pricing.get("multipliers", {})
        condition = estimate.get("condition", {}) or {}
        issues = condition.get("issues", []) or []
        dirt_level = condition.get("dirt_level", "medium")

        modifier_factor = 1.0
        applied = {}

        if dirt_level == "heavy":
            value = float(modifiers_cfg.get("heavy_soiling", 0))
            modifier_factor *= 1 + value
            applied["heavy_soiling"] = value

        mapping = {
            "oil_stains": "oil_stains",
            "algae": "algae_biocide",
            "algae_growth": "algae_biocide",
            "algae/biocide": "algae_biocide",
            "biocide": "algae_biocide",
            "access": "access_difficulty",
            "difficult_access": "access_difficulty",
            "access_difficulty": "access_difficulty",
        }
        for issue in issues:
            key = mapping.get(issue, issue)
            if key in modifiers_cfg:
                value = float(modifiers_cfg.get(key, 0))
                modifier_factor *= 1 + value
                applied[key] = value

        subtotal = base + area * rate * modifier_factor
        return round(subtotal, 2), applied


class ImageProcessor:
    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

    def __init__(self, limits: Dict[str, Any]):
        self.max_size_mb = float(limits.get("max_image_size_mb", 8))

    def process(self, file_storage: FileStorage) -> Tuple[str, str]:
        filename = secure_filename(file_storage.filename or "upload")
        ext = Path(filename).suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file type: {ext}")

        file_storage.stream.seek(0, os.SEEK_END)
        size_mb = file_storage.stream.tell() / (1024 * 1024)
        file_storage.stream.seek(0)
        if size_mb > self.max_size_mb:
            raise ValueError(f"File {filename} exceeds max size of {self.max_size_mb} MB")

        tmp_path = TMP_DIR / f"{uuid.uuid4().hex}{ext}"
        file_storage.save(tmp_path)
        try:
            if ext in {".heic", ".heif"}:
                return self._convert_heif(tmp_path)
            else:
                return self._encode_base64(tmp_path)
        finally:
            self._schedule_cleanup(tmp_path)

    def _convert_heif(self, path: Path) -> Tuple[str, str]:
        if Image is None:
            raise ValueError("Pillow is required for HEIC/HEIF conversion but is not available")
        try:
            with Image.open(path) as img:
                rgb_path = path.with_suffix(".jpg")
                img.convert("RGB").save(rgb_path, format="JPEG", quality=90)
                return self._encode_base64(rgb_path)
        except Exception as exc:
            raise ValueError("Unable to convert HEIC/HEIF image. Please convert manually.") from exc
        finally:
            if path.exists():
                path.unlink(missing_ok=True)

    def _encode_base64(self, path: Path) -> Tuple[str, str]:
        with path.open("rb") as fh:
            data = fh.read()
        encoded = base64.b64encode(data).decode("utf-8")
        mime = self._guess_mime(path.suffix)
        data_url = f"data:{mime};base64,{encoded}"
        path.unlink(missing_ok=True)
        return data_url, path.name

    @staticmethod
    def _guess_mime(ext: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        }.get(ext.lower(), "application/octet-stream")

    @staticmethod
    def _schedule_cleanup(path: Path) -> None:
        # Remove files older than 1 hour
        cutoff = time.time() - 3600
        for item in TMP_DIR.glob("*"):
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)


def _extract_claude_text(response) -> str:
    """Extract plain text content from a Claude messages response."""
    parts = []
    for block in response.content:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
    return "".join(parts).strip()


class AIClient:
    def __init__(self):
        if Anthropic is None:
            raise RuntimeError("anthropic package is required but not installed")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.client = Anthropic(api_key=api_key)

    def chat(self, system_prompt: str, user_parts: List[Dict[str, Any]], response_format: str,
             history: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        instructions = (
            "You are the AI assistant for PowWash, an exterior cleaning company. "
            "Assess the customer's message and any photos, then call the submit_estimate tool.\n\n"
            "CRITICAL — the 'summary' field is THE MESSAGE THE CUSTOMER READS. "
            "Write it ALWAYS as a warm, natural WhatsApp message from the business owner. "
            "Follow the communication style guide in the system prompt word for word. "
            "Only open with a warm greeting on the FIRST message — on follow-ups, skip the greeting "
            "and just continue the conversation naturally. "
            "Use phrases like 'Could you let me know...' or 'If you can send...' "
            "never blunt commands. Sound like a human, not a form.\n\n"
            "This applies WHETHER or not you need more photos. Even when asking for more info, "
            "write the summary as a friendly, conversational request — not a list of requirements.\n\n"
            "The 'next_request' field is internal tracking only and is NEVER shown to the customer."
        )

        full_system = f"{system_prompt}\n\n{instructions}"

        # Prepend conversation history as context in the user message
        if history:
            history_lines = []
            for turn in history:
                role_label = "Customer" if turn["role"] == "customer" else "PowWash"
                history_lines.append(f"{role_label}: {turn['text']}")
            history_block = "\n".join(history_lines)
            context_part = {
                "type": "text",
                "text": f"[Conversation so far]\n{history_block}\n\n[Customer's new message]",
            }
            user_parts = [context_part] + list(user_parts)

        response = self.client.messages.create(
            model=CLAUDE_MAIN_MODEL,
            max_tokens=1024,
            system=full_system,
            messages=[{"role": "user", "content": user_parts}],
            tools=[ESTIMATE_TOOL],
            tool_choice={"type": "tool", "name": "submit_estimate"},
        )

        for block in response.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "submit_estimate":
                return {"raw": json.dumps(block.input), "response": response}

        raise RuntimeError("Claude did not return a submit_estimate tool call")

    def repair_json(self, broken: str) -> str:
        response = self.client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=800,
            system="You fix JSON. Return only valid JSON with the same information. No explanation.",
            messages=[{"role": "user", "content": broken}],
        )
        return _extract_claude_text(response)


defaults = load_defaults()
params = ParameterStore(defaults)
pricing_engine = PricingEngine(params)
sessions = SessionState()

TONE_PROFILE_PATH = PersistentFile(APP_ROOT.parent / "tone_profile.md")
TUNE_EXAMPLES_PATH = PersistentFile(APP_ROOT / "tune_examples.json")
KB_PRICES_PATH = PersistentFile(APP_ROOT / "knowledge_base.json")
DIAGNOSTICS_PATH = PersistentFile(APP_ROOT / "diagnostics.json")
KB_EMBED_PATH = PersistentFile(APP_ROOT / "kb_embeddings.json")
CUSTOM_PROMPT_PATH = PersistentFile(APP_ROOT / "custom_system_prompt.txt")
FINETUNE_STATE_PATH = PersistentFile(APP_ROOT / "finetune_state.json")
GOAL_CONFIG_PATH = PersistentFile(APP_ROOT / "goal_config.json")
OPERATOR_CONTACTS_PATH = PersistentFile(APP_ROOT.parent / "operator_contacts.json")
PENDING_CONSULTATIONS_PATH = APP_ROOT.parent / "pending_consultations.json"

_GOAL_CONFIG_DEFAULTS: Dict[str, Any] = {
    "goal": "",
    "process": "",
    "escalationTriggers": "",
    "escalationPhone": "",
    "escalationChannel": "whatsapp",
    "escalationMessage": "Hi, a customer enquiry needs your attention: {customerSummary}. Please review and follow up.",
    "calendarCheckEnabled": True,
    "calendarBookEnabled": True,
    "calendarDemoMode": True,
}


CALENDAR_CONFIG_PATH = PersistentFile(APP_ROOT / "calendar_config.json")

def _load_goal_config() -> Dict[str, Any]:
    cfg = dict(_GOAL_CONFIG_DEFAULTS)
    try:
        if GOAL_CONFIG_PATH.exists():
            cfg.update(json.loads(GOAL_CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    # calendarDemoMode is also stored in calendar_config.json (set via the Calendar tab UI).
    # Always let calendar_config win over goal_config for this flag so the two files stay in sync.
    try:
        if CALENDAR_CONFIG_PATH.exists():
            cc = json.loads(CALENDAR_CONFIG_PATH.read_text(encoding="utf-8"))
            if cc.get("calendarDemoMode") is not None:
                cfg["calendarDemoMode"] = cc["calendarDemoMode"]
    except Exception:
        pass
    return cfg


def _save_goal_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _load_goal_config()
    cfg.update(patch)
    GOAL_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def _load_finetune_state() -> Dict[str, Any]:
    if FINETUNE_STATE_PATH.exists():
        try:
            return json.loads(FINETUNE_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"status": "none", "active": False, "model_id": None, "job_id": None}


def _save_finetune_state(state: Dict[str, Any]) -> None:
    FINETUNE_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_active_finetune_model() -> str | None:
    """Return the fine-tuned model ID if one is active, else None."""
    state = _load_finetune_state()
    if state.get("active") and state.get("model_id"):
        return state["model_id"]
    return None

tune_sessions: Dict[str, Dict[str, Any]] = {}
_TUNE_SESSION_TTL_HOURS = 4


def _cleanup_tune_sessions() -> None:
    cutoff = time.time() - _TUNE_SESSION_TTL_HOURS * 3600
    stale = [sid for sid, s in tune_sessions.items() if s.get("created_at", 0) < cutoff]
    for sid in stale:
        del tune_sessions[sid]


app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# ── Persistent secret key (survives restarts) ─────────────────────────────
_sk_path = PersistentFile(APP_ROOT / ".secret_key")
if _sk_path.exists():
    app.secret_key = _sk_path.read_text().strip()
else:
    _sk = secrets.token_hex(32)
    _sk_path.write_text(_sk)
    app.secret_key = _sk

# ── User store helpers ────────────────────────────────────────────────────
def _load_users() -> list:
    if USERS_PATH.exists():
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    return []

def _save_users(users: list) -> None:
    USERS_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")

def _find_user(email: str) -> Optional[Dict]:
    return next((u for u in _load_users() if u["email"].lower() == email.lower()), None)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── Gate every request ────────────────────────────────────────────────────
_PUBLIC_PREFIXES = ("/login", "/logout", "/static/", "/healthz", "/favicon", "/webhook/", "/api/twilio/status-callback")

@app.before_request
def require_login():
    if any(request.path.startswith(p) for p in _PUBLIC_PREFIXES):
        return None
    if "user_email" not in session:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect("/login")

if CUSTOM_PROMPT_PATH.exists():
    try:
        _persisted_prompt = CUSTOM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        if _persisted_prompt:
            params.update({"system_prompt": _persisted_prompt})
            logger.info("Loaded persisted custom system prompt from disk")
    except Exception:
        logger.warning("Could not load persisted custom prompt")


# ── Auth routes ───────────────────────────────────────────────────────────
@app.route("/sw.js")
def service_worker():
    """Serve the service worker from the root so its scope covers the whole app."""
    response = send_from_directory(os.path.join(APP_ROOT, "static"), "sw.js",
                                   mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_email" in session:
            return redirect("/")
        return render_template("login.html")
    data  = request.get_json(force=True) or {}
    email = data.get("email", "").strip().lower()
    pwd   = data.get("password", "")
    user  = _find_user(email)
    if not user or not check_password_hash(user["password_hash"], pwd):
        return jsonify({"error": "Invalid email or password."}), 401
    session.permanent    = True
    session["user_email"] = user["email"]
    session["user_role"]  = user.get("role", "user")
    session["user_name"]  = user.get("name", user["email"])
    return jsonify({"ok": True, "role": user.get("role", "user")})

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect("/login")

@app.route("/api/auth/me")
def auth_me():
    if "user_email" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "email": session["user_email"],
        "role":  session.get("user_role", "user"),
        "name":  session.get("user_name", ""),
    })

@app.route("/api/auth/users", methods=["GET"])
def auth_users_list():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    users = _load_users()
    return jsonify([{k: v for k, v in u.items() if k != "password_hash"} for u in users])

@app.route("/api/auth/users", methods=["POST"])
def auth_users_create():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data  = request.get_json(force=True) or {}
    email = data.get("email", "").strip().lower()
    pwd   = data.get("password", "").strip()
    role  = data.get("role", "user")
    name  = data.get("name", "").strip()
    if not email or not pwd:
        return jsonify({"error": "Email and password required."}), 400
    users = _load_users()
    if any(u["email"].lower() == email for u in users):
        return jsonify({"error": "A user with that email already exists."}), 409
    users.append({"email": email, "name": name, "role": role,
                  "password_hash": generate_password_hash(pwd)})
    _save_users(users)
    return jsonify({"ok": True})

@app.route("/api/auth/users/<path:email>", methods=["PATCH"])
def auth_users_update(email):
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data  = request.get_json(force=True) or {}
    users = _load_users()
    user  = next((u for u in users if u["email"].lower() == email.lower()), None)
    if not user:
        return jsonify({"error": "Not found."}), 404
    if "role" in data:
        user["role"] = data["role"]
    if "name" in data:
        user["name"] = data["name"]
    if data.get("password"):
        user["password_hash"] = generate_password_hash(data["password"])
    _save_users(users)
    return jsonify({"ok": True})

@app.route("/api/auth/users/<path:email>", methods=["DELETE"])
def auth_users_delete(email):
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    if email.lower() == session["user_email"].lower():
        return jsonify({"error": "You cannot delete your own account."}), 400
    users = [u for u in _load_users() if u["email"].lower() != email.lower()]
    _save_users(users)
    return jsonify({"ok": True})

# ── Push notification infrastructure ──────────────────────────────────────
PUSH_SUBS_PATH   = PersistentFile(APP_ROOT / "push_subscriptions.json")
NOTIF_PREFS_PATH = PersistentFile(APP_ROOT / "notification_prefs.json")
VAPID_KEYS_PATH      = PersistentFile(APP_ROOT / "vapid_keys.json")
QUOTE_REQUESTS_PATH  = PersistentFile(APP_ROOT / "quote_requests.json")
COVERAGE_ALERTS_PATH = PersistentFile(APP_ROOT / "coverage_alerts.json")
ATTENTION_ALERTS_PATH = PersistentFile(APP_ROOT / "attention_alerts.json")
BOOKINGS_LOG_PATH    = PersistentFile(APP_ROOT / "bookings_log.json")
BOOKINGS_SEEN_PATH   = PersistentFile(APP_ROOT / "bookings_seen.json")
CHECKATRADE_SETTINGS_PATH = PersistentFile(APP_ROOT / "checkatrade_settings.json")
CHECKATRADE_LEADS_PATH    = PersistentFile(APP_ROOT / "checkatrade_leads.json")

_vapid_public_key: str  = ""
_vapid_private_pem: str = ""
_vapid_instance = None  # pre-built py_vapid.Vapid object (avoids key-format ambiguity)

def _load_vapid() -> None:
    """Load VAPID keys.

    Self-heals if the stored private key is still in the old 121-byte DER format
    (pywebpush 2.x needs the raw 32-byte EC scalar in base64url).  Any detected
    DER key is converted to raw format and immediately persisted back to Postgres.
    """
    global _vapid_public_key, _vapid_private_pem, _vapid_instance
    if not VAPID_KEYS_PATH.exists():
        return
    d = json.loads(VAPID_KEYS_PATH.read_text(encoding="utf-8"))
    _vapid_public_key = d.get("public_key", "")
    raw_key = d.get("private_key") or d.get("private_key_pem", "")
    if not raw_key:
        return

    # ── Auto-migrate DER → raw scalar ───────────────────────────────────────
    try:
        import base64 as _b64
        decoded = _b64.urlsafe_b64decode(raw_key + "==")
        if len(decoded) > 32:
            # Old 121-byte DER: bytes 7–38 are the raw private scalar (SEC1 format)
            raw_bytes = decoded[7:39]
            raw_key   = _b64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
            d["private_key"] = raw_key
            VAPID_KEYS_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
            logger.info("_load_vapid: migrated DER private key → raw 32-byte scalar; saved to Postgres")
    except Exception as _ke:
        logger.warning("_load_vapid: key migration check failed: %s", _ke)

    _vapid_private_pem = raw_key

    # ── Pre-build Vapid instance (fastest + most reliable route into pywebpush)
    try:
        import base64 as _b64
        from py_vapid import Vapid
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        _vapid_instance = Vapid.from_raw(raw_key.encode())

        # Derive the public key from the private key — never trust the stored value.
        # VapidPkHashMismatch happens when the stored public key doesn't match the
        # private key; deriving it here guarantees they're always in sync.
        _derived_pub = _b64.urlsafe_b64encode(
            _vapid_instance.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        ).rstrip(b"=").decode()

        if _derived_pub != _vapid_public_key:
            logger.warning(
                "_load_vapid: stored public key MISMATCH (stored=%s… derived=%s…) — correcting",
                _vapid_public_key[:20], _derived_pub[:20]
            )
            d["public_key"] = _derived_pub
            VAPID_KEYS_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
        _vapid_public_key = _derived_pub  # always use cryptographically-derived value

        # ── Purge subscriptions that don't carry a matching vapid_pk tag ─────
        # Subscriptions saved before this fix have no vapid_pk → always stale.
        # Subscriptions saved with a different vapid_pk → key-changed → stale.
        # Both produce VapidPkHashMismatch at send time; purge them now so the
        # user gets a clean slate and re-subscribes with the current key.
        if PUSH_SUBS_PATH.exists():
            try:
                _all_subs = json.loads(PUSH_SUBS_PATH.read_text(encoding="utf-8"))
                _valid    = [s for s in _all_subs if s.get("vapid_pk") == _vapid_public_key]
                if len(_valid) != len(_all_subs):
                    PUSH_SUBS_PATH.write_text(json.dumps(_valid, indent=2), encoding="utf-8")
                    logger.info(
                        "_load_vapid: purged %d stale subscription(s) (vapid_pk mismatch or missing)",
                        len(_all_subs) - len(_valid)
                    )
            except Exception as _pe:
                logger.warning("_load_vapid: could not purge stale subs: %s", _pe)

        logger.info("_load_vapid: Vapid instance OK (public key %s…)", _vapid_public_key[:20])
    except Exception as _ve:
        _vapid_instance = None
        logger.warning("_load_vapid: could not build Vapid instance: %s", _ve)

_load_vapid()

def _load_push_subscriptions() -> list:
    if PUSH_SUBS_PATH.exists():
        return json.loads(PUSH_SUBS_PATH.read_text(encoding="utf-8"))
    return []

def _save_push_subscriptions(subs: list) -> None:
    PUSH_SUBS_PATH.write_text(json.dumps(subs, indent=2), encoding="utf-8")

def _remove_push_subscription(endpoint: str) -> None:
    subs = [s for s in _load_push_subscriptions()
            if s.get("subscription", {}).get("endpoint") != endpoint]
    _save_push_subscriptions(subs)

def _load_quote_requests() -> list:
    if QUOTE_REQUESTS_PATH.exists():
        try:
            return json.loads(QUOTE_REQUESTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_quote_requests(qrs: list) -> None:
    QUOTE_REQUESTS_PATH.write_text(json.dumps(qrs, indent=2, default=str), encoding="utf-8")

_bookings_write_lock = threading.Lock()

def _load_bookings_log() -> list:
    if BOOKINGS_LOG_PATH.exists():
        try:
            return json.loads(BOOKINGS_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_bookings_log(rows: list) -> None:
    BOOKINGS_LOG_PATH.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

def _load_bookings_seen() -> dict:
    if BOOKINGS_SEEN_PATH.exists():
        try:
            return json.loads(BOOKINGS_SEEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_bookings_seen(seen: dict) -> None:
    BOOKINGS_SEEN_PATH.write_text(json.dumps(seen, indent=2, default=str), encoding="utf-8")

def _log_booking(job_spec: dict, slot: dict, engineer_name: str,
                 conversation_id: str, event: dict, is_ai: bool = True) -> None:
    """Append a confirmed booking to the persistent bookings log for the
    Overview dashboard. quotedBy is resolved from the most recent answered quote
    request for this conversation (falls back to 'AI' when priced automatically)."""
    try:
        from datetime import datetime as _dtb, timezone as _tzb
        # Resolve who gave the price (answeredBy on the matching answered quote).
        quoted_by = "AI"
        if conversation_id:
            for _q in _load_quote_requests():  # newest-first
                if (_q.get("conversationId") == conversation_id
                        and _q.get("status") == "answered"):
                    quoted_by = _q.get("answeredBy") or "Operator"
                    break
        # Normalise services to a list of names.
        svc = job_spec.get("service", "")
        services = svc if isinstance(svc, list) else ([svc] if svc else [])
        price = job_spec.get("price", "")
        start = slot.get("start", "") or ""
        row = {
            "id":             event.get("id") or uuid.uuid4().hex,
            "createdAt":      _dtb.now(_tzb.utc).isoformat(),
            "jobDate":        start[:10],
            "startTime":      start[11:16],
            "postcode":       job_spec.get("postcode", ""),
            "customerName":   job_spec.get("customerName", ""),
            "services":       services,
            "price":          price,
            "engineerName":   engineer_name or "",
            "quotedBy":       quoted_by,
            "isAI":           bool(is_ai),
            "conversationId": conversation_id or "",
            "summary":        event.get("summary", ""),
            "htmlLink":       event.get("htmlLink", ""),
        }
        with _bookings_write_lock:
            rows = _load_bookings_log()
            rows.insert(0, row)
            _save_bookings_log(rows[:500])  # cap log size
        try:
            _sse_push("new_booking", {"booking": row})
        except Exception:
            pass
    except Exception as _exc:
        logger.warning("_log_booking failed: %s", _exc)

def _load_coverage_alerts() -> list:
    if COVERAGE_ALERTS_PATH.exists():
        try:
            return json.loads(COVERAGE_ALERTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_coverage_alerts(alerts: list) -> None:
    COVERAGE_ALERTS_PATH.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")

def _load_attention_alerts() -> list:
    if ATTENTION_ALERTS_PATH.exists():
        try:
            return json.loads(ATTENTION_ALERTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_attention_alerts(alerts: list) -> None:
    ATTENTION_ALERTS_PATH.write_text(json.dumps(alerts, indent=2, default=str), encoding="utf-8")

def _reconcile_coverage_alerts() -> None:
    """Auto-resolve pending coverage alerts whose area now has a bookable engineer
    (e.g. an engineer was re-ticked or given a calendar)."""
    from datetime import datetime as _dtn, timezone as _tzn
    try:
        from scheduler.smart_scheduler import get_coverage_status
    except Exception:
        return
    alerts  = _load_coverage_alerts()
    changed = False
    for a in alerts:
        if a.get("status") != "pending":
            continue
        try:
            status = get_coverage_status(a.get("postcode", "") or "")
        except Exception:
            continue
        if status.get("eligible"):
            a["status"]     = "resolved"
            a["resolvedAt"] = _dtn.now(_tzn.utc).isoformat()
            changed = True
    if changed:
        _save_coverage_alerts(alerts)

def _download_twilio_media(url: str, acct_sid: str, auth_token: str):
    """Download media from a Twilio-authenticated URL. Returns (bytes, content_type) or (None, None)."""
    try:
        import requests as _req
        r = _req.get(url, auth=(acct_sid, auth_token), timeout=20)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "image/jpeg")
    except Exception as _de:
        logger.warning("_download_twilio_media: %s – %s", url[:60], _de)
        return None, None

def _cleanup_old_media(max_age_days: int = 30) -> None:
    """Strip image attachment data from messages older than max_age_days to save space."""
    import time as _t
    cutoff = _t.time() - max_age_days * 86400
    try:
        from local_store import LocalConversationStore
        cs = LocalConversationStore()
        changed = False
        with cs._lock:
            cs._refresh()
            for cid, convo in cs._data.items():
                for msg in convo.get("messages", []):
                    atts = msg.get("attachments") or []
                    if not atts:
                        continue
                    saved_at = atts[0].get("savedAt", 0) if isinstance(atts[0], dict) else 0
                    if saved_at and saved_at < cutoff:
                        msg["attachments"] = []
                        changed = True
            if changed:
                cs._save()
        logger.info("_cleanup_old_media: completed (cutoff=%d days)", max_age_days)
    except Exception as _ce:
        logger.warning("_cleanup_old_media: %s", _ce)

def _load_notif_prefs() -> dict:
    if NOTIF_PREFS_PATH.exists():
        return json.loads(NOTIF_PREFS_PATH.read_text(encoding="utf-8"))
    return {}

def _save_notif_prefs(prefs: dict) -> None:
    NOTIF_PREFS_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")

_DEFAULT_NOTIF_PREFS = {
    "customer_message":  {"enabled": True, "tone": "customer"},
    "human_input":       {"enabled": True, "tone": "human"},
    "booking_complete":  {"enabled": True, "tone": "booking"},
}

def _send_push_to_all(title: str, body: str, notif_type: str, url: str = "/") -> None:
    """Send a Web Push notification to all subscribed users who have the type enabled."""
    if not _vapid_instance:
        logger.warning("_send_push_to_all: no VAPID instance — push skipped")
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — push skipped")
        return
    all_subs = _load_push_subscriptions()
    # Drop subscriptions created under a different VAPID key — they will always 403
    subs = [s for s in all_subs if s.get("vapid_pk", _vapid_public_key) == _vapid_public_key]
    stale_from_old_key = [s.get("subscription", {}).get("endpoint", "")
                          for s in all_subs if s not in subs]
    for ep in stale_from_old_key:
        _remove_push_subscription(ep)
    prefs = _load_notif_prefs()
    stale_endpoints: List[str] = []
    for entry in subs:
        email      = entry.get("user_email", "")
        user_prefs = prefs.get(email, _DEFAULT_NOTIF_PREFS)
        type_prefs = user_prefs.get(notif_type, _DEFAULT_NOTIF_PREFS.get(notif_type, {}))
        if not type_prefs.get("enabled", True):
            continue
        tone    = type_prefs.get("tone", notif_type)
        payload = json.dumps({"title": title, "body": body,
                              "type": notif_type, "tone": tone, "url": url})
        try:
            webpush(
                subscription_info=entry["subscription"],
                data=payload,
                vapid_private_key=_vapid_instance,
                vapid_claims={"sub": "mailto:admin@example.com"},
            )
        except Exception as _pe:
            logger.warning("Push failed for %s: %s", email, _pe)
            resp = getattr(_pe, "response", None)
            # 400/403/404/410 all mean the subscription is permanently dead
            if resp is not None and resp.status_code in (400, 403, 404, 410):
                stale_endpoints.append(
                    entry.get("subscription", {}).get("endpoint", ""))
    for ep in stale_endpoints:
        _remove_push_subscription(ep)

def _push_bg(title: str, body: str, notif_type: str, url: str = "/") -> None:
    """Fire push notification in a background thread so it never blocks a request."""
    threading.Thread(target=_send_push_to_all,
                     args=(title, body, notif_type, url), daemon=True).start()

@app.route("/api/push/vapid-public-key")
def push_vapid_key():
    return jsonify({"publicKey": _vapid_public_key})

@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    data = request.get_json(force=True) or {}
    email = session.get("user_email", "")
    logger.info("push_subscribe called: email=%r endpoint_prefix=%r", email, str(data.get("endpoint", ""))[:50])
    if not email:
        logger.warning("push_subscribe: no session email — returning 401")
        return jsonify({"error": "Unauthorized"}), 401
    endpoint = data.get("endpoint", "")
    if not endpoint:
        return jsonify({"error": "No endpoint"}), 400
    subs = _load_push_subscriptions()
    subs = [s for s in subs if s.get("subscription", {}).get("endpoint") != endpoint]
    subs.append({"user_email": email, "subscription": data, "vapid_pk": _vapid_public_key})
    _save_push_subscriptions(subs)
    logger.info("push_subscribe: saved subscription for %s (vapid_pk=%s… total %d)",
                email, _vapid_public_key[:16], len(subs))
    return jsonify({"ok": True})

@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    data     = request.get_json(force=True) or {}
    endpoint = data.get("endpoint", "")
    if endpoint:
        _remove_push_subscription(endpoint)
    return jsonify({"ok": True})

@app.route("/api/push/test", methods=["POST"])
def push_test():
    subs = _load_push_subscriptions()
    if not subs:
        return jsonify({"ok": False, "error": "No subscription found — tap Enable notifications first, then try again."}), 400
    if not _vapid_instance:
        return jsonify({"ok": False, "error": "VAPID key not loaded — contact support."}), 500
    data       = request.get_json(force=True) or {}
    notif_type = data.get("type", "customer_message")
    labels     = {"customer_message": "Customer message",
                  "human_input": "Human input needed",
                  "booking_complete": "Booking complete"}
    title   = labels.get(notif_type, "Test")
    payload = json.dumps({"title": title, "body": "This is a test notification.",
                          "type": notif_type, "url": "/"})
    sent = 0
    errs: list = []
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return jsonify({"ok": False, "error": "pywebpush not installed on server"}), 500
    stale: list = []
    for entry in subs:
        ep = entry.get("subscription", {}).get("endpoint", "")
        try:
            webpush(
                subscription_info=entry["subscription"],
                data=payload,
                vapid_private_key=_vapid_instance,
                vapid_claims={"sub": "mailto:admin@example.com"},
            )
            sent += 1
            logger.info("push_test: sent to %s", entry.get("user_email"))
        except Exception as pe:
            resp = getattr(pe, "response", None)
            code = resp.status_code if resp is not None else "?"
            errs.append(f"[{code}] {pe}")
            logger.warning("push_test failed for %s: %s", entry.get("user_email"), pe)
            if resp is not None and resp.status_code in (400, 404, 410):
                stale.append(ep)
    for ep in stale:
        _remove_push_subscription(ep)
    if errs and not sent:
        msg = errs[0]
        if "VapidPkHashMismatch" in msg:
            msg = ("Subscription was created with a different key. "
                   "Tap 'Re-register subscription' then try again.")
        return jsonify({"ok": False, "error": msg}), 500
    return jsonify({"ok": True, "sent": sent})

@app.route("/api/notifications/prefs", methods=["GET"])
def notif_prefs_get():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    prefs = _load_notif_prefs()
    return jsonify(prefs.get(email, _DEFAULT_NOTIF_PREFS))

@app.route("/api/notifications/prefs", methods=["POST"])
def notif_prefs_set():
    email = session.get("user_email", "")
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    data  = request.get_json(force=True) or {}
    prefs = _load_notif_prefs()
    prefs[email] = data
    _save_notif_prefs(prefs)
    return jsonify({"ok": True})

# ── Main app ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template(
        "index.html",
        service_presets={k: v.get("label", k.title()) for k, v in params.preset_options().items()},
        checkatrade_scraper_url=os.environ.get("CHECKATRADE_SCRAPER_PUBLIC_URL", ""),
    )


@app.route("/api/params", methods=["GET"])
def get_params():
    state = params.get().copy()
    state["service_presets"] = params.preset_options()
    return jsonify(state)


@app.route("/api/params", methods=["POST"])
def update_params():
    payload = request.json or {}
    state = params.update(payload)
    logger.info("Parameters updated: %s", json.dumps(state))
    return jsonify({"status": "ok", "params": state})


@app.route("/api/chat", methods=["POST"])
def chat():
    form = request.form
    message = form.get("message", "").strip()
    session_id = form.get("session_id") or uuid.uuid4().hex
    session = sessions.get(session_id)

    files = request.files.getlist("images[]")
    image_processor = ImageProcessor(params.get().get("limits", {}))
    image_assets: List[Dict[str, Any]] = []
    image_parts: List[Dict[str, Any]] = []
    try:
        for file in files:
            if not file or not file.filename:
                continue
            data_url, name = image_processor.process(file)
            image_assets.append({"name": name, "data_url": data_url})
            header, b64_data = data_url.split(",", 1)
            media_type = header.split(";")[0].split(":")[1]
            image_parts.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
            })
    except Exception as exc:
        logger.exception("Image processing failed")
        return jsonify({"error": str(exc)}), 400

    if not message and not image_parts:
        return jsonify({"error": "Message or at least one image is required."}), 400

    user_content: List[Dict[str, Any]] = []
    if message:
        user_content.append({"type": "text", "text": message})
    user_content.extend(image_parts)

    system_prompt = build_system_prompt(params.get(), defaults, customer_message=message)

    try:
        ai_client = AIClient()
    except Exception as exc:
        logger.exception("AI client initialisation failed")
        return jsonify({"error": str(exc)}), 500

    response_format = params.get().get("response_format", "json")
    history = sessions.get_history(session_id)
    try:
        raw_result = ai_client.chat(system_prompt, user_content, response_format, history=history)
        parsed = parse_model_output(raw_result["raw"], ai_client)
    except Exception as exc:
        logger.exception("Model call failed")
        return jsonify({"error": f"Unable to generate estimate: {exc}"}), 500

    pricing, modifiers = pricing_engine.compute_price(parsed)
    parsed["price_gbp"] = pricing
    parsed["modifiers"] = modifiers

    coverage = params.get().get("coverage_policy", {})
    max_requests = int(coverage.get("max_additional_photo_requests", 0))
    confidence_threshold = float(coverage.get("confidence_threshold", 0))

    needs_more = bool(parsed.get("needs_more_photos")) and parsed.get("next_request")
    photo_requests = session.get("photo_requests", 0)

    if needs_more and photo_requests < max_requests:
        sessions.increment_photo_requests(session_id)

    summary = build_summary(parsed, confidence_threshold)
    sessions.append_history(session_id, message, summary)

    payload = {
        "session_id": session_id,
        "ai": {
            "text": summary,
            "json": parsed,
            "price_gbp": pricing,
            "confidence": parsed.get("confidence"),
        },
        "images": image_assets,
        "photo_requests": session.get("photo_requests", 0),
    }
    return jsonify(payload)


@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok"})


def build_summary(parsed: Dict[str, Any], confidence_threshold: float) -> str:
    if parsed.get("summary"):
        return parsed["summary"]
    parts = []
    service = parsed.get("service", "service")
    area = parsed.get("area_estimate_m2")
    condition = parsed.get("condition", {}) or {}
    issues = condition.get("issues", []) or []
    notes = parsed.get("notes", "")
    price = parsed.get("price_gbp")
    confidence = parsed.get("confidence")
    missing = parsed.get("missing_sections", []) or []

    parts.append(f"Estimated {service} ~{area} m². Price £{price}.")
    if issues:
        parts.append("Issues: " + ", ".join(issues))
    if missing:
        parts.append("Missing coverage: " + ", ".join(missing))
    if confidence is not None and confidence < confidence_threshold:
        parts.append("Confidence is low; recommend on-site validation.")
    if notes:
        parts.append(notes)
    return " ".join(parts)


def build_system_prompt(state: Dict[str, Any], defaults_cfg: Dict[str, Any], customer_message: str = "") -> str:
    preset_key = state.get("service_preset")
    preset = defaults_cfg.get("service_presets", {}).get(preset_key, {})
    prompt = state.get("system_prompt", defaults_cfg.get("system_prompt", ""))
    focus = preset.get("focus")
    response_format = state.get("response_format", "json")
    instructions = [prompt]
    if focus:
        instructions.append(f"Service focus: {focus}")

    if TONE_PROFILE_PATH.exists():
        try:
            tone = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip()
            if tone:
                instructions.append(f"Communication style guide (follow this carefully when writing the summary reply):\n{tone}")
        except Exception:
            pass

    try:
        kb_prices = _load_kb_prices()
        if kb_prices:
            instructions.append(f"Price guide (use these as your reference when quoting):\n{_prices_to_text(kb_prices)}")
    except Exception:
        pass

    try:
        scenarios = _load_scenarios()
        if scenarios:
            instructions.append(_scenarios_to_text(scenarios))
    except Exception:
        pass

    query = customer_message.strip() if customer_message.strip() else "exterior cleaning estimate customer enquiry"
    examples = _find_similar_examples(query, top_k=10)
    if examples:
        lines = [
            "Style correction examples (TONE AND PHRASING ONLY — do NOT copy prices from these examples):",
            "PRICING WARNING: Any prices mentioned in the examples below may be outdated or wrong. "
            "ALWAYS use the price guide above. Never take a price from an example.",
        ]
        for ex in examples:
            lines.append(f"Customer: {ex['customer']}\nOwner: {ex['owner']}")
        instructions.append("\n".join(lines))

    instructions.append(
        "Respond using the configured response format and include a field named 'summary' that succinctly explains the quote."
    )
    if response_format == "json":
        instructions.append("Return strictly valid JSON without additional commentary.")
    elif response_format == "json+explanation":
        instructions.append("Return JSON followed by a short explanation prefixed by 'EXPLANATION:'.")
    elif response_format == "markdown":
        instructions.append("Return JSON inside a markdown fenced code block.")
    return "\n".join(instructions)


def parse_model_output(raw_text: str, ai_client: AIClient) -> Dict[str, Any]:
    try:
        return extract_json(raw_text)
    except json.JSONDecodeError:
        logger.warning("Initial JSON parsing failed; attempting repair")
        repaired = ai_client.repair_json(raw_text)
        try:
            return extract_json(repaired)
        except json.JSONDecodeError:
            logger.error("JSON repair failed")
            raise RuntimeError("Model returned invalid JSON")


def extract_json(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
    if text.lower().startswith("json"):
        text = text[4:].strip()
    if text.upper().startswith("EXPLANATION:"):
        text = text.split("EXPLANATION:", 1)[0].strip()
    # Remove explanation suffix if present
    if "EXPLANATION:" in text:
        text = text.split("EXPLANATION:", 1)[0].strip()
    return json.loads(text)


def _load_tune_examples() -> List[Dict[str, str]]:
    if TUNE_EXAMPLES_PATH.exists():
        try:
            return json.loads(TUNE_EXAMPLES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_tune_examples(examples: List[Dict]) -> None:
    TUNE_EXAMPLES_PATH.write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalise_tone_profile(text: str) -> str:
    """Ensure the tone profile is properly formatted as markdown bullet lines.

    Handles the case where the AI returns all bullets on one comma-separated line.
    """
    import re as _re
    text = text.strip()
    if not text:
        return text
    # If there are no newlines and the text contains '.,Capital' patterns, it's comma-separated
    if "\n" not in text and _re.search(r"\.,\s*[A-Z]", text):
        items = _re.split(r"\.,\s*(?=[A-Z])", text)
        lines = []
        for item in items:
            item = item.strip()
            if not item.endswith("."):
                item += "."
            if not item.startswith("- "):
                item = f"- {item}"
            lines.append(item)
        return "\n".join(lines)
    # Ensure each line that isn't already a bullet gets one
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("- ") and not line.startswith("* ") and not line.startswith("#"):
            line = f"- {line}"
        lines.append(line)
    return "\n".join(lines)


def _get_embedding(text: str) -> List[float]:
    """Return an embedding vector for text using OpenAI text-embedding-3-small."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return []
    try:
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:3000],
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding request failed: %s", exc)
        return []


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Dot product of two unit-norm vectors equals cosine similarity."""
    return sum(x * y for x, y in zip(a, b))


def _find_similar_examples(query_text: str, top_k: int = 10) -> List[Dict]:
    """Return the top_k examples most semantically similar to query_text.

    Falls back to the last top_k examples when embeddings are unavailable.
    Silently backfills missing embeddings on any example that lacks them.
    """
    examples = _load_tune_examples()
    if not examples:
        return []

    changed = False
    for ex in examples:
        if not ex.get("embedding"):
            combined = f"Customer: {ex['customer']}\nOwner: {ex['owner']}"
            ex["embedding"] = _get_embedding(combined)
            if ex["embedding"]:
                changed = True
    if changed:
        _save_tune_examples(examples)

    embedded = [ex for ex in examples if ex.get("embedding")]
    if not embedded:
        return examples[-top_k:]

    query_vec = _get_embedding(query_text)
    if not query_vec:
        return examples[-top_k:]

    scored = [(ex, _cosine_similarity(query_vec, ex["embedding"])) for ex in embedded]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [ex for ex, _ in scored[:top_k]]


def _extract_and_store_examples(conversation_text: str) -> int:
    """Ask the AI to pull clean customer→owner pairs from raw conversation text.

    Returns the number of new pairs successfully stored.
    Silently ignores any failures so the main analysis flow is never blocked.
    """
    extract_prompt = (
        "You are extracting training examples from WhatsApp-style customer conversations for a UK exterior cleaning business.\n\n"
        "Read the conversations below and extract up to 25 of the BEST customer→owner message pairs — "
        "pairs where the owner's reply clearly shows their personal style, pricing approach, or how they handle enquiries.\n\n"
        "Rules:\n"
        "- Only include complete exchanges (both customer and owner message must be clear)\n"
        "- Clean up timestamps and WhatsApp metadata — keep only the actual message text\n"
        "- Prefer pairs that show pricing discussion, job scope, booking, or handling objections\n"
        "- Skip pleasantries like 'thanks', 'no problem', or one-word replies\n"
        "- If a customer message is a photo, write '[photo sent]' as the customer text\n\n"
        "Return only valid JSON: an array of objects, each with fields \"customer\" and \"owner\".\n"
        "Example: [{\"customer\": \"Hi how much for a driveway clean?\", \"owner\": \"Hi! Typically starts at £80...\"}]\n"
        "Return only the JSON array, no commentary."
    )
    try:
        raw = _call_ai([
            {"role": "system", "content": extract_prompt},
            {"role": "user", "content": f"Conversations:\n\n{conversation_text[:60_000]}"},
        ], max_tokens=3000)
        pairs = json.loads(raw) if raw.strip().startswith("[") else _parse_tune_json(raw)
        if not isinstance(pairs, list):
            return 0
    except Exception as exc:
        logger.warning("Example extraction failed: %s", exc)
        return 0

    existing = _load_tune_examples()
    existing_set = {(ex["customer"][:60], ex["owner"][:60]) for ex in existing}

    added = 0
    for pair in pairs:
        customer = (pair.get("customer") or "").strip()
        owner = (pair.get("owner") or "").strip()
        if not customer or not owner:
            continue
        if (customer[:60], owner[:60]) in existing_set:
            continue
        embedding = _get_embedding(f"Customer: {customer}\nOwner: {owner}")
        existing.append({"customer": customer, "owner": owner, "embedding": embedding})
        existing_set.add((customer[:60], owner[:60]))
        added += 1

    if added:
        _save_tune_examples(existing)
        logger.info("Auto-extracted %d example pairs from uploaded conversations", added)

    return added


def _call_ai(messages: List[Dict[str, Any]], max_tokens: int = 1200, model: str | None = None) -> str:
    """Call Claude with a list of messages in OpenAI-compatible format.

    Extracts system messages into the top-level system parameter,
    passes everything else as the messages list.
    """
    if Anthropic is None:
        raise RuntimeError("anthropic package is required but not installed")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = Anthropic(api_key=api_key)

    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    chat_messages = [m for m in messages if m.get("role") != "system"]

    kwargs: Dict[str, Any] = {
        "model": model or CLAUDE_FAST_MODEL,
        "max_tokens": max_tokens,
        "messages": chat_messages,
    }
    if system_parts:
        kwargs["system"] = "\n\n".join(system_parts)

    response = client.messages.create(**kwargs)
    return _extract_claude_text(response)


_STAGE_BANNERS = {
    "ENQUIRY": (
        "NEW ENQUIRY (no photos yet). Your ONLY job in this reply is to ask for photos of the area "
        "and the postcode (Rule 0). Do NOT quote, do NOT ask about surface/property type, do NOT "
        "discuss dates. Nothing else matters at this stage."
    ),
    "QUOTING": (
        "QUOTING (photos received, no price given yet). Establish property type first if you don't "
        "know it (Rule 3), then give the price straight from the price guide. If the job genuinely "
        "cannot be priced from the guide, emit ONLY [NEEDS_HUMAN_QUOTE: <full details>] and write "
        "NOTHING else — never promise to 'come back with a quote'. Do NOT invent a price."
    ),
    "POST_QUOTE": (
        "CLOSING ON DATES (price already given). Close by offering to find dates (Rule 4) — never "
        "'getting booked in'. To check availability you MUST emit "
        "[CALENDAR_CHECK_NEEDED postcode=\"...\" service=\"...\" preference=\"...\"] (Rule 13). "
        "Never say you'll 'check' or 'have a look' without emitting that token. Do NOT repeat the price (Rule 12)."
    ),
    "BOOKING": (
        "BOOKING (a slot is being agreed). Collect name, surname and email together in ONE message "
        "(Rule 9) if you don't have them. Do NOT say the customer is 'booked in' until you actually "
        "emit [CALENDAR_BOOK_NEEDED] in the same reply (Rule 10). A slot offer is a question, not a confirmation."
    ),
}


def _detect_stage(
    conversation_history: Optional[List[Dict[str, Any]]],
    customer_message: str,
    has_photos: bool,
) -> str:
    """
    Classify the current conversation stage so the system prompt can foreground the
    handful of rules that matter RIGHT NOW (the AI skims a long rule list, so the
    single most relevant directive is hoisted to the very top of the prompt).

    Stages: ENQUIRY → QUOTING → POST_QUOTE → BOOKING. Heuristic and deliberately
    conservative — when unsure it falls back to the earlier, safer stage.
    """
    import re as _re_stage
    msgs = conversation_history or []
    assistant_text = " ".join(
        (t.get("content") or "")
        for t in msgs
        if (t.get("role") or "") in ("assistant", "ai", "owner")
    )

    price_given  = "£" in assistant_text
    # BOOKING only once an actual slot (day + time) has been OFFERED by us. A bare
    # "yes/ok/great" after a price is just acknowledgement — we still owe them dates,
    # so that stays POST_QUOTE (which pushes the CALENDAR_CHECK_NEEDED token).
    slot_offered = bool(_re_stage.search(
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        r'.{0,40}(\d{1,2}\s*(am|pm)|\d{1,2}[:.]\d{2})',
        assistant_text, _re_stage.IGNORECASE,
    ))

    if not has_photos:
        return "ENQUIRY"
    if not price_given:
        return "QUOTING"
    if slot_offered:
        return "BOOKING"
    return "POST_QUOTE"


def _generate_kb_reply(
    customer_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    goal_config: Optional[Dict[str, Any]] = None,
    max_tokens: int = 400,
    extra_context: str = "",
    has_photos: bool = False,
) -> str:
    """
    Generate a conversational WhatsApp reply using the fully-trained KB AI:
      - Custom system prompt (from KB / params)
      - Tone profile (tone_profile.md)
      - RAG few-shot examples (tune_examples.json)
      - Goal config (escalation triggers, calendar, etc.)
      - Claude via _call_ai (same as tune/simulate)
    """
    current_tone   = TONE_PROFILE_PATH.read_text(encoding="utf-8") if TONE_PROFILE_PATH.exists() else ""
    current_prompt = params.get().get("system_prompt", "")

    # ── Price guide + knowledge base (RAG: retrieve only what's relevant) ─────
    # Always includes the service menu and the full detail for the active service;
    # semantically retrieves the most relevant extra FAQs / diagnostic notes.
    try:
        kb_prices = _load_kb_prices()
        kb_scenarios = _load_scenarios()
        kb_ctx = _build_kb_context(customer_message, conversation_history, kb_prices, kb_scenarios)
        price_block = (
            "PRICE GUIDE & KNOWLEDGE BASE — always use these figures when quoting. Never invent a "
            "price or say you don't have pricing data. If the customer's service type is not in the "
            "menu, say you will need to visit to give an accurate quote.\n\n"
            + kb_ctx
            + "\n"
        ) if kb_ctx else ""
    except Exception:
        logger.exception("KB RAG context build failed; falling back to full price dump")
        try:
            kb_prices = _load_kb_prices()
            price_block = (
                "PRICE GUIDE — always use these figures when quoting. Never invent a price or say you "
                "don't have pricing data. If the customer's service type is not listed, say you will need "
                "to visit to give an accurate quote.\n\n"
                + _prices_to_text(kb_prices)
                + "\n"
            ) if kb_prices else ""
        except Exception:
            price_block = ""

    examples = _find_similar_examples(customer_message, top_k=8)

    few_shot_block = ""
    if examples:
        lines = [f"Customer: {ex['customer']}\nYou: {ex['owner']}" for ex in examples]
        few_shot_block = (
            "STYLE EXAMPLES — these show TONE AND PHRASING only. "
            "Any prices in these examples are historical and may be wrong. "
            "ALWAYS use the price guide above for all pricing. Never copy a price from an example.\n\n"
            + "\n\n".join(lines) + "\n\n"
        )

    # Goal config additions
    gc = goal_config or {}
    goal_block = ""
    if gc.get("goal"):
        goal_block += f"\nULTIMATE GOAL OF EVERY CONVERSATION:\n{gc['goal']}\n"
    if gc.get("process"):
        goal_block += f"\nPROCESS TO FOLLOW:\n{gc['process']}\n"
    escalation = (gc.get("escalationTriggers") or "").strip()
    if escalation:
        goal_block += (
            "\nESCALATION: If any of the following arise, prepend [NEEDS_HUMAN_REVIEW] to your reply:\n"
            f"{escalation}\n"
        )

    goal_block += (
        "\nCUSTOM QUOTE NEEDED: If the job is unusual, complex, or cannot be accurately priced from the "
        "standard price guide alone (e.g. commercial premises, non-standard materials, uncertain size, "
        "damaged surfaces needing assessment), your ENTIRE reply must be ONLY the token "
        "[NEEDS_HUMAN_QUOTE: <description>] and nothing else. "
        "CRITICAL: Do NOT write any message to the customer. Do NOT say 'I'll get a quote sorted', "
        "'I'll be back shortly', 'let me put a quote together', or acknowledge in any way. "
        "The customer must receive NO reply at all until a real, accurate quote is ready — a holding "
        "message that promises a quote with no price is worse than silence. "
        "Do NOT invent a price. Do NOT combine with [NEEDS_HUMAN_REVIEW].\n"
        "IMPORTANT — the <description> inside [NEEDS_HUMAN_QUOTE: ...] is a note for the human reviewer "
        "who will look at the photos. Include EVERY piece of relevant information you already know from "
        "the conversation: surface type (driveway, patio, path, render, etc.), material if mentioned "
        "(block paving, tarmac, concrete, sandstone, etc.), approximate size or area if known, "
        "condition notes (heavily stained, mossy, oil stains, etc.), property type, postcode if given, "
        "and anything else that will help price the job accurately. "
        "Do NOT leave out details the customer has already provided — the reviewer only has your note "
        "and the photos to go on, so give them as much context as possible.\n"
    )

    goal_block += (
        "\nNEEDS HUMAN ATTENTION (silent hand-off): There are situations you must NOT handle yourself. "
        "In these cases your ENTIRE reply must be ONLY the token [NEEDS_HUMAN_ATTENTION: <short reason for the human>] "
        "and nothing else — send the customer NO words at all (no holding message, no acknowledgement). "
        "A real person will see the alert and step in. Use it when:\n"
        "1. AI IDENTITY: The customer asks, in any form, whether they are talking to an AI, a bot, a robot, "
        "an automated system, or a real person (e.g. 'are you a bot?', 'is this an AI?', 'am I talking to a human?'). "
        "Do NOT confirm, deny, deflect, or joke about it — say NOTHING and emit the token, e.g. "
        "[NEEDS_HUMAN_ATTENTION: customer asked if they're talking to an AI].\n"
        "2. GENUINELY PERSONAL / SENSITIVE: The customer asks something genuinely personal, or references a "
        "specific experience with one of our employees/staff (a complaint about a person, something that "
        "happened on a previous visit, etc.). Hand these to a human rather than answering, e.g. "
        "[NEEDS_HUMAN_ATTENTION: customer is referencing a personal experience with an employee].\n"
        "Do NOT combine this token with any other token or with any customer-facing text.\n"
        "\nLIGHT PERSONAL / SMALL TALK: For light, harmless personal or off-topic questions (e.g. 'how's your "
        "day going?', casual chit-chat), do NOT use the token. Keep your answer professional, brief and a "
        "little boring, then steer politely back to how you can help with their cleaning enquiry. Only escalate "
        "with [NEEDS_HUMAN_ATTENTION] when something is genuinely personal/sensitive or involves an employee.\n"
    )

    # ── Calendar instructions (injected into KB path so the token system works) ──
    _cal_demo = gc.get("calendarDemoMode", True)
    if gc.get("calendarCheckEnabled", True):
        if _cal_demo:
            from datetime import date as _today_date
            _today_str = _today_date.today().strftime("%-d %B %Y")  # e.g. "4 June 2026"
            goal_block += (
                f"\nCALENDAR — AVAILABILITY (demo mode — no live calendar):\n"
                f"TODAY'S DATE: {_today_str}. All invented slots MUST be at least 1 working day from today.\n"
                "Once you have the customer's postcode, service needed, and estimated duration, "
                "invent 2–3 realistic slots across the next 3–5 working days from today and present them naturally. "
                "Do NOT include the year when mentioning dates. Do NOT emit any signal token.\n"
            )
        else:
            from datetime import date as _live_date
            _live_today = _live_date.today().strftime("%-d %B %Y")
            goal_block += (
                f"\nCALENDAR — BOOKING FLOW (live calendar connected):\n"
                f"TODAY'S DATE: {_live_today}. Never suggest dates in the past.\n"
                "PHILOSOPHY: Lead with OUR best available slots. Never ask when the customer is free first. "
                "Get dates in front of them quickly — don't make them wait through admin before seeing availability.\n\n"
                "STEP A — TRIGGER CALENDAR CHECK IMMEDIATELY:\n"
                "As soon as the customer agrees to the price and wants to proceed, emit the calendar check token. "
                "You already have their postcode from the property details step — use it now. "
                "Do NOT ask for name or email before checking dates. "
                "Emit this token at the very START of your reply:\n"
                "  [CALENDAR_CHECK_NEEDED postcode=\"UK_POSTCODE\" service=\"service description\" preference=\"\"]\n"
                "Rules for the token:\n"
                "  - postcode: the customer's UK postcode (from earlier in the conversation)\n"
                "  - service: brief description (e.g. gutter clean, driveway clean)\n"
                "  - preference: fill ONLY if the customer voluntarily mentioned a preferred day/time — otherwise leave empty (\"\").\n"
                "  - Emit this token ONCE. The system injects real slots before your reply reaches the customer.\n\n"
                "IMMEDIATE TOKEN — DAY PREFERENCE TRIGGER:\n"
                "If the customer mentions ANY day, time, or availability preference AT ANY POINT "
                "(e.g. 'is there anything Wednesday?', 'do you have anything next week?', "
                "'Wednesday works for me', 'anything on Friday?'), you MUST emit [CALENDAR_CHECK_NEEDED] "
                "immediately in that same reply with the preference field set — do NOT say you will check, "
                "do NOT say 'let me have a look', do NOT send any holding reply and wait. "
                "Emit the token NOW. The system handles the lookup; your job is to trigger it instantly.\n\n"
                "STEP B — PRESENT SLOTS:\n"
                "You will receive 'AVAILABLE SLOTS FROM CALENDAR: ...' in your context. "
                "Present only Option 1 warmly and naturally (e.g. 'We have [day] at [time], does that work for you?'). "
                "Do NOT list all options at once.\n"
                "  - If the customer declines but does NOT mention a specific day, offer Option 2 from the existing list.\n"
                "  - If the customer mentions a specific day or days they are free (e.g. 'Tuesday works', 'Monday no good but I'm free Thursday'), "
                "you MUST re-emit [CALENDAR_CHECK_NEEDED] with that day in the preference field — do NOT just cycle through existing options, "
                "and do NOT say 'let me check what we have on [day]' without emitting the token. "
                "Saying you will check WITHOUT emitting the token is a critical error — you have no ability to check the calendar yourself; "
                "the token is the ONLY mechanism that triggers the calendar lookup. "
                "Example: [CALENDAR_CHECK_NEEDED postcode=\"SW1A1AA\" service=\"driveway clean\" preference=\"Tuesday\"]\n\n"
                "CRITICAL — TOKEN OR NOTHING: When a calendar check is needed, ONLY emit the [CALENDAR_CHECK_NEEDED ...] token. "
                "NEVER write phrases like 'let me check', 'I'll have a look', 'let me see what we have', 'I'll check the diary' "
                "without the token — those phrases are meaningless and confuse the customer. The token handles the check; "
                "your text should respond naturally AFTER the slots are injected.\n\n"
                "STEP C — COLLECT BOOKING DETAILS AFTER SLOT IS CONFIRMED:\n"
                "Once the customer says yes to a specific slot, ask for their full name, email address, "
                "and full property address including postcode — ALL in ONE message. "
                "You MUST collect the full address (house number/name, street, town, postcode) to enter into the calendar. "
                "Only ask for details not already known from the conversation. "
                "Example: 'Perfect! Just pop your full name, email, and full address including postcode over and I'll get that booked in for you'\n\n"
                "STEP D — CREATE THE BOOKING:\n"
                "Once you have the customer's name, email, and full address including postcode, emit [CALENDAR_BOOK_NEEDED] — exactly those characters, no extra attributes — at the very start of your reply.\n"
            )

    if gc.get("calendarBookEnabled", True) and not _cal_demo:
        goal_block += (
            "\nCALENDAR — BOOKING CONFIRMATION:\n"
            "After emitting [CALENDAR_BOOK_NEEDED], confirm the booking warmly and share the disclaimer form: "
            "https://docs.google.com/forms/d/e/1FAIpQLSfsqpZf6FsfNBCzqhOaU-0O9oOAi5LRLv3EEJUxl8wb0nyQWA/viewform?usp=header\n"
            "Ask them to complete it before the visit.\n"
        )

    # ── Behavioural guardrails ────────────────────────────────────────────────
    _rule0 = (
        "0. PHOTOS ALREADY RECEIVED — do NOT ask for photos again under any circumstances. "
        "The customer has already sent photos of the area in this conversation. Continue the conversation naturally "
        "based on what has already been shared. Asking for photos again would be confusing and unprofessional.\n"
    ) if has_photos else (
        "0. PHOTOS FIRST — CRITICAL OVERRIDE (highest priority, cannot be overridden by any other rule or KB content): "
        "If the customer's enquiry involves pressure washing, driveway cleaning, patio cleaning, path cleaning, "
        "decking, render washing, fascia washing, or ANY external surface cleaning, AND no photos have been "
        "received or acknowledged in this conversation yet, your reply MUST consist ONLY of asking for photos "
        "and postcode. Do NOT ask about area type, surface type, property type, size, or any other details first. "
        "Do NOT give any pricing. Example response: "
        "'Thanks for getting in touch! To get you an accurate price, could you send some photos of the area along "
        "with your postcode?' "
        "This rule applies even if the Knowledge Base booking process says something different. "
        "Photos must come before anything else for surface cleaning jobs.\n"
    )
    goal_block += (
        "\nIMPORTANT RULES — follow these throughout every conversation:\n"
        + _rule0
        + "1. TONE IS NON-NEGOTIABLE: The tone guide takes absolute priority at all times. Every message must "
        "match the established style — conversational, warm, concise, no em dashes, natural UK English — "
        "regardless of service type, conversation stage, or how technical the topic gets. Never let pricing "
        "detail or calendar logistics override the tone.\n"
        "1a. EMOJI — USE SPARINGLY: Do NOT put an emoji at the end of every message — that reads as robotic. "
        "A friendly emoji (e.g. \U0001f60a) is fine every now and again, but most messages should have none. "
        "Never use the camera \U0001f4f8 or other picture/pictogram emojis.\n"
        "1b. VARY YOUR PHRASING: Never send the exact same sentence twice. Reword greetings, closes and "
        "booking prompts naturally each time so replies never look copy-pasted (e.g. 'Brilliant, just send "
        "your full name, email and full address with postcode and I'll get it booked in' vs 'Lovely, pop "
        "over your name, email and full address including postcode and I'll sort the booking').\n"
        "2. SERVICE FOCUS — BUT HANDLE MULTI-SERVICE CLEANLY: Lead with the service the customer first asked "
        "about and don't volunteer unrelated services. BUT customers often genuinely want more than one job "
        "(e.g. 'do you do the windows too?' or 'driveway and patio'). When that happens, do NOT brush it off or "
        "force it to 'later' — quote each service CLEARLY and SEPARATELY so there is no confusion: give a "
        "distinct price for each (use the correct pricing section for each one), e.g. 'Driveway clean: £X+VAT' "
        "and 'Window clean: £Y+VAT'. Confirm which services they'd like to go ahead with. When you then move to "
        "dates, book ALL the agreed services into ONE combined visit (the engineer does them in the same trip), "
        "and the calendar slot is sized to cover all of them together. Never quote a vague combined lump sum — "
        "always show the per-service breakdown so the customer (and the invoice) sees each line.\n"
        "3. PROPERTY TYPE: Always establish whether the property is a terrace, semi-detached, or detached "
        "BEFORE giving any price estimate. Property type significantly affects the price. If the customer "
        "asks for a price before you know the property type, ask for it first.\n"
        "4. PRICE CLOSE — NO HAGGLE INVITATION: After giving a price, always close by referencing the next "
        "concrete step, which is looking at dates — NOT confirming a booking. Use phrasings like: "
        "'If that all sounds good, just let me know and I'll have a look at some dates for you 😊' "
        "or 'Happy to sort some dates if that works for you 😊' or 'Just say the word and I'll find us a date 😊'. "
        "The closing MUST reference finding/sorting dates, not 'getting booked in'. "
        "NEVER use vague closes like 'let me know if you'd like to go ahead', 'get that sorted for you', "
        "'Does that sound alright?', 'Does that work for you?', or 'Is that OK?'. "
        "Those phrasings are banned — they invite hesitation without naming the next step.\n"
        "5. NO REPEAT QUESTIONS: Never ask for information the customer has already provided in this conversation "
        "(postcode, address, email, name, etc.). Refer back to what was already shared.\n"
        "6. PHONE NUMBER: The customer's phone number is already known — it is the number they are texting from. "
        "Never ask for it.\n"
        "7. NAME: If you already know the customer's first name, never ask for it again. When you need a surname "
        "for booking purposes, ask only 'And your surname?' — not for their full name again.\n"
        "8. NAME HANDLING: If you already know the customer's first name from earlier in the conversation, "
        "continue using it. If they later mention a different name (e.g. full name for booking), "
        "note it for admin but do not suddenly switch to calling them by the new name — it confuses people. "
        "If uncertain which name to use, simply avoid addressing them by name in that reply.\n"
        "9. GROUP QUESTIONS EFFICIENTLY — MINIMISE EXCHANGES: When you need multiple pieces of information "
        "to produce a quote (e.g. property type, number of storeys, extension, postcode), ask ALL of them "
        "together in a single message. Do NOT ask one question, wait for the answer, then ask the next. "
        "Every unnecessary back-and-forth exchange reduces the chance of a booking. "
        "The only exception is when the customer's reply makes a follow-up genuinely necessary "
        "(e.g. they say 'detached' and you now need to ask about a conservatory you could not have known about). "
        "Booking details (name, email, address) must also be requested together in one message.\n"
        "10. NEVER CONFIRM A BOOKING PREMATURELY: Do NOT say 'I've got you booked in', 'You're all booked', "
        "'You're booked in', 'I'll get that booked', 'all booked', or ANY phrase implying the booking is "
        "confirmed UNTIL you are actively emitting [CALENDAR_BOOK_NEEDED] in the same reply. "
        "Collecting the customer's name and email does NOT mean they are booked — that step only creates the booking. "
        "When presenting an available slot, always phrase it as an offer ('Does Friday 6 June at 8am work for you?') "
        "and wait for the customer to say yes before proceeding. "
        "Saying 'you're all booked in' before emitting [CALENDAR_BOOK_NEEDED] is a critical error.\n"
        "11. SIGN-OFF — STRICTLY BANNED: NEVER end a message with 'PowWash Team', 'The PowWash Team', "
        "'Thanks, PowWash Team', or any variation. This is absolutely prohibited. "
        "Do not add any sign-off at the end of WhatsApp messages — just end naturally after the content.\n"
        "12. PRICE RECAP: Once a price has been stated in the conversation, do NOT repeat the figure "
        "in a later message unless the customer specifically asks about price again. "
        "They remember the number — repeating it sounds pushy and unprofessional.\n"
        "13. CALENDAR LOOKUP — TOKEN IS MANDATORY: You CANNOT check the calendar yourself. "
        "The ONLY way to check availability is to emit [CALENDAR_CHECK_NEEDED postcode=\"...\" service=\"...\" preference=\"...\"]. "
        "NEVER say 'let me check', 'I'll have a look', 'let me see what we have on [day]', 'I'll check the diary', "
        "or ANY phrase implying you are checking the calendar, UNLESS you are simultaneously emitting the token. "
        "If the customer names a preferred day (e.g. 'Can you do Tuesday?'), you MUST emit the token with preference=\"Tuesday\" — "
        "do NOT just respond verbally. Verbally promising to check without the token is a critical error.\n"
        "13a. CAPTURE AVAILABILITY CONSTRAINTS: If the customer mentions WHEN they are (or aren't) available — "
        "e.g. 'I'm back from the school run by 8:15', 'not before 9', 'only mornings work', 'after 2pm', "
        "'I work from home Fridays' — you MUST pass that into the preference field of the calendar token, "
        "e.g. preference=\"available from 8:15am, mornings\". Never offer or agree a start time EARLIER than the "
        "time they said they're free. If they're free from 8:15, a 9am or 10am start is fine but an 8am start is "
        "not. When the slots come back, pick the one that best fits their stated window and phrase it as an offer.\n"
    )

    # Stage banner — hoist the few rules that matter RIGHT NOW to the very top so
    # the AI (which skims a long rule list) reads the priority directive first.
    _stage = _detect_stage(conversation_history, customer_message, has_photos)
    _stage_banner = (
        "════════════════════════════════════════════════════════════\n"
        f"▶ WHERE WE ARE RIGHT NOW: {_STAGE_BANNERS.get(_stage, '')}\n"
        "The full rules below still apply, but the line above is your priority for THIS reply.\n"
        "════════════════════════════════════════════════════════════\n\n"
    )

    system = (
        _stage_banner
        + f"{current_prompt}\n\n"
        f"Tone guide:\n{current_tone}\n\n"
        + (f"{price_block}\n" if price_block else "")
        + f"{goal_block}\n"
        f"{few_shot_block}"
        "Reply to the customer message as if you are the business owner texting back on WhatsApp. "
        "Be natural, concise, and true to the tone guide. Do not use formal email language or bullet points."
        + (f"\n\n{extra_context}" if extra_context else "")
    )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for turn in (conversation_history or []):
        role    = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            messages.append({"role": "user" if role in ("user", "customer") else "assistant", "content": content})
    messages.append({"role": "user", "content": customer_message})

    reply = _call_ai(messages, max_tokens=max_tokens)
    import re as _re_strip
    _pre_strip_reply = reply
    # Nuclear strip 1 — remove any "PowWash Team" sign-off regardless of source
    reply = _re_strip.sub(
        r'\s*[,.]?\s*(?:The\s+)?PowWash\s+Team\.?\s*$', '', reply,
        flags=_re_strip.IGNORECASE
    ).strip()
    # Nuclear strip 1b — remove formal email-style sign-offs the model sometimes adds
    # despite the tone guide (e.g. "Kind regards, Alex", "Best wishes\nAlex", "Regards").
    # These look out of place on WhatsApp. Matches the closing phrase plus an optional
    # trailing first name (same line or on the next line).
    reply = _re_strip.sub(
        r'\s*\n*\s*(?:kind regards|warm regards|best regards|best wishes|many thanks|regards)'
        r'\b[,!.]*\s*(?:\n+\s*)?(?:[A-Z][a-zA-Z]+)?[.!]*\s*$',
        '', reply, flags=_re_strip.IGNORECASE
    ).strip()
    # Safeguard — if sign-off stripping emptied the reply (e.g. the whole message was
    # just "Regards, Alex"), keep the original so we never send a blank message.
    if not reply.strip():
        reply = _pre_strip_reply.strip()
    # Nuclear strip 2 — replace em dashes (—) and en dashes (–) with a plain hyphen
    # The AI repeatedly uses these despite the tone guide ban; strip them here unconditionally
    reply = reply.replace('\u2014', ' - ').replace('\u2013', ' - ')
    # Collapse any double spaces left behind
    reply = _re_strip.sub(r'  +', ' ', reply).strip()
    return reply


# ─────────────────────────────────────────────────────────────────────────────
# CALENDAR TWO-PASS: resolve [CALENDAR_CHECK_NEEDED] signals in AI replies
# ─────────────────────────────────────────────────────────────────────────────
# When the conversation AI emits [CALENDAR_CHECK_NEEDED postcode="..." service="..." preference="..."],
# this system intercepts it, calls the scheduling agent, injects the real slot results, and
# re-runs the AI so the final reply presents the best slot naturally to the customer.
# ─────────────────────────────────────────────────────────────────────────────

_CAL_TOKEN_RE      = re.compile(r'\[CALENDAR_CHECK_NEEDED([^\]]*)\]', re.IGNORECASE)
_CAL_BOOK_TOKEN_RE = re.compile(r'\[CALENDAR_BOOK_NEEDED[^\]]*\]',   re.IGNORECASE)
_QUOTE_TOKEN_RE    = re.compile(r'\[NEEDS_HUMAN_QUOTE:\s*(.+?)\]',   re.IGNORECASE | re.DOTALL)
_COVERAGE_TOKEN_RE = re.compile(r'\[COVERAGE_GAP([^\]]*)\]',         re.IGNORECASE)
_ATTENTION_TOKEN_RE = re.compile(r'\[NEEDS_HUMAN_ATTENTION:\s*(.+?)\]', re.IGNORECASE | re.DOTALL)

# Phrases the AI writes when it intends to check the calendar but forgot the token.
# Kept tight — only match clear "I will check the calendar" constructions, not
# innocent phrases like "looking forward to" or "have a look at the photo".
_CAL_PLACEHOLDER_RE = re.compile(
    r"(let me (have a look|check|see what we have)|"
    r"i('ll| will) (have a look|check the calendar|check the diary|look at availability)|"
    r"have a look at (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"i('ll| will) (check|look) (what we have|availability|what's available))",
    re.IGNORECASE,
)
# Day mentions specifically in the customer message
_CUSTOMER_DAY_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"anything (on |this |next )?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"is there anything (on |this |next )?(monday|tuesday|wednesday|thursday|friday)|"
    r"any slots? (on |for )?(monday|tuesday|wednesday|thursday|friday))\b",
    re.IGNORECASE,
)
# Postcode pattern
_PC_RE_CAL = re.compile(r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b', re.IGNORECASE)


def _enforce_calendar_token(
    draft: str,
    customer_message: str,
    conversation_history: list,
    goal_config: dict,
    extra_search_text: str = "",
) -> str:
    """
    If the AI wrote a placeholder ('I'll have a look at Wednesday') without emitting
    [CALENDAR_CHECK_NEEDED], inject the token so the two-pass fires correctly.
    Conservative — only fires when a specific day name appears in the customer message
    AND a clear checking-phrase appears in the draft AND a postcode is known.
    Always returns the original draft on any exception so the AI never goes silent.
    """
    try:
        gc = goal_config or {}
        if gc.get("calendarDemoMode", True) or not gc.get("calendarCheckEnabled", True):
            return draft
        if not draft:
            return draft
        # Only act when customer mentions a specific day AND AI wrote a placeholder
        if not _CUSTOMER_DAY_RE.search(customer_message):
            return draft
        if _CAL_TOKEN_RE.search(draft):
            return draft  # token already present — nothing to do
        if not _CAL_PLACEHOLDER_RE.search(draft):
            return draft  # no placeholder phrase — AI replied normally

        # Extract postcode from conversation history — ONLY inject if we have one.
        # Search the filtered history, the current message AND the full raw
        # conversation text (extra_search_text) so a postcode given earlier in any
        # message — not just those that survived history filtering — is still found.
        all_text = " ".join(
            (m.get("content") or m.get("text") or "")
            for m in (conversation_history or [])
        ) + " " + customer_message + " " + (extra_search_text or "")
        pc_m = _PC_RE_CAL.search(all_text)
        if not pc_m:
            # No postcode known — can't call scheduler, leave draft as-is
            logger.info("_enforce_calendar_token: placeholder detected but no postcode found — leaving draft")
            return draft
        postcode = re.sub(r'\s+', ' ', pc_m.group(1).upper().strip())

        # Extract the specific day preference from the customer message
        day_m = re.search(
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            customer_message, re.IGNORECASE,
        )
        preference = day_m.group(1).capitalize() if day_m else ""

        # Infer service from history
        service = "cleaning"
        for kw in ["driveway", "patio", "gutter", "render", "fascia", "conservatory",
                    "roof", "path", "decking", "fence"]:
            if kw in all_text.lower():
                service = kw + " clean"
                break

        token = (
            f'[CALENDAR_CHECK_NEEDED postcode="{postcode}" '
            f'service="{service}" preference="{preference}"]'
        )
        logger.info("_enforce_calendar_token: injecting %s (replaced placeholder)", token)
        return token

    except Exception as _exc:
        logger.warning("_enforce_calendar_token error — returning original draft: %s", _exc)
        return draft

def _parse_cal_token(token_body: str) -> dict:
    """Extract postcode, service, preference from the CALENDAR_CHECK_NEEDED token body."""
    def _attr(key):
        m = re.search(rf'{key}="([^"]*)"', token_body, re.IGNORECASE)
        return m.group(1).strip() if m else ""
    return {
        "postcode":   _attr("postcode"),
        "service":    _attr("service"),
        "preference": _attr("preference"),
    }


def _parse_token_attrs(token_body: str) -> dict:
    """Generic key="value" attribute parser for signal tokens."""
    return {k.lower(): v.strip() for k, v in re.findall(r'(\w+)="([^"]*)"', token_body or "")}


def _format_slots_for_ai(result: dict) -> str:
    """Format scheduling agent results into a concise context string for the AI."""
    from datetime import date as _td
    today_str = _td.today().strftime("%-d %B %Y")
    current_year = _td.today().year

    if not result.get("ok") or not result.get("recommendations"):
        return (
            f"TODAY'S DATE: {today_str}\n"
            "No slots currently available — ask the customer for their general availability. "
            "Do NOT emit any [CALENDAR_CHECK_NEEDED] token or say you will 'have a look' — "
            "just ask which days/times suit them best."
        )

    lines = []
    from datetime import datetime as _dt_fmt
    for rec in result["recommendations"]:
        rank    = rec.get("rank", "?")
        eng     = rec.get("engineer", "")
        slot    = rec.get("timeSlot", "")
        note    = rec.get("travelNote", "")
        caveat  = rec.get("caveat", "")
        # Always recompute the date string from the authoritative ISO rawSlot.start
        # — never trust the LLM's day-name which can be wrong (e.g. June 9 2025 was
        #   Monday; the agent incorrectly labels June 9 2026 as Monday too).
        raw_start = rec.get("rawSlot", {}).get("start", "")
        if raw_start:
            try:
                dt   = _dt_fmt.fromisoformat(raw_start)
                date = dt.strftime("%A %-d %B")   # e.g. "Tuesday 9 June"
                slot = slot or f"{dt.strftime('%H:%M')} – {_dt_fmt.fromisoformat(rec.get('rawSlot',{}).get('end', raw_start)).strftime('%H:%M')}"
            except Exception:
                date = rec.get("date", "")
        else:
            date = rec.get("date", "")
            if date and str(current_year) not in date:
                date = f"{date} {current_year}"
        line    = f"  Option {rank}: {date}, {slot} — {eng}."
        if note:   line += f" {note}."
        if caveat: line += f" ⚠ {caveat}"
        lines.append(line)

    slots_text = "\n".join(lines)
    return (
        f"TODAY'S DATE: {today_str}.\n"
        f"AVAILABLE SLOTS FROM CALENDAR:\n{slots_text}\n\n"
        "YOUR JOB IN THIS REPLY: Propose Option 1 to the customer in a relaxed, low-key way and ask if it suits. "
        "Example: 'No problem, we have Wednesday 24th around 2pm if that suits?' "
        "CRITICAL RULES for this reply:\n"
        "  - NEVER include the year in the date — just day name and date, e.g. 'Wednesday 24th' or 'Wednesday 24 June'.\n"
        "  - ALWAYS say 'around' before the time, e.g. 'around 2pm' not 'at 2pm' — so the customer knows it is approximate.\n"
        "  - Keep the tone simple and matter-of-fact — no 'Great news!', no enthusiasm. Just friendly and direct.\n"
        "  - DO NOT say 'I've got you booked in' or any phrase that implies the booking is confirmed.\n"
        "  - DO NOT emit [CALENDAR_BOOK_NEEDED] in this reply.\n"
        "  - CRITICAL: The slots above are REAL availability already fetched for you. "
        "Do NOT emit [CALENDAR_CHECK_NEEDED] and do NOT say 'let me have a look' / 'let me check' / "
        "'let me see what we've got' — you have the answer, so PRESENT it now as a concrete offer.\n"
        "  - DO NOT list Option 2 or Option 3 unless the customer declines Option 1 first.\n"
        "  - The customer MUST explicitly say yes to the proposed slot before you can confirm the booking.\n"
        "  - This is a PROPOSAL, not a confirmation. Always end with something like 'does that work for you?'"
    )


_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _occasional_emoji(emoji: str = "😊", chance: float = 0.35) -> str:
    """Return a leading-space emoji roughly `chance` of the time, else "".

    Keeps replies feeling human: a friendly emoji now and again rather than one
    tacked onto the end of every single message (which reads as robotic)."""
    return f" {emoji}" if random.random() < chance else ""


def _preference_to_target_date(preference: str) -> str:
    """Resolve a named weekday in the customer's preference (e.g. 'Thursday',
    'next Tuesday') to the soonest matching ISO date, so the scheduler can
    hard-target that day instead of treating it as free-text and defaulting to
    the earliest available day. Returns '' when no weekday is mentioned."""
    if not preference:
        return ""
    from datetime import date as _d, timedelta as _delta
    m = re.search(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        preference, re.IGNORECASE,
    )
    if not m:
        return ""
    want = _WEEKDAYS[m.group(1).lower()]
    is_next = "next" in preference.lower()
    today = _d.today()
    # Start from tomorrow to avoid same-day ambiguity; 'next X' skips this week's.
    for i in range(1, 22):
        cand = today + _delta(days=i)
        if cand.weekday() == want:
            if is_next and i <= 7:
                continue
            return cand.isoformat()
    return ""


def _deterministic_slot_reply(result: dict, preference: str = "", strict: bool = False) -> str:
    """Build a customer-facing slot offer directly from the scheduler result.

    Used as a guaranteed fallback when the AI re-run fails to present the slots
    (returns empty, re-emits a calendar token, or repeats a 'let me have a look'
    placeholder). This ensures the customer ALWAYS receives a concrete date
    instead of a dead-end 'let me check' promise. When the customer asked for a
    specific weekday, prefer a recommendation that actually falls on that day."""
    from datetime import datetime as _dt
    recs = (result or {}).get("recommendations") or []
    if not recs:
        return ""

    want = None
    m = re.search(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        preference or "", re.IGNORECASE,
    )
    if m:
        want = _WEEKDAYS[m.group(1).lower()]

    def _parse(rec):
        raw = (rec.get("rawSlot") or {}).get("start", "")
        if not raw:
            return None, "", ""
        try:
            d = _dt.fromisoformat(raw)
        except Exception:
            return None, "", ""
        return d, d.strftime("%A %-d %B"), d.strftime("%-I%p").lower()

    chosen = None
    if want is not None:
        for rec in recs:
            d, _, _ = _parse(rec)
            if d is not None and d.weekday() == want:
                chosen = rec
                break
    if chosen is None:
        # In strict mode, a named weekday with no matching recommendation must
        # NOT silently downgrade to the earliest day — the caller will read the
        # calendar directly for that weekday instead.
        if strict and want is not None:
            return ""
        chosen = recs[0]

    _, date_label, time_label = _parse(chosen)
    if not date_label:
        date_label = chosen.get("date", "")
    if not time_label:
        ts = chosen.get("timeSlot", "")
        time_label = ts.split("–")[0].strip() if ts else ""

    if date_label and time_label:
        return f"No problem, we have {date_label} around {time_label} if that suits?{_occasional_emoji()}"
    if date_label:
        return f"No problem, we have availability on {date_label} if that suits?{_occasional_emoji()}"
    return ""


def _earliest_slot_on_weekday(postcode: str, service: str, weekday: int, notes: str = "") -> Optional[tuple]:
    """Read the calendar directly for the earliest REAL free slot on a given
    weekday (0=Mon … 6=Sun), independent of the logistics AI's ranking.

    The scheduling agent ranks slots by travel efficiency and routinely ignores
    a customer's requested day (filling from the front instead). When a customer
    explicitly asks for, say, Thursday, we must offer an actual Thursday slot —
    so we bypass the AI and scan the genuine free-slot calendar. Returns
    (date_label, time_label) for the soonest matching slot, or None."""
    try:
        from scheduler.ai_scheduling_agent import (
            _fetch_calendar_context, load_agent_config, resolve_job_duration,
        )
        from scheduler.smart_scheduler import get_coverage_status
        from datetime import datetime as _dt
        cfg = load_agent_config()
        dur = resolve_job_duration(service, notes, cfg)
        eligible = (get_coverage_status(postcode) or {}).get("eligible", [])
        if not eligible:
            return None
        caldata = _fetch_calendar_context(eligible, cfg.get("maxDaysAhead", 21), dur)
        days = caldata.get("days", {}) or {}
        for ds in sorted(days):
            try:
                d0 = _dt.fromisoformat(ds)
            except Exception:
                continue
            if d0.weekday() != weekday:
                continue
            best = None
            for _eng, slots in (days[ds].get("engineers", {}) or {}).items():
                for s in slots:
                    st = s.get("start")
                    if st and (best is None or st < best):
                        best = st
            if best:
                dt = _dt.fromisoformat(best)
                return dt.strftime("%A %-d %B"), dt.strftime("%-I%p").lower()
        return None
    except Exception as exc:
        logger.warning("_earliest_slot_on_weekday failed: %s", exc)
        return None


# Safe non-empty replies. The customer must NEVER receive total silence on a
# normal conversational turn — only the deliberate coverage-gap / human-quote
# branches are allowed to stay silent. These fallbacks keep the thread alive
# when calendar resolution or an AI re-run would otherwise yield an empty draft.
_CAL_FALLBACK_REPLY = (
    "Let me check our availability for you and I'll come back shortly with some "
    "options. In the meantime, do mornings or afternoons generally suit you best? 😊"
)
_SAFE_FALLBACK_REPLY = (
    "Thanks for your message! Let me look into that for you and I'll come straight "
    "back to you 😊"
)


def _resolve_calendar_signals(
    draft: str,
    customer_message: str,
    conversation_history,
    goal_config: dict,
    has_photos: bool = False,
) -> str:
    """
    If draft contains [CALENDAR_CHECK_NEEDED ...], call the scheduling agent and
    re-run the conversation AI with real slot data injected. Returns the final clean reply.
    """
    match = _CAL_TOKEN_RE.search(draft)
    if not match:
        return draft

    token_body = match.group(1)
    params     = _parse_cal_token(token_body)
    postcode   = params["postcode"]
    service    = params["service"]
    preference = params["preference"]

    # Strip the token from the draft regardless (prevent it leaking to customer)
    draft_stripped = _CAL_TOKEN_RE.sub("", draft).strip()

    if not postcode or not service:
        # Not enough info to call the scheduling agent — return stripped draft.
        # If stripping the token left nothing, the customer would get silence — fall
        # back to a safe reply so they always hear something back.
        logger.info("CALENDAR_CHECK_NEEDED fired but postcode/service missing — skipping calendar call")
        if not draft_stripped:
            logger.warning("_resolve_calendar_signals: empty draft after token strip (missing postcode/service) — using fallback")
            return _CAL_FALLBACK_REPLY
        return draft_stripped

    try:
        from scheduler.ai_scheduling_agent import recommend_slots as _recommend_slots
        _target = _preference_to_target_date(preference)
        if _target:
            logger.info("Calendar two-pass: resolved preference %r -> target_date %s", preference, _target)
        result = _recommend_slots(
            job_postcode=postcode,
            service_type=service,
            customer_notes=preference or "",
            target_date=_target or None,
        )
        if result.get("coverageGap"):
            _names = ", ".join(b.get("name", "") for b in result.get("blockedEngineers", []))
            logger.info("Calendar two-pass: COVERAGE GAP for %s — only blocked engineers: %s", postcode, _names)
            # Emit a signal token the live messaging path turns into a coverage
            # alert + silent hold. Non-live paths strip it.
            return f'[COVERAGE_GAP postcode="{postcode}" service="{service}" engineers="{_names}"]'
        slots_context = _format_slots_for_ai(result)
        logger.info("Calendar two-pass: %d slots found for %s (%s)", len(result.get("recommendations", [])), postcode, service)
    except Exception as exc:
        logger.warning("Calendar two-pass scheduling call failed: %s", exc)
        # Never send the AI's pre-token 'let me have a look' placeholder — it
        # promises a check that will never arrive. Prefer a safe holding reply.
        if draft_stripped and not _CAL_PLACEHOLDER_RE.search(draft_stripped):
            return draft_stripped
        return _CAL_FALLBACK_REPLY

    # ── SPECIFIC-DAY REQUEST: present the requested weekday deterministically ──
    # When the customer names a day (e.g. "anything on Thursday?"), the logistics
    # AI frequently ranks by travel and returns a DIFFERENT day, and the
    # conversation re-run then offers the wrong day or a "let me check"
    # placeholder. So for a named weekday we build the offer ourselves: prefer a
    # recommendation on that day, else read the calendar directly for the soonest
    # real free slot on that weekday. Only if the requested day has no
    # availability at all do we fall through to the AI re-run (nearest alternative).
    _wd_m = re.search(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        preference or "", re.IGNORECASE,
    )
    if _wd_m:
        requested_wd = _WEEKDAYS[_wd_m.group(1).lower()]
        day_reply = _deterministic_slot_reply(result, preference, strict=True)
        if not day_reply:
            direct = _earliest_slot_on_weekday(postcode, service, requested_wd, preference or "")
            if direct:
                date_label, time_label = direct
                day_reply = f"No problem, we have {date_label} around {time_label} if that suits? 😊"
        if day_reply:
            logger.info("Calendar two-pass: specific-day request (%s) — deterministic offer: %s",
                        preference, day_reply)
            return day_reply
        logger.info("Calendar two-pass: no availability on requested day (%s) — falling back to AI re-run", preference)

    # Re-run the AI with slot data injected into context
    try:
        final = _generate_kb_reply(
            customer_message=customer_message,
            conversation_history=conversation_history,
            goal_config=goal_config,
            max_tokens=450,
            extra_context=slots_context,
            has_photos=has_photos,
        )
        final_clean = _CAL_TOKEN_RE.sub("", final or "").strip()

        # The re-run sometimes ignores the injected slots: it sees the named day
        # in the customer message and tries to "check" AGAIN — re-emitting a
        # calendar token and/or a "let me have a look" placeholder. The two-pass
        # only runs once, so that token gets stripped downstream and the customer
        # is left with a dead-end promise and NO date (the reported bug). Detect
        # that failure and present the slots deterministically from the scheduler
        # result instead, so a concrete date ALWAYS goes out.
        re_run_failed = (
            not final_clean
            or bool(_CAL_TOKEN_RE.search(final or ""))
            or bool(_CAL_PLACEHOLDER_RE.search(final_clean))
        )
        if re_run_failed:
            deterministic = _deterministic_slot_reply(result, preference)
            if deterministic:
                logger.warning(
                    "_resolve_calendar_signals: re-run failed to present slots (%r) — using deterministic offer",
                    (final_clean or "")[:80],
                )
                return deterministic
            if final_clean:
                return final_clean
            if draft_stripped and not _CAL_PLACEHOLDER_RE.search(draft_stripped):
                return draft_stripped
            return _CAL_FALLBACK_REPLY
        return final_clean
    except Exception as exc:
        logger.warning("Calendar two-pass re-run failed: %s", exc)
        deterministic = _deterministic_slot_reply(result, preference)
        if deterministic:
            return deterministic
        if draft_stripped and not _CAL_PLACEHOLDER_RE.search(draft_stripped):
            return draft_stripped
        return _CAL_FALLBACK_REPLY


_RELAY_DUR_RE = re.compile(
    r"""
    (?:\s*[,;.\-–—]\s*|\s+)?                                  # optional leading separator
    (?:and\s+|but\s+|then\s+)?
    (?:i['’]?(?:ll|d)\s+|it['’]?(?:s|ll)?\s+|this\s+|that\s+|the\s+(?:job|work)\s+|we['’]?ll\s+|you['’]?ll\s+)?
    (?:should\s+|will\s+|would\s+|can\s+|usually\s+|normally\s+|typically\s+|['’]?ll\s+|need\s+to\s+)?
    (?:allow|take|takes|taking|spend|need|needs|require|requires|last|lasts|be|budget|set\s+aside|give\s+it)?\s*
    (?:me\s+|us\s+|you\s+|it\s+|for\s+|about\s+|around\s+|roughly\s+|approx(?:imately)?\.?\s+|up\s+to\s+|just\s+|only\s+|maybe\s+|probably\s+|a\s+|an\s+)*
    \b(?P<num>\d+(?:\.\d+)?)\s*(?:(?:-|–|to|or)\s*(?P<num2>\d+(?:\.\d+)?)\s*)?
    (?P<unit>hours?|hrs?|h|minutes?|mins?)\b
    (?:\s+(?:of\s+work|or\s+so|work|on\s+(?:the\s+)?(?:day|site)|to\s+complete|to\s+do|on\s+site))?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _strip_duration_for_relay(advice: str) -> str:
    """Remove job-time estimates (e.g. 'allow 3 hours', 'takes 2-3 hrs') from
    owner quote advice BEFORE it is injected into the customer reply prompt. The
    job duration is INTERNAL scheduling info — the AI must never relay it to the
    customer. The full advice (incl. duration) is still stored on the quote
    request so the scheduler can size the calendar slot. Only strips realistic
    job lengths (30–600 min) so phrases like 'within 24 hours' or '50m of gutter'
    are left untouched."""
    if not advice:
        return advice

    def _maybe_strip(m: "re.Match") -> str:
        try:
            v1 = float(m.group("num"))
        except (TypeError, ValueError):
            return m.group(0)
        v2 = None
        if m.group("num2"):
            try:
                v2 = float(m.group("num2"))
            except ValueError:
                v2 = None
        val = max(v1, v2) if v2 is not None else v1
        unit = (m.group("unit") or "").lower()
        # All hour units start with 'h' (hour/hrs/h); minute units start with 'm'.
        mins = val * 60 if unit.startswith("h") else val
        return " " if 30 <= mins <= 600 else m.group(0)

    out = _RELAY_DUR_RE.sub(_maybe_strip, advice)
    # Tidy whitespace / dangling punctuation left behind by removed clauses.
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([,;:\-–—])\s*(?=[,;:.\-–—])", "", out)
    out = re.sub(r"^[\s,;:.\-–—]+", "", out)
    out = re.sub(r"[\s,;:\-–—]+$", "", out).strip()
    # If stripping removed everything meaningful, keep the original advice.
    if not re.search(r"[A-Za-z0-9£]", out):
        return advice.strip()
    return out


def _extract_and_create_booking(conversation_history: list, ai_reply: str,
                                explicit_duration_mins: int | None = None,
                                customer_phone: str = "") -> dict:
    """
    Ask Claude to pull booking details out of the conversation, then create a Google Calendar event.
    Returns {"ok": True, "summary": ..., "details": ..., "htmlLink": ...}
         or {"ok": False, "error": ...}
    """
    lines = []
    for m in (conversation_history or []):
        role    = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"{'Customer' if role == 'user' else 'AI'}: {content}")
    lines.append(f"AI: {ai_reply}")
    conv_text = "\n".join(lines)

    from datetime import date as _date
    today_iso = _date.today().isoformat()  # e.g. "2026-06-04"
    extraction_prompt = (
        f'TODAY\'S DATE: {today_iso}\n\n'
        'Extract booking details from this conversation as JSON with exactly these fields:\n'
        '{"customerName":"","customerEmail":"","customerAddress":"","postcode":"",'
        '"services":[{"service":"","price":""}],'
        '"engineerName":"","date":"YYYY-MM-DD","startTime":"HH:MM","endTime":"HH:MM"}\n'
        'IMPORTANT: "services" is a LIST — add one object per DISTINCT service the customer '
        'agreed to book (e.g. a driveway clean AND window cleaning = two entries). If only one '
        'service was booked, return a single-item list. Only include services the customer actually '
        'agreed to, not ones merely discussed or declined.\n'
        'Leave unknown fields as empty strings. For each price, extract the quoted figure including £ and '
        'VAT note (e.g. "£145+VAT"). For date/time use the single combined slot that was agreed. '
        f'All dates must be in {_date.today().year} or later — never in the past.\n\n'
        f'Conversation:\n{conv_text}'
    )

    try:
        raw = _call_ai([
            {"role": "system", "content": "Extract structured booking data. Reply with valid JSON only, no other text."},
            {"role": "user",   "content": extraction_prompt},
        ], max_tokens=250)
        # Match the OUTERMOST braces (greedy) so nested service objects survive —
        # a non-greedy/[^{}] regex would truncate the "services" list.
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        details: dict = json.loads(m.group() if m else raw.strip())
    except Exception as exc:
        return {"ok": False, "error": f"Could not extract booking details: {exc}"}

    if not details.get("date") or not details.get("startTime"):
        return {"ok": False, "error": "No agreed date/time found in conversation"}

    # Normalise services into parallel name/price lists. Newer extraction returns a
    # "services" list of {service, price}; tolerate the legacy single service/price
    # shape too so older callers/data keep working.
    services_in = details.get("services")
    svc_names: list = []
    svc_prices: list = []
    if isinstance(services_in, list) and services_in:
        for item in services_in:
            if isinstance(item, dict):
                name = str(item.get("service", "")).strip()
                if not name:
                    continue
                svc_names.append(name)
                svc_prices.append(str(item.get("price", "")).strip())
    if not svc_names:
        # Fall back to legacy flat fields.
        if details.get("service"):
            svc_names = [str(details["service"]).strip()]
            svc_prices = [str(details.get("price", "")).strip()]

    def _clean_time(t: str) -> str:
        t = t.replace(":", "").strip()[:4]
        return f"{t[:2]}:{t[2:]}" if len(t) == 4 else t

    # Resolve a realistic job duration so the event is sized to the service
    # (gutters ~1h, render ~3h, …) and honours any explicit time the owner gave
    # in quote feedback (e.g. "allow 3 hours"). For a multi-service booking the
    # slot must be big enough for ALL services, so SUM the per-service durations.
    from scheduler.ai_scheduling_agent import resolve_job_duration as _resolve_dur
    if explicit_duration_mins and explicit_duration_mins > 0:
        # Owner gave an explicit job time in their quote advice. That duration is
        # stripped from the customer-facing reply (internal only) so it never
        # reaches the conversation text — recover it here so the calendar slot is
        # still sized correctly for the whole job.
        _job_dur = explicit_duration_mins
    elif svc_names:
        _job_dur = sum(_resolve_dur(n, conv_text) or 120 for n in svc_names)
    else:
        _job_dur = _resolve_dur(details.get("service", ""), conv_text) or 120

    start_dt = f"{details['date']}T{_clean_time(details['startTime'])}:00"
    from datetime import datetime as _dt2, timedelta as _td2
    _multi = len(svc_names) > 1
    # For a single service we trust an explicit endTime; for a combined multi-service
    # booking the slot MUST cover the summed duration, so always derive it from
    # _job_dur and ignore any single-service endTime the extractor guessed.
    if details.get("endTime") and not _multi:
        end_dt = f"{details['date']}T{_clean_time(details['endTime'])}:00"
    else:
        try:
            end_dt = (_dt2.fromisoformat(start_dt) + _td2(minutes=_job_dur)).isoformat()
        except Exception:
            end_dt = start_dt

    # Pass service/price through as LISTS when several services were booked so the
    # calendar event renders one invoice line per service; keep scalars otherwise.
    if _multi:
        spec_service: object = svc_names
        spec_price: object = svc_prices
    elif svc_names:
        spec_service = svc_names[0]
        spec_price = svc_prices[0] if svc_prices else ""
    else:
        spec_service = details.get("service", "Cleaning")
        spec_price = details.get("price", "")

    # The customer's phone number is the WhatsApp number they are texting from —
    # the AI never asks for it, so the extractor can't return it. Pass it through
    # from the conversation id so the calendar event records a contact number.
    _phone = (customer_phone or details.get("phone", "") or "").strip()

    # Postcode: prefer the extracted field, else recover it from the address /
    # conversation text (customers often type it inline, e.g. "153 Dorset Rd SW19 4JH").
    _postcode = (details.get("postcode") or "").strip()
    if not _postcode:
        _pcm = re.search(
            r"[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}",
            f"{details.get('customerAddress', '')} {conv_text}",
        )
        if _pcm:
            _postcode = _pcm.group(0)
    if _postcode:
        # Normalise to "OUTWARD INWARD" (UK inward part is always 3 chars).
        _pc_compact = re.sub(r"\s+", "", _postcode).upper()
        if len(_pc_compact) >= 5:
            _postcode = f"{_pc_compact[:-3]} {_pc_compact[-3:]}"
        else:
            _postcode = _pc_compact

    job_spec = {
        "customerName":  details.get("customerName",  "Customer"),
        "customerEmail": details.get("customerEmail", ""),
        "phone":         _phone,
        "address":       details.get("customerAddress", ""),
        "postcode":      _postcode,
        "service":       spec_service,
        "price":         spec_price,
        "notes":         "Booked via AI simulator",
    }
    slot = {"start": start_dt, "end": end_dt}

    try:
        from scheduler import calendar_client as _cc
        from scheduler.smart_scheduler import get_eligible_engineers
        cfg = _cc.load_config()

        # Resolve the engineer's OWN calendar. Never fall back to a shared/primary
        # calendar — that caused engineers to double-book the same diary.
        eng_name = (details.get("engineerName") or "").lower()
        eligible = get_eligible_engineers(job_spec["postcode"] or "")
        if not eligible:
            return {"ok": False, "error": "No bookable engineer/calendar for this job — not booked."}

        # Resolve which engineer to book. The customer-facing slot offer often does
        # NOT name the engineer, so we cannot rely on extraction alone — in multi-
        # engineer regions with multiple eligible engineers that left bookings failing with
        # "no bookable engineer". Instead: try any named engineer first, then fall
        # through to all eligible engineers in priority order (the same ordering the
        # scheduler used to pick Option 1) and choose the first who actually has the
        # offered slot FREE. This both resolves the engineer and re-checks the slot
        # is still open, preventing double-bookings.
        candidates = []
        if eng_name:
            named = next((e for e in eligible if eng_name in e.get("name", "").lower()), None)
            if named:
                candidates.append(named)
        for e in eligible:
            if e not in candidates:
                candidates.append(e)

        from datetime import datetime as _dt_chk
        try:
            # Make the day tz-aware (business tz) — Google's events.list rejects
            # naive RFC3339 bounds with a 400, which would silently fail the re-check.
            _day = _dt_chk.fromisoformat(slot["start"]).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=_cc.business_tz()
            )
        except Exception:
            _day = None
        _want = slot["start"][11:16]

        def _mins(hhmm: str):
            try:
                h, m = hhmm.split(":")[:2]
                return int(h) * 60 + int(m)
            except Exception:
                return None

        _want_mins = _mins(_want)
        SNAP_TOLERANCE_MINS = 120  # accept the nearest real slot within ~2h of the spoken time

        chosen, cal_id, snapped_slot = None, "", None
        for cand in candidates:
            cid = (cand.get("calendarId") or "").strip()
            if not cid:
                continue
            _free = None
            if _day is not None:
                try:
                    _free = _cc.find_free_slots(
                        calendar_id=cid,
                        target_date=_day,
                        duration_mins=_job_dur,
                        working_hours=cfg.get("workingHours") or cfg.get("preferredWorkingHours"),
                        travel_buffer_mins=cfg.get("travelBufferMinutes", 20),
                    )
                except Exception as _chk_exc:
                    logger.debug("Booking slot re-check failed for %s: %s", cand.get("name"), _chk_exc)
                    _free = None
            if _free is None:
                # Couldn't verify availability (API error / unparseable date). Only
                # trust this candidate if it's the single eligible engineer; otherwise
                # keep looking so we don't guess wrong in a multi-engineer region.
                if len(candidates) == 1:
                    chosen, cal_id = cand, cid
                    break
                continue
            if not _free:
                continue
            # The customer-facing offer uses an APPROXIMATE time ("around 2pm"), so the
            # extracted time rarely matches the precise slot grid (e.g. 13:00) exactly.
            # Snap to the nearest real free slot within tolerance so the event lands on
            # a genuine conflict-free slot rather than failing or booking a clashing time.
            best, best_diff = None, None
            for s in _free:
                s_mins = _mins(s.get("start", "")[11:16])
                if s_mins is None or _want_mins is None:
                    continue
                diff = abs(s_mins - _want_mins)
                if best is None or diff < best_diff:
                    best, best_diff = s, diff
            if best is not None and best_diff is not None and best_diff <= SNAP_TOLERANCE_MINS:
                chosen, cal_id, snapped_slot = cand, cid, best
                break

        if not cal_id:
            return {"ok": False,
                    "error": f"Slot {slot['start']} is no longer free on any eligible engineer's calendar."}

        # Book the REAL (snapped) slot times so the event lands on a genuine
        # conflict-free slot, even when the customer agreed to an approximate time.
        if snapped_slot:
            if snapped_slot.get("start"):
                if snapped_slot.get("start", "")[11:16] != _want:
                    logger.info("Booking snapped requested %s → real free slot %s for %s",
                                _want, snapped_slot["start"][11:16], chosen.get("name"))
                slot["start"] = snapped_slot["start"]
            if snapped_slot.get("end"):
                slot["end"] = snapped_slot["end"]

        event_body = _cc.build_booking_event(job_spec, slot, cfg)
        # Times extracted from conversation are local UK times — correct the timezone
        event_body["start"]["timeZone"] = "Europe/London"
        event_body["end"]["timeZone"]   = "Europe/London"

        event = _cc.create_event(cal_id, event_body)
        try:
            _log_booking(job_spec, slot, chosen.get("name", ""),
                         customer_phone, event, is_ai=True)
        except Exception as _log_exc:
            logger.warning("booking log failed: %s", _log_exc)
        return {
            "ok":       True,
            "event_id": event.get("id"),
            "summary":  event.get("summary"),
            "htmlLink": event.get("htmlLink"),
            "details":  details,
        }
    except Exception as exc:
        logger.warning("_extract_and_create_booking failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _parse_tune_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        client = AIClient()
        repaired = client.repair_json(raw)
        return json.loads(repaired)
    except Exception as exc:
        raise ValueError(f"Could not parse AI response as JSON: {exc}") from exc


def _extract_conversations_from_files(files: list) -> str:
    import csv
    import io
    parts = []
    for f in files:
        filename = secure_filename(f.filename or "upload")
        raw = f.read()
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")

        ext = Path(filename).suffix.lower()
        if ext == ".csv":
            reader = csv.reader(io.StringIO(text))
            rows = [" | ".join(row) for row in reader if any(cell.strip() for cell in row)]
            parts.append(f"--- File: {filename} ---\n" + "\n".join(rows))
        else:
            parts.append(f"--- File: {filename} ---\n{text}")
    return "\n\n".join(parts)


@app.route("/api/tune/import-examples", methods=["POST"])
def tune_import_examples():
    """Extract and store example pairs from uploaded files with no Q&A."""
    files = request.files.getlist("files[]")
    if not files or all(not f.filename for f in files):
        return jsonify({"error": "Upload at least one conversation file."}), 400

    try:
        conversation_text = _extract_conversations_from_files(files)
    except Exception as exc:
        logger.exception("Failed to extract conversations")
        return jsonify({"error": str(exc)}), 400

    if len(conversation_text) > 80_000:
        conversation_text = conversation_text[:80_000]

    added = _extract_and_store_examples(conversation_text)
    total = len(_load_tune_examples())
    return jsonify({"examples_added": added, "total_examples": total})


@app.route("/api/tune/analyse", methods=["POST"])
def tune_analyse():
    files = request.files.getlist("files[]")
    if not files or all(not f.filename for f in files):
        return jsonify({"error": "Upload at least one conversation file."}), 400

    try:
        conversation_text = _extract_conversations_from_files(files)
    except Exception as exc:
        logger.exception("Failed to extract conversations")
        return jsonify({"error": str(exc)}), 400

    if len(conversation_text) > 80_000:
        conversation_text = conversation_text[:80_000] + "\n... [truncated for analysis]"

    existing_profile = ""
    if TONE_PROFILE_PATH.exists():
        try:
            existing_profile = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if existing_profile:
        meta_prompt = (
            "You are an expert communication coach helping a small exterior cleaning business owner "
            "train an AI assistant to respond to customers exactly like they do.\n\n"
            "You have previously built a tone profile for this owner (shown below). "
            "Now they have uploaded NEW conversations. Your job is to:\n"
            "1. Analyse what is NEW or DIFFERENT in these conversations compared to the existing profile.\n"
            "2. Identify any NEW job types, pricing scenarios, property types, or situations not covered before.\n"
            "3. Spot any inconsistencies or evolution in their style since the last session.\n\n"
            "Then produce 3 to 5 targeted questions ONLY about things NOT already covered by the existing profile — "
            "focus on gaps, new scenarios, or anything that would meaningfully improve the profile.\n\n"
            "EXISTING PROFILE:\n"
            f"{existing_profile}\n\n"
            "Return your response as JSON with two fields:\n"
            '- "analysis_summary": a 2-3 sentence summary of what is new or different in these conversations\n'
            '- "questions": an array of 3-5 question strings focused on gaps and new scenarios\n\n'
            "Return only valid JSON, no commentary."
        )
    else:
        meta_prompt = (
            "You are an expert communication coach helping a small exterior cleaning business owner "
            "train an AI assistant to respond to customers exactly like they do.\n\n"
            "Analyse the following customer conversations and identify the business owner's communication patterns: "
            "greeting style, how they handle pricing enquiries, tone (formal/casual), phrases they use often, "
            "how they handle difficult customers, whether they give quotes upfront or ask questions first, etc.\n\n"
            "Then produce EXACTLY 3 to 5 targeted clarifying questions about anything ambiguous or inconsistent "
            "you spotted. Questions should be specific (reference actual examples from the conversations).\n\n"
            "Return your response as JSON with two fields:\n"
            '- "analysis_summary": a 2-3 sentence summary of the owner\'s style\n'
            '- "questions": an array of 3-5 question strings\n\n'
            "Return only valid JSON, no commentary."
        )

    try:
        raw = _call_ai([
            {"role": "system", "content": meta_prompt},
            {"role": "user", "content": f"Here are the conversations to analyse:\n\n{conversation_text}"},
        ], max_tokens=1000)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.exception("Analysis failed")
        return jsonify({"error": f"Analysis failed: {exc}"}), 500

    examples_added = _extract_and_store_examples(conversation_text)

    _cleanup_tune_sessions()
    session_id = uuid.uuid4().hex
    questions = data.get("questions", [])
    first_question = questions[0] if questions else None
    tune_sessions[session_id] = {
        "conversation_text": conversation_text,
        "analysis_summary": data.get("analysis_summary", ""),
        "existing_profile": existing_profile,
        "qa_history": [],
        "current_question": first_question or "",
        "generated_profile": None,
        "created_at": time.time(),
    }

    return jsonify({
        "session_id": session_id,
        "analysis_summary": data.get("analysis_summary", ""),
        "examples_added": examples_added,
        "question": first_question,
        "question_number": 1,
        "total_questions": len(questions),
        "is_update": bool(existing_profile),
    })


@app.route("/api/tune/chat", methods=["POST"])
def tune_chat():
    payload = request.json or {}
    session_id = payload.get("session_id")
    answer = (payload.get("answer") or "").strip()

    session = tune_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found. Please re-upload your files."}), 404
    if not answer:
        return jsonify({"error": "Answer is required."}), 400

    qa_history = session["qa_history"]
    current_q = session.get("current_question", "")

    if current_q:
        qa_history.append({"q": current_q, "a": answer})

    qa_so_far = "\n".join(f"Q: {item['q']}\nA: {item['a']}" for item in qa_history)

    existing_profile = session.get("existing_profile", "")
    existing_context = (
        f"\n\nNote: this owner already has an established profile (shown below). "
        f"Focus follow-up questions ONLY on new scenarios, gaps, or things not covered in it.\n"
        f"EXISTING PROFILE:\n{existing_profile}"
        if existing_profile else ""
    )

    decide_prompt = (
        "You are a communication coach helping train an AI assistant to sound like a specific business owner. "
        "You have analysed their customer conversations and asked clarifying questions. "
        "Based on the Q&A so far, decide: do you have enough information to generate a tone profile, "
        "or do you need to ask ONE more targeted follow-up question?\n\n"
        "Rules:\n"
        "- Ask a follow-up only if there is a genuinely important gap not yet answered and not already in the existing profile.\n"
        "- Questions must be about things you genuinely don't know (new job types, pricing scenarios, edge cases).\n"
        "- Do NOT repeat anything already established in the existing profile.\n"
        "- Do NOT ask more than 6 total questions across the session.\n"
        f"- Questions asked so far: {len(qa_history)}\n"
        "- If 6 or more questions have been answered, always signal ready.\n\n"
        "Return JSON with one of these shapes:\n"
        '{"ready": true}\n'
        'or\n'
        '{"ready": false, "question": "Your next question here"}\n\n'
        "Return only valid JSON."
    )

    user_content = (
        f"Conversation analysis:\n{session['analysis_summary']}\n\n"
        f"Q&A so far:\n{qa_so_far if qa_so_far else '(none yet)'}"
        f"{existing_context}"
    )

    try:
        raw = _call_ai([
            {"role": "system", "content": decide_prompt},
            {"role": "user", "content": user_content},
        ], max_tokens=300)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.exception("AI follow-up decision failed")
        return jsonify({"error": f"Follow-up decision failed: {exc}"}), 500

    if data.get("ready"):
        session["current_question"] = ""
        return jsonify({"ready": True, "total_questions": len(qa_history)})

    next_question = data.get("question", "")
    session["current_question"] = next_question
    return jsonify({
        "question": next_question,
        "question_number": len(qa_history) + 1,
        "total_questions": None,
        "ready": False,
    })


@app.route("/api/tune/generate", methods=["POST"])
def tune_generate():
    payload = request.json or {}
    session_id = payload.get("session_id")

    session = tune_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found."}), 404

    qa_text = "\n".join(
        f"Q: {item['q']}\nA: {item['a']}" for item in session["qa_history"]
    )
    query_for_examples = session.get("analysis_summary", "") or "exterior cleaning customer conversation"
    examples = _find_similar_examples(query_for_examples, top_k=5)
    few_shot_text = ""
    if examples:
        lines = []
        for ex in examples:
            lines.append(f"Customer: {ex['customer']}\nOwner reply: {ex['owner']}")
        few_shot_text = "\n\n".join(lines)

    existing_profile = session.get("existing_profile", "")

    if existing_profile:
        gen_prompt = (
            "You are updating an AI assistant persona for a UK exterior cleaning business owner. "
            "They have an existing tone profile (shown below) and have now provided new conversations and answers. "
            "Your task is to UPDATE and IMPROVE the existing profile by:\n"
            "1. Keeping everything that is still accurate and well-established.\n"
            "2. Adding new bullet points for any new job types, pricing scenarios, or situations discovered.\n"
            "3. Refining existing bullet points where the new information gives more clarity.\n"
            "4. Updating the system prompt to incorporate any new insights.\n\n"
            "Do NOT remove anything unless the owner's new answers explicitly contradict it.\n"
            "The result should be a richer, more complete profile — not a replacement.\n\n"
            "EXISTING PROFILE:\n"
            f"{existing_profile}\n\n"
            "Return JSON with two fields: \"tone_profile\" (updated markdown string — each bullet on its own line starting with '- ', no comma-separated lists) "
            "and \"system_prompt\" (updated plain string).\n"
            "Return only valid JSON."
        )
    else:
        gen_prompt = (
            "You are crafting an AI assistant persona for a UK exterior cleaning business owner. "
            "Based on the conversation analysis, the owner's answers to clarifying questions, "
            "and any example corrections they've provided, write:\n\n"
            "1. A tone profile (5-10 bullet points describing how the AI should communicate — tone, style, dos and don'ts)\n"
            "2. A system prompt (2-4 sentences instructing the AI exactly how to respond to customers)\n\n"
            "The tone profile and system prompt must reflect the OWNER's actual style, not generic business language.\n\n"
            "IMPORTANT: Format tone_profile as markdown with each bullet on its own line starting with '- '. Do NOT put all bullets on one line separated by commas.\n\n"
            "Return JSON with two fields: \"tone_profile\" (markdown string, one bullet per line) and \"system_prompt\" (plain string).\n"
            "Return only valid JSON."
        )

    user_content = (
        f"Conversation analysis summary:\n{session['analysis_summary']}\n\n"
        f"Owner's answers to clarifying questions:\n{qa_text}"
    )
    if few_shot_text:
        user_content += f"\n\nExample corrections the owner has provided:\n{few_shot_text}"

    try:
        raw = _call_ai([
            {"role": "system", "content": gen_prompt},
            {"role": "user", "content": user_content},
        ], max_tokens=800)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.exception("Profile generation failed")
        return jsonify({"error": f"Generation failed: {exc}"}), 500

    session["generated_profile"] = data
    return jsonify({
        "tone_profile": data.get("tone_profile", ""),
        "system_prompt": data.get("system_prompt", ""),
    })


@app.route("/api/tune/coach-start", methods=["POST"])
def tune_coach_start():
    """Start a standalone coaching session using only the existing profile."""
    existing_profile = ""
    if TONE_PROFILE_PATH.exists():
        try:
            existing_profile = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if not existing_profile:
        return jsonify({"error": "No profile yet — upload some conversations first to build a starting profile."}), 400

    coach_prompt = (
        "You are a communication coach for a UK exterior cleaning business owner. "
        "You have built a tone profile for this owner (shown below). "
        "Identify the single most important gap — a realistic scenario, job type, pricing situation, "
        "or customer interaction NOT covered by the existing profile — and ask ONE targeted question about it.\n\n"
        "EXISTING PROFILE:\n"
        f"{existing_profile}\n\n"
        "Rules:\n"
        "- Ask exactly ONE question about the most important missing scenario\n"
        "- Be specific and practical — reference a real situation\n"
        "- Do NOT ask about anything already answered in the profile\n\n"
        "Return JSON: {\"question\": \"Your question here\"}\n"
        "Return only valid JSON."
    )
    try:
        raw = _call_ai([
            {"role": "system", "content": coach_prompt},
            {"role": "user", "content": "What is the single most important gap in my profile?"},
        ], max_tokens=250)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.exception("Coach start failed")
        return jsonify({"error": f"Could not start coaching: {exc}"}), 500

    first_question = data.get("question", "")
    _cleanup_tune_sessions()
    session_id = uuid.uuid4().hex
    tune_sessions[session_id] = {
        "conversation_text": "",
        "analysis_summary": "Coaching session — filling gaps in existing profile",
        "existing_profile": existing_profile,
        "qa_history": [],
        "current_question": first_question,
        "generated_profile": None,
        "created_at": time.time(),
        "is_coaching": True,
    }
    return jsonify({"session_id": session_id, "question": first_question})


@app.route("/api/tune/coach-complete", methods=["POST"])
def tune_coach_complete():
    """Merge coaching session answers into the profile and apply immediately."""
    payload = request.json or {}
    session_id = payload.get("session_id")
    session = tune_sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found."}), 404

    qa_history = session.get("qa_history", [])
    if not qa_history:
        return jsonify({"error": "No answers recorded yet."}), 400

    qa_text = "\n".join(f"Q: {item['q']}\nA: {item['a']}" for item in qa_history)
    existing_profile = session.get("existing_profile", "")

    gen_prompt = (
        "You are updating an AI assistant persona for a UK exterior cleaning business owner. "
        "They have an existing tone profile (shown below) and have answered gap-filling coaching questions. "
        "UPDATE the profile by:\n"
        "1. Keeping everything already there — only ADD or REFINE, never remove.\n"
        "2. Adding new bullet points for anything genuinely new from their answers.\n"
        "3. Refining existing bullets where answers give more precision.\n\n"
        "EXISTING PROFILE:\n"
        f"{existing_profile}\n\n"
        "IMPORTANT: tone_profile must have each bullet on its own line starting with '- '. Do NOT comma-separate bullets on one line.\n"
        "Return JSON: {\"tone_profile\": \"...\", \"system_prompt\": \"...\"}\n"
        "Return only valid JSON."
    )
    try:
        raw = _call_ai([
            {"role": "system", "content": gen_prompt},
            {"role": "user", "content": f"Owner's coaching answers:\n{qa_text}"},
        ], max_tokens=900)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.exception("Coach complete failed")
        return jsonify({"error": f"Profile update failed: {exc}"}), 500

    tone_profile = data.get("tone_profile", "").strip()
    system_prompt_text = data.get("system_prompt", "").strip()

    try:
        if tone_profile:
            TONE_PROFILE_PATH.write_text(_normalise_tone_profile(tone_profile), encoding="utf-8")
        if system_prompt_text:
            CUSTOM_PROMPT_PATH.write_text(system_prompt_text, encoding="utf-8")
            params.update({"system_prompt": system_prompt_text})
        logger.info("Profile updated via coaching session")
    except Exception as exc:
        logger.exception("Failed to save coached profile")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "ok", "tone_profile": tone_profile, "system_prompt": system_prompt_text})


@app.route("/api/tune/patch-profile", methods=["POST"])
def tune_patch_profile():
    """Merge a single customer→owner correction into the existing tone profile."""
    payload = request.json or {}
    customer = (payload.get("customer_message") or "").strip()
    owner = (payload.get("owner_reply") or "").strip()

    if not customer or not owner:
        return jsonify({"error": "Both messages are required."}), 400

    existing_profile = ""
    if TONE_PROFILE_PATH.exists():
        try:
            existing_profile = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if not existing_profile:
        return jsonify({"status": "skipped", "updated": False})

    current_system_prompt = params.get().get("system_prompt", "")

    patch_prompt = (
        "You are maintaining a tone profile for a UK exterior cleaning business owner's AI assistant. "
        "You have one new customer→owner exchange that reveals how the owner actually communicates. "
        "Compare it against the existing profile:\n"
        "- If it reveals something NEW not covered, add a concise bullet point.\n"
        "- If it contradicts something, refine that bullet.\n"
        "- If it just confirms what is already there, do NOT change anything.\n\n"
        "EXISTING PROFILE:\n"
        f"{existing_profile}\n\n"
        "CURRENT SYSTEM PROMPT:\n"
        f"{current_system_prompt}\n\n"
        "IMPORTANT: tone_profile must have each bullet on its own line starting with '- '. Do NOT comma-separate bullets on one line.\n"
        "Return JSON: {\"updated\": true/false, \"tone_profile\": \"...\", \"system_prompt\": \"...\"}\n"
        "Return only valid JSON."
    )
    try:
        raw = _call_ai([
            {"role": "system", "content": patch_prompt},
            {"role": "user", "content": f"New exchange:\nCustomer: {customer}\nOwner: {owner}"},
        ], max_tokens=600)
        data = _parse_tune_json(raw)
    except Exception as exc:
        logger.warning("Profile patch failed: %s", exc)
        return jsonify({"status": "error", "updated": False}), 500

    updated = bool(data.get("updated"))
    if updated:
        tp = data.get("tone_profile", "").strip()
        sp = data.get("system_prompt", "").strip()
        if tp:
            TONE_PROFILE_PATH.write_text(_normalise_tone_profile(tp), encoding="utf-8")
        if sp:
            CUSTOM_PROMPT_PATH.write_text(sp, encoding="utf-8")
            params.update({"system_prompt": sp})
        logger.info("Tone profile patched from simulation correction")

    return jsonify({"status": "ok", "updated": updated})


@app.route("/api/tune/apply", methods=["POST"])
def tune_apply():
    payload = request.json or {}
    session_id = payload.get("session_id")
    tone_profile = (payload.get("tone_profile") or "").strip()
    system_prompt_text = (payload.get("system_prompt") or "").strip()

    if not tone_profile or not system_prompt_text:
        return jsonify({"error": "Both tone profile and system prompt are required."}), 400

    if not session_id or session_id not in tune_sessions:
        return jsonify({"error": "Invalid or expired session. Please re-upload your conversations."}), 400

    if not tune_sessions[session_id].get("generated_profile"):
        return jsonify({"error": "No profile has been generated for this session yet."}), 400

    try:
        TONE_PROFILE_PATH.write_text(_normalise_tone_profile(tone_profile), encoding="utf-8")
        CUSTOM_PROMPT_PATH.write_text(system_prompt_text, encoding="utf-8")
        params.update({"system_prompt": system_prompt_text})
        logger.info("Tone profile and system prompt updated and persisted to disk")
    except Exception as exc:
        logger.exception("Failed to apply profile")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "ok", "message": "Tone profile applied successfully."})


@app.route("/api/tune/simulate", methods=["POST"])
def tune_simulate():
    payload = request.json or {}
    customer_message = (payload.get("message") or "").strip()
    history_raw = payload.get("history") or []

    if not customer_message:
        return jsonify({"error": "Customer message is required."}), 400

    history = []
    for turn in history_raw:
        role = turn.get("role", "customer")
        text = (turn.get("text") or "").strip()
        if text:
            history.append({"role": "user" if role == "customer" else "assistant", "content": text})

    try:
        reply = _generate_kb_reply(
            customer_message=customer_message,
            conversation_history=history or None,
            goal_config=_load_goal_config(),
            max_tokens=350,
        )
        reply = _resolve_calendar_signals(reply, customer_message, history or [], _load_goal_config())
        reply = _CAL_TOKEN_RE.sub("", reply).strip()
        reply = reply.replace("[NEEDS_HUMAN_REVIEW]", "").strip()
        reply = _CAL_BOOK_TOKEN_RE.sub("", reply).strip()
        reply = _COVERAGE_TOKEN_RE.sub("", reply).strip()
        reply = _ATTENTION_TOKEN_RE.sub("", reply).strip()
    except Exception as exc:
        logger.exception("Simulation failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"reply": reply, "model": "claude"})


@app.route("/api/tune/feedback", methods=["POST"])
def tune_feedback():
    payload = request.json or {}
    customer_message = (payload.get("customer_message") or "").strip()
    owner_reply = (payload.get("owner_reply") or "").strip()

    if not customer_message or not owner_reply:
        return jsonify({"error": "Both customer message and your reply are required."}), 400

    embedding = _get_embedding(f"Customer: {customer_message}\nOwner: {owner_reply}")
    examples = _load_tune_examples()
    examples.append({"customer": customer_message, "owner": owner_reply, "embedding": embedding})
    _save_tune_examples(examples)

    return jsonify({"status": "ok", "total_examples": len(examples)})


@app.route("/api/tune/examples", methods=["GET"])
def get_tune_examples():
    examples = _load_tune_examples()
    return jsonify({"examples": examples, "total": len(examples)})


TUNE_AIM_PATH = APP_ROOT / "tune_aim.json"
USER_INSTR_PATH = APP_ROOT / "tune_user_instructions.json"


@app.route("/api/tune/aim", methods=["GET", "POST"])
def tune_aim():
    if request.method == "POST":
        data = request.json or {}
        aim = (data.get("aim") or "").strip()
        with open(TUNE_AIM_PATH, "w") as f:
            json.dump({"aim": aim}, f)
        return jsonify({"ok": True})
    if TUNE_AIM_PATH.exists():
        with open(TUNE_AIM_PATH) as f:
            return jsonify(json.load(f))
    return jsonify({"aim": ""})


@app.route("/api/tune/user-instructions", methods=["GET", "POST"])
def tune_user_instructions():
    if request.method == "POST":
        data = request.json or {}
        users = data.get("users", [])
        users = [u for u in users if isinstance(u, dict)][:2]
        with open(USER_INSTR_PATH, "w") as f:
            json.dump({"users": users}, f, indent=2)
        return jsonify({"ok": True})
    if USER_INSTR_PATH.exists():
        with open(USER_INSTR_PATH) as f:
            return jsonify(json.load(f))
    return jsonify({"users": []})


@app.route("/api/tune/insight", methods=["POST"])
def tune_insight():
    payload = request.json or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    tone_profile = ""
    if TONE_PROFILE_PATH.exists():
        try:
            tone_profile = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    custom_prompt = ""
    if CUSTOM_PROMPT_PATH.exists():
        try:
            custom_prompt = CUSTOM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    examples = _load_tune_examples()
    examples_text = ""
    if examples:
        lines = [f"Customer: {ex['customer']}\nOwner reply: {ex['owner']}" for ex in examples[-10:]]
        examples_text = "\n\n".join(lines)

    if not tone_profile and not custom_prompt and not examples:
        return jsonify({
            "answer": "No training data found yet. Upload some conversation files in the Tune My AI tab first, "
                      "go through the Q&A, and apply a profile — then I'll be able to answer questions about your training."
        })

    total_examples = len(examples)
    knowledge_block = ""
    if tone_profile:
        knowledge_block += f"TONE PROFILE:\n{tone_profile}\n\n"
    if custom_prompt:
        knowledge_block += f"CUSTOM SYSTEM PROMPT:\n{custom_prompt}\n\n"
    knowledge_block += f"EXAMPLE PAIRS IN LIBRARY: {total_examples} total stored\n"
    if examples_text:
        knowledge_block += f"SAMPLE EXAMPLE PAIRS (most recent):\n{examples_text}\n\n"

    system_prompt = (
        "You are the training system for an AI assistant used by a UK exterior cleaning business owner. "
        "You have access to everything that has been learned about the owner's style, pricing, and communication. "
        "IMPORTANT CONTEXT: Conversation files uploaded during training are NOT stored permanently — "
        "they are processed to build the tone profile and extract example pairs, then discarded. "
        "The 'example pairs' in the library are individual customer→owner message pairs extracted from those uploads. "
        "When asked about files or conversations uploaded, clarify this distinction accurately. "
        "Answer the owner's questions honestly and specifically — drawing directly from the training data provided. "
        "If something hasn't been covered in training, say so clearly. "
        "If there are gaps or weaknesses, point them out constructively. "
        "Be concise but thorough. Write in plain English, not bullet-point summaries unless helpful."
    )

    user_content = (
        f"Here is everything currently in my training data:\n\n"
        f"{knowledge_block}"
        f"The owner's question: {question}"
    )

    try:
        answer = _call_ai([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ], max_tokens=600)
    except Exception as exc:
        logger.exception("Insight query failed")
        return jsonify({"error": f"Could not get insight: {exc}"}), 500

    return jsonify({"answer": answer})


@app.route("/api/tune/finetune-status", methods=["GET"])
def tune_finetune_status():
    state = _load_finetune_state()
    examples = _load_tune_examples()
    state["examples_count"] = len(examples)
    return jsonify(state)


@app.route("/api/tune/finetune-start", methods=["POST"])
def tune_finetune_start():
    import io as _io
    examples = _load_tune_examples()
    if len(examples) < 10:
        return jsonify({"error": f"Need at least 10 examples to train. You have {len(examples)}. Upload more WhatsApp conversations first."}), 400

    tone_profile = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip() if TONE_PROFILE_PATH.exists() else ""
    custom_sp = CUSTOM_PROMPT_PATH.read_text(encoding="utf-8").strip() if CUSTOM_PROMPT_PATH.exists() else ""

    finetune_system = (
        "You are a friendly, professional customer service assistant for PowWash, "
        "a UK exterior cleaning business. Reply to customers in the owner's natural style — "
        "warm, direct, and clear about pricing and next steps."
    )
    if tone_profile:
        finetune_system += f"\n\nSTYLE GUIDE:\n{tone_profile}"
    if custom_sp:
        finetune_system += f"\n\n{custom_sp}"

    lines = []
    for ex in examples:
        customer_msg = (ex.get("customer") or "").strip()
        owner_reply = (ex.get("owner") or "").strip()
        if not customer_msg or not owner_reply:
            continue
        record = {
            "messages": [
                {"role": "system", "content": finetune_system},
                {"role": "user", "content": customer_msg},
                {"role": "assistant", "content": owner_reply},
            ]
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    if len(lines) < 10:
        return jsonify({"error": f"Only {len(lines)} usable example pairs. Need at least 10."}), 400

    jsonl_bytes = "\n".join(lines).encode("utf-8")

    try:
        if OpenAI is None:
            raise RuntimeError("openai package is required for fine-tuning")
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY is required for fine-tuning (Claude does not support fine-tuning)")
        oai_client = OpenAI(api_key=openai_key)
        uploaded = oai_client.files.create(
            file=("training.jsonl", _io.BytesIO(jsonl_bytes), "application/jsonl"),
            purpose="fine-tune",
        )
        job = oai_client.fine_tuning.jobs.create(
            training_file=uploaded.id,
            model="gpt-4o-mini-2024-07-18",
        )
    except Exception as exc:
        logger.exception("Failed to start fine-tuning job")
        return jsonify({"error": f"Could not start training: {exc}"}), 500

    state = {
        "status": "validating_files",
        "job_id": job.id,
        "file_id": uploaded.id,
        "model_id": None,
        "active": False,
        "created_at": time.time(),
        "training_examples": len(lines),
        "error": None,
    }
    _save_finetune_state(state)
    logger.info("Fine-tuning job started: %s with %d examples", job.id, len(lines))
    return jsonify({"ok": True, "job_id": job.id, "examples": len(lines)})


@app.route("/api/tune/finetune-poll", methods=["POST"])
def tune_finetune_poll():
    state = _load_finetune_state()
    job_id = state.get("job_id")
    if not job_id:
        return jsonify({"error": "No training job in progress."}), 400

    try:
        if OpenAI is None:
            raise RuntimeError("openai package is required for fine-tuning")
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY is required to check fine-tuning status")
        oai_client = OpenAI(api_key=openai_key)
        job = oai_client.fine_tuning.jobs.retrieve(job_id)
    except Exception as exc:
        return jsonify({"error": f"Could not check job status: {exc}"}), 500

    state["status"] = job.status
    if job.status == "succeeded":
        state["model_id"] = job.fine_tuned_model
        state["finished_at"] = time.time()
    elif job.status in ("failed", "cancelled"):
        raw_err = job.error
        state["error"] = raw_err.message if hasattr(raw_err, "message") else str(raw_err)
        state["finished_at"] = time.time()

    _save_finetune_state(state)
    state["examples_count"] = len(_load_tune_examples())
    return jsonify(state)


@app.route("/api/tune/finetune-activate", methods=["POST"])
def tune_finetune_activate():
    state = _load_finetune_state()
    if state.get("status") != "succeeded" or not state.get("model_id"):
        return jsonify({"error": "No completed model ready to activate."}), 400
    state["active"] = True
    _save_finetune_state(state)
    logger.info("Fine-tuned model activated: %s", state["model_id"])
    return jsonify({"ok": True, "model_id": state["model_id"]})


@app.route("/api/tune/finetune-deactivate", methods=["POST"])
def tune_finetune_deactivate():
    state = _load_finetune_state()
    state["active"] = False
    _save_finetune_state(state)
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE API
# ─────────────────────────────────────────────────────────────────────────────

import re as _re


def _merge_tone_profile(existing: str, new_info: str) -> str:
    """Merge new tone info into existing rules, resolving conflicts and keeping it concise."""
    system = (
        "You are a business tone coach editing a live tone guide for an AI assistant.\n\n"
        "Rules for updating:\n"
        "1. INTEGRATE new information into the existing rules — do NOT start from scratch.\n"
        "2. If new information CONTRADICTS an existing rule, replace the old rule with the new one.\n"
        "3. If new information ADDS something genuinely new, add it as a bullet.\n"
        "4. If new information REINFORCES something already covered, do not duplicate it.\n"
        "5. Keep the guide CONCISE — maximum 15 bullets. If adding a bullet would exceed 15, "
        "remove or merge the least important existing bullet to make room.\n"
        "6. Prioritise rules that most affect how the AI sounds day-to-day "
        "(sign-offs, length, formality, pricing language, emojis) over edge-case policies.\n"
        "7. Each bullet starts with '- ' and is one clear, actionable sentence.\n"
        "Output ONLY the updated bullet list — no intro text, no headings."
    )
    user = (
        f"EXISTING TONE GUIDE:\n{existing}\n\n"
        f"NEW INFORMATION TO INTEGRATE:\n{new_info}\n\n"
        "Produce the updated tone guide."
    )
    result = _call_ai(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=700,
        model=CLAUDE_FAST_MODEL,
    )
    return _normalise_tone_profile(result)


def _parse_and_merge_price_entry(label: str, description: str, existing: Dict[str, Any] | None) -> Dict[str, Any]:
    """Use Claude to parse a natural-language price description and merge with existing data."""
    existing_block = (
        f"EXISTING DATA:\n{json.dumps(existing, indent=2)}\n\n" if existing else ""
    )
    system = (
        "You are a pricing data manager for a UK exterior cleaning company. "
        "Parse natural-language pricing descriptions into clean, structured JSON.\n\n"
        "Output ONLY valid JSON matching this schema (omit any key whose array would be empty):\n"
        "{\n"
        '  "label": "Display Name",\n'
        '  "unit": "per job",\n'
        '  "variants": [\n'
        '    {"name": "Variant name", "price": 125, "price_to": null, "notes": "short clarification"}\n'
        "  ],\n"
        '  "add_ons": [{"name": "Extension", "add": 10}],\n'
        '  "ai_hints": ["Short operational hint the AI should tell customers or be aware of"],\n'
        '  "areas": [{"key": "london", "label": "London", "note": "pricing note"}]\n'
        "}\n\n"
        "Merge rules when existing data is provided:\n"
        "- INTEGRATE new info — do not erase existing variants, hints, or add-ons unless they conflict.\n"
        "- REPLACE a variant's price if the new description gives a different price for the same variant.\n"
        "- ADD a new variant if the new description mentions a type not already in the list.\n"
        "- REPLACE an area's pricing note if the new description updates that area.\n"
        "- Keep notes and hints concise (one sentence each).\n"
        "Output ONLY the JSON object — no markdown, no explanation."
    )
    user = (
        f"Service: {label}\n\n"
        f"{existing_block}"
        f"NEW DESCRIPTION:\n{description}"
    )
    raw = _call_ai(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=900,
        model=CLAUDE_FAST_MODEL,
    )
    # Extract JSON from response (strip any accidental markdown fences)
    clean = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=_re.MULTILINE).strip()
    match = _re.search(r"\{.*\}", clean, _re.DOTALL)
    return json.loads(match.group() if match else clean)


def _load_kb_prices() -> Dict[str, Any]:
    if KB_PRICES_PATH.exists():
        try:
            return json.loads(KB_PRICES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_kb_prices(data: Dict[str, Any]) -> None:
    KB_PRICES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _prices_to_text(prices: Dict[str, Any]) -> str:
    if not prices:
        return "No prices set yet."
    sections = []
    for key, info in prices.items():
        label = info.get("label", key)
        parts = [f"=== {label} ==="]

        # Per-service booking process
        if info.get("booking_process"):
            parts.append(f"\n  Booking Process for {label}:\n  {info['booking_process']}")

        # Per-service things to know (general, applies unless sub-category overrides)
        if info.get("things_to_know"):
            parts.append(
                f"\n  General Things to Know for {label} (applies to all sub-categories unless a sub-category's own 'Things to Know' covers the same point):\n  {info['things_to_know']}"
            )

        # New structured format: sub_categories
        sub_cats = info.get("sub_categories", {})
        if sub_cats:
            for sc_key, sc in sub_cats.items():
                sc_label = sc.get("label", sc_key.replace("_", " ").title())
                parts.append(f"\n  Sub-category: {sc_label}")
                if sc.get("pricing_and_time"):
                    parts.append(f"    Pricing & Time: {sc['pricing_and_time']}")
                if sc.get("common_questions"):
                    parts.append(f"    Common Questions: {sc['common_questions']}")
                if sc.get("things_to_know"):
                    parts.append(f"    Things to Know: {sc['things_to_know']}")
        else:
            # Legacy format fallback (variants, base_prices, add_ons, ai_hints, price_from)
            unit = info.get("unit", "per job")
            parts[0] = f"**{label}** ({unit})"
            if info.get("pricing_rule"):
                parts.append(f"  RULE: {info['pricing_rule']}")
            base_prices = info.get("base_prices", {})
            if base_prices:
                parts.append("  Base prices by property type:")
                for ptype, amount in base_prices.items():
                    parts.append(f"    - {ptype.replace('_', ' ')}: £{amount}")
            for v in info.get("variants", []):
                p = f"£{v['price']}" if v.get("price") is not None else "TBC"
                if v.get("price_to"):
                    p += f"–£{v['price_to']}"
                note = f" — {v['notes']}" if v.get("notes") else ""
                parts.append(f"  • {v.get('name', 'Standard')}: {p}{note}")
            add_ons = info.get("add_ons", [])
            if add_ons:
                ao_text = ", ".join(
                    f"{a['name']} +£{a['add']}" + (f" ({a['notes']})" if a.get("notes") else "")
                    for a in add_ons
                )
                parts.append(f"  Add-ons: {ao_text}")
            for ex in info.get("worked_examples", []):
                parts.append(f"  Example: {ex['property']}: {ex['calculation']} = £{ex['total']}")
            for h in info.get("ai_hints", []):
                parts.append(f"  Tip: {h}")
            if not info.get("variants") and not info.get("base_prices"):
                pf = info.get("price_from")
                pt = info.get("price_to")
                if pf is not None:
                    pstr = f"£{pf}" + (f"–£{pt}" if pt else "")
                    parts[0] += f": {pstr}"
                if info.get("notes"):
                    parts.append(f"  {info['notes']}")

        sections.append("\n".join(parts))
    return "\n\n".join(sections)


def _load_scenarios() -> List[Dict[str, Any]]:
    if DIAGNOSTICS_PATH.exists():
        try:
            return json.loads(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_scenarios(data: List[Dict[str, Any]]) -> None:
    DIAGNOSTICS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _scenarios_to_text(scenarios: List[Dict[str, Any]]) -> str:
    if not scenarios:
        return ""
    from collections import defaultdict
    grouped: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for s in scenarios:
        svc = s.get("service_label") or s.get("service", "General")
        cat = s.get("category_label") or s.get("category", "General")
        grouped[svc][cat].append(s["content"])
    parts = [
        "Diagnostic & Troubleshooting Knowledge "
        "(use this when a customer describes a problem or asks for advice — "
        "ask relevant diagnostic questions and set expectations appropriately):"
    ]
    for svc_label, categories in grouped.items():
        parts.append(f"\n{svc_label}:")
        for cat_label, contents in categories.items():
            parts.append(f"  {cat_label}:")
            for c in contents:
                parts.append(f"  • {c}")
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE RAG
# ─────────────────────────────────────────────────────────────────────────────
# The conversation AI used to receive the ENTIRE price guide on every turn. As the
# KB grows that bloats the prompt and the model starts skimming / "forgetting".
#
# Instead we now retrieve only what matters for the current message:
#   • ALWAYS — a compact service menu (so the AI always knows the full range of
#     services and can identify / switch service) and ALL details for the service
#     the customer is actually discussing (deterministic — never missed by search).
#   • RELEVANT — the top-k most semantically similar extra chunks (other services'
#     FAQs, diagnostic/troubleshooting notes) so niche questions get answered
#     without dumping everything.
# Falls back to a full dump if embeddings are unavailable, so nothing ever breaks.
# ─────────────────────────────────────────────────────────────────────────────

# Domain synonyms used to detect which service the customer is discussing. Keys are
# the service keys in knowledge_base.json; only applied when that key exists.
_SERVICE_SYNONYMS = {
    "gutter_cleaning": [
        "gutter", "gutters", "guttering", "downpipe", "downpipes", "fascia",
        "fascias", "soffit", "soffits",
    ],
    "driveway_cleaning": [
        "driveway", "drive way", "patio", "patios", "path", "pathway", "paths",
        "decking", "deck", "pressure wash", "pressure washing",
        "jet wash", "jetwash", "jet washing", "block paving", "blockpaving", "paving",
        "tarmac", "slabs", "flagstones", "concrete drive",
    ],
    "window_cleaning": [
        "window", "windows", "window clean", "window cleaning", "glass",
    ],
    "roof_cleaning": [
        "roof", "roofs", "roof clean", "roof cleaning", "roof wash", "tiles",
    ],
    "render_cleaning": [
        "render", "rendering", "rendered", "facade", "façade", "render clean",
        "render cleaning", "facade cleaning", "k-rend", "krend", "pebbledash",
    ],
}


def _kb_chunks(prices: Dict[str, Any], scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten the KB into retrievable chunks: pricing (per sub-category), service
    process/notes, and diagnostic scenarios. Each chunk: {id, service, kind, label, text}."""
    import hashlib
    chunks: List[Dict[str, Any]] = []
    for skey, info in (prices or {}).items():
        slabel = info.get("label", skey)
        if info.get("booking_process"):
            chunks.append({
                "id": f"{skey}::booking_process", "service": skey, "kind": "process",
                "label": f"{slabel} — Booking Process",
                "text": f"=== {slabel} ===\nBooking Process for {slabel}:\n{info['booking_process']}",
            })
        if info.get("things_to_know"):
            chunks.append({
                "id": f"{skey}::service_notes", "service": skey, "kind": "notes",
                "label": f"{slabel} — General Notes",
                "text": f"=== {slabel} ===\nGeneral things to know for {slabel} "
                        f"(apply unless a sub-category overrides):\n{info['things_to_know']}",
            })
        for sckey, sc in (info.get("sub_categories") or {}).items():
            sclabel = sc.get("label", sckey.replace("_", " ").title())
            parts = [f"=== {slabel} → {sclabel} ==="]
            if sc.get("pricing_and_time"):
                parts.append(f"Pricing & Time: {sc['pricing_and_time']}")
            if sc.get("common_questions"):
                parts.append(f"Common Questions: {sc['common_questions']}")
            if sc.get("things_to_know"):
                parts.append(f"Things to Know: {sc['things_to_know']}")
            chunks.append({
                "id": f"{skey}::{sckey}", "service": skey, "kind": "pricing",
                "label": f"{slabel} — {sclabel}", "text": "\n".join(parts),
            })
    for s in (scenarios or []):
        sid = s.get("id") or hashlib.md5((s.get("content") or "").encode("utf-8")).hexdigest()[:8]
        svc_label = s.get("service_label") or s.get("service", "General")
        cat_label = s.get("category_label") or s.get("category", "")
        head = f"{svc_label} — {cat_label}".strip(" —")
        chunks.append({
            "id": f"scenario::{sid}", "service": s.get("service", ""), "kind": "scenario",
            "label": head,
            "text": f"=== {head} (diagnostic / troubleshooting knowledge) ===\n{s.get('content', '')}",
        })
    return chunks


def _load_kb_embeddings() -> Dict[str, Any]:
    if KB_EMBED_PATH.exists():
        try:
            return json.loads(KB_EMBED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_kb_embeddings(data: Dict[str, Any]) -> None:
    try:
        KB_EMBED_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist KB embeddings: %s", exc)


def _kb_embed_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Return {chunk_id: embedding}, computing and caching by content hash so we only
    re-embed a chunk when its text actually changes. Prunes embeddings for deleted chunks."""
    import hashlib
    cache = _load_kb_embeddings()
    out: Dict[str, List[float]] = {}
    changed = False
    valid_ids = set()
    for c in chunks:
        valid_ids.add(c["id"])
        h = hashlib.md5(c["text"].encode("utf-8")).hexdigest()
        entry = cache.get(c["id"])
        if entry and entry.get("hash") == h and entry.get("embedding"):
            out[c["id"]] = entry["embedding"]
            continue
        emb = _get_embedding(c["text"])
        if emb:
            cache[c["id"]] = {"hash": h, "embedding": emb}
            out[c["id"]] = emb
            changed = True
    for k in list(cache.keys()):
        if k not in valid_ids:
            cache.pop(k, None)
            changed = True
    if changed:
        _save_kb_embeddings(cache)
    return out


def _service_directory_text(prices: Dict[str, Any]) -> str:
    """Compact always-on menu of every service, so the AI never forgets the full range."""
    if not prices:
        return ""
    lines = [
        "SERVICE MENU — every service PowWash offers. Use this to identify the customer's "
        "service and to know what else we do. For full pricing, rely on the ACTIVE SERVICE / "
        "RELEVANT KNOWLEDGE sections below."
    ]
    for skey, info in prices.items():
        slabel = info.get("label", skey)
        subs = info.get("sub_categories") or {}
        sub_labels = ", ".join(sc.get("label", k) for k, sc in subs.items())
        photo = " [photos required before quoting]" if info.get("booking_process") else ""
        line = f"- {slabel}{photo}"
        if sub_labels:
            line += f": {sub_labels}"
        lines.append(line)
    return "\n".join(lines)


def _detect_active_service(
    history: Optional[List[Dict[str, Any]]],
    customer_message: str,
    prices: Dict[str, Any],
) -> Optional[str]:
    """Return the service key most recently referenced in the conversation, or None.
    Scans the current message first, then back through history (most recent customer
    turn wins). Uses whole-word matching with synonym-weighted scoring so generic
    property descriptors (e.g. "detached", "terrace") never decide the service."""
    if not prices:
        return None
    # Generic property/common tokens that appear in sub-category labels but say
    # nothing about WHICH service the customer wants — must not drive detection.
    _STOP = {
        "detached", "terrace", "terraced", "semi", "semi-detached", "storey",
        "storeys", "story", "stories", "standard", "larger", "large", "small",
        "single", "double", "property", "house", "home", "extension", "extensions",
        "conversion", "loft", "front", "back", "side", "bedroom", "level", "floor",
        "floors", "cleaning", "clean", "wash", "washing", "area", "areas",
    }
    # service key -> {token: weight}.  Synonyms are strong (2); label tokens weak (1).
    weights: Dict[str, Dict[str, int]] = {}
    for skey, info in prices.items():
        wmap = weights.setdefault(skey, {})
        for src in [info.get("label", "")] + [
            sc.get("label", "") for sc in (info.get("sub_categories") or {}).values()
        ]:
            for tok in (src or "").lower().split():
                tok = tok.strip(".,()/")
                if len(tok) > 3 and tok not in _STOP:
                    wmap[tok] = max(wmap.get(tok, 0), 1)
    for skey, words in _SERVICE_SYNONYMS.items():
        if skey in prices:
            wmap = weights.setdefault(skey, {})
            for w in words:
                wmap[w] = 2

    import re as _re_det

    def _score(text: str) -> Optional[str]:
        tl = (text or "").lower()
        best_key, best_score = None, 0
        for skey, wmap in weights.items():
            score = 0
            for tok, wt in wmap.items():
                # whole-word / phrase match (word boundaries) — no naive substrings
                if _re_det.search(r"\b" + _re_det.escape(tok) + r"\b", tl):
                    score += wt
            if score > best_score:
                best_key, best_score = skey, score
        return best_key if best_score > 0 else None

    # Most recent text first: current message, then customer turns newest→oldest.
    texts = [customer_message or ""]
    for turn in reversed(history or []):
        if (turn.get("role") or "") in ("user", "customer"):
            texts.append(turn.get("content") or "")
    for t in texts:
        hit = _score(t)
        if hit:
            return hit
    return None


def _build_kb_context(
    customer_message: str,
    history: Optional[List[Dict[str, Any]]],
    prices: Dict[str, Any],
    scenarios: List[Dict[str, Any]],
    top_k: int = 6,
) -> str:
    """Build the knowledge block for the system prompt via RAG (see section header)."""
    if not prices and not scenarios:
        return ""
    directory = _service_directory_text(prices)
    chunks = _kb_chunks(prices, scenarios)
    if not chunks:
        return directory

    active = _detect_active_service(history, customer_message, prices)
    included: List[Dict[str, Any]] = []
    included_ids = set()
    if active:
        for c in chunks:
            if c["service"] == active:
                included.append(c)
                included_ids.add(c["id"])

    emb_map = _kb_embed_chunks(chunks)
    query = customer_message or ""
    cust_turns = [
        (t.get("content") or "")
        for t in (history or [])
        if (t.get("role") or "") in ("user", "customer")
    ]
    if cust_turns:
        query = (query + "\n" + "\n".join(cust_turns[-2:])).strip()
    qvec = _get_embedding(query) if emb_map else []

    semantic: List[Dict[str, Any]] = []
    if qvec and emb_map:
        scored = []
        for c in chunks:
            if c["id"] in included_ids:
                continue
            v = emb_map.get(c["id"])
            if not v:
                continue
            scored.append((c, _cosine_similarity(qvec, v)))
        scored.sort(key=lambda x: x[1], reverse=True)
        semantic = [c for c, _ in scored[:top_k]]
    else:
        # Embeddings unavailable — fall back to including everything (old behaviour)
        # so the AI never loses access to pricing data.
        semantic = [c for c in chunks if c["id"] not in included_ids]

    out: List[str] = []
    if directory:
        out.append(directory)
    if included:
        out.append(
            "ACTIVE SERVICE — full pricing & details for the service this customer is "
            "discussing. Use these figures exactly; never invent a price.\n\n"
            + "\n\n".join(c["text"] for c in included)
        )
    if semantic:
        out.append(
            "RELEVANT KNOWLEDGE — extra pricing, FAQs and diagnostic notes most relevant "
            "to the latest message:\n\n"
            + "\n\n".join(c["text"] for c in semantic)
        )
    return "\n\n".join(out)


@app.route("/api/kb/scenarios", methods=["GET"])
def kb_get_scenarios():
    return jsonify(_load_scenarios())


def _format_and_merge_scenario_bullets(
    ai_client_instance,
    service_label: str,
    category_label: str,
    new_text: str,
    existing_bullets: List[str],
) -> List[str]:
    """Use Claude to turn raw text into clean bullet points, merging with existing bullets."""
    existing_block = ""
    if existing_bullets:
        existing_block = (
            "\n\nExisting knowledge bullets already saved for this topic:\n"
            + "\n".join(f"- {b}" for b in existing_bullets)
            + "\n\nMerge the new information with the existing bullets. "
            "If new info contradicts or updates an existing bullet, replace that bullet. "
            "If it adds new points, include them. Remove duplicates."
        )

    prompt = (
        f"You are structuring operational knowledge for PowWash, an exterior cleaning business.\n\n"
        f"The owner has provided the following information about "
        f"{service_label} — {category_label}:\n\n"
        f"\"\"\"\n{new_text}\n\"\"\""
        f"{existing_block}\n\n"
        "Extract the key practical points as concise, standalone bullet strings. "
        "Each bullet must be a complete sentence — clear, direct, and useful for the AI when talking to a customer. "
        "Return ONLY a valid JSON array of strings, e.g. [\"Point one.\", \"Point two.\"] — no extra text."
    )

    response = ai_client_instance.client.messages.create(
        model=CLAUDE_FAST_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    bullets = json.loads(raw)
    return [b.strip() for b in bullets if b.strip()]


@app.route("/api/kb/scenarios", methods=["POST"])
def kb_add_scenario():
    import uuid as _uuid
    from datetime import date as _date
    data = request.get_json(force=True)
    service = (data.get("service") or "").strip()
    service_label = (data.get("service_label") or service).strip()
    category = (data.get("category") or "").strip()
    category_label = (data.get("category_label") or category).strip()
    content = (data.get("content") or "").strip()
    if not service or not category or not content:
        return jsonify({"error": "service, category, and content are required"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500
    _ai = AIClient()

    scenarios = _load_scenarios()

    # Gather existing bullets for this service+category so Claude can merge
    existing_bullets = [
        s["content"] for s in scenarios
        if s.get("service") == service and s.get("category") == category
    ]

    try:
        merged_bullets = _format_and_merge_scenario_bullets(
            _ai, service_label, category_label, content, existing_bullets
        )
    except Exception as exc:
        logger.warning("Scenario AI formatting failed, storing raw: %s", exc)
        merged_bullets = [content]

    # Replace all existing bullets for this service+category with the merged set
    scenarios = [s for s in scenarios if not (s.get("service") == service and s.get("category") == category)]
    today = str(_date.today())
    for bullet in merged_bullets:
        scenarios.append({
            "id": _uuid.uuid4().hex[:8],
            "service": service,
            "service_label": service_label,
            "category": category,
            "category_label": category_label,
            "content": bullet,
            "created_at": today,
        })

    _save_scenarios(scenarios)
    return jsonify(scenarios), 201


@app.route("/api/kb/scenarios/<scenario_id>", methods=["DELETE"])
def kb_delete_scenario(scenario_id: str):
    scenarios = _load_scenarios()
    scenarios = [s for s in scenarios if s.get("id") != scenario_id]
    _save_scenarios(scenarios)
    return jsonify(scenarios)


@app.route("/api/kb/goal", methods=["GET"])
def kb_goal_get():
    return jsonify(_load_goal_config())


@app.route("/api/kb/goal/refine", methods=["POST"])
def kb_goal_refine():
    """
    Merge new input into the existing goal, process, and escalation triggers.

    Rules (same as tone profile merge):
    - PRESERVE everything not addressed by new input
    - ADD new points that don't already exist
    - REPLACE any point directly contradicted by new input
    - Never start from scratch
    """
    data = request.get_json(force=True) or {}
    existing_goal      = (data.get("goal")              or "").strip()
    existing_process   = (data.get("process")           or "").strip()
    existing_triggers  = (data.get("escalationTriggers") or "").strip()
    new_info           = (data.get("newInfo")            or "").strip()

    if not new_info:
        return jsonify({"error": "newInfo is required"}), 400

    # Build context block so the AI can see everything at once
    context_parts = []
    if existing_goal:
        context_parts.append(f"CURRENT GOAL:\n{existing_goal}")
    if existing_process:
        context_parts.append(f"CURRENT PROCESS:\n{existing_process}")
    if existing_triggers:
        context_parts.append(f"CURRENT ESCALATION TRIGGERS:\n{existing_triggers}")
    context = "\n\n".join(context_parts) if context_parts else "(Nothing saved yet.)"

    system = (
        "You are editing the goal, process steps, and escalation triggers for an AI customer-service "
        "assistant used by PowWash, a UK exterior cleaning company.\n\n"
        "MERGE RULES — follow these strictly:\n"
        "1. PRESERVE all existing content unless the new input directly contradicts it.\n"
        "2. ADD new points, steps, or triggers when they are genuinely new.\n"
        "3. REPLACE a specific item only when the new input directly contradicts it — "
        "treat this as an intentional update by the owner.\n"
        "4. Do NOT start from scratch. Never lose information.\n"
        "5. Keep the goal to 1–2 clear sentences. Keep the process as a numbered list. "
        "Keep escalation triggers as a bullet list (one per line, starting with '- ').\n\n"
        "Return ONLY valid JSON in this exact shape — no markdown fences, no extra keys:\n"
        '{"goal":"...","process":"...","escalationTriggers":"..."}\n\n'
        "If a section was empty and the new input doesn't address it, return it empty (\"\")."
    )
    user = (
        f"EXISTING CONTENT:\n{context}\n\n"
        f"NEW INPUT TO INTEGRATE:\n{new_info}\n\n"
        "Produce the updated JSON."
    )

    try:
        raw = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=900,
            model=CLAUDE_FAST_MODEL,
        )
        # Strip markdown fences if present
        raw = _re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = _re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
    except Exception as exc:
        logger.exception("kb_goal_refine AI parse failed")
        return jsonify({"error": f"AI returned unexpected output: {exc}"}), 500

    # Persist the refined config immediately (merge with other stored fields)
    cfg = _load_goal_config()
    cfg["goal"]              = parsed.get("goal",              existing_goal)
    cfg["process"]           = parsed.get("process",           existing_process)
    cfg["escalationTriggers"] = parsed.get("escalationTriggers", existing_triggers)
    GOAL_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    return jsonify({
        "ok": True,
        "goal":              cfg["goal"],
        "process":           cfg["process"],
        "escalationTriggers": cfg["escalationTriggers"],
    })


def _normalize_goal_content(goal: str, process: str, escalation_triggers: str) -> dict:
    """
    Run goal, process, and escalation triggers through a fast AI normalizer so they
    are structured in a way that's easy for an AI assistant to parse and follow.

    - goal: 1–2 clear imperative sentences, no filler.
    - process: numbered list, one step per line (1. Verb …).
    - escalationTriggers: bullet list, one trigger per line (- …).

    Returns a dict with keys "goal", "process", "escalationTriggers".
    Preserves original values for any field that is empty.
    """
    # Only normalize fields that have content
    needs_norm = goal.strip() or process.strip() or escalation_triggers.strip()
    if not needs_norm:
        return {"goal": goal, "process": process, "escalationTriggers": escalation_triggers}

    system = (
        "You are formatting configuration text for an AI customer-service assistant "
        "used by PowWash, a UK exterior cleaning company.\n\n"
        "Your task is to take raw, possibly messy text and reformat it cleanly — "
        "fixing grammar, punctuation, and structure — WITHOUT changing the meaning or "
        "adding/removing content that isn't already there.\n\n"
        "FORMAT RULES:\n"
        "• goal — rewrite as 1–2 clear, imperative sentences. No bullet points.\n"
        "• process — rewrite as a clean numbered list: '1. Verb …' one step per line. "
        "Preserve every step; split run-on steps into separate numbered items.\n"
        "• escalationTriggers — rewrite as a bullet list: '- …' one trigger per line. "
        "Preserve every trigger.\n\n"
        "Return ONLY valid JSON, no markdown fences, exactly this shape:\n"
        '{"goal":"...","process":"...","escalationTriggers":"..."}\n\n'
        "If a field was empty, return it as an empty string."
    )
    parts = []
    if goal.strip():
        parts.append(f"GOAL:\n{goal}")
    if process.strip():
        parts.append(f"PROCESS:\n{process}")
    if escalation_triggers.strip():
        parts.append(f"ESCALATION TRIGGERS:\n{escalation_triggers}")
    user = "\n\n".join(parts) + "\n\nFormat and return as JSON."

    try:
        raw = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=800,
            model=CLAUDE_FAST_MODEL,
        )
        raw = _re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = _re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
        return {
            "goal":               parsed.get("goal",               goal),
            "process":            parsed.get("process",            process),
            "escalationTriggers": parsed.get("escalationTriggers", escalation_triggers),
        }
    except Exception:
        logger.exception("_normalize_goal_content failed — using raw values")
        return {"goal": goal, "process": process, "escalationTriggers": escalation_triggers}


@app.route("/api/kb/goal", methods=["POST"])
def kb_goal_save():
    data = request.get_json(force=True) or {}
    allowed = {
        "goal", "process", "escalationTriggers", "escalationPhone",
        "escalationChannel", "escalationMessage",
        "calendarCheckEnabled", "calendarBookEnabled",
    }
    patch = {k: v for k, v in data.items() if k in allowed}

    # Normalize goal / process / escalation triggers if any are present
    raw_goal     = patch.get("goal",               "").strip()
    raw_process  = patch.get("process",             "").strip()
    raw_triggers = patch.get("escalationTriggers",  "").strip()
    if raw_goal or raw_process or raw_triggers:
        normed = _normalize_goal_content(raw_goal, raw_process, raw_triggers)
        if raw_goal:
            patch["goal"]               = normed["goal"]
        if raw_process:
            patch["process"]            = normed["process"]
        if raw_triggers:
            patch["escalationTriggers"] = normed["escalationTriggers"]

    cfg = _save_goal_config(patch)
    return jsonify({"ok": True, "config": cfg})


def _load_all_kb_sections() -> dict:
    """Return a concise snapshot of every KB section for cross-checking."""
    tone = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip() if TONE_PROFILE_PATH.exists() else ""
    prices = _load_kb_prices()
    goal_cfg = _load_goal_config()
    scenarios = _load_scenarios()

    # Summarise scenarios so the prompt stays compact
    scen_summary: dict = {}
    for s in scenarios:
        k = f"{s.get('service_label', 'General')} › {s.get('category_label', 'General')}"
        scen_summary.setdefault(k, [])
        bullet = s.get("content", "")
        if bullet:
            scen_summary[k].append(bullet[:140])

    price_lines = []
    for key, entry in (prices or {}).items():
        price_lines.append(f"- {entry.get('label', key)}")
    prices_text = "\n".join(price_lines) if price_lines else "(none)"

    return {
        "tone":               tone or "(not set)",
        "prices":             prices_text,
        "goal":               goal_cfg.get("goal") or "(not set)",
        "process":            goal_cfg.get("process") or "(not set)",
        "escalationTriggers": goal_cfg.get("escalationTriggers") or "(not set)",
        "scenarios":          json.dumps(scen_summary, indent=2) if scen_summary else "(none)",
    }


def _build_cross_check_prompt(section: str, updated_text: str, sections: dict) -> tuple[str, str]:
    """Return (system, user) prompt for the cross-check call."""
    section_map = {
        "goal":      ("Goal & Process",   "goal, process, and escalation triggers"),
        "tone":      ("Tone Profile",     "tone / communication style rules"),
        "prices":    ("Price Guide",      "pricing for services"),
        "scenarios": ("Scenarios",        "specific Q&A / edge-case knowledge"),
    }
    sec_label, sec_desc = section_map.get(section, (section, section))

    other_sections = "\n\n".join([
        f"TONE PROFILE:\n{sections['tone']}",
        f"PRICE GUIDE:\n{sections['prices']}",
        f"GOAL:\n{sections['goal']}",
        f"PROCESS:\n{sections['process']}",
        f"ESCALATION TRIGGERS:\n{sections['escalationTriggers']}",
        f"SCENARIOS (summary):\n{sections['scenarios']}",
    ])

    system = (
        "You are a knowledge-base advisor for PowWash, a UK exterior cleaning company. "
        "You monitor the AI assistant's knowledge sections and flag only GENUINE issues "
        "that could cause the AI to behave inconsistently or confusingly.\n\n"
        "WHAT TO CHECK:\n"
        "1. Direct contradictions between sections (e.g. tone says 'never mention price comparisons' "
        "but goal says 'compare prices when asked').\n"
        "2. Content in the wrong section that would work better elsewhere.\n"
        "3. A gap the update reveals (e.g. new process step references a service not in the price guide).\n\n"
        "RULES:\n"
        "- Set hasInsight=true ONLY for clear, actionable issues worth interrupting the user.\n"
        "- If everything looks coherent, return hasInsight=false — silence is better than noise.\n"
        "- message: 1–3 sentences, specific and direct.\n"
        "- applyLabel: short button label (≤5 words) for the suggested fix, or null.\n"
        "- applyPayload: if you can safely auto-fix the issue, provide the COMPLETE API call:\n"
        '  Update tone  → {"endpoint":"/api/kb/tone","body":{"raw":"...one or more new/updated tone rules..."}}\n'
        '  Update goal  → {"endpoint":"/api/kb/goal","body":{"goal":"...","process":"..."}}\n'
        '  Add scenario → {"endpoint":"/api/kb/scenarios","body":{"service":"key","service_label":"Label","category":"key","category_label":"Label","content":"..."}}\n'
        "  Otherwise applyPayload=null.\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        '{"hasInsight":bool,"message":"...","applyLabel":null|"...","applyPayload":null|{...}}'
    )
    user = (
        f"JUST UPDATED — {sec_label} ({sec_desc}):\n{updated_text}\n\n"
        f"ALL OTHER SECTIONS:\n{other_sections}\n\n"
        "Analyse and return JSON."
    )
    return system, user


@app.route("/api/kb/cross-check", methods=["POST"])
def kb_cross_check():
    data = request.get_json(force=True) or {}
    section      = (data.get("section") or "").strip()
    updated_text = (data.get("updatedText") or "").strip()

    if not section or not updated_text:
        return jsonify({"hasInsight": False})

    sections = _load_all_kb_sections()
    system, user = _build_cross_check_prompt(section, updated_text, sections)

    try:
        raw = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=600,
            model=CLAUDE_FAST_MODEL,
        )
        raw = _re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = _re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
    except Exception:
        logger.exception("kb_cross_check AI parse failed")
        return jsonify({"hasInsight": False})

    return jsonify({
        "hasInsight":   bool(parsed.get("hasInsight")),
        "message":      parsed.get("message", ""),
        "applyLabel":   parsed.get("applyLabel"),
        "applyPayload": parsed.get("applyPayload"),
    })


@app.route("/api/kb/cross-check/respond", methods=["POST"])
def kb_cross_check_respond():
    """Handle user follow-up reply in the advisor modal (accept with conditions, etc.)."""
    data = request.get_json(force=True) or {}
    section         = (data.get("section") or "").strip()
    updated_text    = (data.get("updatedText") or "").strip()
    current_insight = (data.get("currentInsight") or "").strip()
    user_message    = (data.get("userMessage") or "").strip()

    if not user_message:
        return jsonify({"hasInsight": False})

    sections = _load_all_kb_sections()
    _, base_user = _build_cross_check_prompt(section, updated_text, sections)

    system = (
        "You are a knowledge-base advisor for PowWash continuing a conversation. "
        "You previously flagged an issue and the user has replied. "
        "Interpret their reply and produce a revised or confirmed action.\n\n"
        "RULES:\n"
        "- If the user wants the fix applied with conditions, adapt the applyPayload to match their conditions.\n"
        "- If the user asks a question, answer it in message and set applyPayload=null.\n"
        "- If the user says 'no' / 'dismiss' / 'ignore', set hasInsight=false.\n"
        "Return ONLY valid JSON (same shape as before — no markdown):\n"
        '{"hasInsight":bool,"message":"...","applyLabel":null|"...","applyPayload":null|{...}}'
    )
    user = (
        f"ORIGINAL CONTEXT:\n{base_user}\n\n"
        f"MY PREVIOUS INSIGHT:\n{current_insight}\n\n"
        f"USER REPLY:\n{user_message}\n\n"
        "Produce updated JSON."
    )

    try:
        raw = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=600,
            model=CLAUDE_FAST_MODEL,
        )
        raw = _re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = _re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
    except Exception:
        logger.exception("kb_cross_check_respond AI parse failed")
        return jsonify({"hasInsight": False, "message": "Sorry, something went wrong."})

    return jsonify({
        "hasInsight":   bool(parsed.get("hasInsight")),
        "message":      parsed.get("message", ""),
        "applyLabel":   parsed.get("applyLabel"),
        "applyPayload": parsed.get("applyPayload"),
    })


@app.route("/api/kb/status", methods=["GET"])
def kb_status():
    tone = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip() if TONE_PROFILE_PATH.exists() else ""
    prices = _load_kb_prices()
    return jsonify({"tone": tone, "prices": prices})


@app.route("/api/kb/tone", methods=["POST"])
def kb_tone_update():
    data = request.get_json(force=True)
    raw = data.get("raw", "").strip()
    if not raw:
        return jsonify({"error": "No description provided."}), 400
    existing = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip() if TONE_PROFILE_PATH.exists() else ""
    try:
        if existing:
            saved = _merge_tone_profile(existing, raw)
        else:
            # No existing profile — build from scratch
            built = _call_ai([
                {"role": "system", "content": (
                    "You are a business tone coach. Convert the owner's description into up to 15 "
                    "clear, actionable markdown bullet points. Each bullet starts with '- '. "
                    "Output ONLY the bullet list — no intro text, no headings."
                )},
                {"role": "user", "content": (
                    f"How I want my AI to sound:\n\n{raw}\n\n"
                    "Produce the tone guide as bullet points."
                )},
            ], max_tokens=700, model=CLAUDE_FAST_MODEL)
            saved = _normalise_tone_profile(built)
    except Exception as exc:
        logger.exception("KB tone update failed")
        return jsonify({"error": str(exc)}), 500
    TONE_PROFILE_PATH.write_text(saved, encoding="utf-8")
    return jsonify({"tone": saved})


@app.route("/api/kb/prices", methods=["GET"])
def kb_prices_get():
    return jsonify(_load_kb_prices())


@app.route("/api/kb/prices", methods=["POST"])
def kb_prices_save():
    data = request.get_json(force=True)
    service = data.get("service", "").strip()
    if not service:
        return jsonify({"error": "Service key required."}), 400
    label = data.get("label") or service.replace("_", " ").title()
    prices = _load_kb_prices()
    existing = prices.get(service) or {"label": label, "sub_categories": {}}
    existing.setdefault("label", label)

    # Sub-category upsert (new structured format)
    sub_cat_label = data.get("sub_category_label", "").strip()
    if sub_cat_label:
        sc_key = data.get("sub_category_key") or sub_cat_label.lower().replace(" ", "_").replace("/", "_")
        sc_key = "".join(c if c.isalnum() or c == "_" else "_" for c in sc_key)
        existing.setdefault("sub_categories", {})
        existing["sub_categories"][sc_key] = {
            "label": sub_cat_label,
            "pricing_and_time": data.get("pricing_and_time", ""),
            "common_questions": data.get("common_questions", ""),
            "things_to_know": data.get("things_to_know", ""),
        }
        prices[service] = existing
        _save_kb_prices(prices)
        return jsonify(prices)

    # Service-only upsert (no sub-category data)
    prices[service] = existing
    _save_kb_prices(prices)
    return jsonify(prices)


@app.route("/api/kb/prices/<service>", methods=["PATCH"])
def kb_prices_patch(service: str):
    data   = request.get_json(force=True) or {}
    prices = _load_kb_prices()
    if service not in prices:
        return jsonify({"error": "Not found"}), 404
    if "label" in data:
        label = (data["label"] or "").strip()
        if label:
            prices[service]["label"] = label
    if "booking_process" in data:
        prices[service]["booking_process"] = (data["booking_process"] or "").strip()
    if "things_to_know" in data:
        prices[service]["things_to_know"] = (data["things_to_know"] or "").strip()
    _save_kb_prices(prices)
    return jsonify({"ok": True})


@app.route("/api/kb/prices/<service>", methods=["DELETE"])
def kb_prices_delete(service: str):
    prices = _load_kb_prices()
    prices.pop(service, None)
    _save_kb_prices(prices)
    return jsonify(prices)


@app.route("/api/kb/prices/<service>/sub_categories/<sc_key>", methods=["PATCH"])
def kb_prices_patch_subcat(service: str, sc_key: str):
    data   = request.get_json(force=True) or {}
    prices = _load_kb_prices()
    sc     = prices.get(service, {}).get("sub_categories", {}).get(sc_key)
    if sc is None:
        return jsonify({"error": "Not found"}), 404
    for field in ("pricing_and_time", "common_questions", "things_to_know", "label"):
        if field in data:
            sc[field] = data[field]
    _save_kb_prices(prices)
    return jsonify({"ok": True})


@app.route("/api/kb/prices/<service>/sub_categories/<sc_key>", methods=["DELETE"])
def kb_prices_delete_subcat(service: str, sc_key: str):
    prices = _load_kb_prices()
    if service in prices:
        prices[service].get("sub_categories", {}).pop(sc_key, None)
    _save_kb_prices(prices)
    return jsonify(prices)


@app.route("/api/kb/refine-text", methods=["POST"])
def kb_refine_text():
    data    = request.get_json(force=True) or {}
    text    = (data.get("text") or "").strip()
    context = (data.get("context") or "").strip()
    if not text:
        return jsonify({"refined": text})
    system = (
        "You are an editor for a UK exterior cleaning business knowledge base. "
        "Improve the clarity, grammar, and readability of the text below. "
        "Keep the same meaning and all facts — do not add or remove information. "
        "Keep it concise. Return ONLY the improved text, no intro, no quotes, nothing else."
    )
    user_msg = (f"Context: {context}\n\nText to improve:\n{text}") if context else f"Text to improve:\n{text}"
    try:
        refined = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            max_tokens=400,
            model=CLAUDE_FAST_MODEL,
        )
        return jsonify({"refined": refined.strip()})
    except Exception:
        logger.exception("kb_refine_text failed")
        return jsonify({"refined": text})


@app.route("/api/kb/chat", methods=["POST"])
def kb_chat():
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "Message required."}), 400

    tone = TONE_PROFILE_PATH.read_text(encoding="utf-8").strip() if TONE_PROFILE_PATH.exists() else "Not set yet."
    prices = _load_kb_prices()
    prices_text = _prices_to_text(prices)
    scenarios = _load_scenarios()
    scenarios_text = _scenarios_to_text(scenarios) if scenarios else "No diagnostic scenarios saved yet."

    # Load the booking process and goal
    goal_cfg = _load_goal_config()
    current_goal    = goal_cfg.get("goal", "Not set.")
    current_process = goal_cfg.get("process", "Not set.")

    system = (
        "You are the knowledge base assistant for PowWash, an exterior cleaning company. "
        "You know the full configuration of the AI assistant and can update any part of it.\n\n"
        "=== CURRENT CONFIGURATION ===\n\n"
        f"TONE PROFILE (how the AI sounds):\n{tone}\n\n"
        f"PRICE GUIDE (what the AI quotes):\n{prices_text}\n\n"
        f"BOOKING GOAL:\n{current_goal}\n\n"
        f"BOOKING PROCESS / FLOW (step-by-step instructions):\n{current_process}\n\n"
        f"DIAGNOSTIC SCENARIOS / COMMON ISSUES:\n{scenarios_text}\n\n"
        "=== TWO CORE PRINCIPLES ===\n"
        "1. TONE IS NON-NEGOTIABLE: The tone profile takes absolute priority at all times. "
        "Every reply must stay in the established style regardless of service type or conversation stage. "
        "If the AI ever sounds too formal, too robotic, uses bullet points, em dashes, or loses the "
        "warm conversational feel — that is always a TONE PROFILE fix.\n"
        "2. STAY IN SERVICE LANE: Once the customer's service type is identified (gutter clean, driveway, "
        "patio, render wash, etc.), the AI must use ONLY that service's pricing section. It must not "
        "reference other services' prices unless the customer explicitly asks. If the AI is mixing up "
        "pricing from different services — that is a BOOKING PROCESS or PRICE GUIDE fix.\n\n"
        "=== YOUR JOB ===\n"
        "When the user describes something the AI is doing wrong, or asks to change a rule, "
        "FIRST diagnose which section it belongs to using this routing guide:\n\n"
        "  TONE PROFILE   — word choice, punctuation, em dashes, sign-offs, how to phrase things, "
        "exclamation marks, formality level, how questions are worded, warmth, natural feel\n"
        "  PRICE GUIDE    — wrong prices, missing services, add-on logic, pricing rules\n"
        "  BOOKING PROCESS — wrong order of steps, when to ask for calendar/email/name/address, "
        "flow of the conversation, what triggers a calendar check, staying in service lane\n"
        "  BOOKING GOAL   — the high-level objective the AI is trying to achieve\n"
        "  SCENARIOS      — specific edge cases, FAQs, common issues for a particular service\n\n"
        "After diagnosing, tell the user what you found and what you will change. "
        "Then apply the fix using ONE action tag at the very end of your reply.\n\n"
        "CRITICAL RULE: You NEVER say you have saved or updated something unless your reply contains an <action> tag.\n\n"
        "--- ACTION TAG FORMATS ---\n\n"
        "Update tone profile:\n"
        '<action>{"type":"update_tone","raw":"the new rule or change to apply"}</action>\n\n'
        "Update a price or service:\n"
        '<action>{"type":"update_prices","service":"snake_case_key","label":"Display Name",'
        '"unit":"per job","notes":"any notes"}</action>\n\n'
        "Update the booking process steps (provide the FULL rewritten process — keep steps not affected unchanged):\n"
        '<action>{"type":"update_process","process":"1. Step one.\\n2. Step two.\\n..."}</action>\n\n'
        "Update the booking goal:\n"
        '<action>{"type":"update_goal","goal":"new goal text"}</action>\n\n'
        "Add or update a diagnostic scenario:\n"
        '<action>{"type":"update_scenario","service":"snake_case_key","service_label":"Display Name",'
        '"category":"common_issues","category_label":"Common Issues","content":"full text to save"}</action>\n\n'
        "Valid scenario categories: common_issues, pricing_notes, process_notes, faq.\n\n"
        "Include ONE action tag only when making a change. Be concise and direct — "
        "explain what was wrong and what you changed, not just that you changed it."
    )

    messages = list(history) + [{"role": "user", "content": message}]

    try:
        reply_text = _call_ai(
            [{"role": "system", "content": system}] + messages,
            max_tokens=600,
            model=CLAUDE_FAST_MODEL,
        )
    except Exception as exc:
        logger.exception("KB chat failed")
        return jsonify({"error": str(exc)}), 500

    # Parse optional action tag
    action: Dict[str, Any] | None = None
    action_match = _re.search(r"<action>(.*?)</action>", reply_text, _re.DOTALL)
    if action_match:
        try:
            action = json.loads(action_match.group(1))
            reply_text = reply_text[: action_match.start()].strip()
        except Exception:
            pass

    result: Dict[str, Any] = {"reply": reply_text}

    if action:
        atype = action.get("type")
        if atype == "update_prices":
            skey = action.get("service", "custom_service")
            entry = {k: v for k, v in action.items() if k not in ("type", "service")}
            entry.setdefault("label", skey.replace("_", " ").title())
            prices[skey] = entry
            _save_kb_prices(prices)
            result["action"] = {"type": "prices_updated", "prices": prices}
        elif atype == "update_tone":
            raw_tone = action.get("raw", "")
            if raw_tone:
                try:
                    saved = _merge_tone_profile(tone, raw_tone) if tone and tone != "Not set yet." else _normalise_tone_profile(raw_tone)
                    TONE_PROFILE_PATH.write_text(saved, encoding="utf-8")
                    result["action"] = {"type": "tone_updated", "tone": saved}
                except Exception as exc:
                    logger.exception("KB tone update via chat failed")
        elif atype == "update_process":
            new_process = action.get("process", "").strip()
            if new_process:
                try:
                    goal_cfg2 = _load_goal_config()
                    goal_cfg2["process"] = new_process
                    GOAL_CONFIG_PATH.write_text(json.dumps(goal_cfg2, indent=2, ensure_ascii=False), encoding="utf-8")
                    result["action"] = {"type": "process_updated", "process": new_process}
                except Exception as exc:
                    logger.exception("KB process update via chat failed")
        elif atype == "update_goal":
            new_goal = action.get("goal", "").strip()
            if new_goal:
                try:
                    goal_cfg2 = _load_goal_config()
                    goal_cfg2["goal"] = new_goal
                    GOAL_CONFIG_PATH.write_text(json.dumps(goal_cfg2, indent=2, ensure_ascii=False), encoding="utf-8")
                    result["action"] = {"type": "goal_updated", "goal": new_goal}
                except Exception as exc:
                    logger.exception("KB goal update via chat failed")
        elif atype == "update_scenario":
            import uuid as _uuid
            from datetime import date as _date
            svc = action.get("service", "general").strip()
            svc_label = action.get("service_label", svc.replace("_", " ").title()).strip()
            cat = action.get("category", "common_issues").strip()
            cat_label = action.get("category_label", cat.replace("_", " ").title()).strip()
            content = action.get("content", "").strip()
            if content:
                try:
                    _ai_inst = AIClient()
                    all_scenarios = _load_scenarios()
                    existing_bullets = [
                        s["content"] for s in all_scenarios
                        if s.get("service") == svc and s.get("category") == cat
                    ]
                    merged = _format_and_merge_scenario_bullets(
                        _ai_inst, svc_label, cat_label, content, existing_bullets
                    )
                    all_scenarios = [s for s in all_scenarios if not (s.get("service") == svc and s.get("category") == cat)]
                    today = str(_date.today())
                    for bullet in merged:
                        all_scenarios.append({
                            "id": _uuid.uuid4().hex[:8],
                            "service": svc,
                            "service_label": svc_label,
                            "category": cat,
                            "category_label": cat_label,
                            "content": bullet,
                            "created_at": today,
                        })
                    _save_scenarios(all_scenarios)
                    result["action"] = {"type": "scenario_updated", "scenarios": all_scenarios}
                except Exception as exc:
                    logger.exception("KB scenario update via chat failed")

    return jsonify(result)


# ── WhatsApp Messages Bridge ─────────────────────────────────────────────────

def _get_cs():
    """Return the Postgres-backed conversation store.

    local_store is backed by Postgres (app_kv) so conversations survive
    Autoscale restarts and are shared across instances.  The Firestore
    ConversationStore requires an explicit account_id that this app never
    supplies (it passes None), so we always use local_store here.
    """
    from local_store import get_local_store
    return get_local_store()


def _msgs_store():
    """Return conversation_store singleton, or None if Firebase is not configured."""
    try:
        from conversation_store import conversation_store as _cs
        _cs.list_conversations(None)
        return _cs
    except Exception:
        return None


_msgs_store_checked: bool | None = None  # None=unchecked, True=ok, False=fail
_msgs_store_error: str = ""


def _msgs_store_cached():
    global _msgs_store_checked, _msgs_store_error
    if _msgs_store_checked is None:
        try:
            from conversation_store import conversation_store as _cs
            _cs.list_conversations(None)
            _msgs_store_checked = True
        except Exception as exc:
            _msgs_store_checked = False
            _msgs_store_error = str(exc)
    if _msgs_store_checked:
        from conversation_store import conversation_store as _cs
        return _cs
    return None


@app.route("/api/messages/stream")
@login_required
def messages_stream():
    """SSE endpoint — pushes new_message events to the browser instantly."""
    from flask import Response, stream_with_context
    q: queue.Queue = queue.Queue(maxsize=50)
    with _sse_queues_lock:
        _sse_queues.append(q)

    def generate():
        try:
            yield "data: {\"ok\": true}\n\n"
            while True:
                try:
                    yield q.get(timeout=25)
                except queue.Empty:
                    yield ": ping\n\n"   # keep connection alive
        finally:
            with _sse_queues_lock:
                try:
                    _sse_queues.remove(q)
                except ValueError:
                    pass

    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/api/messages/conversations", methods=["GET"])
def msgs_list_conversations():
    try:
        _cs = _get_cs()
        convos = _cs.list_conversations(None)
        serializable = [c.to_dict() if hasattr(c, "to_dict") else c for c in (convos or [])]
        return jsonify({"connected": True, "conversations": serializable})
    except Exception as exc:
        return jsonify({"connected": False, "conversations": [], "error": str(exc)})


@app.route("/api/messages/conversations/<cid>", methods=["GET"])
def msgs_get_conversation(cid):
    try:
        _cs = _get_cs()
        convo = _cs.get_conversation(None, cid, mark_read=True)
        if convo is None:
            # New outbound thread — no messages yet, return a minimal skeleton
            return jsonify({
                "id": cid,
                "displayName": cid,
                "phoneNumber": cid,
                "messages": [],
                "aiEnabled": False,
                "unreadCount": 0,
            })
        return jsonify(convo.to_dict() if hasattr(convo, "to_dict") else convo)
    except Exception as exc:
        logger.warning("msgs_get_conversation failed: %s", exc)
        return jsonify({"error": str(exc), "messages": [], "id": cid,
                        "displayName": cid, "phoneNumber": cid, "aiEnabled": False,
                        "unreadCount": 0}), 200


@app.route("/api/messages/conversations/<cid>", methods=["DELETE"])
def msgs_delete_conversation(cid):
    try:
        _get_cs().delete_conversation(None, cid)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.warning("msgs_delete_conversation failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/twilio/status-callback", methods=["POST"])
def twilio_status_callback():
    """
    Twilio calls this with delivery/read updates for outbound messages.
    Set this URL as the Status Callback in your Twilio Messaging Service or
    pass it as status_callback when creating messages.
    """
    msg_sid    = (request.form.get("MessageSid") or request.form.get("SmsSid") or "").strip()
    raw_status = (request.form.get("MessageStatus") or request.form.get("SmsStatus") or "").strip()
    status_map = {
        "queued":      "queued",
        "sending":     "sending",
        "sent":        "sent",
        "delivered":   "delivered",
        "read":        "read",
        "failed":      "failed",
        "undelivered": "failed",
    }
    internal_status = status_map.get(raw_status)
    if msg_sid and internal_status:
        try:
            from conversation_store import conversation_store as _cs
            _cs.update_message_by_transport_sid(None, msg_sid, status=internal_status)
            logger.info("Twilio status callback: %s → %s", msg_sid, internal_status)
        except Exception as exc:
            logger.warning("status_callback update failed: %s", exc)
    return ("", 204)


@app.route("/api/messages/conversations/<cid>/draft", methods=["POST"])
def msgs_draft(cid):
    try:
        _cs = _get_cs()
        latest = _cs.latest_customer_message(None, cid) if hasattr(_cs, "latest_customer_message") else None
        if latest is None:
            return jsonify({"error": "No customer message available"}), 400

        # Build conversation history for context
        history = []
        try:
            convo = _cs.get_conversation(None, cid)
            if convo is not None:
                convo_dict = convo.to_dict() if hasattr(convo, "to_dict") else (convo if isinstance(convo, dict) else {})
                msgs = convo_dict.get("messages", [])
                latest_id = latest.id if hasattr(latest, "id") else None
                for m in msgs:
                    mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                    if mid and mid == latest_id:
                        break  # stop before the latest customer message (passed separately)
                    text_val = m.get("text", "") if isinstance(m, dict) else getattr(m, "text", "")
                    direction = m.get("direction", "") if isinstance(m, dict) else getattr(m, "direction", "")
                    if not text_val:
                        continue
                    history.append({
                        "role": "user" if direction == "inbound" else "assistant",
                        "content": text_val,
                    })
        except Exception:
            pass  # gracefully degrade if history fetch fails

        text     = latest.text if hasattr(latest, "text") else str(latest)
        goal_cfg = _load_goal_config()
        draft    = _generate_kb_reply(
            customer_message=text,
            conversation_history=history or None,
            goal_config=goal_cfg,
        )

        # ── Calendar two-pass: call scheduling agent and re-run AI with real slots ──
        draft = _enforce_calendar_token(draft, text, history or [], goal_cfg)
        draft = _resolve_calendar_signals(draft, text, history or [], goal_cfg)

        # ── Detect remaining AI signals ────────────────────────────────
        signals = []
        clean_draft = draft
        # CALENDAR_CHECK_NEEDED may be parameterised — match with regex
        cal_check_match = _CAL_TOKEN_RE.search(clean_draft)
        if cal_check_match:
            signals.append("CALENDAR_CHECK_NEEDED")
            clean_draft = _CAL_TOKEN_RE.sub("", clean_draft).strip()
        if "[NEEDS_HUMAN_REVIEW]" in clean_draft:
            signals.append("NEEDS_HUMAN_REVIEW")
            clean_draft = clean_draft.replace("[NEEDS_HUMAN_REVIEW]", "").strip()
        if _CAL_BOOK_TOKEN_RE.search(clean_draft):
            signals.append("CALENDAR_BOOK_NEEDED")
            clean_draft = _CAL_BOOK_TOKEN_RE.sub("", clean_draft).strip()
        clean_draft = _COVERAGE_TOKEN_RE.sub("", clean_draft).strip()
        if _ATTENTION_TOKEN_RE.search(clean_draft):
            signals.append("NEEDS_HUMAN_ATTENTION")
            clean_draft = _ATTENTION_TOKEN_RE.sub("", clean_draft).strip()

        # Fire escalation notification if signal present and contact configured
        if "NEEDS_HUMAN_REVIEW" in signals:
            _push_bg("Action needed", "The AI needs you to step in on a conversation.", "human_input")
            esc_phone = (goal_cfg.get("escalationPhone") or "").strip()
            if esc_phone:
                try:
                    s = _load_twilio_settings()
                    account_sid = s.get("accountSid", "").strip()
                    auth_token  = s.get("authToken", "").strip()
                    if account_sid and auth_token:
                        from twilio.rest import Client as _TwilioClient
                        tc = _TwilioClient(account_sid, auth_token)
                        channel = goal_cfg.get("escalationChannel", "whatsapp")
                        summary = f"Conversation {cid} — customer message: {text[:200]}"
                        body = (goal_cfg.get("escalationMessage") or "").format(
                            customerSummary=summary
                        ) or f"⚠ Human review needed for conversation with {cid}."
                        if channel == "whatsapp":
                            fnum = s.get("whatsappFrom", "").strip()
                            tc.messages.create(
                                body=body,
                                to=f"whatsapp:{esc_phone}",
                                from_=fnum if fnum.startswith("whatsapp:") else f"whatsapp:{fnum}",
                            )
                        else:
                            fnum = s.get("smsFrom", s.get("whatsappFrom", "")).strip()
                            tc.messages.create(body=body, to=esc_phone, from_=fnum)
                        logger.info("Escalation notification sent to %s (%s)", esc_phone, channel)
                except Exception as esc_exc:
                    logger.warning("Escalation notification failed: %s", esc_exc)

        return jsonify({"draft": clean_draft, "signals": signals})
    except Exception as exc:
        logger.exception("msgs_draft failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/messages/conversations/<cid>/toggle-ai", methods=["POST"])
def msgs_toggle_ai(cid):
    data    = request.get_json(force=True) or {}
    enabled = bool(data.get("enabled", True))
    try:
        _cs = _get_cs()
        result = _cs.set_ai_enabled(None, cid, enabled)
        _ai_enabled_state[cid] = bool(result)
        return jsonify({"enabled": bool(result)})
    except Exception as exc:
        logger.warning("toggle-ai failed (%s) — using in-memory fallback", exc)
        _ai_enabled_state[cid] = enabled
        return jsonify({"enabled": enabled})


@app.route("/api/messages/conversations/<cid>/send", methods=["POST"])
def msgs_send(cid):
    """Send an agent/AI-approved reply. Cancels pending AI drafts, then delivers via Twilio."""
    try:
        _cs = _get_cs()
        from datetime import datetime, timezone
        data = request.get_json(force=True) or {}
        text   = (data.get("text") or "").strip()
        author = (data.get("author") or "agent").strip()  # "agent" or "ai"
        if not text:
            return jsonify({"error": "Message text is required"}), 400

        # Cancel any pending AI messages so this reply takes over
        cancelled = _cs.cancel_pending_ai_messages(None, cid, reason="Agent replied")

        # Attempt to deliver via Twilio
        s = _load_twilio_settings()
        account_sid = s.get("accountSid", "").strip()
        auth_token  = s.get("authToken", "").strip()
        twilio_sid, twilio_status, twilio_error = None, "sent", None

        if account_sid and auth_token:
            try:
                from twilio.rest import Client as _TC
                tc = _TC(account_sid, auth_token)
                phone = cid.lstrip("+")
                phone = "+" + phone if not cid.startswith("+") else cid
                to_wa = f"whatsapp:{phone}"
                msid  = s.get("messagingServiceSid", "").strip()
                fnum  = s.get("whatsappFrom", "").strip()
                kwargs: Dict[str, Any] = {"body": text, "to": to_wa}
                if msid:
                    kwargs["messaging_service_sid"] = msid
                elif fnum:
                    kwargs["from_"] = fnum if fnum.startswith("whatsapp:") else f"whatsapp:{fnum}"
                cb_domain = os.getenv("REPLIT_DEV_DOMAIN", "")
                if cb_domain:
                    kwargs["status_callback"] = f"https://{cb_domain}/api/twilio/status-callback"
                msg = tc.messages.create(**kwargs)
                twilio_sid = msg.sid
                logger.info("msgs_send: sent %s to %s", twilio_sid, to_wa)
            except Exception as exc_tw:
                twilio_error  = str(exc_tw)
                twilio_status = "failed"
                logger.warning("msgs_send: Twilio send failed: %s", exc_tw)

        now = datetime.now(timezone.utc)
        message = _cs.record_message(
            None, cid,
            text=text, author=author, direction="outbound",
            status=twilio_status, transport_sid=twilio_sid,
            sent_at=now if twilio_status == "sent" else None,
            error=twilio_error,
        )
        msg_dict = message.to_dict() if hasattr(message, "to_dict") else (message if isinstance(message, dict) else {})
        result = {
            "status": twilio_status,
            "message": msg_dict,
            "cancelledAiMessages": cancelled,
        }
        if twilio_error:
            result["error"] = twilio_error
        return jsonify(result)
    except Exception as exc:
        logger.exception("msgs_send failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/messages/conversations/<cid>/cancel-draft", methods=["POST"])
def msgs_cancel_draft(cid):
    """Cancel all pending AI drafts for a conversation."""
    try:
        _cs = _get_cs()
        _cs.cancel_pending_ai_messages(None, cid, reason="Operator cancelled")
        return jsonify({"status": "cancelled"})
    except Exception as exc:
        logger.exception("msgs_cancel_draft failed")
        return jsonify({"error": str(exc)}), 500

@app.route("/api/messages/conversations/<cid>/messages/<mid>/cancel", methods=["POST"])
def msgs_cancel_message(cid, mid):
    """Cancel a specific pending AI message."""
    try:
        _cs = _get_cs()
        message = _cs.cancel_scheduled_message(None, cid, mid)
        if message is None:
            return jsonify({"error": "Message not found or already sent"}), 404
        msg_dict = message.to_dict() if hasattr(message, "to_dict") else (message if isinstance(message, dict) else {})
        return jsonify({"status": "cancelled", "message": msg_dict})
    except Exception as exc:
        logger.exception("msgs_cancel_message failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/messages/simulate", methods=["POST"])
def msgs_simulate():
    """
    Customer simulator — uses Claude via _call_ai, identical to
    /api/tune/simulate (the AI that is trained with the knowledge base,
    tone profile, and RAG examples).
    Body: { message: str, history: [{role: "customer"|"ai", text: str}] }
    Returns: { reply: str }
    """
    try:
        data = request.get_json(force=True) or {}
        customer_message = (data.get("message") or "").strip()
        history = data.get("history") or []

        if not customer_message:
            return jsonify({"error": "message is required"}), 400

        # Full pipeline — identical to the real WhatsApp webhook path
        goal_cfg = _load_goal_config()
        conv_history = []
        for turn in history:
            role = turn.get("role", "customer")
            text = (turn.get("text") or "").strip()
            if text:
                conv_history.append({"role": "user" if role == "customer" else "assistant", "content": text})

        reply = _generate_kb_reply(
            customer_message=customer_message,
            conversation_history=conv_history or None,
            goal_config=goal_cfg,
            max_tokens=350,
        )
        reply = _resolve_calendar_signals(reply, customer_message, conv_history or [], goal_cfg)
        reply = _CAL_TOKEN_RE.sub("", reply).strip()
        reply = reply.replace("[NEEDS_HUMAN_REVIEW]", "").strip()
        reply = _COVERAGE_TOKEN_RE.sub("", reply).strip()
        reply = _ATTENTION_TOKEN_RE.sub("", reply).strip()

        # Handle CALENDAR_BOOK_NEEDED — extract details and create a real calendar event
        booking_result = None
        if _CAL_BOOK_TOKEN_RE.search(reply):
            all_history = list(conv_history) + [{"role": "user", "content": customer_message}]
            booking_result = _extract_and_create_booking(all_history, reply)
            reply = _CAL_BOOK_TOKEN_RE.sub("", reply).strip()
            _push_bg("Booking confirmed", "A new job has been added to your calendar.", "booking_complete")

        resp: Dict[str, Any] = {"reply": reply}
        if booking_result:
            resp["booked"]  = booking_result.get("ok", False)
            resp["booking"] = booking_result
        return jsonify(resp)

    except Exception as exc:
        logger.exception("msgs_simulate failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/messages/outbound", methods=["POST"])
def msgs_send_outbound():
    """Start a new conversation by sending an outbound template message."""
    try:
        data = request.get_json(force=True) or {}
        phone   = (data.get("phone") or "").strip()
        message = (data.get("message") or "").strip()
        channel = (data.get("channel") or "whatsapp").strip().lower()

        if not phone or not message:
            return jsonify({"error": "phone and message are required"}), 400
        if not phone.startswith("+"):
            return jsonify({"error": "Phone number must be in E.164 format (e.g. +447700900000)"}), 400

        s = _load_twilio_settings()
        account_sid = s.get("accountSid", "").strip()
        auth_token  = s.get("authToken", "").strip()

        twilio_sid, twilio_status, twilio_error = None, "sent", None

        if account_sid and auth_token:
            try:
                from twilio.rest import Client as _TwilioClient
                from twilio.base.exceptions import TwilioRestException as _TwilioErr
                tc = _TwilioClient(account_sid, auth_token)
                if channel == "whatsapp":
                    to_num      = f"whatsapp:{phone}"
                    msid        = s.get("messagingServiceSid", "").strip()
                    fnum        = s.get("whatsappFrom", "").strip()
                    content_sid = (data.get("content_sid") or "").strip()
                    content_vars= data.get("content_variables") or {}
                    if content_sid:
                        # Approved WhatsApp template — must use content_sid, not body
                        kwargs = {"content_sid": content_sid, "to": to_num}
                        if content_vars:
                            import json as _json
                            kwargs["content_variables"] = _json.dumps(content_vars)
                    else:
                        kwargs = {"body": message, "to": to_num}
                    if msid:
                        kwargs["messaging_service_sid"] = msid
                    elif fnum:
                        kwargs["from_"] = fnum if fnum.startswith("whatsapp:") else f"whatsapp:{fnum}"
                    else:
                        return jsonify({"error": "No WhatsApp sender configured — add one in Settings."}), 400
                    cb_domain = os.getenv("REPLIT_DEV_DOMAIN", "")
                    if cb_domain:
                        kwargs["status_callback"] = f"https://{cb_domain}/api/twilio/status-callback"
                else:
                    fnum = s.get("smsFrom", s.get("whatsappFrom", "")).strip()
                    if not fnum:
                        return jsonify({"error": "No SMS sender configured — add one in Settings."}), 400
                    kwargs = {"body": message, "to": phone, "from_": fnum}
                msg = tc.messages.create(**kwargs)
                twilio_sid = msg.sid
            except Exception as exc:
                twilio_error  = str(exc)
                twilio_status = "failed"
        else:
            twilio_status = "sent"  # store locally even without live Twilio

        # conversation_id = raw phone (no channel prefix)
        conversation_id = phone
        try:
            _cs_out = _get_cs()
            from datetime import datetime, timezone as _tz
            _cs_out.record_message(
                None, conversation_id,
                text=message, author="agent", direction="outbound",
                via=channel, transport_sid=twilio_sid, status=twilio_status,
                sent_at=datetime.now(_tz.utc) if twilio_status == "sent" else None,
                error=twilio_error,
            )
        except Exception:
            pass  # conversation store unavailable — send still succeeded

        result = {"ok": twilio_status == "sent", "conversationId": conversation_id, "status": twilio_status}
        if twilio_error:
            result["error"] = twilio_error
        if twilio_sid:
            result["sid"] = twilio_sid
        return jsonify(result)
    except Exception as exc:
        logger.exception("msgs_send_outbound failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/messages/ai-draft-direct", methods=["POST"])
def msgs_ai_draft_direct():
    """
    Generate a single AI draft reply from a free-text message.
    Works without Firebase. Used by the demo mode in the Messages tab.
    Body: { message: str }
    Returns: { draft: str }
    """
    try:
        data = request.get_json(force=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "message is required"}), 400

        from auto_responder import generate_reply as _gen_reply
        draft = _gen_reply(
            message=message,
            price_list_path=Path("price_list.json"),
            tone_profile_path=Path("tone_profile.md"),
        )
        return jsonify({"draft": draft})
    except Exception as exc:
        logger.exception("msgs_ai_draft_direct failed")
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS — Twilio + Message Templates
# ─────────────────────────────────────────────────────────────────────────────

# ── Live webhook inbox (in-memory, last 100 messages) ────────────────────────
_inbox_messages: List[Dict] = []
_inbox_lock = threading.Lock()
_ai_enabled_state: Dict[str, bool] = {}  # local fallback: cid → bool

# ── SSE: real-time push to browser clients ────────────────────────────────────
_sse_queues: List[queue.Queue] = []
_sse_queues_lock = threading.Lock()

def _sse_push(event: str, data: dict):
    """Push a server-sent event to every connected browser tab."""
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _sse_queues_lock:
        dead = [q for q in _sse_queues if q.full()]
        for q in dead:
            _sse_queues.remove(q)
        for q in _sse_queues:
            try:
                q.put_nowait(msg)
            except Exception:
                pass


TWILIO_SETTINGS_PATH = PersistentFile(APP_ROOT / "twilio_settings.json")
TEMPLATES_PATH = PersistentFile(APP_ROOT / "message_templates.json")


def _load_twilio_settings() -> Dict[str, Any]:
    if TWILIO_SETTINGS_PATH.exists():
        try:
            return json.loads(TWILIO_SETTINGS_PATH.read_text())
        except Exception:
            pass
    return {
        "accountSid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "authToken": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "whatsappFrom": os.getenv("TWILIO_WHATSAPP_FROM", ""),
        "messagingServiceSid": os.getenv("TWILIO_MESSAGING_SERVICE_SID", ""),
        "sandboxMode": True,
        "sandboxKeyword": "",
    }


def _load_templates() -> List[Dict]:
    if TEMPLATES_PATH.exists():
        try:
            data = json.loads(TEMPLATES_PATH.read_text())
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def _describe_quote_request(images: list, context_msg: str = "", transcript: str = "") -> str:
    """Write a short OWNER-FACING context note for the Quotes section.

    The AI does NOT review or interpret the customer's photos — a human prices
    the job from the photos themselves. This note's job is purely to hand the
    human all the CONTEXT they need from the conversation: which service the
    customer wants, the property type / storeys / extensions, the address or
    postcode, any condition notes, and what's being asked. The photos are
    attached to the quote request separately. Falls back to a generic prompt
    on any error.
    """
    _generic = "Customer sent photos — please review the photos and respond with a quote."
    _img_count = len([im for im in (images or [])
                      if im.get("data") and (im.get("contentType") or "").startswith("image/")])
    _photo_note = (f"{_img_count} photo(s) attached above. " if _img_count else "")

    ctx = (context_msg or "").strip()
    convo = (transcript or "").strip()
    # Nothing to summarise from — return a minimal but useful note.
    if not convo and (not ctx or ctx == "[Media only]"):
        return f"{_photo_note}Please review the photos and respond with a quote.".strip()

    system = (
        "You are assisting the owner of PowWash, an exterior cleaning company, inside their internal "
        "Quotes dashboard. This note is for the OWNER only — it is NEVER sent to the customer. "
        "A human will look at the customer's PHOTOS to price the job, so do NOT describe or guess what "
        "is in the photos and do NOT suggest a price. Your ONLY job is to summarise the CONTEXT from the "
        "conversation that the owner needs in order to quote accurately. In 1-3 short plain sentences, "
        "pull together: the service(s) requested, the property type / number of storeys / any extensions "
        "or conservatory, the address or postcode if given, any condition or access notes, and anything "
        "else the customer has said that affects the price. If a key detail is missing, say so briefly "
        "(e.g. 'no postcode given yet'). Be factual and concise — this is a handover note, not a reply."
    )
    user_parts = []
    if ctx and ctx != "[Media only]":
        user_parts.append(f"Latest customer message: {ctx}")
    if convo:
        user_parts.append(f"Conversation so far:\n{convo}")
    user_text = "\n\n".join(user_parts)

    # Bound the call so a slow/unreachable API can't stall quote-request creation
    # (this runs inside the media-hold Timer thread). Falls back on timeout.
    import concurrent.futures as _cf
    _ex = _cf.ThreadPoolExecutor(max_workers=1)
    try:
        _fut = _ex.submit(
            _call_ai,
            [{"role": "system", "content": system},
             {"role": "user", "content": user_text}],
            220, CLAUDE_MAIN_MODEL,
        )
        note = (_fut.result(timeout=25) or "").strip()
        return (f"{_photo_note}{note}").strip() if note else (
            f"{_photo_note}Please review the photos and respond with a quote.".strip())
    except Exception as _e:
        logger.warning("_describe_quote_request context note failed: %s", _e)
        if ctx and ctx != "[Media only]":
            return f"{_photo_note}Customer enquiry: {ctx}. Please review the photos and quote.".strip()
        return f"{_photo_note}Please review the photos and respond with a quote.".strip()
    finally:
        _ex.shutdown(wait=False)


_draft_locks_master = threading.Lock()
_draft_locks: Dict[str, threading.Lock] = {}


def _draft_lock(conv_id: str) -> threading.Lock:
    """Per-conversation lock. Two webhook deliveries of the same customer turn
    (Twilio re-delivery with a different SID, or Autoscale fan-out) can run
    _auto_draft concurrently; without serialising the cancel+record step each
    thread reads stale state, neither cancels the other's draft, and the customer
    receives the SAME reply twice. This lock makes draft creation atomic."""
    with _draft_locks_master:
        lk = _draft_locks.get(conv_id)
        if lk is None:
            # Bound the map so a long-running instance can't accumulate locks
            # unboundedly. Drop any currently-unheld locks when it grows large;
            # an evicted conversation simply gets a fresh lock next time.
            if len(_draft_locks) > 2000:
                for _k in [k for k, v in _draft_locks.items() if not v.locked()]:
                    del _draft_locks[_k]
            lk = threading.Lock()
            _draft_locks[conv_id] = lk
        return lk


def _auto_draft(conv_id: str, msg_text: str, chan: str,
                images: list = None, extra_context: str = "",
                skip_media_path: bool = False) -> None:
    """Generate and schedule an AI reply for an incoming WhatsApp message.

    Called from a background thread.  *images* is a list of
    {"data": base64_str, "contentType": mime, "savedAt": float} dicts.
    *extra_context* is prepended to the system prompt (used for human quote advice).
    Handles [NEEDS_HUMAN_QUOTE] signal by creating a quote request and sending
    a holding reply to the customer.
    """
    try:
        import threading as _th2
        from datetime import datetime, timezone as _tz2, timedelta as _td2
        _cs2 = _get_cs()

        convo = _cs2.get_conversation(None, conv_id)
        if convo is None:
            return
        convo_d = convo.to_dict() if hasattr(convo, "to_dict") else (convo if isinstance(convo, dict) else {})
        if not convo_d.get("aiEnabled", True):
            return

        history = []
        _conv_has_photos = bool(images)  # photos passed directly to this call
        for m in convo_d.get("messages", []):
            t   = m.get("text", "") if isinstance(m, dict) else getattr(m, "text", "")
            d   = m.get("direction", "") if isinstance(m, dict) else getattr(m, "direction", "")
            att = m.get("attachments") if isinstance(m, dict) else getattr(m, "attachments", None)
            if att:  # any stored media in conversation history = photos were sent
                _conv_has_photos = True
            if t:
                history.append({"role": "user" if d == "inbound" else "assistant", "content": t})

        goal_cfg = _load_goal_config()

        # ── Pending human-review check (text messages only) ──────────────────
        # If a quote request is already waiting for human input on this conversation,
        # append any new customer text to it and skip AI — human will see the update.
        if not images:
            _pending_qrs = _load_quote_requests()
            _pending_for_conv = next(
                (q for q in _pending_qrs
                 if q.get("conversationId") == conv_id and q.get("status") == "pending"),
                None,
            )
            if _pending_for_conv and msg_text and msg_text != "[Media]":
                _existing_ctx = (_pending_for_conv.get("customerMessage") or "").strip()
                _pending_for_conv["customerMessage"] = (
                    _existing_ctx + "\n\n" + msg_text if _existing_ctx else msg_text
                )
                _save_quote_requests(_pending_qrs)
                logger.info(
                    "_auto_draft: updated pending quote request %s with new customer text",
                    _pending_for_conv["id"],
                )
                return

        # ── Active media hold check ───────────────────────────────────────────
        # If photos were received in the last 30 seconds, a scheduled placeholder
        # message exists with status="scheduled". Any text the customer sends in
        # that window (e.g. their postcode) should be collected silently — the
        # _fire_media_hold thread already picks it up. Do NOT send an AI reply.
        if not images:
            _all_conv_msgs = convo_d.get("messages", [])
            _hold_active = any(
                (m.get("text") if isinstance(m, dict) else getattr(m, "text", "")) == "[media received — awaiting review]"
                and (m.get("status") if isinstance(m, dict) else getattr(m, "status", "")) == "scheduled"
                for m in _all_conv_msgs
            )
            if _hold_active and msg_text and msg_text != "[Media]":
                logger.info(
                    "_auto_draft: media hold active for %s — collecting '%s' silently",
                    conv_id, msg_text[:60],
                )
                return

        # ── Media path: customer sent photos/videos ───────────────────────────
        # Skip AI entirely. After 30 s, collect all context then flag for human review.
        # No auto-reply is sent — humans review and action via the Quotes tab.
        # skip_media_path=True means we're replying with human advice — go straight to AI.
        if images and not skip_media_path:
            # A photo just arrived — supersede any pending (not-yet-sent) AI draft.
            # Customers routinely send context (e.g. a postcode) and then a photo a few
            # seconds later. The earlier message may have triggered a premature draft
            # (e.g. "still waiting on your photos"); the photo changes the context
            # entirely, so that scheduled draft must be cancelled rather than delivered.
            for _pend in convo_d.get("messages", []):
                _pst = (_pend.get("status") if isinstance(_pend, dict)
                        else getattr(_pend, "status", "")) or ""
                _pauth = (_pend.get("author") if isinstance(_pend, dict)
                          else getattr(_pend, "author", "")) or ""
                if _pst == "scheduled" and _pauth == "ai":
                    _pid = (_pend.get("id") if isinstance(_pend, dict)
                            else getattr(_pend, "id", None))
                    if _pid:
                        try:
                            _cs2.cancel_scheduled_message(None, conv_id, _pid)
                            logger.info(
                                "_auto_draft: photo arrived for %s — cancelled pending AI draft %s",
                                conv_id, _pid,
                            )
                        except Exception:
                            pass
            _MEDIA_DELAY   = 30
            _media_send_at = datetime.now(_tz2.utc) + _td2(seconds=_MEDIA_DELAY)
            _placeholder_rec = _cs2.record_message(
                None, conv_id,
                text="[media received — awaiting review]", author="system",
                direction="outbound",
                via=chan, status="scheduled",
                scheduled_send_at=_media_send_at, sent_at=None,
            )
            _media_sent_at_ts = time.time()
            _placeholder_mid  = (
                _placeholder_rec.id if hasattr(_placeholder_rec, "id")
                else (_placeholder_rec.get("id") if isinstance(_placeholder_rec, dict) else None)
            )
            _display_name     = convo_d.get("displayName") or conv_id

            def _fire_media_hold(
                cid=conv_id, _chan=chan,
                _imgs=images, _sent_ts=_media_sent_at_ts, _dname=_display_name,
                _pmid=_placeholder_mid,
            ):
                try:
                    _cs_m = _get_cs()
                    convo_m = _cs_m.get_conversation(None, cid)
                    if convo_m is None:
                        return
                    cd_m   = convo_m.to_dict() if hasattr(convo_m, "to_dict") else {}
                    msgs_m = cd_m.get("messages", [])

                    # Cancel the internal placeholder record — no message is sent to customer
                    if _pmid:
                        try:
                            _cs_m.cancel_scheduled_message(None, cid, _pmid)
                        except Exception:
                            pass

                    # Collect any text the customer sent after the media (within the hold window)
                    _extra_texts = []
                    for _m in msgs_m:
                        _m_dir = (_m.get("direction") if isinstance(_m, dict)
                                  else getattr(_m, "direction", "")) or ""
                        _m_ts  = (_m.get("timestamp") if isinstance(_m, dict)
                                  else getattr(_m, "timestamp", None))
                        _m_txt = (_m.get("text") if isinstance(_m, dict)
                                  else getattr(_m, "text", "")) or ""
                        if (_m_dir == "inbound" and _m_txt and _m_txt != "[Media]"
                                and _m_ts and _m_ts > _sent_ts):
                            _extra_texts.append(_m_txt)
                    _context_msg = " | ".join(_extra_texts) if _extra_texts else "[Media only]"

                    # Create or amend quote request now (after 30-sec wait).
                    # If more photos / text arrived during the window, amend the existing QR.
                    from uuid import uuid4 as _uuid4m
                    import re as _re_pcm
                    _all_msgs_text = " ".join(
                        (_m2.get("text") if isinstance(_m2, dict) else getattr(_m2, "text", "")) or ""
                        for _m2 in msgs_m
                    )
                    _pc_m = _re_pcm.search(r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b', _all_msgs_text, _re_pcm.IGNORECASE)
                    _extracted_pc_m = _re_pcm.sub(r'\s+', ' ', _pc_m.group(1).upper().strip()) if _pc_m else ""
                    # Collect ALL inbound images from this conversation's messages
                    _all_imgs = list(_imgs)  # start with images from this trigger call
                    for _m2 in msgs_m:
                        _m2_att = (_m2.get("attachments") if isinstance(_m2, dict) else getattr(_m2, "attachments", None)) or []
                        for _att in _m2_att:
                            if isinstance(_att, dict) and _att.get("data") and _att.get("contentType"):
                                if not any(a["data"] == _att["data"] for a in _all_imgs):
                                    _all_imgs.append(_att)
                    _new_imgs = [{"data": im["data"], "contentType": im["contentType"]} for im in _all_imgs]

                    # Owner-facing CONTEXT note for the Quotes dashboard. The AI does
                    # not interpret the photos (a human prices from them) — it just
                    # summarises the conversation context the human needs to quote.
                    _qr_transcript = "\n".join(
                        f"{'Customer' if ((_m2.get('author') if isinstance(_m2, dict) else getattr(_m2,'author','')) or '') == 'customer' else 'Us'}: "
                        f"{((_m2.get('text') if isinstance(_m2, dict) else getattr(_m2,'text','')) or '').strip()}"
                        for _m2 in msgs_m
                        if ((_m2.get('text') if isinstance(_m2, dict) else getattr(_m2,'text','')) or '').strip()
                    )
                    _vision_desc = _describe_quote_request(_new_imgs, _context_msg, _qr_transcript)

                    _qrs_now = _load_quote_requests()
                    _existing_qr = next(
                        (q for q in _qrs_now if q.get("conversationId") == cid and q.get("status") == "pending"),
                        None,
                    )
                    if _existing_qr:
                        # Amend: update description, customer message and images in place
                        _existing_qr["customerMessage"] = _context_msg
                        _existing_qr["description"] = _vision_desc
                        if _new_imgs:
                            _existing_qr["images"] = _new_imgs
                        if _extracted_pc_m:
                            _existing_qr["postcode"] = _extracted_pc_m
                        _existing_qr["updatedAt"] = datetime.now(_tz2.utc).isoformat()
                        _save_quote_requests(_qrs_now)
                        _sse_push("new_quote_request", {"id": _existing_qr["id"], "displayName": _dname})
                    else:
                        _qr_m = {
                            "id":              str(_uuid4m()),
                            "conversationId":  cid,
                            "displayName":     _dname,
                            "description":     _vision_desc,
                            "customerMessage": _context_msg,
                            "postcode":        _extracted_pc_m,
                            "images":          _new_imgs,
                            "status":          "pending",
                            "createdAt":       datetime.now(_tz2.utc).isoformat(),
                            "humanAdvice":     None,
                            "answeredAt":      None,
                        }
                        _qrs_now.insert(0, _qr_m)
                        _save_quote_requests(_qrs_now)
                        _push_bg(
                            "Photos received",
                            f"Media from {_dname} — review needed",
                            "human_input",
                        )
                        _sse_push("new_quote_request", {"id": _qr_m["id"], "displayName": _dname})
                except Exception as _ae_m:
                    logger.warning("_fire_media_hold failed for %s: %s", cid, _ae_m)

            _th2.Timer(_MEDIA_DELAY, _fire_media_hold).start()
            return

        customer_msg = msg_text
        # When replying after human advice, remind AI that photos were already received
        if images and skip_media_path:
            _media_parts = []
            for _img in images:
                _ct = _img.get("contentType", "")
                if _ct.startswith("video/"):
                    _media_parts.append("a video")
                elif _ct.startswith("image/"):
                    _media_parts.append("a photo")
                else:
                    _media_parts.append("a media file")
            customer_msg = (
                msg_text
                + f"\n\n[SYSTEM NOTE — DO NOT REPEAT TO CUSTOMER: "
                f"The customer already sent {', '.join(_media_parts)} of the area. "
                f"Do NOT ask them for photos or more details about the area — "
                f"give them their quote now using your pricing assessment above.]"
            )

        # ── Checkatrade lead seeding ──────────────────────────────────────────
        # If this conversation began as a Checkatrade enquiry, inject the known
        # customer details so the AI greets them by name and never re-asks for
        # postcode / email / job type.
        try:
            _ca_lead = _load_checkatrade_leads().get(conv_id)
            if _ca_lead:
                _ca_block = _checkatrade_lead_context_block(_ca_lead)
                extra_context = (_ca_block + "\n\n" + extra_context) if extra_context else _ca_block
        except Exception:
            pass

        draft = _generate_kb_reply(
            customer_message=customer_msg,
            conversation_history=history or None,
            goal_config=goal_cfg,
            extra_context=extra_context,
            has_photos=_conv_has_photos,
        )
        # Build a full raw-conversation text blob so the calendar backstop can find a
        # postcode the customer gave anywhere earlier (even in messages dropped by the
        # history filter), letting it reliably re-trigger a Friday/weekday slot search.
        _raw_convo_text = " ".join(
            ((m.get("text") if isinstance(m, dict) else getattr(m, "text", "")) or "")
            for m in convo_d.get("messages", [])
        )
        draft = _enforce_calendar_token(draft, msg_text, history or [], goal_cfg,
                                        extra_search_text=_raw_convo_text)
        draft = _resolve_calendar_signals(draft, msg_text, history or [], goal_cfg, has_photos=_conv_has_photos)

        # Drafts are only allowed to end up empty when a deliberate silence branch
        # fires (coverage gap or human-quote). Track that so an accidentally empty
        # draft never leaves the customer with no reply at all.
        _intentional_silence = False

        # ── Detect COVERAGE_GAP signal ───────────────────────────────────────
        # The only engineers who cover this area are unticked or have no calendar
        # linked. We must NOT invent a booking and must NOT send the customer any
        # reply — stay silent and raise a human-facing alert until someone acts.
        cov_match = _COVERAGE_TOKEN_RE.search(draft)
        if cov_match:
            _cov = _parse_token_attrs(cov_match.group(1))
            from uuid import uuid4 as _uuid4c
            _disp = convo_d.get("displayName") or conv_id
            _alerts = _load_coverage_alerts()
            _existing = next(
                (c for c in _alerts
                 if c.get("conversationId") == conv_id and c.get("status") == "pending"),
                None,
            )
            if _existing:
                _existing["postcode"] = _cov.get("postcode", "") or _existing.get("postcode", "")
                _existing["service"]  = _cov.get("service", "")  or _existing.get("service", "")
                _existing["blockedEngineers"] = _cov.get("engineers", "")
                _existing["customerMessage"]  = msg_text
                _existing["updatedAt"] = datetime.now(_tz2.utc).isoformat()
                _save_coverage_alerts(_alerts)
                _alert_id = _existing["id"]
            else:
                _alert = {
                    "id":               str(_uuid4c()),
                    "conversationId":   conv_id,
                    "displayName":      _disp,
                    "postcode":         _cov.get("postcode", ""),
                    "service":          _cov.get("service", ""),
                    "blockedEngineers": _cov.get("engineers", ""),
                    "customerMessage":  msg_text,
                    "status":           "pending",
                    "createdAt":        datetime.now(_tz2.utc).isoformat(),
                }
                _alerts.insert(0, _alert)
                _save_coverage_alerts(_alerts)
                _push_bg("Coverage gap",
                         f"No bookable engineer for {_disp} ({_cov.get('postcode','')})",
                         "human_input")
                _alert_id = _alert["id"]
            _sse_push("new_coverage_alert", {"id": _alert_id, "displayName": _disp})
            logger.info("_auto_draft: coverage gap for %s (%s) — staying silent",
                        conv_id, _cov.get("postcode", ""))
            draft = ""
            _intentional_silence = True

        # ── Detect NEEDS_HUMAN_ATTENTION signal ──────────────────────────────
        # The AI hit something it must NOT handle itself — e.g. the customer asked
        # "are you an AI?", or asked something genuinely personal / about a specific
        # employee's experience. We send the customer NOTHING and raise a human-
        # facing attention alert so a real person can step in.
        attn_match = _ATTENTION_TOKEN_RE.search(draft)
        if attn_match:
            _reason = (attn_match.group(1) or "").strip() or "The AI needs a human to step in."
            from uuid import uuid4 as _uuid4a
            _disp_a = convo_d.get("displayName") or conv_id
            _attn_alerts = _load_attention_alerts()
            _existing_a = next(
                (c for c in _attn_alerts
                 if c.get("conversationId") == conv_id and c.get("status") == "pending"),
                None,
            )
            if _existing_a:
                _existing_a["reason"]          = _reason
                _existing_a["customerMessage"] = msg_text
                _existing_a["updatedAt"]       = datetime.now(_tz2.utc).isoformat()
                _save_attention_alerts(_attn_alerts)
                _attn_id = _existing_a["id"]
            else:
                _attn = {
                    "id":              str(_uuid4a()),
                    "conversationId":  conv_id,
                    "displayName":     _disp_a,
                    "reason":          _reason,
                    "customerMessage": msg_text,
                    "status":          "pending",
                    "createdAt":       datetime.now(_tz2.utc).isoformat(),
                }
                _attn_alerts.insert(0, _attn)
                _save_attention_alerts(_attn_alerts)
                _push_bg("Needs your attention",
                         f"{_disp_a}: {_reason[:120]}",
                         "human_input")
                _attn_id = _attn["id"]
            _sse_push("new_attention_alert", {"id": _attn_id, "displayName": _disp_a})
            logger.info("_auto_draft: NEEDS_HUMAN_ATTENTION for %s — staying silent (%s)",
                        conv_id, _reason[:80])
            draft = ""
            _intentional_silence = True

        # ── Detect NEEDS_HUMAN_QUOTE signal ──────────────────────────────────
        quote_match = _QUOTE_TOKEN_RE.search(draft)
        if quote_match:
            description = quote_match.group(1).strip()
            from uuid import uuid4 as _uuid4
            import re as _re_pc
            # Search ALL raw messages (not filtered history) for the postcode.
            # Customers often send postcode in photo captions or early text messages.
            _raw_msgs = convo_d.get("messages", [])
            _all_texts = " ".join(
                ((_m.get("text") if isinstance(_m, dict) else getattr(_m, "text", "")) or "")
                for _m in _raw_msgs
            ) + " " + (msg_text or "")
            _PC_RE = r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2})\b'
            _pc_match = _re_pc.search(_PC_RE, _all_texts, _re_pc.IGNORECASE)
            _extracted_postcode = _re_pc.sub(r'\s+', ' ', _pc_match.group(1).upper().strip()) if _pc_match else ""
            qr = {
                "id":              str(_uuid4()),
                "conversationId":  conv_id,
                "displayName":     convo_d.get("displayName") or conv_id,
                "description":     description,
                "customerMessage": msg_text,
                "postcode":        _extracted_postcode,
                "images": [{"data": img["data"], "contentType": img["contentType"]}
                           for img in (images or [])],
                "status":      "pending",
                "createdAt":   datetime.now(_tz2.utc).isoformat(),
                "humanAdvice": None,
                "answeredAt":  None,
            }
            qrs = _load_quote_requests()
            qrs.insert(0, qr)
            _save_quote_requests(qrs)
            _push_bg("Quote needed", f"Custom quote request from {qr['displayName']}", "human_input")
            _sse_push("new_quote_request", {"id": qr["id"], "displayName": qr["displayName"]})
            logger.info("_auto_draft: created quote request %s for %s", qr["id"], conv_id)
            # Stay SILENT — never send a holding "I'll be back with a quote" message.
            # The customer receives no reply until a human submits the real quote via
            # the Quotes tab, which re-triggers _auto_draft with the actual pricing.
            draft = ""
            _intentional_silence = True

        # ── Handle CALENDAR_BOOK_NEEDED in live WhatsApp path ────────────────
        # Extract booking details from conversation and create the calendar event.
        if _CAL_BOOK_TOKEN_RE.search(draft):
            try:
                _book_history = list(history or []) + [{"role": "user", "content": msg_text}]
                # Recover any explicit job duration from the owner's stored quote
                # advice (it is deliberately absent from the customer-facing chat).
                _explicit_dur = None
                try:
                    from scheduler.ai_scheduling_agent import parse_duration_mins as _pdm
                    # _load_quote_requests() is newest-first, so the first answered
                    # match for this conversation is the most recent quote.
                    for _q in _load_quote_requests():
                        if (_q.get("conversationId") == conv_id
                                and _q.get("status") == "answered"
                                and _q.get("humanAdvice")):
                            _d = _pdm(_q["humanAdvice"])
                            if _d:
                                _explicit_dur = _d
                                break
                except Exception:
                    _explicit_dur = None
                _booking_res  = _extract_and_create_booking(
                    _book_history, draft, explicit_duration_mins=_explicit_dur,
                    customer_phone=conv_id)
                if _booking_res.get("ok"):
                    logger.info("_auto_draft: calendar event created — %s", _booking_res.get("summary"))
                    _push_bg("Booking confirmed", "A new job has been added to your calendar.", "booking_complete")
                else:
                    logger.warning("_auto_draft: booking failed — %s", _booking_res.get("error"))
            except Exception as _bk_exc:
                logger.warning("_auto_draft: booking exception — %s", _bk_exc)

        # ── Strip remaining signal tokens ─────────────────────────────────────
        draft = _CAL_TOKEN_RE.sub("", draft).strip()
        draft = draft.replace("[NEEDS_HUMAN_REVIEW]", "").strip()
        draft = _CAL_BOOK_TOKEN_RE.sub("", draft).strip()
        draft = _ATTENTION_TOKEN_RE.sub("", draft).strip()

        # Last-resort guard: if the draft is empty but no deliberate-silence branch
        # fired, something upstream (calendar re-run, token stripping, an AI error)
        # swallowed the reply. The customer is still owed an answer — send a safe
        # holding reply rather than leaving them with total silence.
        if not draft and not _intentional_silence:
            logger.warning("_auto_draft: empty draft with no intentional-silence signal for %s — using safe fallback", conv_id)
            draft = _SAFE_FALLBACK_REPLY

        if draft:
            # ── Atomic cancel-stale + record (per-conversation lock) ──────────
            # Serialise this whole section so concurrent _auto_draft threads for
            # the same customer turn can't each create a scheduled draft (the
            # double-send bug). Inside the lock we re-fetch the LATEST messages so
            # we cancel every still-scheduled draft (including one another thread
            # just created) before recording ours — last writer wins, exactly one
            # reply goes out.
            with _draft_lock(conv_id):
                try:
                    _fresh = _cs2.get_conversation(None, conv_id)
                    _fresh_d = (_fresh.to_dict() if hasattr(_fresh, "to_dict")
                                else (_fresh if isinstance(_fresh, dict) else {})) or {}
                except Exception:
                    _fresh_d = convo_d
                for _old_m in _fresh_d.get("messages", []):
                    _old_st = (_old_m.get("status") if isinstance(_old_m, dict)
                               else getattr(_old_m, "status", "")) or ""
                    if _old_st == "scheduled":
                        _old_id = (_old_m.get("id") if isinstance(_old_m, dict)
                                   else getattr(_old_m, "id", None))
                        if _old_id:
                            try:
                                _cs2.cancel_scheduled_message(None, conv_id, _old_id)
                                logger.info("_auto_draft: cancelled stale scheduled msg %s", _old_id)
                            except Exception:
                                pass

                # Human-advice replies (Quotes tab) send INSTANTLY — a human has already
                # reviewed and submitted the quote, so there is nothing left to wait for.
                # Normal AI drafts keep the review delay so an operator can intercept.
                if skip_media_path:
                    _SEND_DELAY = 0
                else:
                    _SEND_DELAY = 120 + (60 if _seems_unfinished(msg_text) else 0)
                send_at = datetime.now(_tz2.utc) + _td2(seconds=_SEND_DELAY)
                rec = _cs2.record_message(
                    None, conv_id,
                    text=draft, author="ai", direction="outbound",
                    via=chan, status="scheduled",
                    scheduled_send_at=send_at, sent_at=None,
                )
                logger.info("Auto-draft stored for %s (send at %s)", conv_id, send_at.isoformat())

            draft_id   = rec.id if hasattr(rec, "id") else (rec.get("id") if isinstance(rec, dict) else None)
            draft_text = draft

            def _fire_auto_send(cid=conv_id, mid=draft_id, body=draft_text, _chan=chan):
                try:
                    _cs3 = _get_cs()
                    # Atomically claim the message: cancel_scheduled_message returns the message
                    # only if WE changed its status from scheduled→cancelled.  It returns None
                    # if the message was already handled (sent by Send Now, or already cancelled).
                    # This prevents double-sends without any further status checks.
                    _claim = _cs3.cancel_scheduled_message(None, cid, mid)
                    if _claim is None:
                        logger.info("Auto-send skipped — message already handled: %s/%s", mid, cid)
                        return

                    # Cross-instance dedup safety net: the in-process _draft_lock can't
                    # serialise two Autoscale instances handling the same turn, so each
                    # could end up with its own scheduled draft. Before sending, skip if
                    # an identical outbound was already sent very recently (another
                    # instance won the race). Exact-text + short window keeps this safe
                    # given the "vary your phrasing" rule.
                    try:
                        _fresh_c = _cs3.get_conversation(None, cid)
                        _fresh_cd = (_fresh_c.to_dict() if hasattr(_fresh_c, "to_dict")
                                     else (_fresh_c if isinstance(_fresh_c, dict) else {})) or {}
                        _now_dt = datetime.now(_tz2.utc)
                        for _pm in _fresh_cd.get("messages", []):
                            if not isinstance(_pm, dict):
                                continue
                            if _pm.get("id") == mid:
                                continue
                            if (_pm.get("author") == "ai"
                                    and _pm.get("status") == "sent"
                                    and (_pm.get("text") or "").strip() == (body or "").strip()):
                                _st = _pm.get("sentAt") or _pm.get("timestamp") or ""
                                try:
                                    _st_dt = datetime.fromisoformat(_st.replace("Z", "+00:00"))
                                    if _st_dt.tzinfo is None:
                                        _st_dt = _st_dt.replace(tzinfo=_tz2.utc)
                                    if (_now_dt - _st_dt).total_seconds() <= 120:
                                        logger.info("Auto-send skipped — identical reply already sent recently for %s", cid)
                                        return
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    s2    = _load_twilio_settings()
                    acct2 = s2.get("accountSid", "").strip()
                    tok2  = s2.get("authToken",  "").strip()
                    twilio_sid2, tw_status2, tw_err2 = None, "sent", None
                    if acct2 and tok2:
                        try:
                            from twilio.rest import Client as _TC2
                            tc2    = _TC2(acct2, tok2)
                            phone2 = "+" + cid.lstrip("+") if not cid.startswith("+") else cid
                            to_wa2 = f"whatsapp:{phone2}"
                            msid2  = s2.get("messagingServiceSid", "").strip()
                            fnum2  = s2.get("whatsappFrom", "").strip()
                            kw2: Dict[str, Any] = {"body": body, "to": to_wa2}
                            if msid2:
                                kw2["messaging_service_sid"] = msid2
                            elif fnum2:
                                kw2["from_"] = fnum2 if fnum2.startswith("whatsapp:") else f"whatsapp:{fnum2}"
                            cb2 = os.getenv("REPLIT_DEV_DOMAIN", "")
                            if cb2:
                                kw2["status_callback"] = f"https://{cb2}/api/twilio/status-callback"
                            sent2 = tc2.messages.create(**kw2)
                            twilio_sid2 = sent2.sid
                            logger.info("Auto-send delivered %s to %s", twilio_sid2, to_wa2)
                        except Exception as _te:
                            tw_status2, tw_err2 = "failed", str(_te)
                            logger.warning("Auto-send Twilio error: %s", _te)

                    now2 = datetime.now(_tz2.utc)
                    _cs3.record_message(
                        None, cid,
                        text=body, author="ai", direction="outbound",
                        via=_chan, status=tw_status2,
                        transport_sid=twilio_sid2,
                        sent_at=now2 if tw_status2 == "sent" else None,
                        error=tw_err2,
                    )
                except Exception as _ae:
                    logger.warning("_fire_auto_send failed for %s: %s", cid, _ae)

            _th2.Timer(_SEND_DELAY, _fire_auto_send).start()
    except Exception as _e:
        logger.warning("_auto_draft failed for %s: %s", conv_id, _e)


_seen_sids: set = set()
_seen_sids_lock = __import__("threading").Lock()

_UNFINISHED_RE = __import__("re").compile(
    r'\b(also|one more|another|and one|ps\b|p\.s\.|btw|by the way|oh and|and also|'
    r'just one|additionally|quick question|quick one|one thing|while i(\'m| am)|'
    r'meant to ask|forgot to|one more thing)\b|'
    r'(\.\.\.|…)\s*$',
    __import__("re").IGNORECASE,
)

def _seems_unfinished(text: str) -> bool:
    """Return True if the customer message suggests more content is coming."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("...") or t.endswith("…"):
        return True
    if len(t) < 20 and not t.endswith("?"):
        return True
    return bool(_UNFINISHED_RE.search(t))


def _store_incoming(channel: str):
    """Shared logic: store an incoming Twilio message into the inbox and conversation store."""
    from_raw = request.form.get("From", "")
    body     = request.form.get("Body", "")
    sid      = request.form.get("MessageSid", "")

    # Echo filter — Twilio sometimes reflects our OWN outbound messages back to the webhook.
    # If the From number matches our configured WhatsApp/SMS sender, this is an outbound echo;
    # storing it would create a duplicate customer-side bubble with wrong direction.
    try:
        _ts_echo = _load_twilio_settings()
        _our_wa   = re.sub(r"\s+", "", (_ts_echo.get("whatsappFrom") or "")).lstrip("whatsapp:")
        _our_sms  = re.sub(r"\s+", "", (_ts_echo.get("smsFrom", _ts_echo.get("whatsappFrom", "")) or ""))
        _from_num = re.sub(r"\s+", "", from_raw.split(":")[-1] if ":" in from_raw else from_raw)
        if _from_num and ((_our_wa and _from_num == _our_wa) or (_our_sms and _from_num == _our_sms)):
            logger.info("_store_incoming: echo suppressed — From=%s matches our sender", from_raw)
            return '<Response></Response>', 200, {"Content-Type": "text/xml"}
    except Exception:
        pass  # never block a real message due to echo-check failure

    # Deduplicate — Twilio sometimes delivers the same webhook twice
    if sid:
        with _seen_sids_lock:
            if sid in _seen_sids:
                logger.info("_store_incoming: duplicate MessageSid %s — skipping", sid)
                return '<Response></Response>', 200, {"Content-Type": "text/xml"}
            _seen_sids.add(sid)
            if len(_seen_sids) > 2000:
                # Trim oldest entries (sets are unordered so just clear half)
                to_remove = list(_seen_sids)[:1000]
                for s in to_remove:
                    _seen_sids.discard(s)
    num_media = int(request.form.get("NumMedia", 0))
    entry = {
        "sid":      sid,
        "from":     from_raw,
        "to":       request.form.get("To", ""),
        "body":     body,
        "numMedia": num_media,
        "channel":  channel,
        "media":    [request.form.get(f"MediaUrl{i}", "") for i in range(num_media)],
        "timestamp": time.time(),
    }
    with _inbox_lock:
        _inbox_messages.insert(0, entry)
        del _inbox_messages[100:]

    # Also write into the conversation store so the Messages tab shows the reply
    phone = ""
    text  = ""
    try:
        _cs = _get_cs()
        from datetime import datetime, timezone as _tz
        # Strip channel prefix (e.g. "whatsapp:+447700900000" → "+447700900000")
        phone = (from_raw.split(":")[-1] if ":" in from_raw else from_raw).strip()
        # Ensure leading + is present and no spaces in the number
        phone = re.sub(r"\s+", "", phone)
        if phone and not phone.startswith("+"):
            phone = "+" + phone
        text  = body or ("[Media]" if num_media else "")
        profile_name = request.form.get("ProfileName") or None
        # ── Download attached media from Twilio (authenticated) ───────────────
        images = []
        if num_media > 0:
            _ts2 = _load_twilio_settings()
            _sid2 = _ts2.get("accountSid", "").strip()
            _tok2 = _ts2.get("authToken",  "").strip()
            for _i in range(num_media):
                _murl = request.form.get(f"MediaUrl{_i}", "")
                _mct  = request.form.get(f"MediaContentType{_i}", "image/jpeg")
                if _murl and _sid2 and _tok2:
                    _bytes, _ct = _download_twilio_media(_murl, _sid2, _tok2)
                    if _bytes:
                        images.append({
                            "data":        base64.b64encode(_bytes).decode(),
                            "contentType": _ct or _mct,
                            "savedAt":     time.time(),
                        })
                        logger.info("_store_incoming: saved media %d bytes (%s)", len(_bytes), _ct)
        if phone and text:
            _cs.record_message(
                None, phone,
                text=text, author="customer", direction="inbound",
                via=channel, transport_sid=sid, status="received",
                sent_at=datetime.now(_tz.utc),
                profile_name=profile_name,
                increment_unread=True,
                attachments=images if images else None,
            )
    except Exception as _exc:
        logger.warning("_store_incoming: failed to write to conversation_store: %s", _exc)
        images = []

    # Push notification — new customer message
    if text:
        sender = phone or from_raw
        preview = text[:80] + ("…" if len(text) > 80 else "")
        _push_bg("New message", f"{sender}: {preview}", "customer_message")
        # Real-time SSE push to any open browser tab
        _sse_push("new_message", {"conversationId": phone, "from": phone, "preview": preview})

    # Fire AI reply in background — delay extended automatically if message seems unfinished
    if phone and (text or images):
        __import__("threading").Thread(
            target=_auto_draft,
            args=(phone, text or "[Media]", channel),
            kwargs={"images": images or []},
            daemon=True,
        ).start()

    return '<Response></Response>', 200, {"Content-Type": "text/xml"}


@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    """Receive incoming WhatsApp messages from Twilio."""
    if request.method == "GET":
        return "PowWash WhatsApp webhook is active. Configure this URL in Twilio as a POST webhook.", 200
    return _store_incoming("whatsapp")


@app.route("/webhook/sms", methods=["GET", "POST"])
def sms_webhook():
    """Receive incoming SMS messages from Twilio."""
    if request.method == "GET":
        return "PowWash SMS webhook is active. Configure this URL in Twilio as a POST webhook.", 200
    return _store_incoming("sms")


@app.route("/api/webhook/messages", methods=["GET"])
def get_inbox_messages():
    with _inbox_lock:
        return jsonify({"messages": list(_inbox_messages)})


@app.route("/api/webhook/messages", methods=["DELETE"])
def clear_inbox_messages():
    with _inbox_lock:
        _inbox_messages.clear()
    return jsonify({"ok": True})


@app.route("/api/messages/settings", methods=["GET"])
@login_required
def wa_get_settings():
    """Combined settings endpoint used by the Messages UI."""
    ts = _load_twilio_settings()
    openai_key_set = bool(os.environ.get("OPENAI_API_KEY", ""))
    return jsonify({
        "twilio": {
            "accountSid": ts.get("accountSid", ""),
            "authTokenConfigured": bool(ts.get("authToken")),
            "whatsappFrom": ts.get("whatsappFrom", ""),
            "messagingServiceSid": ts.get("messagingServiceSid", ""),
            "sandboxMode": ts.get("sandboxMode", True),
        },
        "openAi": {
            "organizationId": "",
            "baseUrl": "",
            "apiKeyConfigured": openai_key_set,
        },
    })


@app.route("/api/settings/twilio", methods=["GET"])
def get_twilio_settings():
    s = _load_twilio_settings()
    return jsonify({
        "accountSid": s.get("accountSid", ""),
        "authTokenSet": bool(s.get("authToken")),
        "whatsappFrom": s.get("whatsappFrom", ""),
        "messagingServiceSid": s.get("messagingServiceSid", ""),
        "sandboxMode": s.get("sandboxMode", True),
        "sandboxKeyword": s.get("sandboxKeyword", ""),
        "senderName": s.get("senderName", ""),
    })


@app.route("/api/settings/twilio", methods=["POST"])
def save_twilio_settings():
    data = request.get_json(force=True) or {}
    existing = _load_twilio_settings()
    new_token = (data.get("authToken") or "").strip()
    save_data = {
        "accountSid": (data.get("accountSid") or "").strip(),
        "authToken": new_token if new_token else existing.get("authToken", ""),
        "whatsappFrom": (data.get("whatsappFrom") or "").strip(),
        "messagingServiceSid": (data.get("messagingServiceSid") or "").strip(),
        "sandboxMode": bool(data.get("sandboxMode")),
        "sandboxKeyword": (data.get("sandboxKeyword") or "").strip(),
        "senderName": (data.get("senderName") or "").strip(),
    }
    TWILIO_SETTINGS_PATH.write_text(json.dumps(save_data, indent=2))
    return jsonify({"ok": True})


@app.route("/api/settings/twilio/test", methods=["POST"])
def test_twilio_connection():
    try:
        s = _load_twilio_settings()
        sid = s.get("accountSid", "").strip()
        token = s.get("authToken", "").strip()
        if not sid or not token:
            return jsonify({"ok": False, "error": "Account SID and Auth Token are required. Save your credentials first."})
        from twilio.rest import Client as TwilioClient
        client = TwilioClient(sid, token)
        account = client.api.accounts(sid).fetch()
        return jsonify({"ok": True, "name": account.friendly_name, "status": account.status})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/settings/webhook/test", methods=["POST"])
@login_required
def test_webhook_reachability():
    import requests as _req, time as _time
    webhook_url = "http://127.0.0.1:5000/webhook/whatsapp"
    payload = {
        "From": "whatsapp:+447700900000",
        "To": "whatsapp:+447700900123",
        "Body": "Webhook connectivity test from PowWash AI settings",
        "MessageSid": f"SMtest{int(_time.time())}",
        "ProfileName": "Webhook Test",
        "NumMedia": "0",
        "AccountSid": "ACtest",
    }
    try:
        resp = _req.post(webhook_url, data=payload, timeout=10)
        if resp.status_code == 200:
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": f"Webhook returned HTTP {resp.status_code}: {resp.text[:200]}"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/settings/twilio/send-test", methods=["POST"])
def send_test_whatsapp():
    try:
        s = _load_twilio_settings()
        sid   = s.get("accountSid", "").strip()
        token = s.get("authToken", "").strip()
        if not sid or not token:
            return jsonify({"ok": False, "error": "No credentials saved. Save your Account SID and Auth Token first."})

        data = request.get_json(force=True) or {}
        to_raw  = (data.get("to") or "").strip()
        body    = (data.get("body") or "").strip()
        if not to_raw:
            return jsonify({"ok": False, "error": "Recipient number is required."})
        if not body:
            return jsonify({"ok": False, "error": "Message text is required."})

        # Normalise the to-number: ensure whatsapp: prefix
        to_num = to_raw if to_raw.startswith("whatsapp:") else f"whatsapp:{to_raw}"

        # Choose sender: messaging service SID or whatsapp-from number
        messaging_sid = s.get("messagingServiceSid", "").strip()
        from_num      = s.get("whatsappFrom", "").strip()

        from twilio.rest import Client as TwilioClient
        client = TwilioClient(sid, token)

        kwargs = {"body": body, "to": to_num}
        if messaging_sid:
            kwargs["messaging_service_sid"] = messaging_sid
        elif from_num:
            kwargs["from_"] = from_num if from_num.startswith("whatsapp:") else f"whatsapp:{from_num}"
        else:
            return jsonify({"ok": False, "error": "No sender configured. Set a WhatsApp Number or Messaging Service SID in Settings."})

        msg = client.messages.create(**kwargs)
        return jsonify({"ok": True, "sid": msg.sid, "status": msg.status})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@app.route("/api/settings/templates", methods=["GET"])
def get_templates():
    return jsonify({"templates": _load_templates()})


@app.route("/api/settings/templates", methods=["POST"])
def save_templates():
    data = request.get_json(force=True) or {}
    templates = data.get("templates", [])
    if not isinstance(templates, list):
        return jsonify({"error": "templates must be a list"}), 400
    TEMPLATES_PATH.write_text(json.dumps(templates, indent=2))
    return jsonify({"ok": True, "count": len(templates)})


# ─────────────────────────────────────────────────────────────────────────────
# CHECKATRADE LEAD INTAKE
# When a job comes in from Checkatrade (via the external scraper webhook, or the
# admin test panel), seed a conversation with the customer's known details
# (name / postcode / email / job) so the AI never re-asks for them, pick the most
# relevant approved WhatsApp template, and send the opening message immediately.
# Gated by an activate/deactivate toggle (default OFF). Fully testable via dry-run
# (route preview) and live test sends from the Settings tab.
# ─────────────────────────────────────────────────────────────────────────────

_checkatrade_lock = threading.Lock()


def _load_checkatrade_settings() -> Dict[str, Any]:
    if CHECKATRADE_SETTINGS_PATH.exists():
        try:
            d = json.loads(CHECKATRADE_SETTINGS_PATH.read_text())
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {"active": False, "defaultTemplateSid": "", "autoMatch": True}


def _save_checkatrade_settings(d: Dict[str, Any]) -> None:
    CHECKATRADE_SETTINGS_PATH.write_text(json.dumps(d, indent=2))


def _load_checkatrade_leads() -> Dict[str, Any]:
    if CHECKATRADE_LEADS_PATH.exists():
        try:
            d = json.loads(CHECKATRADE_LEADS_PATH.read_text())
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _store_checkatrade_lead(conv_id: str, lead: Dict[str, Any]) -> None:
    """Persist a lead's known details keyed by conversation id (phone)."""
    with _checkatrade_lock:
        leads = _load_checkatrade_leads()
        leads[conv_id] = lead
        CHECKATRADE_LEADS_PATH.write_text(json.dumps(leads, indent=2))


def _extract_uk_postcode(text: str) -> str:
    """Best-effort UK postcode extraction from free text."""
    if not text:
        return ""
    m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b", text.upper())
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # outward code only (e.g. "SW19")
    m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", text.upper())
    return m.group(1) if m else ""


def _derive_location(address: str, postcode: str) -> str:
    """Pick a human 'location' (town/area) for template variables.

    Prefers a clean town segment from the address (one without digits, so we
    skip 'house number + street' lines), else falls back to the outward
    postcode (e.g. 'SW19'). Used to build area-specific URLs in templates, so
    the result must be URL-safe — never a street line with a house number."""
    outward = ""
    if postcode:
        m = re.match(r"^([A-Z]{1,2}\d{1,2}[A-Z]?)", postcode.upper())
        if m:
            outward = m.group(1)
    if address:
        pc_up = (postcode or "").upper().replace(" ", "")
        parts = [p.strip() for p in address.split(",") if p.strip()]
        parts = [p for p in parts if p.upper().replace(" ", "") != pc_up]
        # Prefer the last town-like segment: no digits (skips street/house no.)
        # and not just the outward postcode repeated.
        for p in reversed(parts):
            if not any(ch.isdigit() for ch in p) and p.upper().replace(" ", "") != outward:
                return p
    return outward


def _checkatrade_sendable_templates(templates: List[Dict]) -> List[Dict]:
    """Only approved WhatsApp templates can be sent. Keep legacy entries that
    predate the status field (blank status), but never auto-pick pending ones."""
    sendable = [t for t in templates
                if (t.get("twilioStatus") or "").strip().lower() in ("", "approved")]
    return sendable or templates


def _ai_pick_checkatrade_template(job_text: str,
                                  templates: List[Dict]) -> Tuple[Optional[Dict], str]:
    """Use Claude to read the lead's job and choose the best-fitting template.

    The model sees the *live* list of templates, so any template the owner adds
    later (gutter, pressure washing, a neutral catch-all, …) is automatically
    considered without any code change. Returns (template_or_None, reason).
    Returns (None, …) when the AI is unsure or errors — the caller then falls
    back to keyword matching / the default template."""
    if not job_text or not templates:
        return None, ""
    menu_lines = []
    for i, t in enumerate(templates):
        name = (t.get("name") or t.get("sid") or f"Template {i + 1}").strip()
        body = re.sub(r"\s+", " ", (t.get("body") or "")).strip()
        if len(body) > 180:
            body = body[:180] + "…"
        menu_lines.append(f'{i}: "{name}" — {body or "(no body)"}')
    menu = "\n".join(menu_lines)
    system = (
        "You route incoming exterior-cleaning leads to the single most "
        "appropriate WhatsApp opening template. You are given a numbered list of "
        "templates and a customer's enquiry. Pick the template whose purpose best "
        "matches the job (e.g. a gutter-clearing enquiry -> a gutter template; a "
        "driveway, patio, render or roof enquiry -> a pressure-washing template). "
        "If a general/neutral template fits the lead better than any specific one, "
        "choose that. Reply with ONLY a compact JSON object of the form "
        '{"index": <number or -1>, "reason": "<short justification>"}. '
        "Use -1 only if none of the templates could reasonably be sent."
    )
    user = (f"TEMPLATES:\n{menu}\n\nCUSTOMER ENQUIRY:\n{job_text.strip()}\n\n"
            "Which template index best fits?")
    try:
        raw = _call_ai(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            max_tokens=150, model=CLAUDE_FAST_MODEL,
        )
        m = re.search(r"\{.*\}", raw, re.S)
        obj = json.loads(m.group(0)) if m else {}
        idx = int(obj.get("index", -1))
        reason = str(obj.get("reason", "")).strip()
        if 0 <= idx < len(templates):
            return templates[idx], reason
        return None, reason
    except Exception as e:  # noqa: BLE001
        logger.warning("Checkatrade AI template pick failed: %s", e)
        return None, ""


def _choose_checkatrade_template(job_text: str,
                                 settings: Dict[str, Any],
                                 templates: List[Dict]) -> Dict[str, Any]:
    """Choose the best approved template for a job and report how it was chosen.

    Order of preference:
      1. AI assessment (if `aiMatch` is on) — reads the lead, picks from the
         live template list.
      2. Keyword auto-match (if `autoMatch` is on) — scores template name words
         against the job text.
      3. The configured default template, then the first available template.

    Returns {"template": tpl|None, "method": str, "reason": str}."""
    if not templates:
        return {"template": None, "method": "none", "reason": ""}
    templates = _checkatrade_sendable_templates(templates)
    default_sid = (settings.get("defaultTemplateSid") or "").strip()
    default_tpl = next((t for t in templates if t.get("sid") == default_sid), None)

    if settings.get("aiMatch", True) and job_text:
        tpl, reason = _ai_pick_checkatrade_template(job_text, templates)
        if tpl:
            return {"template": tpl, "method": "ai", "reason": reason}

    if settings.get("autoMatch", True) and job_text:
        jt = job_text.lower()
        _generic = {"template", "templates", "cleaning", "clean", "service",
                    "services", "the", "and", "powwash", "pow", "wash"}
        best, best_score = None, 0
        for t in templates:
            words = [w for w in re.findall(r"[a-z]+", (t.get("name") or "").lower())
                     if w not in _generic and len(w) > 2]
            score = sum(1 for w in words if w in jt)
            if score > best_score:
                best, best_score = t, score
        if best and best_score > 0:
            return {"template": best, "method": "keyword", "reason": ""}

    if default_tpl:
        return {"template": default_tpl, "method": "default", "reason": ""}
    return {"template": templates[0] if templates else None,
            "method": "fallback", "reason": ""}


def _select_checkatrade_template(job_text: str,
                                 settings: Dict[str, Any],
                                 templates: List[Dict]) -> Optional[Dict]:
    """Backward-compatible helper returning just the chosen template."""
    return _choose_checkatrade_template(job_text, settings, templates)["template"]


def _resolve_lead_var(name: str, lead: Dict[str, Any]) -> str:
    n = (name or "").lower()
    full = (lead.get("customerName") or "").strip()
    first = full.split(" ")[0] if full else ""
    if "first" in n or n in ("name", "customer_name", "customername"):
        return first or full
    if "name" in n:
        return first or full
    if "location" in n or "town" in n or "area" in n or "city" in n:
        return lead.get("location") or lead.get("postcode") or ""
    if "postcode" in n or "post_code" in n or "postal" in n:
        return lead.get("postcode") or ""
    if "email" in n:
        return lead.get("email") or ""
    if "phone" in n or "number" in n:
        return lead.get("phone") or ""
    if "job" in n or "service" in n or "work" in n:
        return lead.get("jobTitle") or ""
    return ""


def _build_template_variables(template: Dict, lead: Dict[str, Any]) -> Dict[str, str]:
    """Build Twilio content_variables (positional dict) from a template's varMap."""
    var_map = template.get("varMap") or {}
    out: Dict[str, str] = {}
    for pos, var_name in var_map.items():
        out[str(pos)] = _resolve_lead_var(var_name, lead)
    return out


def _render_template_body(template: Dict, content_vars: Dict[str, str]) -> str:
    """Render a template body for preview/inbox display using its varMap + values."""
    body = template.get("body") or ""
    var_map = template.get("varMap") or {}
    for pos, var_name in var_map.items():
        val = content_vars.get(str(pos), "")
        body = body.replace("{{" + str(var_name) + "}}", val)
        body = body.replace("{{" + str(pos) + "}}", val)
    return body


def _checkatrade_lead_context_block(lead: Dict[str, Any]) -> str:
    parts = ["KNOWN CUSTOMER DETAILS (from a Checkatrade enquiry — already on file. "
             "Do NOT ask the customer for any of these again):"]
    if lead.get("customerName"):
        parts.append(f"- Name: {lead['customerName']}")
    if lead.get("postcode"):
        parts.append(f"- Postcode: {lead['postcode']}")
    if lead.get("email"):
        parts.append(f"- Email: {lead['email']}")
    if lead.get("phone"):
        parts.append(f"- Phone: {lead['phone']}")
    if lead.get("jobTitle"):
        parts.append(f"- Job type: {lead['jobTitle']}")
    if lead.get("jobDescription"):
        parts.append(f"- Their enquiry: {lead['jobDescription']}")
    parts.append("Use the postcode above for any availability/booking checks without "
                 "re-asking, and greet them by first name.")
    return "\n".join(parts)


def _send_whatsapp_template(phone: str, content_sid: str,
                            content_vars: Dict[str, str], body: str,
                            display_name: str = "") -> Dict[str, Any]:
    """Send an approved WhatsApp template to a customer and record it on the
    conversation. Mirrors the /api/messages/outbound send path."""
    s = _load_twilio_settings()
    account_sid = s.get("accountSid", "").strip()
    auth_token = s.get("authToken", "").strip()
    twilio_sid, twilio_status, twilio_error = None, "sent", None

    if account_sid and auth_token:
        try:
            from twilio.rest import Client as _TwilioClient
            tc = _TwilioClient(account_sid, auth_token)
            to_num = f"whatsapp:{phone}"
            msid = s.get("messagingServiceSid", "").strip()
            fnum = s.get("whatsappFrom", "").strip()
            if content_sid:
                kwargs = {"content_sid": content_sid, "to": to_num}
                if content_vars:
                    kwargs["content_variables"] = json.dumps(content_vars)
            else:
                kwargs = {"body": body, "to": to_num}
            if msid:
                kwargs["messaging_service_sid"] = msid
            elif fnum:
                kwargs["from_"] = fnum if fnum.startswith("whatsapp:") else f"whatsapp:{fnum}"
            else:
                return {"ok": False, "status": "failed",
                        "error": "No WhatsApp sender configured — add one in Settings."}
            cb_domain = os.getenv("REPLIT_DEV_DOMAIN", "")
            if cb_domain:
                kwargs["status_callback"] = f"https://{cb_domain}/api/twilio/status-callback"
            msg = tc.messages.create(**kwargs)
            twilio_sid = msg.sid
        except Exception as exc:
            twilio_error, twilio_status = str(exc), "failed"
    else:
        twilio_status = "sent"  # store locally even without live Twilio

    try:
        from datetime import datetime as _dt, timezone as _tz
        _get_cs().record_message(
            None, phone,
            text=body, author="agent", direction="outbound",
            via="whatsapp", transport_sid=twilio_sid, status=twilio_status,
            profile_name=display_name or None,
            sent_at=_dt.now(_tz.utc) if twilio_status == "sent" else None,
            error=twilio_error,
        )
    except Exception:
        pass

    res = {"ok": twilio_status == "sent", "status": twilio_status}
    if twilio_sid:
        res["sid"] = twilio_sid
    if twilio_error:
        res["error"] = twilio_error
    return res


def _process_checkatrade_lead(lead_raw: Dict[str, Any], *,
                              dry_run: bool = False,
                              force: bool = False) -> Tuple[Dict[str, Any], int]:
    """Core Checkatrade intake. Returns (result, http_status).

    dry_run=True  → return the route preview only (never sends / persists).
    dry_run=False → seed the conversation and send, gated by active|force.
    """
    from datetime import datetime, timezone
    settings = _load_checkatrade_settings()
    active = bool(settings.get("active"))

    name      = (lead_raw.get("customerName") or lead_raw.get("name") or "").strip()
    email     = (lead_raw.get("email") or "").strip()
    phone_raw = (lead_raw.get("phone") or "").strip()
    postcode  = (lead_raw.get("postcode") or "").strip().upper()
    address   = (lead_raw.get("address") or "").strip()
    job_title = (lead_raw.get("jobTitle") or lead_raw.get("job") or "").strip()
    job_desc  = (lead_raw.get("jobDescription") or lead_raw.get("message") or "").strip()
    profile   = (lead_raw.get("profile") or "").strip()
    source    = (lead_raw.get("sourceUrl") or lead_raw.get("source") or "").strip()

    if not postcode and address:
        postcode = _extract_uk_postcode(address)
    if not postcode and job_desc:
        postcode = _extract_uk_postcode(job_desc)
    location = _derive_location(address, postcode)
    phone = _normalize_op_phone(phone_raw) if phone_raw else ""

    lead = {
        "customerName": name, "email": email, "phone": phone,
        "postcode": postcode, "address": address, "location": location,
        "jobTitle": job_title, "jobDescription": job_desc,
        "profile": profile, "source": source or "checkatrade",
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }

    result: Dict[str, Any] = {"ok": False, "active": active,
                              "dryRun": dry_run, "lead": lead}

    if not name and not phone:
        result["error"] = "Lead needs at least a customer name or phone number."
        return result, 400

    templates = _load_templates()
    choice = _choose_checkatrade_template(f"{job_title} {job_desc}", settings, templates)
    tpl = choice["template"]
    content_vars = _build_template_variables(tpl, lead) if tpl else {}
    rendered = _render_template_body(tpl, content_vars) if tpl else ""
    conv_id = phone or ""

    route = {
        "conversationId": conv_id,
        "displayName": name or conv_id,
        "template": {"name": tpl.get("name"), "sid": tpl.get("sid")} if tpl else None,
        "match": {"method": choice["method"], "reason": choice["reason"]},
        "contentVariables": content_vars,
        "renderedMessage": rendered,
        "leadContext": _checkatrade_lead_context_block(lead),
        "willSend": (not dry_run) and (active or force) and bool(conv_id) and bool(tpl),
    }
    result["route"] = route

    if dry_run:
        result["ok"] = True
        if not tpl:
            result["warning"] = "No message template available to match this job — add one under Approved Message Templates."
        elif not conv_id:
            result["warning"] = "No phone number supplied — a real lead must include one to message the customer."
        return result, 200

    if not (active or force):
        result["skipped"] = True
        result["reason"] = "Checkatrade intake is turned off."
        return result, 200

    if not conv_id:
        result["error"] = "A phone number is required to message the customer."
        return result, 400
    if not tpl:
        result["error"] = "No message template available — add one in Settings."
        return result, 400

    # Seed the conversation context so the AI never re-asks for these details.
    _store_checkatrade_lead(conv_id, lead)

    send = _send_whatsapp_template(phone, tpl.get("sid"), content_vars,
                                   rendered, display_name=name)
    result.update(send)
    result["conversationId"] = conv_id
    try:
        _sse_push("conversation_update", {"conversationId": conv_id})
    except Exception:
        pass
    return result, (200 if send.get("ok") else 502)


@app.route("/api/checkatrade/settings", methods=["GET"])
@login_required
def checkatrade_settings_get():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    s = _load_checkatrade_settings()
    domain = os.getenv("REPLIT_DEV_DOMAIN", "")
    return jsonify({
        "active": bool(s.get("active")),
        "defaultTemplateSid": s.get("defaultTemplateSid", ""),
        "aiMatch": bool(s.get("aiMatch", True)),
        "autoMatch": bool(s.get("autoMatch", True)),
        "webhookUrl": (f"https://{domain}/webhook/checkatrade" if domain else "/webhook/checkatrade"),
        "tokenRequired": bool(os.getenv("CHECKATRADE_WEBHOOK_TOKEN", "").strip()),
    })


@app.route("/api/checkatrade/settings", methods=["POST"])
@login_required
def checkatrade_settings_post():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True) or {}
    s = _load_checkatrade_settings()
    s["active"] = bool(data.get("active"))
    s["defaultTemplateSid"] = (data.get("defaultTemplateSid") or "").strip()
    s["aiMatch"] = bool(data.get("aiMatch", True))
    s["autoMatch"] = bool(data.get("autoMatch", True))
    _save_checkatrade_settings(s)
    return jsonify({"ok": True})


_SCRAPER_INTERNAL = os.environ.get("CHECKATRADE_SCRAPER_INTERNAL_URL", "http://127.0.0.1:8080")


@app.route("/api/checkatrade/scraper-credentials", methods=["GET"])
@login_required
def scraper_credentials_get():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    import urllib.request as _ur
    try:
        with _ur.urlopen(f"{_SCRAPER_INTERNAL}/api/checkatrade/credentials", timeout=5) as r:
            return jsonify(json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/checkatrade/scraper-credentials", methods=["POST"])
@login_required
def scraper_credentials_post():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    import urllib.request as _ur
    try:
        payload = json.dumps(request.get_json(force=True) or {}).encode()
        req = _ur.Request(
            f"{_SCRAPER_INTERNAL}/api/checkatrade/credentials",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _ur.urlopen(req, timeout=5) as r:
            return jsonify(json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/checkatrade/test-scraper-credentials", methods=["POST"])
@login_required
def test_scraper_credentials():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    import urllib.request as _ur
    try:
        payload = json.dumps(request.get_json(force=True, silent=True) or {}).encode()
        req = _ur.Request(
            f"{_SCRAPER_INTERNAL}/api/checkatrade/test-credentials",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _ur.urlopen(req, timeout=20) as r:
            return jsonify(json.loads(r.read()))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/checkatrade-tools")
@login_required
def checkatrade_tools():
    if session.get("user_role") != "admin":
        return redirect("/")
    from flask import make_response as _mkr
    resp = _mkr(render_template("checkatrade_tools.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/checkatrade/run-test", methods=["POST"])
@login_required
def checkatrade_run_test():
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    import urllib.request as _ur
    from flask import stream_with_context, Response as _Resp
    def _gen():
        try:
            req = _ur.Request(
                f"{_SCRAPER_INTERNAL}/api/checkatrade/test-scrape",
                data=b"", method="POST",
            )
            with _ur.urlopen(req, timeout=300) as r:
                while True:
                    chunk = r.read(512)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            yield f"event: testdone\ndata: {json.dumps({'error': str(e)})}\n\n".encode()
    return _Resp(
        stream_with_context(_gen()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/webhook/checkatrade", methods=["POST"])
def checkatrade_lead_webhook():
    """Production webhook hit by the external Checkatrade scraper.

    Optionally protected by a shared secret: if CHECKATRADE_WEBHOOK_TOKEN is set,
    requests must send a matching X-Checkatrade-Token header."""
    token_req = os.getenv("CHECKATRADE_WEBHOOK_TOKEN", "").strip()
    if token_req:
        sent = (request.headers.get("X-Checkatrade-Token") or "").strip()
        if sent != token_req:
            return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result, code = _process_checkatrade_lead(data, dry_run=False, force=False)
    return jsonify(result), code


@app.route("/api/checkatrade/test", methods=["POST"])
@login_required
def checkatrade_test():
    """Admin test panel: simulate a Checkatrade payload.

    dryRun=true  → preview the chosen template + route without sending.
    force=true   → actually send a test message even while the toggle is off."""
    if session.get("user_role") != "admin":
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True) or {}
    dry = bool(data.get("dryRun"))
    force = bool(data.get("force"))
    result, code = _process_checkatrade_lead(data, dry_run=dry, force=force)
    return jsonify(result), code


@app.route("/api/templates/submit-twilio", methods=["POST"])
def templates_submit_twilio():
    """
    Create a WhatsApp content template in Twilio and submit it for Meta approval.

    POST body: { "template_name": "Pressure Washing Template", "category": "UTILITY" }
    category options: UTILITY (default), MARKETING, AUTHENTICATION

    Named placeholders ({{customer_name}}) are converted to numbered ({{1}}) for Twilio.
    The SID and approval status are saved back to the stored template.
    """
    import re as _re
    import base64 as _b64
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    try:
        data     = request.get_json(force=True) or {}
        name     = (data.get("template_name") or "").strip()
        category = (data.get("category") or "UTILITY").strip().upper()
        if category not in ("UTILITY", "MARKETING", "AUTHENTICATION"):
            category = "UTILITY"
        if not name:
            return jsonify({"error": "'template_name' is required"}), 400

        templates = _load_templates()
        tmpl = next((t for t in templates if t.get("name", "").strip() == name), None)
        if tmpl is None:
            return jsonify({"error": f"Template '{name}' not found"}), 404

        raw_body = tmpl.get("body", "")
        if not raw_body:
            return jsonify({"error": "Template body is empty"}), 400

        # Convert {{named_var}} → {{N}} and build variable map
        vars_seen: list = []
        def _to_numbered(m):
            key = m.group(1).strip()
            if key not in vars_seen:
                vars_seen.append(key)
            return "{{" + str(vars_seen.index(key) + 1) + "}}"

        numbered_body = _re.sub(r"\{\{([^}]+)\}\}", _to_numbered, raw_body)
        var_map = {str(i + 1): v for i, v in enumerate(vars_seen)}
        # default sample values for Twilio (required for submission)
        variables_payload = {str(i + 1): v.replace("_", " ").title() for i, v in enumerate(vars_seen)}

        # Twilio Content API
        s           = _load_twilio_settings()
        account_sid = s.get("accountSid", "").strip()
        auth_token  = s.get("authToken", "").strip()
        if not account_sid or not auth_token:
            return jsonify({"error": "Twilio credentials not configured in Settings"}), 400

        creds = _b64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

        # 1. Create the content template
        create_payload = json.dumps({
            "friendly_name": name,
            "language": "en",
            "variables": variables_payload,
            "types": {
                "twilio/text": {"body": numbered_body}
            },
        }).encode()

        try:
            req = _urlreq.Request(
                "https://content.twilio.com/v1/Content",
                data=create_payload,
                headers=headers,
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=15) as resp:
                content_resp = json.loads(resp.read())
        except _urlerr.HTTPError as he:
            body_text = he.read().decode(errors="replace")
            return jsonify({"error": f"Twilio create failed ({he.code}): {body_text}"}), 502
        except Exception as exc:
            return jsonify({"error": f"Twilio create error: {exc}"}), 502

        content_sid = content_resp.get("sid", "")
        if not content_sid:
            return jsonify({"error": "Twilio returned no SID", "response": content_resp}), 502

        # 2. Submit for WhatsApp approval
        twilio_name = _re.sub(r"[^a-z0-9_]", "_", name.lower().strip())[:60]
        approve_payload = json.dumps({
            "name": twilio_name,
            "category": category,
        }).encode()

        approval_status = "pending"
        approval_error  = None
        try:
            req2 = _urlreq.Request(
                f"https://content.twilio.com/v1/Content/{content_sid}/ApprovalRequests/whatsapp",
                data=approve_payload,
                headers=headers,
                method="POST",
            )
            with _urlreq.urlopen(req2, timeout=15) as resp2:
                approval_resp = json.loads(resp2.read())
            approval_status = approval_resp.get("status", "pending")
        except _urlerr.HTTPError as he2:
            approval_error = he2.read().decode(errors="replace")
            approval_status = "approval_failed"
        except Exception as exc2:
            approval_error = str(exc2)
            approval_status = "approval_failed"

        # 3. Persist SID, status, varMap back to stored template
        tmpl["sid"]          = content_sid
        tmpl["twilioStatus"] = approval_status
        tmpl["varMap"]       = var_map
        TEMPLATES_PATH.write_text(json.dumps(templates, indent=2))

        return jsonify({
            "ok": True,
            "sid": content_sid,
            "status": approval_status,
            "var_map": var_map,
            "approval_error": approval_error,
        })

    except Exception as exc:
        logger.exception("templates_submit_twilio failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/templates/check-status", methods=["POST"])
def templates_check_status():
    """
    Poll Twilio for the latest approval status of a content template.
    POST body: { "sid": "HXxxx..." }
    Updates the stored template record with the latest status.
    """
    import base64 as _b64
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    try:
        data = request.get_json(force=True) or {}
        sid  = (data.get("sid") or "").strip()
        if not sid:
            return jsonify({"error": "'sid' is required"}), 400

        s           = _load_twilio_settings()
        account_sid = s.get("accountSid", "").strip()
        auth_token  = s.get("authToken", "").strip()
        if not account_sid or not auth_token:
            return jsonify({"error": "Twilio credentials not configured"}), 400

        creds   = _b64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}

        try:
            req = _urlreq.Request(
                f"https://content.twilio.com/v1/Content/{sid}/ApprovalRequests",
                headers=headers,
            )
            with _urlreq.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read())
        except _urlerr.HTTPError as he:
            body_text = he.read().decode(errors="replace")
            return jsonify({"error": f"Twilio check failed ({he.code}): {body_text}"}), 502
        except Exception as exc:
            return jsonify({"error": f"Twilio check error: {exc}"}), 502

        # Extract WhatsApp approval status
        wa = resp_data.get("whatsapp", {})
        status = wa.get("status", "pending")

        # Update stored template
        templates = _load_templates()
        for t in templates:
            if t.get("sid", "") == sid:
                t["twilioStatus"] = status
                break
        TEMPLATES_PATH.write_text(json.dumps(templates, indent=2))

        return jsonify({"ok": True, "sid": sid, "status": status, "raw": resp_data})

    except Exception as exc:
        logger.exception("templates_check_status failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/templates/send", methods=["POST"])
def templates_send():
    """
    Send a saved template with variable substitution.

    Expected JSON body:
    {
        "to":            "+447700900000",   // E.164 phone number (required)
        "template_name": "Pressure Washing Template",  // match by name (required unless template_body supplied)
        "template_body": "Hey {{customer_name}} ...",  // alternative: supply body directly
        "channel":       "whatsapp",       // "whatsapp" (default) or "sms"
        "variables": {
            "customer_name": "Sarah",      // replaces {{customer_name}} — blank is fine
            "location":      "bristol"     // replaces {{location}} — blank is fine
            // any other {{key}} pairs in the template body
        }
    }

    Response:
    {
        "ok": true,
        "rendered": "Hello Sam\\n\\nThis is Alex from ...",
        "twilio_sid": "SMxxxxxxxxx",   // null if Twilio not configured
        "signals": []
    }
    """
    import re as _re
    try:
        data     = request.get_json(force=True) or {}
        to       = (data.get("to") or "").strip()
        channel  = (data.get("channel") or "whatsapp").strip().lower()
        name     = (data.get("template_name") or "").strip()
        raw_body = (data.get("template_body") or "").strip()
        variables: Dict[str, str] = data.get("variables") or {}

        if not to:
            return jsonify({"error": "'to' (phone number) is required"}), 400
        if not to.startswith("+"):
            return jsonify({"error": "Phone must be E.164 format e.g. +447700900000"}), 400

        # Resolve template body
        if not raw_body:
            if not name:
                return jsonify({"error": "Provide 'template_name' or 'template_body'"}), 400
            tmpl = next((t for t in _load_templates() if t.get("name", "").strip() == name), None)
            if tmpl is None:
                return jsonify({"error": f"Template '{name}' not found"}), 404
            raw_body = tmpl.get("body", "")

        # Auto-inject {{user_name}} from stored sender name if not supplied
        s_cfg = _load_twilio_settings()
        sender_name = s_cfg.get("senderName", "").strip()
        if "user_name" not in variables and sender_name:
            variables = dict(variables)
            variables["user_name"] = sender_name

        # Substitute {{variable}} placeholders; missing keys → empty string
        def _replace(m):
            key = m.group(1).strip()
            return str(variables.get(key, ""))

        rendered = _re.sub(r"\{\{([^}]+)\}\}", _replace, raw_body)

        # Send via Twilio (same pattern as msgs_send_outbound)
        s           = _load_twilio_settings()
        account_sid = s.get("accountSid", "").strip()
        auth_token  = s.get("authToken", "").strip()
        twilio_sid  = None

        if account_sid and auth_token:
            from twilio.rest import Client as _TC
            tc = _TC(account_sid, auth_token)
            if channel == "whatsapp":
                to_addr = f"whatsapp:{to}"
                msid = s.get("messagingServiceSid", "").strip()
                fnum = s.get("whatsappFrom", "").strip()
                kwargs: Dict[str, Any] = {"body": rendered, "to": to_addr}
                if msid:
                    kwargs["messaging_service_sid"] = msid
                elif fnum:
                    kwargs["from_"] = fnum if fnum.startswith("whatsapp:") else f"whatsapp:{fnum}"
                else:
                    return jsonify({"error": "No WhatsApp sender configured in Settings"}), 400
            else:
                fnum = s.get("smsFrom", s.get("whatsappFrom", "")).strip()
                if not fnum:
                    return jsonify({"error": "No SMS sender configured in Settings"}), 400
                kwargs = {"body": rendered, "to": to, "from_": fnum}
            msg = tc.messages.create(**kwargs)
            twilio_sid = msg.sid
            logger.info("templates_send: sent %s to %s via %s", twilio_sid, to, channel)
        else:
            logger.info("templates_send: Twilio not configured — message not sent")

        return jsonify({"ok": True, "rendered": rendered, "twilio_sid": twilio_sid})

    except Exception as exc:
        logger.exception("templates_send failed")
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
#  CALENDAR / SCHEDULER ROUTES
# ─────────────────────────────────────────────────────────────

def _cal_client():
    from scheduler.calendar_client import (
        check_connection, list_calendars, load_config, save_config,
        find_free_slots, create_event, update_event, delete_event,
        build_hold_event, build_booking_event,
    )
    return {
        "check_connection": check_connection,
        "list_calendars": list_calendars,
        "load_config": load_config,
        "save_config": save_config,
        "find_free_slots": find_free_slots,
        "create_event": create_event,
        "update_event": update_event,
        "delete_event": delete_event,
        "build_hold_event": build_hold_event,
        "build_booking_event": build_booking_event,
    }


@app.route("/api/calendar/status", methods=["GET"])
def cal_status():
    """Check Google Calendar connection and return config."""
    try:
        c = _cal_client()
        status = c["check_connection"]()
        config = c["load_config"]()
        return jsonify({**status, "config": config})
    except Exception as exc:
        logger.warning("cal_status failed: %s", exc)
        try:
            from scheduler.calendar_client import load_config
            return jsonify({"connected": False, "reason": str(exc), "config": load_config()})
        except Exception:
            return jsonify({"connected": False, "reason": str(exc), "config": {}})


# ─────────────────────────────────────────────────────────────────────────────
# SYNC RULE — CALENDAR CONFIG ↔ SCHEDULING KNOWLEDGE
# ─────────────────────────────────────────────────────────────────────────────
# Working hours, travel buffer, and hold timeout exist in TWO places:
#   1. calendar_config.json (structured — source of truth for the scheduler)
#   2. ai_agent_config.json "instructions" (freeform text — used by the AI agent)
#
# Whenever calendar_config.json is saved, _sync_knowledge_from_cal_config()
# MUST be called to keep the two in sync.  Any future code that writes to
# calendar_config.json should also call this function, or the AI agent will
# reason from stale values.
# ─────────────────────────────────────────────────────────────────────────────

def _sync_knowledge_from_cal_config(cfg: dict) -> None:
    """
    Update the '## Scheduling Rules (Live Configuration)' section of the
    AI scheduling agent's knowledge document to match the given calendar config.
    This keeps the human-readable knowledge doc in sync with the structured config.
    """
    import re as _re
    from pathlib import Path as _Path

    agent_cfg_path = PersistentFile(_Path(__file__).parent / "scheduler" / "ai_agent_config.json")
    if not agent_cfg_path.exists():
        return

    try:
        agent_cfg = json.loads(agent_cfg_path.read_text())
    except Exception:
        return

    instructions = agent_cfg.get("instructions", "")
    if not instructions:
        return

    # ── Build replacement values from calendar config ──────────────────────
    wh          = cfg.get("workingHours", {})
    wh_start    = wh.get("start", "08:00")
    wh_end      = wh.get("end",   "17:30")
    wh_days     = wh.get("days",  [1, 2, 3, 4, 5])

    _DAY_NAMES = {0:"Sunday",1:"Monday",2:"Tuesday",3:"Wednesday",
                  4:"Thursday",5:"Friday",6:"Saturday"}
    sorted_days = sorted(wh_days)
    if sorted_days == [1, 2, 3, 4, 5]:
        days_str = "Monday–Friday"
    elif sorted_days == [1, 2, 3, 4, 5, 6]:
        days_str = "Monday–Saturday"
    elif sorted_days == [0, 1, 2, 3, 4, 5, 6]:
        days_str = "Monday–Sunday"
    else:
        days_str = ", ".join(_DAY_NAMES.get(d, str(d)) for d in sorted_days)

    buffer_mins   = cfg.get("travelBufferMinutes", 60)
    hold_mins     = cfg.get("holdTimeoutMinutes",  60)
    hold_hrs      = hold_mins / 60
    hold_str      = (f"{int(hold_hrs)} hour{'s' if hold_hrs != 1 else ''}"
                     if hold_hrs >= 1 and hold_hrs == int(hold_hrs)
                     else f"{hold_hrs:.1g} hours" if hold_hrs >= 1
                     else f"{hold_mins} mins")

    new_wh_line      = f"- Working hours: {wh_start}–{wh_end}, {days_str}."
    new_buffer_line  = f"- Travel buffer between jobs: {buffer_mins} mins."
    new_hold_line    = f"- Hold timeout (unconfirmed bookings expire): {hold_str}."

    # ── Replace only the three config-driven lines inside the section ───────
    updated = _re.sub(r"- Working hours: [^\n]+",         new_wh_line,     instructions)
    updated = _re.sub(r"- Travel buffer between jobs: [^\n]+",  new_buffer_line, updated)
    updated = _re.sub(r"- Hold timeout \([^)]+\): [^\n]+", new_hold_line,   updated)

    if updated == instructions:
        return  # nothing changed

    agent_cfg["instructions"] = updated
    agent_cfg_path.write_text(json.dumps(agent_cfg, indent=2, ensure_ascii=False))
    logger.info("Synced scheduling knowledge from calendar config: hours=%s–%s, buffer=%dm, hold=%s",
                wh_start, wh_end, buffer_mins, hold_str)


@app.route("/api/calendar/config", methods=["POST"])
def cal_save_config():
    """Save calendar configuration (working hours, format, etc.).

    NOTE: After saving, _sync_knowledge_from_cal_config() is called to keep
    the AI scheduling agent's knowledge document consistent with these values.
    See the SYNC RULE block above for details.
    """
    try:
        from scheduler.calendar_client import save_config
        data = request.get_json(force=True) or {}
        cfg  = save_config(data)
        _sync_knowledge_from_cal_config(cfg)   # keep AI knowledge in sync
        return jsonify({"ok": True, "config": cfg})
    except Exception as exc:
        logger.warning("cal_save_config failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/connect", methods=["POST"])
def cal_connect():
    """Legacy endpoint — kept for backwards compat. Returns status."""
    try:
        from scheduler.calendar_client import check_connection
        return jsonify({"ok": True, **check_connection()})
    except Exception as exc:
        logger.warning("cal_connect failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/credentials", methods=["GET", "POST"])
def cal_credentials():
    """GET: return masked credential status. POST: save client_id + client_secret."""
    from scheduler.calendar_client import load_credentials, save_credentials
    if request.method == "GET":
        creds = load_credentials()
        cid = creds.get("client_id", "") or os.environ.get("GOOGLE_CLIENT_ID", "")
        has_secret = bool(creds.get("client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET", ""))
        _host = request.host
        if _host.startswith("localhost") or _host.startswith("127."):
            _host = os.environ.get("REPLIT_DEV_DOMAIN", _host)
        return jsonify({
            "hasCredentials": bool(cid and has_secret),
            "clientIdMasked": (cid[:12] + "…" + cid[-6:]) if len(cid) > 20 else (cid or ""),
            "redirectUri": f"https://{_host}/api/calendar/oauth/callback",
        })
    # POST — save
    try:
        data = request.get_json(force=True) or {}
        client_id     = (data.get("clientId") or "").strip()
        client_secret = (data.get("clientSecret") or "").strip()
        if not client_id or not client_secret:
            return jsonify({"error": "Both clientId and clientSecret are required"}), 400
        save_credentials(client_id, client_secret)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.warning("cal_credentials POST failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/disconnect", methods=["POST"])
def cal_disconnect():
    """Remove stored OAuth tokens to disconnect Google Calendar."""
    try:
        from scheduler.calendar_client import clear_tokens
        clear_tokens()
        return jsonify({"ok": True, "connected": False})
    except Exception as exc:
        logger.warning("cal_disconnect failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/oauth/start")
def cal_oauth_start():
    """Redirect the browser to Google's OAuth consent screen."""
    import urllib.parse
    from scheduler.calendar_client import _client_id as _cid
    client_id = _cid()
    if not client_id:
        return (
            "<h3>Setup required</h3>"
            "<p>Save your Google OAuth credentials in the <strong>Calendar</strong> tab first, then try again.</p>",
            500,
        )
    # The frontend passes its own origin so the server never has to guess the
    # public domain (Replit's reverse proxy makes request.host unreliable).
    redirect_uri = request.args.get("redirect_uri", "").strip()
    if not redirect_uri or not redirect_uri.startswith("https://"):
        # Fallback: derive from request headers (works in dev/local)
        _host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip() or request.host
        redirect_uri = f"https://{_host}/api/calendar/oauth/callback"
    # Store so the callback can use the exact same URI
    session["cal_oauth_redirect_uri"] = redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(url)


@app.route("/api/calendar/oauth/callback")
def cal_oauth_callback():
    """Exchange the auth code for tokens and store them."""
    import urllib.parse
    import requests as _req
    from scheduler.calendar_client import save_tokens

    error = request.args.get("error")
    if error:
        return f"""<html><body><script>
window.opener && window.opener.postMessage({{calendarOAuth:'error',reason:{json.dumps(error)}}}, '*');
window.close();
</script><p>OAuth error: {error}. You can close this window.</p></body></html>"""

    code = request.args.get("code", "")
    from scheduler.calendar_client import _client_id as _cid, _client_secret as _csec
    client_id     = _cid()
    client_secret = _csec()
    # Re-use the exact redirect_uri stored when the OAuth flow started —
    # Google requires it to match precisely.
    redirect_uri = session.get("cal_oauth_redirect_uri", "")
    if not redirect_uri:
        _cb_host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip() or request.host
        redirect_uri = f"https://{_cb_host}/api/calendar/oauth/callback"

    try:
        resp = _req.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
        save_tokens({
            "access_token":  token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri":     "https://oauth2.googleapis.com/token",
            "expiry":        None,
        })
        return """<html><body><script>
window.opener && window.opener.postMessage({calendarOAuth:'success'}, '*');
window.close();
</script><p>Google Calendar connected! You can close this window.</p></body></html>"""
    except Exception as exc:
        logger.warning("cal_oauth_callback token exchange failed: %s", exc)
        err_msg = str(exc)
        return f"""<html><body><script>
window.opener && window.opener.postMessage({{calendarOAuth:'error',reason:{json.dumps(err_msg)}}}, '*');
window.close();
</script><p>Connection failed: {err_msg}. You can close this window.</p></body></html>"""


@app.route("/api/calendar/calendars", methods=["GET"])
def cal_list_calendars():
    """List all Google Calendars available to the connected account."""
    try:
        from scheduler.calendar_client import list_calendars
        calendars = list_calendars()
        return jsonify({"calendars": calendars})
    except Exception as exc:
        logger.warning("cal_list_calendars failed: %s", exc)
        return jsonify({"error": str(exc), "calendars": []}), 200


@app.route("/api/calendar/slots", methods=["GET"])
def cal_get_slots():
    """Find available slots for a job on a given date."""
    try:
        from scheduler.scheduling_agent import find_slots
        date_str = request.args.get("date", "")
        duration = int(request.args.get("duration", 120))
        calendar_id = request.args.get("calendarId") or None
        if not date_str:
            return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400
        result = find_slots(date_str, duration, calendar_id)
        return jsonify(result)
    except Exception as exc:
        logger.warning("cal_get_slots failed: %s", exc)
        return jsonify({"error": str(exc), "slots": []}), 200


@app.route("/api/calendar/hold", methods=["POST"])
def cal_create_hold():
    """Create a HOLD event on the calendar."""
    try:
        from scheduler.scheduling_agent import create_hold
        data = request.get_json(force=True) or {}
        job_spec = data.get("jobSpec", {})
        slot = data.get("slot", {})
        calendar_id = data.get("calendarId") or None
        if not slot.get("start") or not slot.get("end"):
            return jsonify({"error": "slot.start and slot.end are required"}), 400
        result = create_hold(job_spec, slot, calendar_id)
        return jsonify(result)
    except Exception as exc:
        logger.warning("cal_create_hold failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/hold/<event_id>", methods=["PUT"])
def cal_confirm_hold(event_id):
    """Convert a HOLD into a confirmed booking."""
    try:
        from scheduler.scheduling_agent import confirm_booking
        data = request.get_json(force=True) or {}
        job_spec = data.get("jobSpec", {})
        slot = data.get("slot", {})
        calendar_id = data.get("calendarId") or None
        result = confirm_booking(job_spec, slot, event_id, calendar_id)
        return jsonify(result)
    except Exception as exc:
        logger.warning("cal_confirm_hold failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/hold/<event_id>", methods=["DELETE"])
def cal_release_hold(event_id):
    """Release (delete) a HOLD event."""
    try:
        from scheduler.scheduling_agent import release_hold
        calendar_id = request.args.get("calendarId") or None
        result = release_hold(event_id, calendar_id)
        return jsonify(result)
    except Exception as exc:
        logger.warning("cal_release_hold failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/calendar/holds", methods=["GET"])
def cal_list_holds():
    """List all active HOLD events with urgency status."""
    try:
        from scheduler.calendar_client import list_holds, load_config
        cfg = load_config()
        calendar_id   = request.args.get("calendarId") or cfg.get("calendarId")
        timeout_mins  = cfg.get("holdTimeoutMinutes", 60)
        holds         = list_holds(calendar_id)
        for h in holds:
            age   = h.get("ageMinutes")
            until = h.get("hoursUntil")
            if age is not None and age >= timeout_mins and until is not None and until < 24:
                h["status"] = "overdue"
            elif until is not None and until < 24:
                h["status"] = "urgent"
            else:
                h["status"] = "active"
        return jsonify({"ok": True, "holds": holds, "timeoutMinutes": timeout_mins})
    except Exception as exc:
        logger.warning("cal_list_holds failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SMART SCHEDULING — ENGINEER PROFILES & RULES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/scheduling/engineers", methods=["GET"])
def sched_get_engineers():
    try:
        from scheduler.smart_scheduler import load_profiles
        return jsonify({"engineers": load_profiles()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/engineers", methods=["POST"])
def sched_add_engineer():
    try:
        import uuid
        from scheduler.smart_scheduler import load_profiles, save_profiles
        data = request.get_json(force=True) or {}
        profiles = load_profiles()
        new_eng = {
            "id":           data.get("id") or f"eng-{uuid.uuid4().hex[:8]}",
            "name":         data.get("name", "New Engineer"),
            "homePostcode": data.get("homePostcode", ""),
            "region":       data.get("region", "both"),
            "priority":     int(data.get("priority", 99)),
            "fillAheadDays": int(data.get("fillAheadDays", 0)),
            "active":       bool(data.get("active", True)),
            "notes":        data.get("notes", ""),
            "calendarId":   data.get("calendarId", ""),
        }
        profiles.append(new_eng)
        save_profiles(profiles)
        _reconcile_coverage_alerts()
        return jsonify({"ok": True, "engineer": new_eng})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/engineers/<eng_id>", methods=["PUT"])
def sched_update_engineer(eng_id):
    try:
        from scheduler.smart_scheduler import load_profiles, save_profiles
        data = request.get_json(force=True) or {}
        profiles = load_profiles()
        for i, eng in enumerate(profiles):
            if eng.get("id") == eng_id:
                profiles[i] = {**eng, **{
                    k: data[k] for k in
                    ["name", "homePostcode", "region", "priority",
                     "fillAheadDays", "active", "notes", "calendarId"]
                    if k in data
                }}
                if "priority" in profiles[i]:
                    profiles[i]["priority"] = int(profiles[i]["priority"])
                if "fillAheadDays" in profiles[i]:
                    profiles[i]["fillAheadDays"] = int(profiles[i]["fillAheadDays"])
                save_profiles(profiles)
                _reconcile_coverage_alerts()
                return jsonify({"ok": True, "engineer": profiles[i]})
        return jsonify({"error": "Engineer not found"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/engineers/<eng_id>", methods=["DELETE"])
def sched_delete_engineer(eng_id):
    try:
        from scheduler.smart_scheduler import load_profiles, save_profiles
        profiles = load_profiles()
        profiles = [e for e in profiles if e.get("id") != eng_id]
        save_profiles(profiles)
        _reconcile_coverage_alerts()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/rules", methods=["GET"])
def sched_get_rules():
    try:
        from scheduler.smart_scheduler import load_rules
        return jsonify(load_rules())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/rules", methods=["POST"])
def sched_save_rules():
    try:
        from scheduler.smart_scheduler import save_rules
        data = request.get_json(force=True) or {}
        rules = save_rules(data)
        return jsonify({"ok": True, "rules": rules})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# AI SCHEDULING AGENT
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/scheduling/agent-config", methods=["GET"])
def sched_agent_config_get():
    try:
        from scheduler.ai_scheduling_agent import load_agent_config
        return jsonify(load_agent_config())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/agent-config", methods=["POST"])
def sched_agent_config_save():
    try:
        from scheduler.ai_scheduling_agent import save_agent_config
        data = request.get_json(force=True) or {}
        cfg  = save_agent_config(data)
        return jsonify({"ok": True, "config": cfg})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/agent-recommend", methods=["POST"])
def sched_agent_recommend():
    try:
        from scheduler.ai_scheduling_agent import recommend_slots
        data = request.get_json(force=True) or {}
        postcode     = (data.get("postcode") or "").strip()
        service      = (data.get("service")  or "cleaning job").strip()
        duration     = data.get("durationMins")
        notes        = (data.get("customerNotes") or "").strip()
        target_date  = (data.get("targetDate") or None)
        if not postcode:
            return jsonify({"error": "postcode is required"}), 400
        result = recommend_slots(postcode, service, duration, notes, target_date)
        return jsonify(result)
    except Exception as exc:
        logger.error("agent-recommend error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/agent-config/refine", methods=["POST"])
def sched_agent_config_refine():
    """
    Merge new user input into the existing scheduling agent instructions.
    Rules (same as KB goal refine):
    - PRESERVE everything not addressed by new input
    - ADD new points that don't already exist
    - REPLACE any point directly contradicted by new input
    - Never start from scratch
    """
    try:
        from scheduler.ai_scheduling_agent import load_agent_config, save_agent_config
        from scheduler.smart_scheduler import load_profiles, load_rules
        from scheduler.calendar_client import load_config as load_cal_config

        data     = request.get_json(force=True) or {}
        new_info = (data.get("newInfo") or "").strip()
        if not new_info:
            return jsonify({"error": "newInfo is required"}), 400

        existing_cfg          = load_agent_config()
        existing_instructions = existing_cfg.get("instructions", "").strip()

        # ── Load live system context ─────────────────────────────────────
        engineers = load_profiles()
        rules     = load_rules()
        cal_cfg   = load_cal_config()
        wh        = cal_cfg.get("workingHours", {})

        eng_lines = "\n".join(
            f"  - {e['name']}: region={e.get('region','both')}, "
            f"priority={e.get('priority',1)}, "
            f"home={e.get('homePostcode','?')}, "
            f"active={e.get('active', True)}"
            for e in engineers
        ) or "  (none configured)"

        system_context = (
            "CALENDAR SYSTEM — how it works:\n"
            f"  Working hours: {wh.get('start','08:00')} – {wh.get('end','17:30')}, "
            f"Mon–Fri (days {wh.get('days',[1,2,3,4,5])})\n"
            f"  Travel buffer between jobs: {cal_cfg.get('travelBufferMinutes',20)} mins\n"
            f"  Hold timeout (unconfirmed bookings expire): {cal_cfg.get('holdTimeoutMinutes',30)} mins\n"
            "  Booking flow: customer enquiry → AI agent recommends slots → "
            "HOLD placed in calendar → customer confirms → converted to confirmed booking\n\n"
            "ENGINEERS (live data):\n"
            f"{eng_lines}\n\n"
            "SCHEDULING RULES (live data):\n"
            f"  Fill-ahead days (P1 must be booked this many days ahead before P2 offered): "
            f"{rules.get('fillAheadDays', 5)}\n"
            f"  South/London max grouping radius: {rules.get('londonMaxGroupingKm', 20)} km\n"
            f"  South/London urgent radius: {rules.get('londonUrgentKm', 35)} km\n"
            f"  North max grouping radius: {rules.get('northMaxGroupingKm', 60)} km\n"
            f"  North urgent radius: {rules.get('northUrgentKm', 90)} km\n"
        )

        system = (
            "You are a scheduling knowledge editor for PowWash, a UK exterior cleaning company.\n\n"
            "You have access to the live configuration of the scheduling system (engineers, rules, "
            "working hours). Use this to interpret the owner's input accurately — "
            "for example, if they mention an engineer name, you know their region and home base. "
            "If they mention time preferences, you know the working hours to fit them within.\n\n"
            f"{system_context}\n"
            "YOUR JOB: produce a single, clean, well-organised scheduling knowledge document "
            "by intelligently integrating the new information into the existing one.\n\n"
            "INTEGRATION RULES:\n"
            "1. ORGANISE BY ENGINEER first (one section per engineer), then shared/general rules at the end.\n"
            "2. Weave new info into the relevant engineer or topic section — do NOT append at the bottom.\n"
            "3. If new info updates or corrects an existing point, REPLACE that point in-place.\n"
            "4. Clarify vague input using system context — e.g. 'morning slots' → 'slots starting by 09:00', "
            "engineer names → include their home/region, time preferences → fit within working hours.\n"
            "5. Merge redundant phrasing. Say each thing once, cleanly.\n"
            "6. Keep every fact not contradicted by the new input.\n"
            "7. Format: bold engineer name as heading, bullet points for details. Concise, no waffle.\n"
            "8. FEEDBACK EXAMPLES — the owner will regularly describe things the AI got wrong, "
            "using a specific case as an example (e.g. 'booking 9am was bad because if the 8am job "
            "runs 1hr + 1hr travel, we can't make 9am'). When this happens:\n"
            "   a) Extract the GENERAL REASONING PRINCIPLE the example demonstrates — not the literal case.\n"
            "   b) Write it as a transferable guideline that would catch the same class of problem in ANY "
            "context (different times, engineers, postcodes).\n"
            "   c) Do NOT write rules tied to specific times or slots (e.g. 'never book 9am unless 8am is taken'). "
            "DO write reasoning patterns (e.g. 'always verify the engineer can finish their current job "
            "and travel before the proposed slot — with typical job+travel durations, consecutive bookings "
            "need at least 2 hours of gap').\n"
            "   d) The owner is teaching you HOW to think about scheduling, not what to hardcode.\n\n"
            "Return ONLY the final knowledge document — no preamble, no markdown fences, no commentary."
        )
        user = (
            f"EXISTING KNOWLEDGE:\n{existing_instructions or '(Nothing yet.)'}\n\n"
            f"NEW INFORMATION TO INTEGRATE:\n{new_info}\n\n"
            "Produce the updated, fully integrated knowledge document."
        )

        updated = _call_ai(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=1100,
            model=CLAUDE_FAST_MODEL,
        ).strip()

        save_agent_config({**existing_cfg, "instructions": updated})
        return jsonify({"ok": True, "instructions": updated})
    except Exception as exc:
        logger.error("sched_agent_config_refine error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/assistant", methods=["POST"])
def sched_assistant():
    """Scheduling-aware AI chat assistant — answers questions about the current setup."""
    try:
        data    = request.get_json(force=True) or {}
        message = (data.get("message") or "").strip()
        history = data.get("history") or []
        if not message:
            return jsonify({"error": "Message required"}), 400

        from scheduler.calendar_client import load_config as _load_cal_cfg
        from scheduler.ai_scheduling_agent import load_agent_config as _load_agent_cfg
        try:
            from scheduler.smart_scheduler import load_engineers as _load_eng, load_rules as _load_rules
            engineers = _load_eng()
            rules     = _load_rules()
        except Exception:
            engineers, rules = [], {}

        cal_cfg   = _load_cal_cfg()
        agent_cfg = _load_agent_cfg()
        wh        = cal_cfg.get("workingHours", {})
        buf       = cal_cfg.get("travelBufferMinutes", 60)
        hold      = cal_cfg.get("holdTimeoutMinutes", 60)

        eng_lines = []
        for e in (engineers or []):
            eng_lines.append(
                f"  • {e.get('name','?')} — Priority {e.get('priority',1)}, "
                f"region: {e.get('region','?')}, home: {e.get('homePostcode','?')}, "
                f"active: {e.get('active', True)}"
            )

        system = (
            "You are a scheduling assistant for PowWash, a UK exterior cleaning company. "
            "You know the full current scheduling setup and can answer questions about it honestly and helpfully.\n\n"
            f"WORKING HOURS: {wh.get('start','08:00')} – {wh.get('end','17:30')}, Monday–Friday\n"
            f"TRAVEL BUFFER BETWEEN JOBS: {buf} mins\n"
            f"HOLD TIMEOUT: {hold} mins\n\n"
            "ENGINEERS:\n" + ("\n".join(eng_lines) if eng_lines else "  (none configured)") + "\n\n"
            f"SCHEDULING RULES:\n"
            f"  Fill-ahead days: {rules.get('fillAheadDays', 5)} "
            f"(P1 engineers must be booked this many days ahead before P2 is offered work)\n"
            f"  South/London grouping radius: {rules.get('londonMaxGroupingKm', 20)} km\n"
            f"  North grouping radius: {rules.get('northMaxGroupingKm', 60)} km\n\n"
            "SCHEDULING KNOWLEDGE DOCUMENT (full text used by the AI agent):\n"
            f"{agent_cfg.get('instructions', '(none)')}\n\n"
            "Be concise and direct — this is a chat widget. "
            "If the user wants to change scheduling knowledge, suggest they use the 'Update with AI' "
            "box in the Scheduling Knowledge panel."
        )

        messages = list(history) + [{"role": "user", "content": message}]
        reply = _call_ai(
            [{"role": "system", "content": system}] + messages,
            max_tokens=450,
            model=CLAUDE_FAST_MODEL,
        )
        return jsonify({"reply": reply})
    except Exception as exc:
        logger.error("sched_assistant error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/maps-config", methods=["GET"])
def sched_maps_config_get():
    try:
        from scheduler.maps_client import get_maps_api_key
        key = get_maps_api_key()
        # Don't make a live test call on every page load — just report whether a key is saved.
        # The live test only happens on POST (when the user explicitly saves a new key).
        return jsonify({
            "hasKey": bool(key),
            "status": {"connected": bool(key), "source": "google_maps" if key else "haversine_estimate"},
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scheduling/maps-config", methods=["POST"])
def sched_maps_config_save():
    try:
        from scheduler.maps_client import save_maps_api_key, get_maps_status
        data = request.get_json(force=True) or {}
        key  = (data.get("apiKey") or "").strip()
        if key:
            save_maps_api_key(key)
            status = get_maps_status()
        else:
            status = {"connected": False, "source": "haversine_estimate"}
        return jsonify({"ok": True, "status": status})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# OPERATOR CONTACTS
# ─────────────────────────────────────────────────────────────────────────────

def _load_operators() -> list:
    if OPERATOR_CONTACTS_PATH.exists():
        try:
            return json.loads(OPERATOR_CONTACTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_operators(ops: list) -> None:
    OPERATOR_CONTACTS_PATH.write_text(json.dumps(ops, indent=2), encoding="utf-8")

def _normalize_op_phone(raw: str) -> str:
    """Best-effort E.164 normalization for an operator phone number."""
    import re as _re2
    v = _re2.sub(r"[\s\-\(\)]", "", (raw or "").strip())
    if v.startswith("00"):
        v = "+" + v[2:]
    elif v.startswith("0") and not v.startswith("0+"):
        v = "+44" + v[1:]
    elif not v.startswith("+"):
        v = "+" + v
    return v


@app.route("/api/operators", methods=["GET"])
def operators_get():
    return jsonify(_load_operators())


@app.route("/api/operators", methods=["POST"])
def operators_post():
    import uuid as _uuid2
    data = request.get_json(force=True) or {}
    name  = (data.get("name")  or "").strip()
    phone = (data.get("phone") or "").strip()
    role  = (data.get("role")  or "").strip()
    if not name or not phone:
        return jsonify({"error": "name and phone are required"}), 400
    phone = _normalize_op_phone(phone)
    ops = _load_operators()
    if any(_normalize_op_phone(op.get("phone", "")) == phone for op in ops):
        return jsonify({"error": "That number is already saved"}), 409
    ops.append({
        "id":     _uuid2.uuid4().hex[:8],
        "name":   name,
        "phone":  phone,
        "role":   role,
        "active": True,
    })
    _save_operators(ops)
    return jsonify({"ok": True, "operators": ops})


@app.route("/api/operators/<op_id>", methods=["PATCH"])
def operators_patch(op_id):
    data = request.get_json(force=True) or {}
    ops = _load_operators()
    for op in ops:
        if op["id"] == op_id:
            if "active" in data:
                op["active"] = bool(data["active"])
            if "name" in data and data["name"].strip():
                op["name"] = data["name"].strip()
            if "role" in data:
                op["role"] = data["role"].strip()
            break
    _save_operators(ops)
    return jsonify({"ok": True, "operators": ops})


@app.route("/api/operators/<op_id>", methods=["DELETE"])
def operators_delete(op_id):
    ops = [op for op in _load_operators() if op["id"] != op_id]
    _save_operators(ops)
    return jsonify({"ok": True, "operators": ops})


# ═════════════════════════════════════════════════════════
# QUOTE REQUESTS — Human Quote section
# ═════════════════════════════════════════════════════════

@app.route("/api/quote-requests")
@login_required
def api_get_quote_requests():
    return jsonify(_load_quote_requests())


@app.route("/api/bookings")
@login_required
def api_get_bookings():
    """Bookings log + dashboard stats for the current user.

    `lastSeen` is per-user — anything created after it is 'unseen' and drives the
    gold new-booking alert. weekCount = bookings made in the past 7 days;
    todayCount = bookings made today (Europe/London); engineerStats aggregates
    how many jobs each person (or AI) priced."""
    from datetime import datetime as _dtg, timezone as _tzg, timedelta as _tdg
    rows  = _load_bookings_log()
    email = session.get("user_email", "")
    seen  = _load_bookings_seen()
    last_seen = seen.get(email)

    now = _dtg.now(_tzg.utc)
    week_ago = now - _tdg(days=7)

    def _parse(ts):
        try:
            return _dtg.fromisoformat((ts or "").replace("Z", "+00:00"))
        except Exception:
            return None

    # Today in business timezone, expressed as a UTC-comparable window.
    try:
        from scheduler import calendar_client as _cc_b
        _tz_biz = _cc_b.business_tz()
    except Exception:
        _tz_biz = _tzg.utc
    today_local = _dtg.now(_tz_biz).date()

    last_seen_dt = _parse(last_seen) if last_seen else None
    week_count = today_count = unseen_count = 0
    eng_stats: dict = {}
    for r in rows:
        created = _parse(r.get("createdAt"))
        if created is None:
            continue
        if created >= week_ago:
            week_count += 1
        if created.astimezone(_tz_biz).date() == today_local:
            today_count += 1
        if last_seen_dt is None or created > last_seen_dt:
            unseen_count += 1
        who = r.get("quotedBy") or "AI"
        eng_stats[who] = eng_stats.get(who, 0) + 1

    engineer_stats = [{"name": k, "count": v}
                      for k, v in sorted(eng_stats.items(), key=lambda kv: -kv[1])]

    return jsonify({
        "bookings":      rows,
        "lastSeen":      last_seen,
        "weekCount":     week_count,
        "todayCount":    today_count,
        "unseenCount":   unseen_count,
        "total":         len(rows),
        "engineerStats": engineer_stats,
    })


@app.route("/api/bookings/mark-seen", methods=["POST"])
@login_required
def api_mark_bookings_seen():
    """Clear the gold new-booking alert for the current user only."""
    from datetime import datetime as _dtg, timezone as _tzg
    email = session.get("user_email", "")
    with _bookings_write_lock:
        seen = _load_bookings_seen()
        seen[email] = _dtg.now(_tzg.utc).isoformat()
        _save_bookings_seen(seen)
    return jsonify({"ok": True, "lastSeen": seen[email]})


@app.route("/api/scheduling/coverage-alerts")
@login_required
def api_get_coverage_alerts():
    _reconcile_coverage_alerts()
    return jsonify(_load_coverage_alerts())


@app.route("/api/scheduling/coverage-alerts/<aid>/dismiss", methods=["POST"])
@login_required
def api_dismiss_coverage_alert(aid):
    from datetime import datetime as _dtn, timezone as _tzn
    alerts = _load_coverage_alerts()
    a = next((x for x in alerts if x.get("id") == aid), None)
    if not a:
        return jsonify({"error": "not found"}), 404
    a["status"]      = "dismissed"
    a["dismissedAt"] = _dtn.now(_tzn.utc).isoformat()
    _save_coverage_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/api/attention-alerts")
@login_required
def api_get_attention_alerts():
    return jsonify(_load_attention_alerts())


@app.route("/api/attention-alerts/<aid>/dismiss", methods=["POST"])
@login_required
def api_dismiss_attention_alert(aid):
    from datetime import datetime as _dtn, timezone as _tzn
    alerts = _load_attention_alerts()
    a = next((x for x in alerts if x.get("id") == aid), None)
    if not a:
        return jsonify({"error": "not found"}), 404
    a["status"]      = "dismissed"
    a["dismissedAt"] = _dtn.now(_tzn.utc).isoformat()
    _save_attention_alerts(alerts)
    return jsonify({"ok": True})


@app.route("/api/quote-requests/<qid>/answer", methods=["POST"])
@login_required
def api_answer_quote_request(qid):
    data   = request.get_json(force=True) or {}
    advice = data.get("advice", "").strip()
    if not advice:
        return jsonify({"error": "advice required"}), 400

    qrs = _load_quote_requests()
    qr  = next((q for q in qrs if q["id"] == qid), None)
    if not qr:
        return jsonify({"error": "not found"}), 404

    from datetime import datetime, timezone as _tz_q, timedelta as _td_q
    qr["humanAdvice"] = advice
    qr["status"]      = "answered"
    qr["answeredAt"]  = datetime.now(_tz_q.utc).isoformat()
    qr["answeredBy"]  = session.get("user_name") or session.get("user_email") or "Operator"
    _save_quote_requests(qrs)

    # Fire _auto_draft in background with human advice injected via extra_context.
    # Pass skip_media_path=True so the hold-for-review path is bypassed and the AI
    # replies directly using the advice. Also pass any stored images so the AI knows
    # photos were already received and won't ask for them again.
    conv_id    = qr["conversationId"]
    qr_images  = qr.get("images") or []
    has_photos = bool(qr_images)
    # Strip any job-time estimate from the advice the AI is asked to relay, so the
    # internal scheduling duration can never leak to the customer. The FULL advice
    # (incl. duration) stays in qr["humanAdvice"] for the scheduler.
    relay_advice = _strip_duration_for_relay(advice)
    extra      = (
        f"YOUR QUOTE FOR THIS JOB — present this to the customer as your own assessment:\n{relay_advice}\n\n"
        "Use the price(s) above exactly as stated. Do NOT cross-check them against the knowledge base "
        "or standard price list — for custom jobs your direct assessment overrides standard pricing. "
        "Do NOT mention a colleague, a system, or where the figure came from. "
        "Present it naturally as if you worked it out yourself.\n"
        "STAY FAITHFUL: Relay what the advice actually says. You may lightly reword it into your normal "
        "friendly tone, but do NOT add embellishments, opinions, reassurances or commentary that are not "
        "in the advice — e.g. NEVER add internal-sounding asides like 'looks straightforward', 'easy job', "
        "'nice and simple', 'no problem at all', 'should be quick'. If the advice contains a note-to-self "
        "like that, DROP it — only relay the customer-relevant facts (the price, any service labels, any "
        "question, any offer). Keep your wording consistent and on-brand; do NOT try to make every reply "
        "unique, quirky or over-the-top.\n"
        "IMPORTANT: If the advice includes a time or duration estimate (e.g. '2 hours', '3 hours'), "
        "do NOT mention it to the customer — it is for internal scheduling only. Just give the price.\n"
        "If quoting a single service, do NOT restate the obvious service name — go straight to the price. "
        "If quoting two or more services, label each one clearly so the customer knows which price is which. "
        "Never say 'so that\'s a driveway wash' or 'so that\'s a patio clean' for a single service — "
        "they already know. Go straight to the figure.\n"
        "PRICING FIDELITY: Use ONLY the prices in the advice. If the advice gives ONE combined price for "
        "several services, present it as that single combined figure — do NOT split it into per-service "
        "amounts or pull any price from the standard list. If the advice gives a SEPARATE price per "
        "service, state each one. NEVER introduce a price the advice did not give. "
        "If the advice includes a conditional offer (e.g. a discount for booking several services "
        "together), relay it plainly as a condition — e.g. 'if you have both done at the same time, "
        "I can do 10% off'.\n"
        "SIGN-OFF: NEVER end with 'PowWash Team' or any business name sign-off. End naturally.\n"
        "If the advice asks you to put a QUESTION to the customer, relay it simply and plainly. "
        "Do NOT add your own reasoning, explanation or context for WHY you're asking "
        "(e.g. do NOT add 'just want to make sure...', 'so we can plan...', 'to help us...'). "
        "Just ask the question as given — no commentary.\n"
        "PRICE RECAP: If the price has already been mentioned earlier in the conversation, "
        "do NOT repeat the figure in this reply. Trust that the customer remembers it. "
        "Only state the price once — when first giving the quote."
        + ("\n\nThe customer has already sent photos of the area. "
           "Do NOT ask them to send more photos or any further information about the area — "
           "give the quote using your assessment above." if has_photos else "")
    )
    import threading as _th_q
    _th_q.Thread(
        target=_auto_draft,
        args=(conv_id, qr.get("customerMessage", ""), "whatsapp"),
        kwargs={"extra_context": extra, "images": qr_images, "skip_media_path": True},
        daemon=True,
    ).start()

    return jsonify({"ok": True})


@app.route("/api/quote-requests/<qid>", methods=["DELETE"])
@login_required
def api_delete_quote_request(qid):
    qrs = [q for q in _load_quote_requests() if q["id"] != qid]
    _save_quote_requests(qrs)
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Run media cleanup in background on startup
    import threading as _th_startup
    _th_startup.Thread(target=_cleanup_old_media, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
