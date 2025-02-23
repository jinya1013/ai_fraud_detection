import json
import asyncio
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from .config import OPENAI_API_KEY, VOICE, SYSTEM_MESSAGE, KIKUCHI_API_URL, LOG_EVENT_TYPES, FORWARD_PHONE_NUMBER, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from twilio.rest import Client
from .twilio_handler import client
from .openai_handler import send_session_update
from .audio import send_base64_audio  # 必要に応じて利用

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
    caller_phone_number = form_data.get('From', 'Unknown')
    called_phone_number = form_data.get('To', 'Unknown')
    call_sid = form_data.get('CallSid', 'Unknown')
    
    print(f"発信者番号: {caller_phone_number}")
    print(f"着信番号: {called_phone_number}")
    print(f"通話SID: {call_sid}")
    
    host = request.url.hostname
    response = VoiceResponse()
    response.say("もしもした、ただいま、AIアシスタントに接続しております。この通話は安全のために録音されています。ご了承ください。それではお話しください。", language="ja-JP")
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """TwilioとOpenAI間のWebSocket接続を処理する。"""
    global call_sid
    print(f"WebSocket接続: 発信者番号 = {call_sid}")
    await websocket.accept()
    
    user_audio_data = []
    ai_audio_data = []
    
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
        additional_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws, VOICE, SYSTEM_MESSAGE)
        stream_sid = None
        
        async def receive_from_twilio():
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.state == websockets.protocol.State.OPEN:
                        user_audio_data.append(data['media']['payload'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"Incoming stream has started {stream_sid}", data['start'], call_sid)
                    elif data['event'] in ['hangup', 'stop']:
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
                    if response_data['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response_data['type']}")
                    if response_data['type'] == 'session.updated':
                        print("Session updated successfully:")
                                
                    if response_data['type'] == 'response.audio.delta' and response_data.get('delta'):
                        try:
                            audio_payload = response_data['delta']
                            ai_audio_data.append(audio_payload)
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            print(f"Error processing audio data: {e}")
                    if response_data['type'] == 'response.done':
                        response_output = response_data['response']['output']
                        if response_output:
                            transcript = response_output[0]['content'][0]['transcript']
                            print(f"Transcript: {transcript}")
                            print(f"Forwarding call to {FORWARD_PHONE_NUMBER}")
                            client.calls(call_sid).update(
                                twiml=f'<Response><Dial>{FORWARD_PHONE_NUMBER}</Dial></Response>'
                            )                                
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")
        
        try:
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
        except WebSocketDisconnect:
            print("Client disconnected.")
        except Exception as e:
            print(f"Error in handle_media_stream: {e}")
        finally:
            pass
            # 必要に応じて、ここでsend_base64_audio(user_audio_data, ai_audio_data, ...) を呼び出す。
