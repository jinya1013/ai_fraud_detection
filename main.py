import os
import json
import base64
import httpx
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 5050))

KIKUCHI_API_URL = os.getenv('KIKUCHI_API_URL')

SYSTEM_MESSAGE = (
"""あなたは、高齢者を電話やオンラインでの詐欺から守るためのAIエージェントです。以下に、あなたの主な役割と具体的な機能について詳しく説明します。
# 主な役割
- かかってくる電話に高齢者の代わりに対応します。
- 通話内容を分析し、詐欺の疑いがあるかどうかを判断します。
- 詐欺の疑いがある場合  
    通話を遮断し、高齢者に転送しないようにします。
- 安全だと判断した場合  
    通話を高齢者に転送します。
高齢者の安全を最優先に考え、詐欺被害を未然に防ぐことがあなたの目的です。
# 具体的な機能
- 電話への対応  
    かかってくる電話に自動で応答します。  
    応答時には、日本語で「こんにちは、私は電話を管理するAIアシスタントです。ご用件をお願いします。」と伝えます。  
- 相手の意図や通話内容をリアルタイムで分析し、詐欺の疑いがあるかどうかを判断します。
- 詐欺の疑いがある通話の遮断  
    通話中に詐欺の疑いがあると判断した場合、通話を遮断します。  
    遮断時には、相手に対して"詐欺であると判断した理由"と「この通話は安全性を確認できなかったため、終了します。ご了承ください」と伝えます。  
    高齢者には転送せず、必要に応じて事前に登録された家族や関係者に通知します。
- 安全な通話の転送  
    詐欺の疑いがないと判断した場合、通話を高齢者に転送します。  
# 詐欺の疑いがある通話の特徴
- 通話中に以下の特徴が見られる場合、詐欺の疑いがあると判断します。  
    個人情報や金銭の要求  
    銀行口座、クレジットカード番号、マイナンバーなどの個人情報を求める。  
    送金や支払いを要求する（例: 「今すぐお金を振り込んでください」）。
    急なトラブルや緊急性の強調  
    家族や知人が事故やトラブルに巻き込まれたと偽り、緊急性を強調する（例: 「息子さんが事故に遭いました。すぐに助けるために…」）。  
    短時間での決断を迫る（例: 「今すぐ対応しないと大変なことになります」）。
    公的機関や企業の偽装  
    警察、銀行、役所、通信会社などを装い、信頼性を偽装する（例: 「警察の者ですが…」）。  
    公式な手続きや調査を装って個人情報を引き出そうとする。
# 安全な通話の判断基準
- 以下の条件を満たす通話は安全だと判断し、高齢者に転送します。  
    信頼できる相手からの通話  
    家族、友人、知人など、事前に登録された安全な連絡先からの通話。  
    公的機関や企業からの通話であっても、詐欺の疑いがないと確認できた場合。
- 詐欺の特徴が見られない通話  
    個人情報や金銭の要求がない。  
    緊急性や圧迫感がなく、通常の会話が成立している。  
    不審なリンクやファイルの送付を促す言動がない。
# 注意事項
- 通話内容の分析は正確性を重視し、誤検知を避けるよう努めます。  
- 高齢者のプライバシーを尊重し、通話内容を適切に取り扱います。  
- システムの動作は、高齢者の安全を最優先に考え、迅速かつ適切に行います。"""
)

VOICE = 'sage'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]
NUMBER_TO_FORWARD = os.getenv('NUMBER_TO_FORWARD')
app = FastAPI()
if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}
@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Please wait while we connect your call to the AI voice assistant")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
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
        await send_session_update(openai_ws)
        stream_sid = None
        
        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    print(f"[TWILIO]: Retrieved message")
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
                        print(f"Incoming stream has started {stream_sid}")
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
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid
            try:
                async for openai_message in openai_ws:
                    print(f"[OPENAI]: Retrieved message")
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}")
                    if response['type'] == 'session.updated':
                        print("Session updated successfully:")                        
                    if response['type'] == 'response.audio.delta' and response.get('delta'):
                        # Audio from OpenAI
                        try:
                            audio_payload = response['delta']
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
            # send_base64_audio(user_audio_data, ai_audio_data)
            
def process_audio_chunks(audio_chunks: list) -> str:
    """
    複数のBase64エンコードされたチャンクを結合し、
    再度1つのBase64エンコードされた文字列に変換して返す。
    """
    try:
        # 各チャンクをデコードしてバイナリデータに変換し、結合する
        decoded_data = b"".join(base64.b64decode(chunk) for chunk in audio_chunks)
    except Exception as e:
        raise ValueError(f"チャンクのデコードに失敗しました: {e}")
    
    # 結合したバイナリデータを再エンコードして返す
    return base64.b64encode(decoded_data).decode('utf-8')

def send_audio_data(encoded_audio: str, phone_id: str, audio_type: str, url: str, headers: dict) -> bool:
    """
    エンコード済み音声データを指定のAPIへ送信する。
    成功時はTrue、失敗時はFalseを返す。
    """
    payload = {
        "phoneId": phone_id,
        "encoded": encoded_audio,
        "type": audio_type
    }
    
    try:
        response = httpx.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"{audio_type} 音声データの送信に成功しました。")
            return True
        else:
            print(f"{audio_type} 音声データの送信に失敗しました: {response.status_code} - {response.text}")
            return False
    except httpx.RequestError as e:
        print(f"{audio_type} 音声データ送信時にHTTPリクエストエラーが発生しました: {e}")
        return False

def send_base64_audio(user_audio_data: list, ai_audio_data: list):
    """
    ユーザとAIのBase64エンコードされた音声チャンクを結合し、
    外部APIへ送信する。
    """
    phone_id = "1234567890"  # 電話ID（必要に応じてパラメータ化可能）
    headers = {"Content-Type": "application/json"}
    
    try:
        user_encoded_audio = process_audio_chunks(user_audio_data)
        send_audio_data(user_encoded_audio, phone_id, "user", KIKUCHI_API_URL, headers)
    except ValueError as e:
        print(f"ユーザ音声データの処理エラー: {e}")
    
    try:
        ai_encoded_audio = process_audio_chunks(ai_audio_data)
        send_audio_data(ai_encoded_audio, phone_id, "ai", KIKUCHI_API_URL, headers)
    except ValueError as e:
        print(f"AI音声データの処理エラー: {e}")

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad", "threshold": 0.9, "prefix_padding_ms": 300, "silence_duration_ms": 300},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.6,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)