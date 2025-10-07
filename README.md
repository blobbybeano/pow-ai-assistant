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
