from typing import Literal

import httpx

from .audio import process_audio_chunks
from .config import KIKUCHI_API_URL


async def send_base64_audio_data(
    based64_encoded_audio: str, phone_id: str, audio_type: str, url: str, headers: dict
) -> bool:
    """
    エンコード済み音声データを指定のAPIへ非同期で送信する。
    成功時はTrue、失敗時はFalseを返す。
    """
    payload = {"phoneId": phone_id, "encoded": based64_encoded_audio, "type": audio_type}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"{audio_type} 音声データの送信に成功しました。")
            return True
        else:
            print(
                f"{audio_type} 音声データの送信に失敗しました: {response.status_code} - {response.text}"
            )
            return False
    except httpx.RequestError as e:
        print(f"{audio_type} 音声データ送信時にHTTPリクエストエラーが発生しました: {e}")
        return False


async def send_base64_audio_to_kikuchi(
    audio_data: list[str],
    phone_id: str,
    audio_type: Literal["ai", "human"],
    api_url: str = KIKUCHI_API_URL,
):
    """
    ユーザとAIのBase64エンコードされた音声チャンクを結合し、
    外部APIへ非同期で送信する。

    Args:
        audio_data (list[str]): 音声データのリスト
        phone_id (str): 電話番号のID
        audio_type (Literal["ai", "human"]): 音声データの種類
        api_url (str): 外部APIのURL
    """
    headers = {"Content-Type": "application/json"}

    try:
        based64_encoded_audio = process_audio_chunks(audio_data)
        await send_base64_audio_data(based64_encoded_audio, phone_id, audio_type, api_url, headers)
    except ValueError as e:
        print(f"音声データの処理エラー: {e}")
