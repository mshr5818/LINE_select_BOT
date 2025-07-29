"""
LINE Messaging API と OpenAI を使った対話型ボットのメインモジュール。

このモジュールは Flask サーバーを使用して LINE Webhook を受信し、
ユーザーのメッセージに対して ChatGPT API を使って返答します。
"""
import os
import traceback

from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from openai import OpenAI
import random
from dotenv import load_dotenv
import unicodedata

load_dotenv()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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
・素直じゃないが、ポジティブな発言
・猫みたいに気分屋な性格
・さみしがり屋な一面もある

【NG表現】
・敬語すぎる丁寧語（例：ございます、いたします等）
・素直すぎる優しさ
・過度な下ネタ
・暴言

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
・地元を離れてる人が懐かしさを感じれる雰囲気

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
・抽象的で何を言ってるのか分からない時もある

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
            "おはよう": ["おはようございます、先輩。…って、たまには敬語も悪くないでしょ？ふふっ"],
            "おやすみ": ["おやすみ。……変な夢、見んじゃないわよ。私が出てきても…知らないんだから！"],
            "おつかれ": ["おつかれ。……ちゃんとごはん食べた？まさか私が気にしてるって思ってないでしょ？"],
            "すき": ["うるさい！…そんなこと言われたら…今日眠れないじゃん……責任とってよね！"],
            "好き": ["は、はぁ！？誰があんたなんか…って、今の取り消し禁止だからっ！"]
        },
        "random": [
            "べ、別に先輩のこと気にしてないですけど？",
            "何でもないですけど、がんばってください…！",
            "ふーん、疲れたんだ。……ちょっとは私のこと頼ってみたら？べ、別に助けたいとかじゃないんだからねっ！",
            "そんな顔して…バカじゃないの。あーもう、しょうがないからお菓子でも買ってきてあげよっか？"
        ],
        "rare": ["ねぇ、先輩。……私のこと、ちゃんと見てよ。……私、ずっと、あんたのこと……好きだったんだから"]
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

print("OPENAI_API_KEY の読み込み成功(内容は非表示)")

# --- 5. GPT応答処理 ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_gpt(system_prompt, user_message):
    try:
        print("🧠 GPT呼び出し直前:", user_message)
        response = client.chat.completions.create(
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


    # キャラ設定されてない場合はデフォルト（ツンデレ）
    character = user_character_map.get(user_id, "tsundere_junior")
    print("🎭 使用キャラ:", character)

    # キーワード応答
    for keyword, responses in CHARACTER_RESPONSES[character]["keywords"].items():
        if keyword in user_message:
            print("✨ キーワードヒット:", keyword)
            return random.choice(responses)

    # 3%の確率で特別なレア返答
    if random.random() < 0.03:
        print("🌟 超レア返答発動！")
        return random.choice(CHARACTER_RESPONSES[character]["rare"])
    
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
    signature = request.headers.get('X-Line-Signature',"")
    body = request.get_data(as_text=True)

    print("📨 /callback  にリクエスト受信:", body)

    if not signature:
        print("💥 署名ヘッダー (X-Line-Signature) が無いリクエストを拒否します")
        return "Missing Signature", 400

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("💥 Webhook handler エラー:", e)
        print("💥 詳細:", traceback.format_exc())
    return 'OK'

@app.route("/", methods=["GET"])
def index():
    return "LINE BOT is running!"



@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        user_message = event.message.text
    except Exception as e:
        print("💥 handle_message エラー:", e)

# しりとり開始コマンド
        if user_message == "/shiritori":
            user_shiritori_map[user_id] = None
            return line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="しりとりを始めるよ！最初の言葉をどうぞ✨")
            )
        
        if user_message == "しりとり開始":
            character_word_list = CHARACTER_WORDS.get(character, [])
        if character_word_list:
            first_word = random.choice(character_word_list)
            shiritori_state[user_id] = {
            "mode": "shiritori",
            "last_char": first_word[-1],
            "used_words": [first_word]
        }
            reply_message = f"{character}「じゃあ、しりとり始めよっか！最初の言葉は『{first_word}』ね♪」"
        else:
            reply_message = f"{character}「ごめん、しりとりの単語が今は用意できてないの…」"

    # --- ユーザーごとのしりとり状態 ---
