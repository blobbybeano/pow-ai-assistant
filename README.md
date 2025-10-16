# pow-ai-assistant

This repository bundles everything you need to run a PowWash operations
workspace end-to-end: the Twilio webhook, OpenAI powered auto-responder, and a
Flutter client for live agent collaboration.

## Unified launcher (Flutter + Flask)

The quickest way to exercise the full stack is via the new
`workspace_launcher.py` helper. It boots the Twilio Flask webhook on the chosen
port and optionally launches the Flutter workspace with the matching API base
URL so you can trial the experience in one step.

### Prerequisites

* Python 3.9+
* Flutter 3.19+ (only if you want to launch the Flutter workspace)
* OpenAI credentials exposed as environment variables (`OPENAI_API_KEY`, plus
  `OPENAI_ORG_ID` / `OPENAI_PROJECT_ID` if required)
* Twilio sandbox credentials for outbound replies (`TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, and either `TWILIO_WHATSAPP_NUMBER` or
  `TWILIO_MESSAGING_SERVICE_SID`)

### Run everything together

```bash
pip install -r requirements.txt
python workspace_launcher.py
```

The launcher will:

1. Serve the Twilio webhook + REST API locally (default `http://0.0.0.0:5002`).
2. Run `flutter pub get` (unless `--skip-pub-get` is supplied).
3. Execute `flutter run` with `--dart-define=API_BASE_URL=http://127.0.0.1:5002`
   so the workspace talks to the freshly started backend.

Use `Ctrl+C` to shut down both processes at once. Pass `--no-flutter` if you only
need the Flask backend (e.g. when deploying to a server or testing webhooks).

#### Helpful flags

* `--flutter-device`: forwards a device ID from `flutter devices` when you need
  to target a physical device or specific simulator.
* `--flutter-base-url`: override the API base URL (for example,
  `http://10.0.2.2:5002` when talking to Android emulators).
* `--flutter-extra-args -- <args>`: append custom arguments to the `flutter run`
  invocation.

All launcher output is prefixed with `[server]`, `[flutter]`, or `[launcher]` so
you can follow the combined logs in a single terminal.

## Backend components

* **`twilio_app.py`** – Flask webhook that records WhatsApp conversations and
  exposes REST endpoints for the workspace. It reuses the shared
  `auto_responder.generate_reply` helper to draft AI responses.
* **`conversation_store.py`** – Thread-safe in-memory + JSON persisted store
  backing the conversation list.
* **`auto_responder.py`** – Standalone CLI for composing replies from the price
  list and tone guide.
* **`twilio_helpers.py`** – Convenience wrapper around the Twilio REST API.

You can still launch the webhook directly with `python twilio_app.py` if you
prefer, but the new launcher handles coordinating ports and environment details
for local development.

## Flutter workspace

The Flutter client lives in [`flutter_app/`](flutter_app/README.md) and mirrors a
WhatsApp-style inbox for PowWash operators. It polls the REST API for
conversations, lets agents toggle AI auto-replies per contact, and supports
manual outbound messaging when Twilio credentials are present. The launcher
described above runs the same `flutter run` workflow you would execute manually.

## Additional utilities

* **`gmail_subjects.py`** – Authenticates with Gmail and prints the ten most
  recent subject lines. Install dependencies with `pip install -r
  requirements.txt` and run `python gmail_subjects.py` to complete the OAuth
  flow.
* **`app.py`** – Minimal Flask app serving a static prototype workspace. Useful
  for quick UI experiments outside of Flutter.

Update `price_list.json` and `tone_profile.md` to keep the AI output aligned
with your current services and brand voice.
