# pow-ai-assistant

## Gmail subject preview script

This repository contains a minimal command-line helper that authenticates with Gmail and prints the subject lines of the ten most recent messages in your inbox.

### Prerequisites

* Python 3.9 or newer.
* A Google account with Gmail access.
* Network access to complete the OAuth sign-in flow.

### Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the script and complete the Google sign-in flow when prompted. The script stores your OAuth token locally in `token.json` (ignored by Git):

   ```bash
   python gmail_subjects.py
   ```

On subsequent runs the stored token will be reused until it expires or is revoked. Delete `token.json` if you need to re-authorize.

## AI-powered auto responder

Use `auto_responder.py` to draft customer replies that reflect your pricing and preferred tone.

### Configure your pricing and tone

* Update `price_list.json` with the services you offer. Each entry needs a name, description, and price.
* Adjust `tone_profile.md` to describe how you want replies to sound.

### Provide OpenAI credentials

The script uses the official OpenAI Python SDK. Ensure the following environment variables are set before running the script:

* `OPENAI_API_KEY`
* Optionally `OPENAI_ORG_ID` and `OPENAI_PROJECT_ID` if your workspace requires them.

### Generate a reply

Pass the inbound customer message on the command line. You can override the model, price list, or tone profile paths if needed.

```bash
python auto_responder.py "Hi, can you help my team automate our reporting?"
```

By default the script calls `gpt-4o-mini` with a balanced temperature of `0.6`. The generated reply is printed to standard output.

## Pow AI collaboration workspace (Flask web app)

The repository now ships with a lightweight Flask app that serves a browser-based chat workspace inspired by the original Flutter mock-up—no additional SDKs or build steps required.

### Features

* Switch between three human teammates to post messages with distinct gradients.
* Toggle automatic Pow AI responses on or off from the chat header.
* Watch the typing indicator before previewing the suggested AI draft, then send or cancel it.
* Compose messages with Shift+Enter for multi-line editing and Enter to send.

### Run the web app

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://127.0.0.1:5000/` and press the **Run** button in your IDE if you prefer; the app uses standard Flask defaults and does not depend on extra virtual environments.

The UI assets live in `templates/` and `static/` and can be customised without rebuilding anything.

## Twilio WhatsApp sandbox auto-responder

The `twilio_app.py` module exposes a Flask webhook that turns inbound WhatsApp sandbox
messages into PowWash quote replies using the shared OpenAI auto-responder logic.

### New Flutter workspace

A production-style Flutter client now lives in `flutter_app/`. It surfaces the
Twilio conversations captured by the webhook, supports toggling AI auto-replies
per contact, and lets you send manual responses directly from your device.

1. Install Flutter 3.19 or newer.
2. Start the Flask webhook (`python twilio_app.py`) and expose it with ngrok if
   you plan to test on a physical device.
3. From `flutter_app/` run `flutter pub get` followed by `flutter run`. Pass the
   appropriate `--dart-define=API_BASE_URL=...` depending on your emulator
   target (e.g. `http://10.0.2.2:5002` for Android).
4. Watch conversations update in real time as Twilio forwards messages. Disable
   Pow AI autopilot for a thread to test human replies or tap **AI Draft** to
   fetch a suggested response without sending it.

### Configure

1. Install the additional dependency:

   ```bash
   pip install -r requirements.txt
   ```

2. Provide your OpenAI credentials in the environment (as described earlier) as
   well as the Twilio credentials needed for outbound sandbox messages:
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and either
   `TWILIO_WHATSAPP_NUMBER` (prefixed with `whatsapp:`) or
   `TWILIO_MESSAGING_SERVICE_SID`.

3. Run the webhook locally:

   ```bash
   python twilio_app.py
   ```

   The server listens on `http://0.0.0.0:5002/twilio/whatsapp`.

4. In the Twilio console, point your WhatsApp sandbox **When a message comes in** URL to
   the public address of this webhook (use a tunnelling tool such as ngrok when running locally).

5. Send a message from your verified WhatsApp number. The AI agent will draft a PowWash reply
   using the updated tone guide and service menu so you can observe the full exchange inside the
   Flutter app connected to the sandbox.

### Local trial workflow (PyCharm + ngrok)

If you are developing inside PyCharm and want to exercise the full sandbox loop, follow the
sequence below:

1. **Create two PyCharm run configurations.**
   * `Twilio webhook` – points to `python twilio_app.py`, uses your preferred virtual
     environment, and loads the OpenAI/Twilio environment variables. Ensure the working
     directory is the project root so the Flask app can find `conversation_store.db`.
   * `Flutter client` – marks `flutter_app/lib/main.dart` as the entry point. PyCharm will use
     the Flutter SDK you configured globally.
2. **Start the backend first.** Run the `Twilio webhook` configuration so the Flask server is
   available at `http://127.0.0.1:5002`. Watch the PyCharm Run tool window for the log output
   confirming the webhook URL.
3. **Expose the webhook to Twilio.** Launch ngrok from a terminal (this can be PyCharm’s
   built-in terminal) with:

   ```bash
   ngrok http 5002
   ```

   Copy the generated `https://` forwarding address and update the Twilio sandbox **When a
   message comes in** webhook URL to `https://<forwarding-host>/twilio/whatsapp`.
4. **Run the Flutter workspace.** Execute the `Flutter client` configuration. When prompted for
   an `API_BASE_URL`, use the host that matches your target device:
   * Android emulator – `http://10.0.2.2:5002`
   * iOS simulator – `http://127.0.0.1:5002`
   * Physical device – replace with your machine’s LAN IP (e.g. `http://192.168.1.50:5002`)
5. **Test the flows.** With all three pieces running (Flask webhook, ngrok tunnel, Flutter app),
   send a WhatsApp message to your sandbox number. The inbox page should refresh with the new
   conversation. Open it to toggle AI autopilot, request an AI draft, or send a manual reply. Any
   replies you send from the Flutter app will appear in the Twilio sandbox thread on your phone.

Keep ngrok running while you iterate so Twilio can continue to reach your local webhook. If you
restart the tunnel, update the sandbox URL with the new forwarding address before sending the
next test message.