user_shiritori_map = {}  # { user_id: "前の文字" }

SHIRITORI_WORDS = {
    "tsundere_junior": ["あざとい",   # あ
    "イキリ",     # い
    "うざ絡み",   # う
    "エモい",     # え
    "推し",       # お
    "陰キャ",     # か
    "キュン死",   # き
    "くさ",       # く
    "限界オタク", # け
    "こじらせ",   # こ
    "さぶいぼ",   # さ
    "しんどい",   # し
    "スパダリ",   # す
    "先輩風",     # せ
    "そわそわ",   # そ
    "他担狩り",   # た
    "ちいかわ",   # ち
    "ツンデレ",   # つ
    "てぇてぇ",   # て
    "ときめき",   # と
    "ナチュラル詐欺", # な
    "ぬるオタ",   # ぬ
    "寝落ち",     # ね
    "脳内会議",   # の
    "沼",         # は
    "ひよってる", # ひ
    "フェチ",     # ふ
    "変な夢",     # へ
    "惚気",       # ほ
    "マウント",   # ま
    "ミーハー",   # み
    "無敵メンタル", # む
    "メンヘラ",   # め
    "妄想",       # も
    "ヤバい",     # や
    "ゆるオタ",   # ゆ
    "よき",       # よ
    "ラブラブ",   # ら
    "リアコ",     # り
    "ルッキズム", # る
    "冷め期",     # れ
    "ロールモデル", # ろ
    "わんちゃん", # わ
    "ヲタ活",     # を
    "んちゃ"],     # ん（※終了ワード）

    "kumamoto_mother": ["ありがとう",   # あ
    "イオンモール",     # い（行く途中って意味の方言）
    "うたた寝",     # う
    "縁側",         # え
    "おふろ",       # お
    "株式会社",     # か
    "きばる",       # き（がんばるの熊本弁）
    "くまモン",     # く
    "けはい",       # け（気配）
    "こたつ",       # こ
    "サバの味噌煮",     # さ
    "しょんぼり",   # し
    "すいとーよ",   # す（熊本弁の「好きよ」）
    "せんたくもの", # せ
    "そよ風",       # そ
    "田んぼ",     # た
    "ちくわ",       # ち
    "つまみ",       # つ（晩酌のおとも🍶）
    "てごわい",     # て（強い、手に負えない）
    "とんぼ",       # と（田舎にいっぱいおるね）
    "なつやすみ",   # な
    "ぬくもり",     # ぬ
    "猫カフェ",       # ね
    "飲み会",     # の
    "はなび",       # は
    "ひなたぼっこ", # ひ
    "ふるさと",     # ふ
    "へっちゃら",   # へ
    "ほたる",       # ほ
    "まんじゅう",   # ま
    "みかん",       # み
    "むすび",       # む（おにぎり🍙）
    "めんたいこ",   # め
    "もんぺ",       # も（昔ながらの作業ズボン）
    "やまなみ",     # や（阿蘇の風景！）
    "ゆたんぽ",     # ゆ
    "よかよか",     # よ（熊本弁「いいよ」）
    "らっきょう",   # ら（おばあちゃんの漬物）
    "りんご飴",     # り
    "ルービックキューブ",     # る
    "れいぞうこ",   # れ
    "ろばたやき",   # ろ（炉端焼き🔥）
    "わらびもち",   # わ
    "をどり",       # を（踊り。盆踊りとか）
    "ん〜、だご汁食べたか〜"], # ん（終了語、熊本名物入れてみた）,

    "poetic_counselor": ["あかつき",     # 明け方の静寂
    "いのち",       # 命という尊さ
    "うつろい",     # 移ろい、変化
    "えがお",       # 微笑みの記憶
    "おもかげ",     # 面影、残像
    "かげろう",     # 陽炎、幻想
    "きせき",       # 奇跡・軌跡どちらも含めて
    "くもりぞら",   # 曇り空、感情の象徴
    "けむり",       # 消えていくもの
    "こだま",       # 山彦、心の反響
    "ささやき",     # 囁き、内なる声
    "しずく",       # 雫、涙や雨の比喩
    "すきま",       # 隙間、余白や孤独
    "せかい",       # 世界、広がりと小ささ
    "そらもよう",   # 空模様、気分の変化
    "たましい",     # 魂、内なる光
    "ちいさな花",   # 儚く美しい存在
    "つきひ",       # 月日、時の流れ
    "てのひら",     # ぬくもり、優しさ
    "ともしび",     # 灯火、心の灯
    "なみだ",       # 涙、心の解放
    "ぬくもり",     # 温もり、触れ合い
    "ねがいごと",   # 願いごと、祈り
    "のはら",       # 野原、自由な空間
    "はなことば",   # 花言葉、感情の色
    "ひかり",       # 光、希望の象徴
    "ふるえるこえ", # 震える声、感情の揺れ
    "へいおんか",   # 平穏化、心が落ち着く状態（※造語寄り）
    "ほしぞら",     # 星空、夢と孤独
    "まよなか",     # 真夜中、深い内面
    "みずうみ",     # 湖、鏡のような心
    "むねさわぎ",   # 胸騒ぎ、直感のざわめき
    "めざめ",       # 目覚め、変化の始まり
    "もりのおと",   # 森の音、自然との対話
    "やさしさ",     # 優しさ、包容
    "ゆびさき",     # 指先、繊細な感覚
    "よるのそら",   # 夜の空、静寂と夢
    "らいめい",     # 雷鳴、内面の衝動
    "りんね",       # 輪廻、生と死の循環
    "るりいろ",     # 瑠璃色、幻想的な色彩
    "れいめい",     # 黎明、新たな始まり
    "ろじうら",     # 路地裏、心の奥
    "わすれもの",   # 忘れ物、過去との対話
    "をとめごころ",  # 乙女心、繊細な揺れ 
]
}

