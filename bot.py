import os
import threading
import time
import traceback
from typing import Optional
import telebot
from flask import Flask
from supabase import create_client, Client
from telebot import types

# --- تنظیمات اصلی ---
TOKEN = "9097671626:AAGAChTkueWdX3FW1bpsiGo2x5jiiiK-JJ0"
ADMIN_ID = 5995862782
CHANNEL_URL = "https://t.me/bot_Sazy"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
if SUPABASE_URL.endswith("/rest/v1"):
    SUPABASE_URL = SUPABASE_URL[:-8]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

DEFAULT_WELCOME_TEXT = (
    "👋✨ <b>سلام و خوش اومدی!</b>\n\n"
    "🎬🎧 برای دریافت ویدیو یا موزیک مورد نظرت، کافیه <b>کد اختصاصی</b> اون رو همین‌جا برام بفرستی.\n\n"
    "📢 از طریق دکمه زیر هم می‌تونی به کانال سر بزنی:"
)

DEFAULT_NOT_FOUND_TEXT = (
    "🔍❌ <b>کد مورد نظر پیدا نشد!</b>\n\n"
    "ممکنه کد رو اشتباه وارد کرده باشی یا هنوز توی سیستم ثبت نشده باشه.\n"
    "✨ لطفاً کد رو دوباره بررسی کن و بفرست."
)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")


def init_supabase() -> Optional[Client]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ SUPABASE_URL یا SUPABASE_KEY تنظیم نشده است.")
        return None
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ اتصال به Supabase برقرار شد.")
        return client
    except Exception as e:
        print(f"❌ خطا در اتصال به Supabase: {e}")
        traceback.print_exc()
        return None


supabase: Optional[Client] = init_supabase()

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
        res = supabase.table("bot_settings").select("value").eq("key", key).limit(1).execute()
        if res.data and len(res.data) > 0:
            val = res.data[0].get("value")
            if val and str(val).strip():
                return str(val)
    except Exception as e:
        print(f"⚠️ خطا در خواندن تنظیمات ({key}): {e}")
    return default_text


def set_setting(key: str, value: str) -> bool:
    if not supabase:
        return False
    try:
        supabase.table("bot_settings").upsert({"key": key, "value": value}).execute()
        return True
    except Exception as e:
        print(f"❌ خطا در ذخیره تنظیمات ({key}): {e}")
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
        print(f"⚠️ خطا در ثبت کاربر {user.id}: {e}")


def get_all_user_ids() -> list:
    if not supabase:
        return []
    try:
        res = supabase.table("users").select("user_id").execute()
        return [row["user_id"] for row in (res.data or []) if row.get("user_id") is not None]
    except Exception as e:
        print(f"⚠️ خطا در دریافت لیست کاربران: {e}")
        return []


def find_post_by_code(code_str: str) -> Optional[dict]:
    if not supabase:
        return None

    clean_code = code_str.strip()
    if not clean_code:
        return None

    try:
        res = supabase.table("music_posts").select("*").eq("code", clean_code).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        print(f"⚠️ خطا در جستجوی متنی کد '{clean_code}': {e}")

    if clean_code.isdigit():
        try:
            res = supabase.table("music_posts").select("*").eq("code", int(clean_code)).limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            print(f"⚠️ خطا در جستجوی عددی کد '{clean_code}': {e}")

    return None


def get_likes_count(code_str: str) -> int:
    if not supabase:
        return 0
    try:
        # ابتدا تلاش برای خواندن از جدول likes (در صورت وجود)
        res = supabase.table("likes").select("user_id").eq("code", str(code_str)).execute()
        if res.data is not None:
            return len(res.data)
    except Exception:
        pass

    # fallback به ستون likes در جدول music_posts
    post = find_post_by_code(str(code_str))
    if post and post.get("likes") is not None:
        try:
            return max(0, int(post.get("likes")))
        except Exception:
            return 0
    return 0


