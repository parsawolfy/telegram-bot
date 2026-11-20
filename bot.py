import os
import threading
import time
import telebot
from flask import Flask
from supabase import create_client, Client
from telebot import types

# --- تنظیمات اصلی ---
TOKEN = "9097671626:AAGAChTkueWdX3FW1bpsiGo2x5jiiiK-JJ0"
ADMIN_ID = 5995862782
CHANNEL_URL = "https://t.me/bot_Sazy"  # آدرس کانال بدون جوین اجباری

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# وب‌سرور Flask برای پاسخ به پورت Render
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is alive and running", 200


# --- توابع کمکی دیتابیس ---
def get_setting(key: str, default_text: str) -> str:
    if not supabase:
        return default_text
    try:
        res = supabase.table("bot_settings").select("value").eq("key", key).execute()
        if res.data and len(res.data) > 0:
            return res.data[0].get("value") or default_text
    except Exception as e:
        print(f"Error reading setting {key}: {e}")
    return default_text


def set_setting(key: str, value: str) -> bool:
    if not supabase:
        return False
    try:
        supabase.table("bot_settings").upsert({"key": key, "value": value}).execute()
        return True
    except Exception as e:
        print(f"Error saving setting {key}: {e}")
        return False


def register_user(user: types.User) -> None:
    if not supabase:
        return
    try:
        supabase.table("users").upsert({
            "user_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or ""
        }).execute()
    except Exception as e:
        print(f"Error registering user {user.id}: {e}")


def get_all_user_ids() -> list:
    if not supabase:
        return []
    try:
        res = supabase.table("users").select("user_id").execute()
        return [row["user_id"] for row in (res.data or []) if "user_id" in row]
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []


def build_channel_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 کانال ربات‌سازی", url=CHANNEL_URL))
    return markup


# --- وضعیت موقت ادمین‌ها ---
admin_states = {}
temp_add_data = {}


# --- دستورات کاربران ---
@bot.message_handler(commands=["start"])
def handle_start(message: types.Message):
    register_user(message.from_user)
    welcome_msg = get_setting(
        "welcome_text",
        "سلام! به ربات خوش آمدید.\nکد موزیک یا ساندترک مورد نظرت را بفرست."
    )
    bot.send_message(message.chat.id, welcome_msg, reply_markup=build_channel_markup())


# --- دستورات ادمین ---
@bot.message_handler(commands=["settext"])
def handle_settext(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("ویرایش متن خوش‌آمدگویی", callback_data="edit_welcome_text"))
    markup.add(types.InlineKeyboardButton("ویرایش متن پیدا نشدن کد", callback_data="edit_not_found_text"))
    bot.send_message(message.chat.id, "کدام متن را می‌خواهی تغییر بدهی؟", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def handle_edit_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    key_name = call.data.replace("edit_", "")
    admin_states[call.from_user.id] = {"action": "awaiting_text_value", "key": key_name}
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"متن جدید برای <code>{key_name}</code> را ارسال کن:")


@bot.message_handler(commands=["add"])
def handle_add_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_states[message.from_user.id] = {"action": "add_code"}
    temp_add_data[message.from_user.id] = {}
    bot.send_message(message.chat.id, "کد اختصاصی پست موزیک را بفرست (مثلاً <code>101</code>):")


@bot.message_handler(commands=["sendall"])
def handle_sendall_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_states[message.from_user.id] = {"action": "awaiting_broadcast"}
    bot.send_message(message.chat.id, "پیام همگانی (متن، عکس، ویدیو یا فایل صوتی) را بفرست تا با وقفه ایمن ارسال شود:")


def run_safe_broadcast(admin_chat_id: int, source_chat_id: int, source_message_id: int):
    user_ids = get_all_user_ids()
    success_count = 0
    fail_count = 0

    bot.send_message(admin_chat_id, f"ارسال همگانی برای {len(user_ids)} کاربر با وقفه ایمن شروع شد...")

    for index, uid in enumerate(user_ids, start=1):
        try:
            bot.copy_message(chat_id=uid, from_chat_id=source_chat_id, message_id=source_message_id)
            success_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            fail_count += 1
            if e.error_code == 429:
                retry_after = 5
                if isinstance(e.result_json, dict):
                    retry_after = e.result_json.get("parameters", {}).get("retry_after", 5)
                time.sleep(min(int(retry_after) + 1, 15))
        except Exception:
            fail_count += 1

        time.sleep(0.15)
        if index % 30 == 0:
            time.sleep(1.5)

    bot.send_message(
        admin_chat_id,
        f"ارسال همگانی تمام شد.\nموفق: <b>{success_count}</b>\nناموفق: <b>{fail_count}</b>"
    )


