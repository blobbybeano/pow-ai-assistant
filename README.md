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