def toggle_like(code_str: str, user_id: int) -> tuple[bool, int]:
    """
    اگر کاربر قبلاً لایک کرده باشد، لایک را حذف می‌کند (False)؛
    در غیر این صورت لایک ثبت می‌کند (True).
    خروجی: (آیا الان لایک شده است؟, تعداد کل لایک‌ها)
    """
    clean_code = str(code_str).strip()
    if not supabase:
        return False, 0

    # روش اول: استفاده از جدول اختصاصی likes با ستون‌های (code, user_id)
    try:
        existing = (
            supabase.table("likes")
            .select("user_id")
            .eq("code", clean_code)
            .eq("user_id", user_id)
            .execute()
        )
        already_liked = bool(existing.data and len(existing.data) > 0)

        if already_liked:
            supabase.table("likes").delete().eq("code", clean_code).eq("user_id", user_id).execute()
            liked_now = False
        else:
            supabase.table("likes").upsert({"code": clean_code, "user_id": user_id}).execute()
            liked_now = True

        count_res = supabase.table("likes").select("user_id").eq("code", clean_code).execute()
        total_likes = len(count_res.data or [])

        # همگام‌سازی ستون likes در music_posts در صورت وجود
        try:
            supabase.table("music_posts").update({"likes": total_likes}).eq("code", clean_code).execute()
        except Exception:
            pass

        return liked_now, total_likes

    except Exception as table_err:
        print(f"ℹ️ استفاده از روش جایگزین لایک (جدول likes): {table_err}")

    # روش جایگزین: اگر جدول likes ساخته نشده باشد، از ستون likes در music_posts استفاده می‌کند
    post = find_post_by_code(clean_code)
    current_likes = 0
    if post and post.get("likes") is not None:
        try:
            current_likes = max(0, int(post.get("likes")))
        except Exception:
            current_likes = 0

    new_likes = max(0, current_likes + 1)
    try:
        supabase.table("music_posts").update({"likes": new_likes}).eq("code", clean_code).execute()
    except Exception as e:
        print(f"⚠️ خطا در آپدیت لایک: {e}")

    return True, new_likes


def build_channel_markup() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 کانال ربات‌سازی", url=CHANNEL_URL))
    return markup


def build_music_actions_markup(code_str: str, likes_count: int, user_liked: bool = False) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(row_width=2)
    heart_icon = "❤️" if user_liked else "🤍"
    like_btn = types.InlineKeyboardButton(
        f"{heart_icon} لایک ({likes_count})",
        callback_data=f"like:{code_str}"
    )
    share_btn = types.InlineKeyboardButton(
        "🔗 اشتراک‌گذاری",
        callback_data=f"share:{code_str}"
    )
    markup.add(like_btn, share_btn)
    return markup


# --- وضعیت موقت ادمین‌ها ---
admin_states = {}
temp_add_data = {}


# --- دستورات کاربران ---
@bot.message_handler(commands=["start"])
def handle_start(message: types.Message):
    register_user(message.from_user)
    welcome_msg = get_setting("welcome_text", DEFAULT_WELCOME_TEXT)
    bot.send_message(message.chat.id, welcome_msg, reply_markup=build_channel_markup())


# --- دکمه‌های لایک و اشتراک‌گذاری ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("like:") or call.data.startswith("share:"))
def handle_music_actions(call: types.CallbackQuery):
    user_id = call.from_user.id
    register_user(call.from_user)

    if call.data.startswith("like:"):
        code_str = call.data.split(":", 1)[1].strip()
        liked_now, total_likes = toggle_like(code_str, user_id)

        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=build_music_actions_markup(code_str, total_likes, user_liked=liked_now)
            )
        except Exception as e:
            print(f"⚠️ خطا در ویرایش دکمه لایک: {e}")

        toast_text = "❤️ لایک شما ثبت شد!" if liked_now else "💔 لایک شما برداشته شد."
        bot.answer_callback_query(call.id, toast_text)

    elif call.data.startswith("share:"):
        code_str = call.data.split(":", 1)[1].strip()
        bot_username = ""
        try:
            me = bot.get_me()
            bot_username = me.username or ""
        except Exception:
            pass

        if bot_username:
            share_link = f"https://t.me/{bot_username}?start={code_str}"
            share_text = (
                f"🎧🎬 <b>لینک اختصاصی کد <code>{code_str}</code>:</b>\n"
                f"<code>{share_link}</code>\n\n"
                f"کافیه این لینک رو برای دوستانت بفرستی یا کد <code>{code_str}</code> رو داخل ربات بفرستن."
            )
        else:
            share_text = (
                f"🎧🎬 برای دریافت این پست، کد <code>{code_str}</code> رو داخل ربات بفرست!"
            )

        bot.answer_callback_query(call.id, "🔗 لینک اشتراک‌گذاری آماده شد.")
        bot.send_message(call.message.chat.id, share_text)


