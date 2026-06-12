from twilio.rest import Client
import os

client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

message = client.messages.create(
    from_=os.environ["TWILIO_WHATSAPP_FROM"],
    to=os.environ["TWILIO_TEST_TO"],
    body="Twilio test message"
)
print(message.sid)
