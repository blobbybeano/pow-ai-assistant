import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore

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

APP_ROOT = Path(__file__).resolve().parent
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
        return self.sessions.setdefault(session_id, {"photo_requests": 0})

    def increment_photo_requests(self, session_id: str) -> None:
        session = self.get(session_id)
        session["photo_requests"] = session.get("photo_requests", 0) + 1


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


class AIClient:
    def __init__(self):
        if OpenAI is None:
            raise RuntimeError("openai package is required but not installed")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        base_url = os.getenv("OPENAI_API_BASE")
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def chat(self, system_prompt: str, user_parts: List[Dict[str, Any]], response_format: str) -> Dict[str, Any]:
        instructions = (
            "You are an assistant producing structured estimate JSON for exterior cleaning services. "
            "Return an object with fields: service, area_estimate_m2, condition (dirt_level, issues array), "
            "missing_sections array, confidence (0-1), needs_more_photos, next_request, notes, summary. "
            "Always include a concise summary string."
        )
        response_kwargs: Dict[str, Any] = {}
        if response_format == "json":
            response_kwargs["response_format"] = {"type": "json_schema", "json_schema": ESTIMATE_JSON_SCHEMA}
        elif response_format == "json+explanation":
            instructions += " After the JSON provide a short explanation prefixed by 'EXPLANATION:'."
        elif response_format == "markdown":
            instructions += " Format the response as JSON inside a fenced code block."

        response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_parts},
            ],
            max_output_tokens=800,
            **response_kwargs,
        )
        if not response.output:
            raise RuntimeError("Empty response from model")
        combined = "".join(part.text or "" for part in response.output if getattr(part, "type", "") == "output_text")
        return {"raw": combined.strip(), "response": response}

    def repair_json(self, broken: str) -> str:
        response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": "You fix JSON. Return only valid JSON with the same information.",
                },
                {"role": "user", "content": broken},
            ],
        )
        if not response.output:
            raise RuntimeError("Empty response while repairing JSON")
        return "".join(part.text or "" for part in response.output if getattr(part, "type", "") == "output_text").strip()


defaults = load_defaults()
params = ParameterStore(defaults)
pricing_engine = PricingEngine(params)
sessions = SessionState()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


@app.route("/")
def index():
    return render_template(
        "index.html",
        service_presets={k: v.get("label", k.title()) for k, v in params.preset_options().items()},
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
            image_parts.append({"type": "input_image", "image_base64": data_url.split(",", 1)[1]})
    except Exception as exc:
        logger.exception("Image processing failed")
        return jsonify({"error": str(exc)}), 400

    if not message and not image_parts:
        return jsonify({"error": "Message or at least one image is required."}), 400

    user_content: List[Dict[str, Any]] = []
    if message:
        user_content.append({"type": "input_text", "text": message})
    user_content.extend(image_parts)

    system_prompt = build_system_prompt(params.get(), defaults)

    try:
        ai_client = AIClient()
    except Exception as exc:
        logger.exception("AI client initialisation failed")
        return jsonify({"error": str(exc)}), 500

    response_format = params.get().get("response_format", "json")
    try:
        raw_result = ai_client.chat(system_prompt, user_content, response_format)
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
        summary = parsed.get("next_request")
    else:
        summary = build_summary(parsed, confidence_threshold)

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


def build_system_prompt(state: Dict[str, Any], defaults_cfg: Dict[str, Any]) -> str:
    preset_key = state.get("service_preset")
    preset = defaults_cfg.get("service_presets", {}).get(preset_key, {})
    prompt = state.get("system_prompt", defaults_cfg.get("system_prompt", ""))
    focus = preset.get("focus")
    response_format = state.get("response_format", "json")
    instructions = [prompt]
    if focus:
        instructions.append(f"Service focus: {focus}")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