# --- دستورات ادمین ---
@bot.message_handler(commands=["settext"])
def handle_settext(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✏️ ویرایش متن خوش‌آمدگویی", callback_data="edit_welcome_text"))
    markup.add(types.InlineKeyboardButton("❌ ویرایش متن پیدا نشدن کد", callback_data="edit_not_found_text"))
    bot.send_message(message.chat.id, "🛠️ کدوم متن رو می‌خوای تغییر بدی؟", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def handle_edit_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    key_name = call.data.replace("edit_", "", 1)
    admin_states[call.from_user.id] = {"action": "awaiting_text_value", "key": key_name}
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"✍️ متن جدید برای <code>{key_name}</code> رو بفرست:")


@bot.message_handler(commands=["add"])
def handle_add_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_states[message.from_user.id] = {"action": "add_code"}
    temp_add_data[message.from_user.id] = {}
    bot.send_message(message.chat.id, "🔢 کد اختصاصی پست رو بفرست (مثلاً <code>101</code>):")


@bot.message_handler(commands=["sendall"])
def handle_sendall_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_states[message.from_user.id] = {"action": "awaiting_broadcast"}
    bot.send_message(message.chat.id, "📣 پیام همگانی رو بفرست تا با وقفه ایمن برای همه ارسال بشه:")


def run_safe_broadcast(admin_chat_id: int, source_chat_id: int, source_message_id: int):
    user_ids = get_all_user_ids()
    success_count = 0
    fail_count = 0

    bot.send_message(admin_chat_id, f"🚀 ارسال همگانی برای <b>{len(user_ids)}</b> کاربر شروع شد...")

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
        f"✅ ارسال همگانی تمام شد!\n"
        f"✔️ موفق: <b>{success_count}</b>\n"
        f"✖️ ناموفق: <b>{fail_count}</b>"
    )


