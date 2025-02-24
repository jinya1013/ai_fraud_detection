from twilio.rest import Client

from .config import AI_PHONE_NUMBER
from .config import FORWARD_PHONE_NUMBER
from .config import TWILIO_ACCOUNT_SID
from .config import TWILIO_AUTH_TOKEN


client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def initiate_call_transfer(stream_sid, caller_phone_number):
    """Twilio REST APIを使って通話を転送。"""
    try:
        call = client.calls.create(
            twiml=f"<Response><Dial>{FORWARD_PHONE_NUMBER}</Dial></Response>",
            to=FORWARD_PHONE_NUMBER,
            from_=caller_phone_number,  # Twilioの番号
        )
        print(f"通話を転送しました: {call.sid}")
    except Exception as e:
        print(f"通話転送中にエラー: {e}")
