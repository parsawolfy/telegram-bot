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
CHANNEL_URL = "https://t.me/bot_Sazy"  # لینک مستقیم بدون جوین اجباری

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
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


def init_supabase() -> Client | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ SUPABASE_URL یا SUPABASE_KEY تنظیم نشده است.")
        return None
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ اتصال به Supabase برقرار شد.")
        return client
    except Exception as e:
        print(f"❌ خطا در اتصال به Supabase: {e}")
        return None


supabase: Client | None = init_supabase()

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


def find_post_by_code(code_str: str) -> dict | None:
    if not supabase:
        return None

    clean_code = code_str.strip()
    if not clean_code:
        return None

    # تلاش اول: جستجوی دقیق متنی
    try:
        res = supabase.table("music_posts").select("*").eq("code", clean_code).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        print(f"⚠️ خطا در جستجوی متنی کد '{clean_code}': {e}")

    # تلاش دوم: اگر کد عدد بود، جستجوی عددی
