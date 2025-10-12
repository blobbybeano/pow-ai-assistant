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

## WhatsApp-inspired Flutter web client

The `flutter_whatsapp_clone` directory contains a Flutter application that mimics a multi-party WhatsApp conversation. It lets
you:

* switch between two or more human participants, each with a unique bubble colour or gradient;
* enable or disable AI auto-replies via a toggle in the top app bar;
* preview an AI-generated response, watch the "thinking" indicator and either send or cancel the draft before it posts;
* interject manually at any time—sending a human message cancels the pending AI response.

### Prerequisites

* Flutter SDK 3.16 or newer with web support enabled.
* Node.js is **not** required; Flutter serves the compiled assets.

### Run the Flutter app in debug mode

```bash
cd flutter_whatsapp_clone
flutter pub get
flutter run -d chrome
```

### Build for the Flask host

1. Compile the Flutter project for the web:

   ```bash
   cd flutter_whatsapp_clone
   flutter pub get
   flutter build web
   ```

2. Start the Flask server, which serves the generated `build/web` directory as a static site:

   ```bash
   cd ..
   pip install -r requirements.txt
   python -m flask --app flask_app.app run
   ```

3. Navigate to `http://127.0.0.1:5000/` to use the chat interface as a static HTML experience.

The Flask application automatically detects missing Flutter build assets and instructs you to run `flutter build web` first.