# --- پردازش پیام‌ها ---
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
                bot.send_message(message.chat.id, f"✅ متن <code>{key}</code> با موفقیت ذخیره شد.")
            else:
                bot.send_message(message.chat.id, "❌ خطا در ذخیره متن در دیتابیس.")
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
            bot.send_message(message.chat.id, "🎵 حالا فایل صوتی (Audio) رو بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_audio":
            if message.text and message.text.strip() == "رد":
                temp_add_data[user_id]["audio_id"] = None
            elif message.audio:
                temp_add_data[user_id]["audio_id"] = message.audio.file_id
            else:
                bot.send_message(message.chat.id, "⚠️ لطفاً فایل صوتی بفرست یا کلمه <code>رد</code> رو بنویس.")
                return
            admin_states[user_id]["action"] = "add_video"
            bot.send_message(message.chat.id, "🎬 حالا فایل ویدیو رو بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_video":
            if message.text and message.text.strip() == "رد":
                temp_add_data[user_id]["video_id"] = None
            elif message.video:
                temp_add_data[user_id]["video_id"] = message.video.file_id
            else:
                bot.send_message(message.chat.id, "⚠️ لطفاً یک ویدیو بفرست یا کلمه <code>رد</code> رو بنویس.")
                return
            admin_states[user_id]["action"] = "add_caption"
            bot.send_message(message.chat.id, "📝 متن توضیحات رو بفرست (یا بنویس <code>رد</code>):")
            return

        elif action == "add_caption":
            caption_val = "" if (message.text and message.text.strip() == "رد") else (message.text or "")
            post_info = temp_add_data.get(user_id, {})
            post_info["caption"] = caption_val

            if not supabase:
                bot.send_message(message.chat.id, "❌ اتصال به دیتابیس برقرار نیست.")
            else:
                try:
                    supabase.table("music_posts").upsert({
                        "code": post_info.get("code"),
                        "audio_file_id": post_info.get("audio_id"),
                        "video_file_id": post_info.get("video_id"),
                        "caption": post_info.get("caption")
                    }).execute()
                    bot.send_message(message.chat.id, f"✅ پست با کد <code>{post_info.get('code')}</code> ذخیره شد.")
                except Exception as e:
                    bot.send_message(message.chat.id, f"❌ خطا در ثبت پست: {e}")

            del admin_states[user_id]
            temp_add_data.pop(user_id, None)
            return

    if message.text:
        if not supabase:
            bot.send_message(message.chat.id, "⚠️ ارتباط با دیتابیس موقتاً در دسترس نیست. لطفاً کمی بعد تلاش کن.")
            return

        code_query = message.text.strip()
        post = find_post_by_code(code_query)

        if not post:
            not_found_msg = get_setting("not_found_text", DEFAULT_NOT_FOUND_TEXT)
            bot.send_message(message.chat.id, not_found_msg)
            return

        print("📦 Post data from DB:", post)

        caption = (post.get("caption") or "").strip()
        video_id = post.get("video_file_id")
        audio_id = post.get("audio_file_id")
        actual_code = str(post.get("code") or code_query).strip()
        sent_any = False

        # ۱. ابتدا ویدیو همراه با توضیحات ارسال می‌شود
        if video_id:
            try:
                bot.send_video(message.chat.id, video_id, caption=caption or None)
                sent_any = True
            except Exception as e:
                print(f"❌ خطا در ارسال ویدیو برای کد {code_query} با id={video_id}: {repr(e)}")
                try:
                    bot.send_message(message.chat.id, f"⚠️ ارسال ویدیو با خطا مواجه شد: {e}")
                except Exception:
                    pass

        # ۲. سپس موزیک (فایل صوتی) همراه با دکمه‌های لایک و اشتراک‌گذاری ارسال می‌شود
        likes_count = get_likes_count(actual_code)
        actions_markup = build_music_actions_markup(actual_code, likes_count, user_liked=False)

        if audio_id:
            try:
                bot.send_audio(
                    message.chat.id,
                    audio_id,
                    caption=caption if (not sent_any and caption) else None,
                    reply_markup=actions_markup
                )
                sent_any = True
            except Exception as e:
                print(f"❌ خطا در ارسال صوت برای کد {code_query} با id={audio_id}: {repr(e)}")
                try:
                    bot.send_message(message.chat.id, f"⚠️ ارسال فایل صوتی با خطا مواجه شد: {e}")
                except Exception:
                    pass
                # اگر موزیک خطا داد ولی ویدیو رفته بود، دکمه‌های لایک و اشتراک‌گذاری را در یک پیام بفرست
                if sent_any:
                    try:
                        bot.send_message(message.chat.id, "🎛️ گزینه‌های تعامل:", reply_markup=actions_markup)
                    except Exception:
                        pass

        # ۳. اگر هیچ فایلی ارسال نشد ولی توضیحات وجود داشت یا پستی پیدا شده بود
        if not sent_any:
            if caption:
                bot.send_message(message.chat.id, caption, reply_markup=actions_markup)
            else:
                bot.send_message(message.chat.id, "ℹ️ برای این کد فایل ویدیو یا صوت ثبت نشده است.", reply_markup=actions_markup)


# --- اجرای هم‌زمان Flask و Polling ربات ---
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def run_bot_polling():
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=20,
                long_polling_timeout=20
            )
        except Exception as e:
            print(f"⚠️ خطای Polling، تلاش مجدد در ۵ ثانیه: {e}")
            time.sleep(5)


if __name__ == "__main__":
    try:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        run_bot_polling()
    except Exception as e:
        print(f"❌ خطای بحرانی در اجرای برنامه: {e}")
        traceback.print_exc()
        time.sleep(10)
