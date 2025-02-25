import base64

import aiofiles
import aiohttp

from .config import TWILIO_ACCOUNT_SID
from .config import TWILIO_AUTH_TOKEN
from .kikuchi_handler import send_base64_audio_to_kikuchi


async def download_and_send_recording(
    recording_url: str, recording_sid: str, call_sid: str, save_file: bool = False
):
    """
    録音データをダウンロードして、保存するか、Kikuchi APIへ送信する。

    Args:
        recording_url (str): 録音データのURL
        recording_sid (str): 録音データのID
        call_sid (str): 通話のID
        save_file (bool): 録音データをファイルに保存するかどうか
    """

    try:
        # 認証情報を追加してURLにアクセス
        auth = aiohttp.BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        full_url = f"{recording_url}.wav"  # wav形式でダウンロード

        async with aiohttp.ClientSession() as session:
            async with session.get(full_url, auth=auth) as response:
                if response.status == 200:
                    # レスポンスデータを取得
                    audio_data = await response.read()

                    if save_file:
                        # ファイルに保存
                        filename = f"{call_sid}_{recording_sid}.wav"
                        async with aiofiles.open(filename, "wb") as f:
                            await f.write(audio_data)

                        print(f"録音ファイルを保存しました: {filename}")

                    # データをBase64エンコードしてKikuchi APIへ送信
                    base64_encoded_audio = base64.b64encode(audio_data).decode("utf-8")
                    await send_base64_audio_to_kikuchi(base64_encoded_audio, call_sid, "human")
                else:
                    print(f"録音の取得に失敗しました。ステータスコード: {response.status}")
    except Exception as e:
        print(f"録音ダウンロード中にエラーが発生しました: {e}")
