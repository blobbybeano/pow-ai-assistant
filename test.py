from twilio.rest import Client
import os

client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

message = client.messages.create(
    from_="whatsapp:+14155238886",  # or your approved sender number
    to="whatsapp:+447541088300",
    body="Twilio test message"
)
print(message.sid)
