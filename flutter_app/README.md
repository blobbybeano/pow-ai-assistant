# PowWash WhatsApp Workspace (Flutter)

This Flutter client pairs with the enhanced `twilio_app.py` webhook to provide
an almost production-ready WhatsApp-style workspace. It lets you monitor
conversations arriving from Twilio, preview or send Pow AI generated drafts, and
switch between automated and human replies in real time.

## Prerequisites

* Flutter 3.19 or newer.
* A running instance of the Flask webhook (`python twilio_app.py`).
* Twilio sandbox credentials configured in the Flask app's environment for
  outbound messaging.

## Getting started

The repository root ships with `workspace_launcher.py`, a helper that boots the
Flask backend and this Flutter client together:

```bash
python workspace_launcher.py
```

If you prefer to run the Flutter workspace manually, the usual workflow still
applies:

```bash
cd flutter_app
flutter pub get
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:5002  # Android emulator
```

Use `http://127.0.0.1:5002` for iOS Simulator or desktop platforms. When
running on a physical device, expose the Flask server with a tunnelling tool
(e.g. ngrok) and pass the public URL instead.

## Features

* Inbox view that mirrors WhatsApp with avatars, unread counters, and last
  message previews.
* Conversation view with polished message bubbles, timeline separators, and
  delivery status indicators.
* Toggle between AI auto-responses and manual replies per conversation.
* Request an AI draft on demand, edit it, and send it manually.
* Pull-to-refresh and background polling to surface new Twilio messages in near
  real time.

## Folder layout

```
lib/
  app.dart                // Entry point & dependency wiring
  controllers/            // State management classes
  models/                 // Dart models that map to the Flask API
  screens/                // Inbox and conversation UI
  services/               // REST API client
  theme/                  // Theme extensions and helpers
  widgets/                // Reusable UI components (bubbles, toggles, etc.)
```

## Testing the flow

1. Launch the Flask webhook and expose it to Twilio if required.
2. Run the Flutter app and open the inbox. Seed conversations appear the first
   time to showcase the layout.
3. Send a WhatsApp message to your sandbox number. The conversation will update
   within a few seconds. Toggle **Pow AI Autoreply** to disable automatic
   drafting for that contact.
4. Tap **AI Draft** when the toggle is off to fetch a suggested reply without
   sending it. Edit the draft and send manually.

Happy testing!
