import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# ----------------------------------------------------
# تنظیمات اختصاصی ربات، کانال و دیتابیس Supabase
# ----------------------------------------------------
TOKEN = "8310861690:AAH0_9qwNItT9WEmAFC0QNe7CFJPNw_VWcY"
ADMIN_ID = 5995862782

# تنظیمات کانال جدید
CHANNEL_USERNAME = "@bot_Sazy"

SUPABASE_URL = "https://badmbeumihdpjywddkli.supabase.co"
SUPABASE_KEY = "sb_publishable_lMDNtw6RhPcviwWxdLMjcw_UzNeQ8GF"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
admin_states = {}

# ----------------------------------------------------
# مدیریت متون پویا در دیتابیس bot_settings
# ----------------------------------------------------
DEFAULT_TEXTS = {
    "welcome_text": (
        "✨ <b>به ساندترک خوش اومدی!</b> ✨\n\n"
        "🎧 <b>بهترین ربات آهنگ یاب</b>\n\n"
        "فقط کد آهنگ رو بفرست و در چند ثانیه آهنگ کامل و اطلاعاتش همراه با ویدیو برات میفرستم."
    ),
    "join_text": (
        "⚠️ <b>برای استفاده از ربات ابتدا باید در کانال ما عضو شوید!</b>\n\n"
        "پس از عضویت، روی دکمه <b>«✅ عضو شدم»</b> کلیک کنید."
    ),
    "not_found_text": "❌ <b>کد مورد نظر در آرشیو ساندترک یافت نشد!</b>"
}

def get_text(key):
    try:
        res = supabase.table("bot_settings").select("value").eq("key", key).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["value"]
    except Exception as e:
        print(f"Error reading text {key}: {e}")
    return DEFAULT_TEXTS.get(key, "")

def set_text_in_db(key, value):
    try:
        supabase.table("bot_settings").upsert({"key": key, "value": value}, on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"Error saving text {key}: {e}")
        return False

