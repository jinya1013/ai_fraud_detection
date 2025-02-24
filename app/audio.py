import base64

import httpx


def process_audio_chunks(audio_chunks: list) -> str:
    """
    複数のBase64エンコードされたチャンクを結合し、
    再度1つのBase64エンコードされた文字列に変換して返す。
    """
    try:
        decoded_data = b"".join(base64.b64decode(chunk) for chunk in audio_chunks)
    except Exception as e:
        raise ValueError(f"チャンクのデコードに失敗しました: {e}")

    return base64.b64encode(decoded_data).decode("utf-8")


def send_audio_data(
    encoded_audio: str, phone_id: str, audio_type: str, url: str, headers: dict
) -> bool:
    """
    エンコード済み音声データを指定のAPIへ送信する。
    成功時はTrue、失敗時はFalseを返す。
    """
    payload = {"phoneId": phone_id, "encoded": encoded_audio, "type": audio_type}

    try:
        response = httpx.post(url, json=payload, headers=headers)
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


def send_base64_audio(audio_data: list, phone_id: str, api_url: str):
    """
    ユーザとAIのBase64エンコードされた音声チャンクを結合し、
    外部APIへ送信する。
    """
    headers = {"Content-Type": "application/json"}

    try:
        encoded_audio = process_audio_chunks(audio_data)
        send_audio_data(encoded_audio, phone_id, "ai", api_url, headers)
    except ValueError as e:
        print(f"音声データの処理エラー: {e}")
