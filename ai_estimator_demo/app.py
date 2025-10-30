import base64
import datetime as dt
import copy
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from openai import OpenAI
from openai.error import OpenAIError
import yaml
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

try:
    from pillow_heif import read_heif
except ImportError:  # pragma: no cover
    read_heif = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ai_estimator_demo")

with open(BASE_DIR / "config" / "defaults.yaml", "r", encoding="utf-8") as fh:
    DEFAULTS = yaml.safe_load(fh)

TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "heic", "heif"}

client = OpenAI()

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


def _initial_params() -> Dict[str, Any]:
    return {
        "model": DEFAULTS.get("model", {}).get("name", os.getenv("AI_ESTIMATOR_MODEL", "gpt-4-turbo")),
        "system_prompt": DEFAULTS.get("system_prompt", ""),
        "service_preset": "driveway",
        "pricing": copy.deepcopy(DEFAULTS.get("pricing", {})),
        "coverage_policy": copy.deepcopy(DEFAULTS.get("coverage_policy", {})),
        "response_format": DEFAULTS.get("response_format", "json+explanation"),
        "max_image_size_mb": DEFAULTS.get("max_image_size_mb", 12),
    }


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


STATE: Dict[str, Any] = {
    "params": _initial_params(),
    "session_photo_requests": {},
}


def cleanup_tmp(max_age_hours: int = 24) -> None:
    threshold = dt.datetime.utcnow() - dt.timedelta(hours=max_age_hours)
    for path in TMP_DIR.glob("*"):
        try:
            if path.is_file():
                mtime = dt.datetime.utcfromtimestamp(path.stat().st_mtime)
                if mtime < threshold:
                    path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover
            logger.debug("Failed to clean tmp file %s: %s", path, exc)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def max_upload_bytes() -> int:
    mb = STATE["params"].get("max_image_size_mb") or DEFAULTS.get("max_image_size_mb", 12)
    try:
        mb_val = float(mb)
    except (TypeError, ValueError):
        mb_val = 12
    return int(mb_val * 1024 * 1024)


def save_uploaded_image(file: FileStorage) -> Tuple[Path, str, str]:
    if not file.filename or not allowed_file(file.filename):
        raise ValueError("Unsupported file type. Allowed: jpg, jpeg, png, webp, heic, heif")

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > max_upload_bytes():
        raise ValueError("File too large. Please upload a smaller image.")

    ext = file.filename.rsplit(".", 1)[1].lower()
    safe_name = secure_filename(file.filename)
    uid = uuid.uuid4().hex
    original_path = TMP_DIR / f"{uid}_{safe_name}"

    if ext in {"heic", "heif"}:
        if read_heif is None or Image is None:
            raise ValueError(
                "HEIC/HEIF support is unavailable. Please install pillow-heif or convert the image manually."
            )
        data = file.read()
        heif_file = read_heif(data)
        image = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
        converted_path = original_path.with_suffix(".jpg")
        image.save(converted_path, format="JPEG")
        mime_type = "image/jpeg"
        stored_path = converted_path
    else:
        file.save(original_path)
        mime_type = file.mimetype or f"image/{ext}"
        stored_path = original_path

    return stored_path, stored_path.name, mime_type


def encode_image_to_data_url(path: Path, mime_type: str) -> str:
    with path.open("rb") as fh:
        data = base64.b64encode(fh.read()).decode("utf-8")
    return f"data:{mime_type};base64,{data}"


