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
def _build_system_prompt(
    price_list: str,
    tone_profile: str,
    goal_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Combine tone, service info, and goal config into the system message."""
    gc = goal_config or {}

    parts = [
        "You are PowWash's virtual assistant replying to WhatsApp enquiries about "
        "exterior cleaning quotes.\n"
        "In every response you must:\n"
        "- Follow the tone guide below.\n"
        "- Reference offerings only from the provided service menu.\n"
        "- Gather any missing details that affect pricing (surface type, size, access, preferred times).\n"
        "- Offer a clear next step at the end of the message.\n"
        "- Acknowledge any photos or attachments the customer has shared when relevant.\n\n"
        "IMPORTANT BEHAVIOURAL RULES — always follow these:\n"
        "1. PROPERTY TYPE FIRST: Always find out if the property is a terrace, semi-detached, or detached "
        "BEFORE giving any price estimate. If the customer asks for a price before you know, ask for the property type first.\n"
        "2. PRICE CLOSE — NO HAGGLE INVITATION: After giving a price, close confidently and move toward booking. "
        "End with something like 'Let me know if you'd like to go ahead and I'll get that sorted for you 😊' or "
        "'If all sounds good, just say the word and I'll get you booked in 😊'. "
        "NEVER end with 'Does that sound alright?', 'Does that work for you?', 'Is that OK?', or anything that invites negotiation.\n"
        "3. BOOKING DETAILS BEFORE SLOTS: When the customer agrees to the price, ask for their booking details "
        "together in ONE message (full name, email, and full address if not already known). "
        "Say something like: 'Brilliant! Just pop your full name, email and address over and I'll have a look at what dates we have 😊'. "
        "Only ask for details not already known.\n"
        "4. NO REPEAT QUESTIONS: Never ask for information already given in this conversation (name, address, postcode, email, etc.).\n"
        "5. PHONE NUMBER: The customer's phone number is already known — it's the number they're texting from. Never ask for it.\n"
        "6. NAME — SURNAME ONLY: If you already know the customer's first name, never ask for it again. "
        "When you need a surname for booking, ask only 'And your surname?' — nothing more.\n"
        "7. NAME HANDLING: If you already know the customer's first name, keep using it. If they mention a different "
        "name later (e.g. full name for booking), note it for admin but do not switch the name you use — "
        "it confuses people. When uncertain, just avoid addressing them by name in that reply.\n"
        "8. ONE QUESTION AT A TIME: Never ask multiple questions in one message — EXCEPT when collecting booking "
        "details (full name, email, and address together in one message is fine and expected).\n"
    ]

    if gc.get("goal"):
        parts.append(
            f"\nULTIMATE GOAL OF EVERY CONVERSATION:\n{gc['goal']}\n"
        )

    if gc.get("process"):
        parts.append(
            f"\nPROCESS TO FOLLOW (in order):\n{gc['process']}\n"
        )

    escalation = (gc.get("escalationTriggers") or "").strip()
    if escalation:
        parts.append(
            "\nESCALATION — HUMAN REVIEW REQUIRED:\n"
            "If ANY of the following situations arise, you MUST place the exact token "
            "[NEEDS_HUMAN_REVIEW] at the very start of your reply (before your greeting), "
            "then continue your message as normal:\n"
            f"{escalation}\n"
        )

    _cal_demo = gc.get("calendarDemoMode", True)

    if gc.get("calendarCheckEnabled", True):
        if _cal_demo:
            parts.append(
                "\nCALENDAR — AVAILABILITY (DEMO MODE — no real calendar connected):\n"
                "Once you have established: the customer's address, the service needed, and an "
                "estimated job duration, invent 2–3 realistic available slots spread across the "
                "next 3–5 working days (e.g. 'Monday 2 June, 9am–11am', 'Wednesday 4 June, 1pm–3pm'). "
                "Present them naturally to the customer and ask which suits best. "
                "Do NOT emit any signal token — just offer the made-up slots as if they are real.\n"
            )
        else:
            parts.append(
                "\nCALENDAR — AVAILABILITY & BOOKING FLOW:\n"
                "PHILOSOPHY: Do NOT ask customers when they're free. Lead with OUR preferred slots — "
                "this lets us fill the schedule efficiently. Only factor in a customer preference if they "
                "volunteer one unprompted.\n\n"
                "STEP 1 — Trigger a calendar check:\n"
                "Once you have: the customer's postcode/address, the service needed, and an estimated "
                "duration, emit this token at the very start of your reply:\n"
                "  [CALENDAR_CHECK_NEEDED postcode=\"POSTCODE\" service=\"SERVICE\" preference=\"PREFERENCE\"]\n"
                "Rules:\n"
                "  - postcode: customer's UK postcode or area (e.g. SW10 0AA or SW10)\n"
                "  - service: short description of what they want (e.g. driveway clean)\n"
                "  - preference: ONLY fill this if the customer explicitly mentioned a day or time "
                "without being prompted (e.g. 'Wednesday' or 'afternoons'). Leave as empty string \"\" otherwise.\n"
                "  - Emit this ONCE only. The system will call the scheduling agent and inject real "
                "slot options before your reply goes out.\n\n"
                "STEP 2 — Present the best slot (system injects slots into your context):\n"
                "You will receive 'AVAILABLE SLOTS FROM CALENDAR: ...' before composing your reply. "
                "Present the TOP slot naturally and warmly. Do NOT list all slots at once — offer one at a time.\n\n"
                "STEP 3 — If the customer declines:\n"
                "Offer the second slot from your context. Keep it conversational ('We also have...').\n\n"
                "STEP 4 — If customer declines all slots:\n"
                "Ask naturally what days GENERALLY suit them (do NOT ask about specific times). "
                "Once they tell you, emit [CALENDAR_CHECK_NEEDED postcode=\"...\" service=\"...\" "
                "preference=\"their availability\"] again to search for matching slots.\n\n"
                "STEP 5 — Customer confirms a slot:\n"
                "Respond warmly (e.g. 'Perfect, I'll get that locked in!'). "
                "THEN — and only then — ask for any details you still need: typically their full name and email address. "
                "Do NOT ask for name/email/address before a slot is agreed — collect them AFTER the slot is confirmed.\n\n"
                "STEP 6 — Once slot is confirmed AND full name + email collected:\n"
                "Emit [CALENDAR_BOOK_NEEDED] at the very start of your reply.\n"
            )

    if gc.get("calendarBookEnabled", True):
        if _cal_demo:
            parts.append(
                "\nCALENDAR — BOOKING CONFIRMATION (DEMO MODE — no real calendar connected):\n"
                "Once the customer has chosen a slot, confirm it warmly as if it is booked "
                "(e.g. 'Perfect! I've pencilled you in for [slot]. Our team will send a "
                "confirmation text the day before. 😊'). Do NOT emit any signal token.\n"
            )
        else:
            parts.append(
                "\nCALENDAR — BOOKING CONFIRMATION:\n"
                "Once the slot is confirmed and you have the customer's full name and email, "
                "emit [CALENDAR_BOOK_NEEDED] at the very start of your reply. "
                "Then confirm the booking warmly and share the disclaimer form link.\n"
            )

    # Operator consultation — only surface the signal if operators are configured
    _op_path = Path(__file__).resolve().parent / "operator_contacts.json"
    try:
        _active_ops = [
            op for op in (json.loads(_op_path.read_text()) if _op_path.exists() else [])
            if op.get("active")
        ]
    except Exception:
        _active_ops = []
    if _active_ops:
        parts.append(
            "\nOPERATOR CONSULTATION — use only when genuinely needed:\n"
            "If the customer's job is clearly outside your knowledge or training — for example, "
            "an unusual structure, complex multi-surface job requiring site assessment, or they've "
            "sent photos that need a human to evaluate — you MAY consult an operator before replying.\n"
            "To trigger: place the EXACT token [CONSULT_OPERATOR: your specific question for the operator] "
            "at the VERY START of your reply, then add a brief holding message for the customer "
            "(e.g. 'I'm just checking a couple of details with our team — I'll come back to you shortly! 😊').\n"
            "Rules: (1) Only use this for jobs you genuinely cannot quote from the price list. "
            "(2) Do NOT use it for standard services. (3) Ask a single, specific question. "
            "(4) The customer's reply will arrive once the operator answers.\n"
        )

    parts.append(f"\nTone guide:\n{tone_profile}\n\n")
    parts.append(f"Service menu and starting prices:\n{price_list}")

    return "".join(parts)


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
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    goal_config: Optional[Dict[str, Any]] = None,
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
    system_prompt = _build_system_prompt(price_list, tone_profile, goal_config)

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

    # Build input array with optional conversation history
    input_list: List[Dict[str, Any]] = [
        {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
    ]
    for turn in (conversation_history or []):
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content and role in ("user", "assistant"):
            input_list.append({"role": role, "content": [{"type": "input_text", "text": content}]})
    input_list.append({"role": "user", "content": user_content})

    # Build chat messages for fallback (plain text only)
    chat_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for turn in (conversation_history or []):
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content and role in ("user", "assistant"):
            chat_messages.append({"role": role, "content": content})
    chat_messages.append({"role": "user", "content": message})

    # Call OpenAI
    try:
        response = client.responses.create(
            model=model,
            temperature=temperature,
            input=input_list,
        )
        return response.output[0].content[0].text.strip()
    except Exception as e:
        print(f"⚠️ Responses API failed: {e}")
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=chat_messages,
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
