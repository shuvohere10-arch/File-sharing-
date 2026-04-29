import os
import json
import uuid
import requests
import threading
from flask import Flask, Response, abort
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore

# ============================
#        CONFIGURATION
# ============================
BOT_TOKEN = "8648408764:AAF0uIM2SRdF2ZDpSplU-9B0t4YovIGYEY4"
SERVER_URL = "https://youtube-23vo.onrender.com"  # তোমার server এর URL
PORT = 5000

# ============================
#     FIREBASE INIT
# ============================
def init_firebase():
    """
    Environment Variable থেকে Firebase key লোড করে।
    Render Dashboard → Environment → FIREBASE_KEY_JSON নামে
    firebase_key.json এর সম্পূর্ণ JSON content paste করতে হবে।
    """
    firebase_key_json = os.environ.get("FIREBASE_KEY_JSON")
    if not firebase_key_json:
        raise ValueError("FIREBASE_KEY_JSON environment variable সেট করা নেই!")

    key_dict = json.loads(firebase_key_json)
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

# ============================
#         DATABASE (Firestore)
# ============================
def save_file(token: str, file_id: str, file_name: str):
    """Firestore-এ ফাইলের তথ্য সেভ করে।"""
    db.collection("files").document(token).set({
        "file_id": file_id,
        "file_name": file_name
    })

def get_file_info(token: str):
    """Token দিয়ে Firestore থেকে ফাইলের তথ্য খোঁজে। পাওয়া গেলে (file_id, file_name) tuple, না হলে None।"""
    doc = db.collection("files").document(token).get()
    if doc.exists:
        data = doc.to_dict()
        return data["file_id"], data["file_name"]
    return None

# ============================
#        FLASK SERVER
# ============================
app = Flask(__name__)

@app.route("/dl/<token>")
def download(token):
    result = get_file_info(token)
    if not result:
        abort(404, "লিংকটি সঠিক নয়।")

    file_id, file_name = result

    tg_response = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        params={"file_id": file_id}
    )
    data = tg_response.json()

    if not data.get("ok"):
        abort(500, "Telegram থেকে ফাইল পাওয়া যায়নি।")

    file_path = data["result"]["file_path"]
    tg_file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    tg_file = requests.get(tg_file_url, stream=True)

    def generate():
        for chunk in tg_file.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    return Response(
        generate(),
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Type": tg_file.headers.get("Content-Type", "application/octet-stream"),
        }
    )

@app.route("/")
def index():
    return "✅ Server চালু আছে!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ============================
#       TELEGRAM BOT
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 স্বাগতম!\n\nযেকোনো ফাইল পাঠাও, আমি তোমাকে একটা ডাউনলোড লিংক দেব।\n📁 ফাইল সাইজ সর্বোচ্চ 2GB।"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "file"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"video_{message.video.file_id[-6:]}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or f"audio_{message.audio.file_id[-6:]}.mp3"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"photo_{message.photo[-1].file_id[-6:]}.jpg"
    else:
        await message.reply_text("❌ এই ধরনের ফাইল সাপোর্ট করে না।")
        return

    token = str(uuid.uuid4()).replace("-", "")[:16]
    save_file(token, file_id, file_name)

    download_link = f"{SERVER_URL}/dl/{token}"
    await message.reply_text(
        f"✅ তোমার ডাউনলোড লিংক:\n\n🔗 {download_link}\n\n"
        f"📄 ফাইল: {file_name}\n\n"
        f"এই লিংক কখনো নষ্ট হবে না!"
    )

# ============================
#           MAIN
# ============================
if __name__ == "__main__":
    # Flask আলাদা thread এ চালাও
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"✅ Server চালু: http://0.0.0.0:{PORT}")

    # Telegram Bot চালাও
    print("✅ Bot চালু হয়েছে...")
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO, handle_file))
    telegram_app.run_polling()
