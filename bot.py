"""
بوت تليجرام لتحميل الصوت والفيديو من يوتيوب
يعتمد فقط على SHRUTI API
ملف واحد فقط - بدون أي مكتبات خارجية (لا pyrogram ولا aiohttp)
يستخدم فقط مكتبات بايثون القياسية (urllib) + Telegram Bot API مباشرة عبر HTTP

التشغيل:
    python bot.py
(لا يحتاج أي pip install على الإطلاق)
"""

import os
import re
import json
import time
import uuid
import mimetypes
import urllib.request
import urllib.parse
import urllib.error

# ============ إعدادات ============
API_ID = os.environ.get("API_ID", "21802065")
API_HASH = os.environ.get("API_HASH", "2a8d929f6584561a32fc93e1f044652d")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

SHRUTI_API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
SHRUTI_API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsd9AApWQ1DQf9z4dXvJp7")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DOWNLOAD_DIR = "downloads"
YT_LINK_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{6,})"
)


# ============ أدوات مساعدة لطلبات HTTP (بدون مكتبات خارجية) ============
def _http_get_json(url, params=None, timeout=60):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _encode_multipart(fields, files):
    """
    fields: dict نصية عادية
    files: dict {form_field_name: (file_name, file_path)}
    """
    boundary = uuid.uuid4().hex
    body = bytearray()

    for key, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()

    for key, (filename, filepath) in files.items():
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
        ).encode()
        body += f"Content-Type: {mime_type}\r\n\r\n".encode()
        with open(filepath, "rb") as f:
            body += f.read()
        body += b"\r\n"

    body += f"--{boundary}--\r\n".encode()
    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


def _http_post_multipart(url, fields, files, timeout=600):
    body, content_type = _encode_multipart(fields, files)
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": content_type}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ============ دوال تيليجرام ============
def tg_get_updates(offset=None, timeout=30):
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    try:
        return _http_get_json(f"{TELEGRAM_API}/getUpdates", params, timeout=timeout + 15)
    except Exception as e:
        print(f"⚠️ خطأ في getUpdates: {e}")
        return {"ok": False, "result": []}


def tg_send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        return _http_post_json(f"{TELEGRAM_API}/sendMessage", payload)
    except Exception as e:
        print(f"⚠️ خطأ في sendMessage: {e}")
        return None


def tg_edit_message(chat_id, message_id, text):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    try:
        return _http_post_json(f"{TELEGRAM_API}/editMessageText", payload)
    except Exception as e:
        print(f"⚠️ خطأ في editMessageText: {e}")
        return None


def tg_delete_message(chat_id, message_id):
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        return _http_post_json(f"{TELEGRAM_API}/deleteMessage", payload)
    except Exception:
        return None


def tg_answer_callback(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        return _http_post_json(f"{TELEGRAM_API}/answerCallbackQuery", payload)
    except Exception:
        return None


def tg_send_audio(chat_id, file_path, caption=""):
    fields = {"chat_id": str(chat_id), "caption": caption}
    files = {"audio": (os.path.basename(file_path), file_path)}
    return _http_post_multipart(f"{TELEGRAM_API}/sendAudio", fields, files)


def tg_send_video(chat_id, file_path, caption=""):
    fields = {"chat_id": str(chat_id), "caption": caption}
    files = {"video": (os.path.basename(file_path), file_path)}
    return _http_post_multipart(f"{TELEGRAM_API}/sendVideo", fields, files)


# ============ استخراج رابط يوتيوب ============
def extract_video_id(text):
    match = YT_LINK_REGEX.search(text or "")
    if match:
        return match.group(1)
    return None


# ============ تحميل من SHRUTI API ============
def download_from_api(video_id, media_type):
    """
    media_type: 'audio' أو 'video'
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ext = "mp3" if media_type == "audio" else "mp4"
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    params = {"url": video_id, "type": media_type, "api_key": SHRUTI_API_KEY}
    url = f"{SHRUTI_API_URL}/download?{urllib.parse.urlencode(params)}"
    timeout = 300 if media_type == "audio" else 600

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            with open(file_path, "wb") as f:
                while True:
                    chunk = resp.read(131072)
                    if not chunk:
                        break
                    f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        print(f"⚠️ خطأ في التحميل: {e}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


# ============ معالجة الرسائل ============
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text.strip() == "/start":
        tg_send_message(
            chat_id,
            "👋 أهلاً بك!\n\n"
            "أرسل لي رابط فيديو يوتيوب وسأقوم بتحميله لك (صوت أو فيديو).\n\n"
            "مثال:\nhttps://www.youtube.com/watch?v=XXXXXXXXXXX",
        )
        return

    video_id = extract_video_id(text)
    if not video_id:
        return

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🎵 تحميل صوت", "callback_data": f"dl_audio_{video_id}"},
                {"text": "🎥 تحميل فيديو", "callback_data": f"dl_video_{video_id}"},
            ]
        ]
    }
    tg_send_message(chat_id, "اختر نوع التحميل الذي تريده:", reply_markup=reply_markup)


def handle_callback(callback_query):
    data = callback_query.get("data", "")
    match = re.match(r"^dl_(audio|video)_(.+)$", data)
    if not match:
        return

    media_type, video_id = match.group(1), match.group(2)
    message = callback_query["message"]
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    tg_answer_callback(callback_query["id"])
    tg_edit_message(chat_id, message_id, "⏳ جاري التحميل، الرجاء الانتظار...")

    file_path = download_from_api(video_id, media_type)

    if not file_path:
        tg_edit_message(chat_id, message_id, "❌ فشل التحميل، حاول مرة أخرى لاحقاً.")
        return

    tg_edit_message(chat_id, message_id, "📤 جاري الرفع إلى تليجرام...")

    try:
        if media_type == "audio":
            tg_send_audio(chat_id, file_path, caption="✅ تم التحميل بنجاح")
        else:
            tg_send_video(chat_id, file_path, caption="✅ تم التحميل بنجاح")
        tg_delete_message(chat_id, message_id)
    except Exception as e:
        tg_edit_message(chat_id, message_id, f"❌ حدث خطأ أثناء الرفع: {e}")


# ============ الحلقة الرئيسية (Long Polling) ============
def main():
    print("✅ البوت يعمل الآن...")
    offset = None

    while True:
        result = tg_get_updates(offset=offset, timeout=30)
        if not result.get("ok"):
            time.sleep(3)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1

            try:
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
            except Exception as e:
                print(f"⚠️ خطأ أثناء معالجة التحديث: {e}")


if __name__ == "__main__":
    main()