def build_system_prompt(params: Dict[str, Any]) -> str:
    preset_key = params.get("service_preset", "driveway")
    services = DEFAULTS.get("services", {})
    preset = services.get(preset_key, {})
    base_prompt = params.get("system_prompt") or DEFAULTS.get("system_prompt", "")
    preset_prompt = preset.get("prompt", "")
    response_format = params.get("response_format", "json+explanation")

    schema_instructions = (
        "You must reply with a single JSON object containing the following keys: "
        "summary_text, service, area_estimate_m2, condition, missing_sections, confidence, needs_more_photos, next_request, notes. "
        "The condition object must include dirt_level (light|medium|heavy) and issues (an array of issue slugs such as oil_stains, algae, weeds, poor_drainage, delicate_surface, loose_joints, access_difficulty). "
        "If information is unknown, use an empty array or null, but keep the key. "
        "summary_text should be written in {} format.".format(
            "clear JSON text" if response_format == "json" else ("markdown" if response_format == "markdown" else "plain English with a short explanation")
        )
    )

    pricing_note = (
        "Estimate surface area in square metres. Always provide a confidence value between 0 and 1. "
        "If more imagery is required, set needs_more_photos to true and craft next_request with one precise photo request."
    )

    preset_label = preset.get("label", preset_key.title())

    return "\n\n".join(
        part
        for part in [
            base_prompt.strip(),
            f"Current focus: {preset_label}.",
            preset_prompt.strip(),
            pricing_note,
            schema_instructions,
        ]
        if part
    )


def compute_price(estimation: Dict[str, Any], params: Dict[str, Any]) -> float:
    pricing = params.get("pricing", {})
    base_callout = float(pricing.get("base_callout", 0))
    rate_per_m2 = float(pricing.get("rate_per_m2", 0))
    multipliers = pricing.get("multipliers", {})

    area = estimation.get("area_estimate_m2") or 0
    try:
        area_val = float(area)
    except (TypeError, ValueError):
        area_val = 0.0

    modifier = 1.0
    condition = estimation.get("condition") or {}
    dirt_level = condition.get("dirt_level")
    issues = condition.get("issues") or []
    if isinstance(dirt_level, str) and dirt_level.lower() == "heavy":
        modifier *= float(multipliers.get("heavy_soiling", 1.0))

    for issue in issues:
        issue_key = str(issue).lower()
        if issue_key in multipliers:
            modifier *= float(multipliers[issue_key])
        if issue_key == "algae":
            modifier *= float(multipliers.get("algae_biocide", 1.0))
        if issue_key == "oil" or issue_key == "oil_stain":
            modifier *= float(multipliers.get("oil_stains", 1.0))

    return round(base_callout + (area_val * rate_per_m2 * modifier), 2)


def get_session_id() -> str:
    session_id = request.form.get("session_id") or request.args.get("session_id")
    if not session_id:
        session_id = uuid.uuid4().hex
    return session_id


def increment_photo_request(session_id: str) -> int:
    tracker = STATE["session_photo_requests"]
    tracker[session_id] = tracker.get(session_id, 0) + 1
    return tracker[session_id]


def get_photo_request_count(session_id: str) -> int:
    return STATE["session_photo_requests"].get(session_id, 0)


@app.route("/")
def index() -> str:
    return render_template(
        "index.html",
        services=DEFAULTS.get("services", {}),
        params=STATE["params"],
    )


@app.route("/uploads/<path:filename>")
def serve_upload(filename: str):
    return send_from_directory(TMP_DIR, filename)