# ----------------------------------------------------
# بررسی عضویت کاربر در کانال عمومی
# ----------------------------------------------------
def check_channel_member(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Error checking membership: {e}")
        return True

# دکمه‌های شیشه‌ای جوین اجباری
def get_join_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    btn_channel = InlineKeyboardButton("📢عضویت در کانال", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
    btn_check = InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")
    markup.add(btn_channel, btn_check)
    return markup

# دکمه‌های شیشه‌ای زیر موزیک (لایک + اشتراک‌گذاری)
def get_file_buttons(code, likes_count):
    markup = InlineKeyboardMarkup()
    btn_like = InlineKeyboardButton(f"❤️ لایک {likes_count}", callback_data=f"like_{code}")
    btn_share = InlineKeyboardButton("🔄 اشتراک‌گذاری موزیک", switch_inline_query=f"کد موزیک {code}")
    markup.add(btn_like)
    markup.add(btn_share)
    return markup

# ----------------------------------------------------
# دستور /start و ثبت‌نام خودکار کاربر
# ----------------------------------------------------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id

    try:
        supabase.table("users").upsert({"user_id": user_id}, on_conflict="user_id").execute()
    except Exception as e:
        print(f"Error saving user: {e}")

    if not check_channel_member(user_id):
        bot.reply_to(message, get_text("join_text"), reply_markup=get_join_keyboard())
        return

    bot.reply_to(message, get_text("welcome_text"))

# ----------------------------------------------------
# پنل مدیریت متون برای ادمین (/settext)
# ----------------------------------------------------
@bot.message_handler(commands=["settext"])
def start_set_text(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ <b>دسترسی غیرمجاز!</b>")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    btn1 = InlineKeyboardButton("📝 تغییر متن خوش‌آمدگویی", callback_data="set_text_welcome_text")
    btn2 = InlineKeyboardButton("📝 تغییر متن جوین اجباری", callback_data="set_text_join_text")
    btn3 = InlineKeyboardButton("📝 تغییر متن عدم یافتن کد", callback_data="set_text_not_found_text")
    markup.add(btn1, btn2, btn3)

    bot.reply_to(message, "⚙️ <b>مدیریت متون ربات:</b>\n\nکدام متن را می‌خواهید ویرایش کنید؟", reply_markup=markup)

# ----------------------------------------------------
# دستور /add مخصوص ادمین
# ----------------------------------------------------
@bot.message_handler(commands=["add"])
def start_add_post(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ <b>دسترسی غیرمجاز!</b>")
        return

    admin_states[message.from_user.id] = {"step": "waiting_code"}
    bot.reply_to(message, "👑 <b>پنل ثبت موزیک جدید</b>\n\nلطفاً <b>کد پست</b> را وارد کنید:")

# ----------------------------------------------------
# دستور /sendall مخصوص ادمین (ارسال همگانی)
# ----------------------------------------------------
@bot.message_handler(commands=["sendall"])
def start_broadcast(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ <b>دسترسی غیرمجاز!</b>")
        return

    admin_states[message.from_user.id] = {"step": "waiting_broadcast_message"}
    bot.reply_to(message, "📢 <b>ارسال همگانی:</b> پیامی که می‌خواهید برای همه ارسال شود را بفرستید:")

# ----------------------------------------------------
# مدیریت کلیک روی دکمه‌های شیشه‌ای
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id

    if call.data == "check_join":
        if check_channel_member(user_id):
            bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد! حالا می‌توانید کد ارسال کنید.")
            bot.send_message(call.message.chat.id, "👇 <b>کد موزیک مورد نظرتان را بفرستید:</b>")
        else:
            bot.answer_callback_query(call.id, "❌ شما هنوز در کانال عضو نشده‌اید!", show_alert=True)
        return

    if call.data.startswith("set_text_") and user_id == ADMIN_ID:
        key = call.data.replace("set_text_", "")
        admin_states[user_id] = {"step": "waiting_new_text", "key": key}
        bot.send_message(call.message.chat.id, f"📝 لطفاً <b>متن جدید</b> برای <code>{key}</code> را ارسال کنید:")
        return

    if call.data.startswith("like_"):
        code = call.data.split("_")[1]
        try:
            res = supabase.table("music_posts").select("likes").eq("code", code).execute()
            if res.data:
                current_likes = res.data[0].get("likes", 0) or 0
                new_likes = current_likes + 1
                
                supabase.table("music_posts").update({"likes": new_likes}).eq("code", code).execute()
                
                bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=get_file_buttons(code, new_likes)
                )
                bot.answer_callback_query(call.id, "❤️ لایک شما با موفقیت ثبت شد!")
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ خطا در ثبت لایک!")
            print(f"Like error: {e}")

# ----------------------------------------------------
# دریافت پیام‌ها و مدیریت درخواست‌ها
# ----------------------------------------------------
@bot.message_handler(content_types=["text", "audio", "video", "document", "photo"])
def handle_messages(message):
    user_id = message.from_user.id

    if user_id != ADMIN_ID and not check_channel_member(user_id):
        bot.reply_to(message, get_text("join_text"), reply_markup=get_join_keyboard())
        return

    if user_id == ADMIN_ID and user_id in admin_states and admin_states[user_id].get("step") == "waiting_new_text":
        key = admin_states[user_id]["key"]
        new_value = message.text
        if set_text_in_db(key, new_value):
            bot.reply_to(message, f"✅ متن <code>{key}</code> با موفقیت به‌روزرسانی شد!")
        else:
            bot.reply_to(message, "❌ خطا در بروزرسانی متن!")
        del admin_states[user_id]
        return

    if user_id == ADMIN_ID and user_id in admin_states and admin_states[user_id].get("step") == "waiting_broadcast_message":
        del admin_states[user_id]
        status_msg = bot.reply_to(message, "⏳ <i>در حال ارسال پیام به تمام کاربران...</i>")
        try:
            users_res = supabase.table("users").select("user_id").execute()
            users = users_res.data
            success_count = 0
            fail_count = 0

            for u in users:
                try:
                    bot.copy_message(chat_id=u["user_id"], from_chat_id=message.chat.id, message_id=message.message_id)
                    success_count += 1
                except Exception:
                    fail_count += 1

            bot.edit_message_text(
                f"✅ <b>پیام همگانی ارسال شد!</b>\n\nموفق: <code>{success_count}</code> | ناموفق: <code>{fail_count}</code>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id
            )
        except Exception as e:
            bot.edit_message_text(f"❌ خطا: <code>{e}</code>", chat_id=message.chat.id, message_id=status_msg.message_id)
        return

    if user_id == ADMIN_ID and user_id in admin_states:
        state = admin_states[user_id]

        if state["step"] == "waiting_code":
            code = message.text.strip()
            admin_states[user_id]["code"] = code
            admin_states[user_id]["step"] = "waiting_audio"
            bot.reply_to(message, f"✅ کد <code>{code}</code> ثبت شد. حالا <b>فایل صوتی</b> را بفرستید:")
            return

        elif state["step"] == "waiting_audio":
            audio_id = message.audio.file_id if message.audio else (message.document.file_id if message.document else None)
            if not audio_id:
                bot.reply_to(message, "⚠️ لطفاً یک فایل صوتی بفرستید.")
                return
            admin_states[user_id]["audio_id"] = audio_id
            admin_states[user_id]["step"] = "waiting_video"
            bot.reply_to(message, "🎵 موزیک دریافت شد. حالا <b>فایل ویدیویی</b> را بفرستید:")
            return

        elif state["step"] == "waiting_video":
            video_id = message.video.file_id if message.video else (message.document.file_id if message.document else None)
            if not video_id:
                bot.reply_to(message, "⚠️ لطفاً یک فایل ویدیویی بفرستید.")
                return
            admin_states[user_id]["video_id"] = video_id
            admin_states[user_id]["step"] = "waiting_info"
            bot.reply_to(message, "🎬 ویدیو دریافت شد. حالا <b>اطلاعات موزیک</b> (توضیحات/متن زیر ویدیو) را ارسال کنید:")
            return

        elif state["step"] == "waiting_info":
            info = message.text or message.caption or "اطلاعاتی ثبت نشده است."
            code = admin_states[user_id]["code"]
            audio_id = admin_states[user_id]["audio_id"]
            video_id = admin_states[user_id]["video_id"]

            try:
                data = {
                    "code": code,
                    "audio_id": audio_id,
                    "video_id": video_id,
                    "caption": info,
                    "downloads": 0,
                    "likes": 0
                }
                supabase.table("music_posts").upsert(data).execute()
                bot.reply_to(message, f"🎉 <b>پست شماره <code>{code}</code> با موفقیت ثبت شد!</b>")
            except Exception as e:
                bot.reply_to(message, f"❌ خطا در ذخیره‌سازی: <code>{e}</code>")

            del admin_states[user_id]
            return

    if message.text and not message.text.startswith("/"):
        code = message.text.strip()
        searching_msg = bot.reply_to(message, "🔍 <i>در حال جستجو در آرشیو...</i>")

        try:
            response = supabase.table("music_posts").select("audio_id, video_id, caption, downloads, likes").eq("code", code).execute()
            result = response.data

            if result and len(result) > 0:
                post = result[0]
                new_downloads = (post.get("downloads", 0) or 0) + 1
                likes_count = post.get("likes", 0) or 0

                supabase.table("music_posts").update({"downloads": new_downloads}).eq("code", code).execute()
                bot.delete_message(message.chat.id, searching_msg.message_id)

                bot.send_video(
                    message.chat.id,
                    post["video_id"],
                    caption=f"🎬 <b>اطلاعات موزیک:</b>\n\n{post['caption']}"
                )

                audio_caption = (
                    f"🎶 <b>کد موزیک:</b> <code>{code}</code>\n"
                    f"📊 <b>تعداد دانلود:</b> {new_downloads} بار"
                )
                bot.send_audio(
                    message.chat.id,
                    post["audio_id"],
                    caption=audio_caption,
                    reply_markup=get_file_buttons(code, likes_count)
                )

            else:
                bot.edit_message_text(get_text("not_found_text"), chat_id=message.chat.id, message_id=searching_msg.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ خطا: <code>{e}</code>", chat_id=message.chat.id, message_id=searching_msg.message_id)

print("🤖 ربات جدید روشن شد...")
bot.polling(none_stop=True, interval=0)
