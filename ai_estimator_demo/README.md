# PowWash AI Estimator Demo

This mini-application provides a self-contained environment for experimenting with AI-assisted quoting for PowWash exterior cleaning services. It does **not** modify or depend on the existing launchers or integrations inside this repository. The demo runs on port `5050` and can be started independently with a single command.

## Features

- WhatsApp-style chat UI with drag-and-drop or file picker uploads for multiple images.
- Inline thumbnails with a lightbox preview and timestamps for every message.
- Support for JPEG, PNG, WEBP, and HEIC/HEIF (automatic conversion when Pillow and `pillow-heif` are installed).
- Server-side OpenAI GPT-4 Turbo vision calls using the same environment variables (`OPENAI_API_KEY`, optional `OPENAI_API_BASE`).
- Pricing calculator with configurable base call-out, square-metre rate, and condition multipliers.
- In-memory “Training & Parameters” panel that can be edited and applied without restarting the server.
- Coverage policy controls for requesting additional photos when confidence is low.
- Graceful error handling with toast notifications and JSON repair retries when the model output is invalid.

## Quick Start

1. **Install dependencies (preferably inside a virtual environment):**

   ```bash
   pip install -r requirements.txt
   pip install flask python-dotenv pyyaml pillow pillow-heif openai
   ```

   The first command ensures the base project requirements are installed. The second line adds the demo dependencies. `pillow-heif` is optional but recommended for HEIC/HEIF conversion.

2. **Copy the environment template and add your secrets:**

   ```bash
   cp ai_estimator_demo/.env.example ai_estimator_demo/.env
   ```

   Update the file with your `OPENAI_API_KEY`. Do **not** commit secrets.

3. **Run the demo server:**

   ```bash
   python ai_estimator_demo/app.py
   ```

   The app listens on [http://localhost:5050](http://localhost:5050) and operates independently from the primary project services.

## Configuration

- Default prompts, service presets, and pricing parameters live in `config/defaults.yaml`.
- The runtime parameter store mirrors these defaults and can be adjusted via the UI under the “Training & Parameters” drawer.
- Use the **Apply & Save** button to update the active session. Changes are kept in memory for the running process.
- The coverage policy controls:
  - `max_additional_photo_requests`: maximum times the AI can ask for more images (default `1`).
  - `confidence_threshold`: below this value the summary will note that on-site validation is recommended.

## API Endpoints

- `GET /` – Serves the chat UI.
- `GET /api/params` – Returns the current effective configuration and presets.
- `POST /api/params` – Updates configuration in memory. Payload mirrors the structure returned by the `GET` endpoint.
- `POST /api/chat` – Accepts form-data with `message`, optional `images[]`, and `session_id`. Returns AI summary text, structured JSON, price, and echoes thumbnails.
- `GET /healthz` – Returns `{"status": "ok"}` for basic monitoring.

## File Handling

- Uploaded images are temporarily saved in `ai_estimator_demo/tmp`. Files older than one hour are cleaned up opportunistically during uploads.
- Maximum upload size defaults to 8 MB (configurable via parameters panel).
- HEIC/HEIF files require Pillow and `pillow-heif` for conversion; otherwise the server returns a friendly error.

## Known Limitations

- Session state is kept in memory and resets when the server restarts.
- Automatic JSON repair relies on a second OpenAI call; if both attempts fail the user receives a friendly error message.
- The UI currently echoes the uploaded thumbnails returned by the server response; production deployments should store files on durable storage or object stores.

## Troubleshooting

- **Missing API key**: Ensure `OPENAI_API_KEY` is present in the environment or `.env` file before starting the server.
- **HEIC conversion errors**: Install `pillow` and `pillow-heif`, or convert the files to JPEG/PNG manually before uploading.
- **Large files rejected**: Adjust the “Max Image Size (MB)” value in the parameters panel and click **Apply & Save**.

Enjoy experimenting with PowWash AI estimates without affecting the main project stack!
