"""Simple script to print the subject lines of the last ten Gmail inbox messages."""
from __future__ import annotations

import os
from typing import Dict, Iterable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

CLIENT_CONFIG: Dict[str, Dict[str, object]] = {
    "installed": {
        "client_id": "651044229586-mf7ok9848tnrd6gecikbcefhlnv6hghj.apps.googleusercontent.com",
        "project_id": "root-hangout-443922-q1",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "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",
        "redirect_uris": ["http://localhost"],
    }
}


def _load_subject(headers: Iterable[Dict[str, str]]) -> str:
    for header in headers:
        if header.get("name") == "Subject":
            return header.get("value", "(No subject)")
    return "(No subject)"


def main() -> None:
    creds: Optional[Credentials] = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)

    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=10)
        .execute()
    )

    message_refs = response.get("messages", [])
    if not message_refs:
        print("No messages found.")
        return

    for ref in message_refs:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["Subject"],
            )
            .execute()
        )
        headers = message.get("payload", {}).get("headers", [])
        print(_load_subject(headers))


if __name__ == "__main__":
    main()