# --- پردازش پیام‌های متنی و مراحل ثبت پست ---
@bot.message_handler(content_types=["text", "audio", "video", "photo", "document"])
def handle_messages(message: types.Message):
    user_id = message.from_user.id
    register_user(message.from_user)

    if user_id == ADMIN_ID and user_id in admin_states:
        state = admin_states[user_id]
        action = state.get("action")

        if action == "awaiting_text_value" and message.text:
            key = state.get("key")
            if set_setting(key, message.text):
                bot.send_message(message.chat.id, f"متن <code>{key}</code> با موفقیت ذخیره شد.")
            else:
                bot.send_message(message.chat.id, "خطا در ذخیره متن در دیتابیس.")
            del admin_states[user_id]
            return

        elif action == "awaiting_broadcast":
            del admin_states[user_id]
            threading.Thread(
                target=run_safe_broadcast,
                args=(message.chat.id, message.chat.id, message.message_id),
                daemon=True
            ).start()
            return

        elif action == "add_code" and message.text:
            temp_add_data[user_id]["code"] = message.text.strip()
            admin_states[user_id]["action"] = "add_audio"
            bot.send_message(message.chat.id, "حالا فایل صوتی (Audio) را بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_audio":
            if message.text and message.text.strip() == "رد":
                temp_add_data[user_id]["audio_id"] = None
            elif message.audio:
                temp_add_data[user_id]["audio_id"] = message.audio.file_id
            else:
                bot.send_message(message.chat.id, "لطفاً یک فایل صوتی بفرست یا کلمه <code>رد</code> را بنویس.")
                return
            admin_states[user_id]["action"] = "add_video"
            bot.send_message(message.chat.id, "حالا فایل ویدیو را بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_video":
            if message.text and message.text.strip() == "رد":
                temp_add_data[user_id]["video_id"] = None
            elif message.video:
                temp_add_data[user_id]["video_id"] = message.video.file_id
            else:
                bot.send_message(message.chat.id, "لطفاً یک ویدیو بفرست یا کلمه <code>رد</code> را بنویس.")
                return
            admin_states[user_id]["action"] = "add_caption"
            bot.send_message(message.chat.id, "متن توضیحات را بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_caption":
            caption_val = "" if (message.text and message.text.strip() == "رد") else (message.text or "")
            post_info = temp_add_data.get(user_id, {})
            post_info["caption"] = caption_val

            if supabase:
                try:
                    supabase.table("music_posts").upsert({
                        "code": post_info.get("code"),
                        "audio_file_id": post_info.get("audio_id"),
                        "video_file_id": post_info.get("video_id"),
                        "caption": post_info.get("caption")
                    }).execute()
                    bot.send_message(message.chat.id, f"پست با کد <code>{post_info.get('code')}</code> ذخیره شد.")
                except Exception as e:
                    bot.send_message(message.chat.id, f"خطا در ثبت پست: {e}")

            del admin_states[user_id]
            temp_add_data.pop(user_id, None)
            return

    if message.text and supabase:
        code_query = message.text.strip()
        try:
            res = supabase.table("music_posts").select("*").eq("code", code_query).execute()
            if res.data and len(res.data) > 0:
                item = res.data[0]
                caption = item.get("caption") or ""
                if item.get("video_file_id"):
                    bot.send_video(message.chat.id, item["video_file_id"], caption=caption)
                if item.get("audio_file_id"):
                    bot.send_audio(message.chat.id, item["audio_file_id"], caption=caption)
                if not item.get("video_file_id") and not item.get("audio_file_id"):
                    bot.send_message(message.chat.id, caption or "محتوا یافت شد.")
            else:
                not_found_msg = get_setting("not_found_text", "کد واردشده در سیستم پیدا نشد.")
                bot.send_message(message.chat.id, not_found_msg)
        except Exception as e:
            print(f"Search error: {e}")


# --- اجرای هم‌زمان Flask و Polling ربات ---
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def run_bot_polling():
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=20,
                long_polling_timeout=20
            )
        except Exception as e:
            print(f"Polling error, retrying in 5s: {e}")
            time.sleep(5)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_bot_polling()
