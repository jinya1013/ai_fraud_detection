import asyncio
import json

from fastapi import APIRouter
from fastapi import Request
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from twilio.rest import Client
from twilio.twiml.voice_response import Connect
from twilio.twiml.voice_response import VoiceResponse
import websockets

from .audio import save_based64_audio
from .config import FORWARD_PHONE_NUMBER
from .config import LOG_EVENT_TYPES
from .config import OPENAI_API_KEY
from .config import SAKURAI_API_URL
from .config import SYSTEM_MESSAGE
from .config import TWILIO_ACCOUNT_SID
from .config import TWILIO_AUTH_TOKEN
from .config import VOICE
from .judge_forward import should_forward_call
from .kikuchi_handler import send_base64_audio_to_kikuchi
from .openai_handler import send_session_update
from .twilio_handler import download_and_send_recording


client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

call_sid = None

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index_page():
    return HTMLResponse(content="Twilio Media Stream Server is running!")


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    global call_sid
    """Twilioからの着信を処理し、Media Streamへの接続を促すTwiMLを返す。"""
    # フォームデータを取得
    form_data = await request.form()

    print("=== リクエスト詳細 ===")
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Query Params: {dict(request.query_params)}")
    print(f"Form Data: {dict(form_data)}")

    # Twilioからの主要なパラメータを取得
    caller_phone_number = form_data.get("From", "Unknown")
    called_phone_number = form_data.get("To", "Unknown")
    call_sid = form_data.get("CallSid", "Unknown")

    print(f"発信者番号: {caller_phone_number}")
    print(f"着信番号: {called_phone_number}")
    print(f"通話SID: {call_sid}")

    host = request.url.hostname
    response = VoiceResponse()
    response.say(
        "もしもした、ただいま、AIアシスタントに接続しております。この通話は安全のために録音されています。ご了承ください。それではお話しください。",
        language="ja-JP",
    )
    connect = Connect()
    connect.stream(url=f"wss://{host}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@router.api_route("/recording-callback", methods=["GET", "POST"])
async def handle_recording_callback(request: Request):
    """転送通話の録音完了後のコールバックを処理する。"""
    form_data = await request.form()

    print("=== 録音コールバック詳細 ===")
    print(f"Form Data: {dict(form_data)}")

    recording_sid = form_data.get("RecordingSid")
    recording_url = form_data.get("RecordingUrl")
    related_call_sid = form_data.get("CallSid")

    if recording_url:
        print(f"録音URL: {recording_url}")
        await download_and_send_recording(recording_url, recording_sid, related_call_sid)

    return HTMLResponse(content="Recording received")


@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """TwilioとOpenAI間のWebSocket接続を処理する。"""
    global call_sid
    print(f"WebSocket接続: 発信者番号 = {call_sid}")
    await websocket.accept()

    audio_data = []

    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17",
        additional_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:
        await send_session_update(openai_ws, VOICE, SYSTEM_MESSAGE)
        stream_sid = None

        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if (
                        data["event"] == "media"
                        and openai_ws.state == websockets.protocol.State.OPEN
                    ):
                        media_payload = data["media"]["payload"]
                        padding = len(media_payload) % 4
                        if padding != 0:
                            media_payload += "=" * (4 - padding)
                        audio_data.append(media_payload)

                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"Incoming stream has started {stream_sid}", data["start"], call_sid)
                    elif data["event"] in ["hangup", "stop"]:
                        print("Call ended. Closing connection.")
                        break
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.state == websockets.protocol.State.OPEN:
                    await openai_ws.close()
            finally:
                print("Closing connection.")
                if openai_ws.state == websockets.protocol.State.OPEN:
                    await openai_ws.close()

        async def send_to_twilio():
            nonlocal stream_sid
            try:
                async for openai_message in openai_ws:
                    response_data = json.loads(openai_message)
                    if response_data["type"] in LOG_EVENT_TYPES:
                        print(f"Received event: {response_data['type']}")
                    if response_data["type"] == "session.updated":
                        print("Session updated successfully:")

                    if response_data["type"] == "response.audio.delta" and response_data.get(
                        "delta"
                    ):
                        try:
                            audio_payload = response_data["delta"]
                            padding = len(audio_payload) % 4
                            if padding != 0:
                                audio_payload += "=" * (4 - padding)
                            audio_data.append(audio_payload)
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload},
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            print(f"Error processing audio data: {e}")
                    if response_data["type"] == "response.done":
                        response_output = response_data["response"]["output"]
                        if response_output:
                            transcript = response_output[0]["content"][0]["transcript"]
                            print(f"Transcript: {transcript}")
                            print(f"Forwarding call to {FORWARD_PHONE_NUMBER}")
                            twiml = f"""
                            <Response>
                                <Dial record="record-from-answer" recordingStatusCallback="{SAKURAI_API_URL}/recording-callback">
                                    {FORWARD_PHONE_NUMBER}
                                </Dial>
                            </Response>
                            """
                            client.calls(call_sid).update(twiml=twiml)
                            await openai_ws.close()
                            break
                            # if should_forward_call(transcript):
                            #     print(f"Forwarding call to {FORWARD_PHONE_NUMBER}")
                            #     client.calls(call_sid).update(
                            #         twiml=f"<Response><Dial>{FORWARD_PHONE_NUMBER}</Dial></Response>"
                            #     )
                            #     await openai_ws.close()
                            #     break
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        try:
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
        except WebSocketDisconnect:
            print("Client disconnected.")
        except Exception as e:
            print(f"Error in handle_media_stream: {e}")
        finally:
            send_base64_audio_to_kikuchi(audio_data, call_sid, "ai")
            # save_based64_audio(audio_data, call_sid)
