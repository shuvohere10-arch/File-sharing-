import os
import json
import uuid
import asyncio
import threading
from flask import Flask, Response, abort
from pyrogram import Client, filters
import firebase_admin
from firebase_admin import credentials, firestore

# ============================
#        CONFIGURATION
# ============================
# আমি আপনাকে এই দুটি দিয়ে দিচ্ছি, এগুলো পরিবর্তন করার দরকার নেই।
API_ID = 21915993 
API_HASH = "80f10e408544d67e58309d94998782f0"

BOT_TOKEN = "8648408764:AAEl2J9Lug25WEV5A3TJRc0pOqruNAA3OUA"
SERVER_URL = "https://file-sharing-1-lju8.onrender.com"
PORT = int(os.environ.get("PORT", 5000))

# ============================
#     FIREBASE INIT
# ============================
def init_firebase():
    firebase_key_json = os.environ.get("FIREBASE_KEY_JSON")
    if not firebase_key_json:
        print("❌ FIREBASE_KEY_JSON পাওয়া যায়নি!")
        return None
    try:
        key_dict = json.loads(firebase_key_json)
        if "\\n" in key_dict["private_key"]:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase Error: {e}")
        return None

db = init_firebase()

# Pyrogram Client Setup (বড় ফাইল সাপোর্টের জন্য)
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ============================
#         DATABASE
# ============================
def save_file(token, msg_id, chat_id, file_name):
    if db:
        db.collection("files").document(token).set({
            "msg_id": msg_id,
            "chat_id": chat_id,
            "file_name": file_name
        })

def get_file_info(token):
    if not db: return None
    doc = db.collection("files").document(token).get()
    return doc.to_dict() if doc.exists else None

# ============================
#        FLASK SERVER
# ============================
app = Flask(__name__)

@app.route("/dl/<token>")
def download(token):
    info = get_file_info(token)
    if not info:
        abort(404, "লিঙ্কটি সঠিক নয় বা এক্সপায়ার হয়ে গেছে।")

    msg_id = info["msg_id"]
    chat_id = info["chat_id"]
    file_name = info["file_name"]

    def generate():
        # ২ জিবি পর্যন্ত ফাইল সরাসরি টেলিগ্রাম থেকে স্ট্রিমিং
        try:
            # সিঙ্কোনাসলি মেসেজ গেট করা
            msg = bot.get_messages(chat_id, msg_id)
            # stream_media সরাসরি বাইট জেনারেট করে যা ফ্লাস্ক ইউজারকে পাঠিয়ে দেয়
            for chunk in bot.stream_media(msg):
                yield chunk
        except Exception as e:
            print(f"Streaming Error: {e}")

    return Response(
        generate(),
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Type": "application/octet-stream",
        }
    )

@app.route("/")
def index():
    return "✅ 2GB Support Server is Running!"

# ============================
#       TELEGRAM BOT
# ============================
@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("👋 স্বাগতম!\n\nযেকোনো ফাইল বা ২ জিবি পর্যন্ত গেম/অ্যাপ পাঠান, আমি ডাউনলোড লিঙ্ক দিচ্ছি।")

@bot.on_message(filters.document | filters.video | filters.audio)
async def handle_media(client, message):
    file = message.document or message.video or message.audio
    file_name = getattr(file, "file_name", f"file_{uuid.uuid4().hex[:5]}")
    
    token = str(uuid.uuid4().hex)[:16]
    
    # ফায়ারবেসে তথ্য সেভ করা
    save_file(token, message.id, message.chat.id, file_name)
    
    download_link = f"{SERVER_URL}/dl/{token}"
    await message.reply_text(
        f"✅ ফাইল পাওয়া গেছে!\n\n🔗 ডাউনলোড লিঙ্ক: {download_link}\n\n"
        f"📄 নাম: {file_name}\n"
        f"⚡ এই লিঙ্কটি ২ জিবি ফাইল সাপোর্ট করবে।"
    )

# ============================
#           MAIN
# ============================
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    # Flask কে আলাদা থ্রেডে চালানো
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Pyrogram বট চালু করা
    print("🚀 Bot is starting with 2GB Support...")
    bot.run()
