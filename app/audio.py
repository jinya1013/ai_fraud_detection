import audioop
import base64
import wave


def process_audio_chunks(audio_chunks: list[str]) -> str:
    """
    複数のBase64エンコードされたチャンクを結合し、
    再度1つのBase64エンコードされた文字列に変換して返す。
    """
    try:
        decoded_data = b"".join(base64.b64decode(chunk) for chunk in audio_chunks)
    except Exception as e:
        raise ValueError(f"チャンクのデコードに失敗しました: {e}")

    return base64.b64encode(decoded_data).decode("utf-8")


def save_audio_wav(base64_audio_data: str, phone_id: str):
    """
    Base64エンコードされた音声データをWAVファイルに保存する。
    """
    # mu-law を PCM (リニア) にデコード
    # mu-lawは通常、8000Hz、8bitでエンコードされている
    mulaw_data = base64.b64decode(base64_audio_data)
    pcm_data = audioop.ulaw2lin(mulaw_data, 2)  # 2はサンプル幅（16bit = 2バイト）

    # wavファイルとして書き出し
    output_wav = f"{phone_id}.wav"
    with wave.open(output_wav, "wb") as wf:
        wf.setnchannels(1)  # モノラル
        wf.setsampwidth(2)  # 16bit PCM
        wf.setframerate(8000)  # サンプリングレート 8000Hz
        wf.writeframes(pcm_data)


def save_based64_audio(audio_data_chunk: list[str], phone_id: str):
    """
    Base64エンコードされた音声データをファイルに保存する。
    """
    try:
        encoded_audio = process_audio_chunks(audio_data_chunk)
        save_audio_wav(encoded_audio, phone_id)
    except ValueError as e:
        print(f"音声データの処理エラー: {e}")
