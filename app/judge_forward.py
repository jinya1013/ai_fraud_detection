import openai

from .config import OPENAI_API_KEY


openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


def should_forward_call(transcript: str) -> bool:
    """
    AIエージェントの発話内容から、通話を転送してよいかを判定する

    Args:
        transcript (str): AIエージェントの発話内容

    Returns:
        bool: 転送してよい場合はTrue、そうでない場合はFalse
    """
    # プロンプトを構築
    prompt = f"""
以下のAIエージェントの発話内容から、通話を人間のオペレーターに転送してよいかを判断してください。
発話内容が「転送する」「転送します」などの転送の意思を示している場合は「yes」を、
そうでない場合は「no」を返してください。「yes」「no」以外の出力はしないでください。

発話内容:
{transcript}

回答は「yes」か「no」のみで答えてください。"""

    # OpenAI APIを呼び出し
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0
    )

    # 応答を取得
    answer = response.choices[0].message.content.strip().lower()

    # 「yes」の場合はTrue、それ以外はFalseを返す
    return answer == "yes"
