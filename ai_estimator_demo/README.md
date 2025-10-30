# AI Estimator Demo

This standalone mini-app provides a PowWash quote exploration experience that mirrors the production estimator without touching the existing launcher, Flask, Twilio, or Flutter services. It runs on its own Flask server at `http://localhost:5050` and reuses the same environment variables (for example, `OPENAI_API_KEY`).

## Features

- WhatsApp-style chat UI with drag-and-drop and multi-image upload support (jpg, jpeg, png, webp, heic/heif).
- GPT-4 Turbo with vision integration for estimating PowWash services.
- Real-time pricing calculator that respects configurable multipliers.
- Parameter drawer for live editing of system prompt, service presets, pricing, coverage policy, and response format without restarting the server.
- Structured responses including confidence, follow-up photo requests, and transparent pricing output.
- Health-check endpoint at `/healthz` for monitoring.

## Prerequisites

- Python 3.10+
- A valid OpenAI API key with access to GPT-4 Turbo vision models.
- Recommended Python packages listed in `requirements.txt` (Flask, OpenAI, PyYAML, python-dotenv, Pillow, pillow-heif, Werkzeug).

## Setup

1. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies:**
   ```bash
   pip install -r ai_estimator_demo/requirements.txt
   ```
3. **Configure environment variables:**
   - Copy `.env.example` to `.env` inside `ai_estimator_demo/` and populate `OPENAI_API_KEY`.
   - Alternatively, export the variables directly in your shell.

## Running the demo

```bash
python ai_estimator_demo/app.py
```

The server listens on `0.0.0.0:5050` by default. Override the port with `AI_ESTIMATOR_PORT` if needed.

Once running, open your browser to [http://localhost:5050](http://localhost:5050).

## Changing defaults

- Default prompts, service presets, pricing, and policy values are stored in `config/defaults.yaml`.
- Updates made through the UI are held in memory per server process. Restarting the app reloads the defaults from YAML.

## Temporary uploads

- Uploaded media is written to `ai_estimator_demo/tmp/`. The server performs a simple cleanup of files older than 24 hours on each request.
- Configure the maximum upload size via the `max_image_size_mb` setting in the YAML file.

## Known limitations

- HEIC/HEIF conversion requires the optional `pillow-heif` dependency. If unavailable, the UI will prompt the user to convert images manually.
- This demo is not production hardened: persistent storage, authentication, and concurrency scaling are intentionally omitted for clarity.
- API errors from OpenAI are surfaced as toast notifications in the UI and logged server-side.

