"""Compose customer replies using the OpenAI API, price list, and tone guide."""
from __future__ import annotations

import argparse
import json
import os
import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI


PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
print(f"PUBLIC_BASE_URL: {PUBLIC_BASE_URL or '(not set)'}")


def _url_is_accessible(url: str, timeout: float = 5.0) -> bool:
    """Best-effort check to confirm the image URL is reachable."""
    try:
        try:
            request = Request(url, method="HEAD")  # type: ignore[arg-type]
        except TypeError:  # Python < 3.9 compatibility
            request = Request(url)

            def _head_method() -> str:
                return "HEAD"

            request.get_method = _head_method  # type: ignore[assignment]

        with urlopen(request, timeout=timeout) as response:  # nosec: B310
            if 200 <= response.status < 400:
                return True
            if response.status == 405:
                raise HTTPError(url, response.status, "Method Not Allowed", response.headers, None)
    except HTTPError as err:
        if err.code == 405:
            try:
                with urlopen(url, timeout=timeout) as get_response:  # nosec: B310
                    return 200 <= getattr(get_response, "status", 200) < 400
            except Exception:
                return False
        return False
    except (URLError, ValueError, TimeoutError):
        return False
    except Exception:
        return False
    return False


def get_public_image_url(file_path: Path, *, content_type: Optional[str] = None) -> str:
    """Return a public URL or base64 data URL for the provided image."""
    absolute_path = file_path.resolve()
    if not absolute_path.exists():
        raise FileNotFoundError(f"Attachment does not exist: {absolute_path}")

    if PUBLIC_BASE_URL:
        uploads_dir = Path.cwd() / "uploads"
        public_suffix = absolute_path.name
        try:
            relative = absolute_path.relative_to(uploads_dir)
            public_suffix = f"uploads/{relative.as_posix()}"
        except ValueError:
            public_suffix = f"uploads/{absolute_path.name}"

        public_url = f"{PUBLIC_BASE_URL.rstrip('/')}/{public_suffix}"
        if _url_is_accessible(public_url):
            return public_url
        print(
            f"⚠️ Image at {absolute_path} is not reachable by OpenAI. Falling back to base64 inline data."
        )

    with absolute_path.open("rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")

    mime_type = (content_type or mimetypes.guess_type(absolute_path.name)[0] or "image/jpeg")
    return f"data:{mime_type};base64,{encoded}"


# ---------------------------------------------------------------------
# Load resources
# ---------------------------------------------------------------------
def _load_price_list(path: Path) -> str:
    """Load and format the JSON price list."""
    if not path.exists():
        raise FileNotFoundError(f"Price list file not found: {path}")

    with path.open("r", encoding="utf-8") as price_file:
        data: Dict[str, Any] = json.load(price_file)

    services: Iterable[Dict[str, Any]] = data.get("services", [])
    lines: List[str] = ["Available services and pricing:"]
    for service in services:
        name = service.get("name", "Unnamed service")
        description = service.get("description", "")
        price = service.get("price")
        price_text = f"£{price}" if price is not None else "price upon request"
        if description:
            lines.append(f"- {name} ({price_text}): {description}")
        else:
            lines.append(f"- {name} ({price_text})")

    if len(lines) == 1:
        lines.append("- (No services configured)")
    return "\n".join(lines)