@app.route("/api/params", methods=["GET", "POST"])
def api_params():
    if request.method == "GET":
        response = copy.deepcopy(STATE["params"])
        response["services"] = DEFAULTS.get("services", {})
        response["max_image_size_mb"] = STATE["params"].get(
            "max_image_size_mb", DEFAULTS.get("max_image_size_mb", 12)
        )
        return jsonify(response)

    payload = request.get_json(force=True, silent=True) or {}
    new_params = _deep_merge(STATE["params"], payload)
    STATE["params"] = new_params
    return jsonify({"status": "ok", "params": new_params})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    cleanup_tmp()
    params = STATE["params"]
    session_id = get_session_id()

    message_text = (request.form.get("message") or "").strip()
    files = request.files.getlist("images[]")

    if not message_text and not files:
        return jsonify({"error": "Please provide a message or at least one image."}), 400

    stored_images: List[Dict[str, Any]] = []
    data_urls: List[Tuple[str, str]] = []

    for file in files:
        if not isinstance(file, FileStorage):
            continue
        if not file.filename:
            continue
        try:
            path, filename, mime_type = save_uploaded_image(file)
        except ValueError as exc:
            logger.warning("Upload error: %s", exc)
            return jsonify({"error": str(exc)}), 400
        stored_images.append({
            "name": filename,
            "url": f"/uploads/{filename}",
            "mime_type": mime_type,
        })
        data_urls.append((encode_image_to_data_url(path, mime_type), mime_type))

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "Missing OpenAI API key. Set OPENAI_API_KEY in the environment."}), 500

    system_prompt = build_system_prompt(params)
    user_content: List[Dict[str, Any]] = []
    if message_text:
        user_content.append({"type": "text", "text": message_text})
    for data_url, _mime in data_urls:
        user_content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}})

    messages = [
        {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
        {"role": "user", "content": user_content},
    ]

    response_format = params.get("response_format", "json+explanation")

    def request_completion(msgs: List[Dict[str, Any]]):
        return client.chat.completions.create(
            model=params.get("model", DEFAULTS.get("model", {}).get("name", "gpt-4-turbo")),
            messages=msgs,
            temperature=0.3,
        )

    try:
        completion = request_completion(messages)
        content = completion.choices[0].message.content or ""
    except OpenAIError as exc:
        logger.exception("OpenAI API error")
        return jsonify({"error": f"OpenAI API error: {exc}"}), 502

    parsed, parse_error = parse_estimator_json(content)

    if parse_error:
        repair_messages = messages + [
            {"role": "assistant", "content": [{"type": "text", "text": content}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Your previous reply was not valid JSON because {}. Please respond again with strictly valid JSON only, respecting the schema.".format(parse_error),
                    }
                ],
            },
        ]
        try:
            completion = request_completion(repair_messages)
            content = completion.choices[0].message.content or ""
            parsed, parse_error = parse_estimator_json(content)
        except OpenAIError as exc:
            logger.exception("OpenAI API error during repair")
            return jsonify({"error": f"OpenAI API error: {exc}"}), 502

    if parse_error:
        logger.error("Failed to parse model response after repair: %s", parse_error)
        summary = content.strip() or "Sorry, I couldn't process that response."
        return jsonify(
            {
                "session_id": session_id,
                "ai": {
                    "text": summary,
                    "json": None,
                    "price_gbp": None,
                    "confidence": None,
                },
                "images": stored_images,
            }
        )

    estimation = parsed
    price = compute_price(estimation, params)
    confidence = estimation.get("confidence")
    needs_more = bool(estimation.get("needs_more_photos"))
    max_requests = int(params.get("coverage_policy", {}).get("max_additional_photo_requests", 1) or 1)
    issued_requests = get_photo_request_count(session_id)

    summary_text = estimation.get("summary_text") or estimation.get("notes") or "Estimate ready."

    if needs_more and issued_requests < max_requests:
        increment_photo_request(session_id)
        ai_text = estimation.get("next_request") or "Please provide an additional targeted photo to continue."
    else:
        details = [summary_text]
        details.append(f"Estimated area: {estimation.get('area_estimate_m2', 'n/a')} m².")
        details.append(f"Indicative price: £{price:.2f}.")
        if confidence is not None:
            try:
                conf_val = float(confidence)
                threshold = float(params.get("coverage_policy", {}).get("confidence_threshold", 0.7) or 0.7)
                if conf_val < threshold:
                    details.append("Confidence is low; recommend on-site validation before final quote.")
            except (TypeError, ValueError):
                pass
        ai_text = " \n".join(details)

    return jsonify(
        {
            "session_id": session_id,
            "ai": {
                "text": ai_text,
                "json": estimation,
                "price_gbp": price,
                "confidence": confidence,
                "raw": content if response_format != "json" else None,
            },
            "images": stored_images,
        }
    )


def parse_estimator_json(payload: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    text = payload.strip()
    if not text:
        return None, "Empty response"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "Response must be a JSON object"
    required_keys = {
        "summary_text",
        "service",
        "area_estimate_m2",
        "condition",
        "missing_sections",
        "confidence",
        "needs_more_photos",
        "next_request",
        "notes",
    }
    missing = [key for key in required_keys if key not in data]
    if missing:
        return None, f"Missing keys: {', '.join(missing)}"
    return data, None


@app.route("/healthz")
def healthz():
    return ("ok", 200)


def main() -> None:
    port = int(os.getenv("AI_ESTIMATOR_PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