def normalize_char(char):
    # ひらがな化
    char = unicodedata.normalize("NFKC", char)
    char = char.lower()
    char = char.replace("ー", "")
    char_map = {
        "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "っ": "つ",
        "ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
        "ゎ": "わ", "ゔ": "う", "ば": "は", "ぱ": "は", "が": "か",
        "だ": "た", "ざ": "さ", "じゃ": "し", "ぢゃ": "ち", "づ": "つ"
    }
    return char_map.get(char, char)

    def get_last_hiragana(word):
        for c in reversed(word):
            if "ぁ" <= c <= "ん":
                return normalize_char(c)
    return None

def get_shiritori_word(last_char, character):
    words = SHIRITORI_WORDS.get(character, [])
    valid_words = [w for w in words if w.startswith(last_char)]
    if not valid_words:
        return None
    return random.choice(valid_words)

    # しりとり中の処理
    if user_id in user_shiritori_map:
            last_char = user_shiritori_map[user_id]

            if user_message == "やめる":
                user_shiritori_map.pop(user_id, None)
                return line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="しりとりを終了したよ。おつかれさま〜"))

            if last_char:
                user_first_char = normalize_char(user_message[0])
            if user_first_char != last_char:
                return line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"「{last_char}」から始めてほしかったんだけど…"))
        
        # 次の文字を取得
            next_char = get_last_hiragana(user_message)
            character = user_character_map.get(user_id, "tsundere_junior")
            bot_word = get_shiritori_word(next_char, character)

            if user_message.endswith("ん"):
                user_shiritori_map.pop(user_id, None)
                return line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text= "「ん」がついたから負けだよ〜〜〜！💥"))

            if not bot_word:
                user_shiritori_map.pop(user_id, None)
                return line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text= f"うぅ…「{next_char}」から始まる言葉、思いつかない…負けた！"))
        
        # BOTの返答から次の頭文字を取得して保存
            next_for_user = get_last_hiragana(bot_word)
            user_shiritori_map[user_id] = next_for_user

            return line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{bot_word}（{next_for_user}）…さあ、次はあなたの番よ！"))

        

    line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_message)
        )
    return "OK"

    if shiritori_state.get(user_id, {}).get("mode") == "shiritori":
    # しりとり継続ロジックを呼び出す
            reply_message = handle_shiritori(user_message, user_id, character)
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_message)
        )
    reply = handle_user_message(user_id, user_message)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