def _load_tone_profile(path: Path) -> str:
    """Load the tone guide markdown file."""
    if not path.exists():
        raise FileNotFoundError(f"Tone profile file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------
def _build_system_prompt(price_list: str, tone_profile: str) -> str:
    """Combine tone and service info into the system message."""
    return (
        "You are PowWash's virtual assistant replying to WhatsApp enquiries about "
        "exterior cleaning quotes.\n"
        "In every response you must:\n"
        "- Follow the tone guide below.\n"
        "- Reference offerings only from the provided service menu.\n"
        "- Gather any missing details that affect pricing (surface type, size, access, preferred times).\n"
        "- Offer a clear next step at the end of the message.\n"
        "- Acknowledge any photos or attachments the customer has shared when relevant.\n\n"
        "Tone guide:\n"
        f"{tone_profile}\n\n"
        f"Service menu and starting prices:\n{price_list}"
    )


# ---------------------------------------------------------------------
# Core AI logic
# ---------------------------------------------------------------------
def generate_reply(
    message: str,
    price_list_path: Path,
    tone_profile_path: Path,
    model: str = "gpt-4o-mini",
    temperature: float = 0.6,
    attachments: Optional[List[Any]] = None,
    client: Optional[OpenAI] = None,
) -> str:
    """
    Return a reply string generated by the OpenAI Responses API.

    attachments may contain plain URLs, local file paths, or dicts such as:
      {"url": "https://example.com/uploads/img.jpg", "content_type": "image/jpeg"}
    Pass an OpenAI client to use custom credentials or endpoints.
    """
    client = client or OpenAI()

    # Load resources
    price_list = _load_price_list(price_list_path)
    tone_profile = _load_tone_profile(tone_profile_path)
    system_prompt = _build_system_prompt(price_list, tone_profile)

    # Normalize attachments
    normalized_attachments: List[Dict[str, Optional[str]]] = []
    for att in attachments or []:
        if isinstance(att, str) and att.strip():
            normalized_attachments.append({"value": att.strip(), "content_type": None})
        elif isinstance(att, dict):
            value = att.get("url")  # prefer URL if available

            # If path/local_path is a Path object -> convert to string
            if not value:
                p = att.get("path") or att.get("local_path")
                if p:
                    value = str(p)

            if isinstance(value, str) and value.strip():
                content_type = att.get("content_type") or att.get("mime_type")
                normalized_attachments.append({
                    "value": value.strip(),
                    "content_type": content_type if isinstance(content_type, str) else None,
                })

    # ---------------- Corrected structure for Responses API ----------------
    user_content: List[Dict[str, Any]] = [
        {"type": "input_text", "text": message}
    ]

    for attachment in normalized_attachments:
        source = attachment.get("value") or ""
        content_type = attachment.get("content_type")
        # Publicly accessible image
        if source.lower().startswith(("http://", "https://")):
            user_content.append({
                "type": "input_image",
                "image_url": source,
            })
            continue

        # Local image files
        file_path = Path(source)
        if not file_path.is_file():
            continue
        try:
            resolved = get_public_image_url(file_path, content_type=content_type)
        except Exception as exc:
            print(f"⚠️ Skipping attachment {file_path}: {exc}")
            continue

        # The Responses API expects `image_url` to be a string (public URL or data URI)
        # rather than an object wrapper.
        user_content.append({
            "type": "input_image",
            "image_url": resolved,
        })

    # Call OpenAI
    try:
        response = client.responses.create(
            model=model,
            temperature=temperature,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": user_content},
            ],
        )
        return response.output[0].content[0].text.strip()
    except Exception as e:
        print(f"⚠️ Responses API failed: {e}")
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
            )
            return completion.choices[0].message.content.strip()
        except Exception as e2:
            print(f"❌ Chat Completions also failed: {e2}")
            return "(No AI reply generated — check model output format.)"


# ---------------------------------------------------------------------
# CLI testing
# ---------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compose a reply to an inbound customer message using your price list and tone guide."
    )
    parser.add_argument("message", help="The inbound customer message.")
    parser.add_argument("--price-list", type=Path, default=Path("price_list.json"))
    parser.add_argument("--tone-profile", type=Path, default=Path("tone_profile.md"))
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--temperature", type=float, default=0.6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reply = generate_reply(
        message=args.message,
        price_list_path=args.price_list,
        tone_profile_path=args.tone_profile,
        model=args.model,
        temperature=args.temperature,
    )
    print(reply)


if __name__ == "__main__":
    main()
