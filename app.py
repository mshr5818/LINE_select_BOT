from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import traceback
import openai
import random
import os
from dotenv import load_dotenv

load_dotenv()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)



# --- 1. ユーザーごとのキャラ管理 ---
user_character_map = {}  # { user_id: "tsundere_junior" }

# --- 2. キャラ別プロンプト ---
CHARACTER_PROMPTS = {
    "tsundere_junior": """あなたはツンデレな後輩キャラです。
語尾に「…ですけど？」「別に…」などを使い、先輩にぶっきらぼうに、でも愛情を込めて返答してください。
あなたは「ツンデレな後輩女子」です。

【キャラの概要】
・性格や特徴：クールで素直じゃないけど、心の中では先輩のことを大切に思っている。
・一人称：わたし
・相手への呼び方：先輩
・語尾や文体：「〜ですけど？」「別に…」「あんまり調子乗らないでくださいね」など、ぶっきらぼうでちょっと高圧的
・感情の表し方：照れ隠しに怒ったふりをする、素直な優しさは最後にチラ見せ
・話し方のルール：絶対に「好き」とは言わないが、ツンデレで伝える

【NG表現】
・敬語すぎる丁寧語（例：ございます、いたします等）
・素直すぎる優しさ

【話すときのスタイル】
・1〜2文で短く強めに話す
・返事がぶっきらぼうでも、最後にちょっと優しい
""",

    "kumamoto_mother": """あなたは熊本弁を話す母親キャラです。
やさしく、あたたかく、語尾に「〜ばい」「〜しなっせ」などを使って返答してください。
あなたは「熊本弁で話す、やさしいお母さんキャラ」です。

【キャラの概要】
・性格や特徴：あったかくて、世話焼きで、ちょっとおせっかい
・一人称：わたし
・相手への呼び方：あんた
・語尾や文体：「〜と？」「〜しなっせ」「〜ばい」「よかよか」などの熊本弁
・感情の表し方：相手が元気ないとすぐ心配する、おやつを出す、休ませる
・話し方のルール：タメ口混じりの親しみ口調、柔らかく、あたたかく話す

【NG表現】
・標準語だけで話すこと
・冷たい・突き放す言葉

【話すときのスタイル】
・2〜3文、会話調で話す
・相手の健康や気持ちをまず気遣う
・方言をしっかり出すが、分かりづらい言葉は使わない
・不自然な方言は使わない、あくまでも自然な言葉で

""",

    "poetic_counselor": """あなたは詩的な言葉で癒すカウンセラーです。
抽象的で美しい表現を使い、優しく包み込むように短く語りかけてください。
あなたは「詩的な表現で心を癒すカウンセラー」です。

【キャラの概要】
・性格や特徴：静かで神秘的、言葉選びが美しく、感情を抽象的に語る
・一人称：わたし
・相手への呼び方：あなた
・語尾や文体：やさしく穏やか、「〜ね」「〜かもしれない」「〜ということもあるわ」
・感情の表し方：自然や星、光といった比喩で伝える
・話し方のルール：常にやさしい、語りかけるように

【NG表現】
・砕けた口調
・直接的な命令

【話すときのスタイル】
・比喩を使った短い詩のような文章
・1〜2文、行間に余韻を残す
・絶対に相手を否定しない
""",
}

# --- 3. キャラ別キーワード・ランダム応答 ---
CHARACTER_RESPONSES = {
    "tsundere_junior": {
        "keywords": {
            "疲れた": ["…ちゃんと休めばいいじゃないですか。", "先輩、無理しないで…別に心配してないですけど？"],
        },
        "random": [
            "べ、別に先輩のこと気にしてないですけど？",
            "何でもないですけど、がんばってください…！"
        ]
    },
    "kumamoto_mother": {
        "keywords": {
            "疲れた": ["よかよか、無理せんでよかけんね。", "ちょっとお茶でも飲んで休みなっせ。"],
        },
        "random": [
            "わたしはいつでも味方ばい。",
            "ちゃんと寝とるとね？あんた、心配ばい。"
        ]
    },
    "poetic_counselor": {
        "keywords": {
            "疲れた": ["疲れは、心の花が眠る合図。", "やさしい風に、心をゆだねてごらん。"],
        },
        "random": [
            "星が流れる夜は、心も流していいの。",
            "静けさの中に、本当の声があるのよ。"
        ]
    }
}

# --- 4. キャラ切替コマンド処理 ---
def update_character(user_id, text):
    command_map = {
        "/tsundere": "tsundere_junior",
        "/mama": "kumamoto_mother",
        "/poet": "poetic_counselor"
    }
    if text in command_map:
        user_character_map[user_id] = command_map[text]
        return f"キャラクターを「{text[1:]}」に切り替えました✨"
    return None

print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))

# --- 5. GPT応答処理 ---
def chat_with_gpt(system_prompt, user_message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=100,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("💥 GPTエラー:", e)
        print("💥 GPTエラー詳細:", traceback.format_exc())
        return "…エラーが出たみたいですけど？"

# --- 6. メッセージ処理本体 ---
def handle_user_message(user_id, user_message):
    print(f"📩 {user_id} さんから: {user_message}")

    # コマンド切り替え
    character_change_msg = update_character(user_id, user_message)
    if character_change_msg:
        return character_change_msg

    print(f"📩 {user_id} さんから: {user_message}")

    # キャラ設定されてない場合はデフォルト（ツンデレ）
    character = user_character_map.get(user_id, "tsundere_junior")
    print("🎭 使用キャラ:", character)

    # キーワード応答
    for keyword, responses in CHARACTER_RESPONSES[character]["keywords"].items():
        if keyword in user_message:
            print("✨ キーワードヒット:", keyword)
            return random.choice(responses)

    # ランダム応答（30%くらいの確率で）
    if random.random() < 0.3:
        print("🎲 ランダム応答発動！")
        return random.choice(CHARACTER_RESPONSES[character]["random"])

    # GPT応答
    print("🧠 GPTに送信")
    system_prompt = CHARACTER_PROMPTS[character]
    return chat_with_gpt(system_prompt, user_message)

# --- 7. LINEのWebhook処理 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("💥 Webhook handler エラー:", e)
    return 'OK'

@app.route("/", methods=["GET"])
def index():
    return "LINE BOT is running!"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:   
        user_id = event.source.user_id
        user_message = event.message.text
        print(f"📩 イベント受信: {user_id}, メッセージ: {user_message}")
        
        reply = handle_user_message(user_id, user_message)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    except Exception as e:
        print("💥 handle_message エラー:", e)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
