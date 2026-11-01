import os
import sqlite3
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "6339382565:AAFx9RDuKIOMvDTI4QyhdmhtUqfD9e0Sp5s").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "1686274364").split(",")
    if x.strip().isdigit()
}
# Required for Channel Archive feature. Example: @your_archive_channel or -1001234567890
CHANNEL_ID = os.getenv("CHANNEL_ID", "-1004427032466").strip()
# Set to a Persistent Disk path on Render, e.g. /var/data/ott_bot.db
DB_PATH = os.getenv("DB_PATH", "data/ott_bot.db")
PORT = int(os.getenv("PORT", "10000"))

PLATFORMS = [
    "JioHotstar", "ZEE5", "SonyLIV", "Sun NXT", "Dangal Play",
    "Hoichoi", "Amazon Prime Video", "Netflix", "Other"
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger("ott-channel-sqlite-bot")
db_lock = threading.RLock()

# ============================================================
# SQLITE: METADATA + CHANNEL MESSAGE POINTERS + DELIVERY LOG
# ============================================================
def connect_db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con

def init_db():
    with db_lock:
        con = connect_db()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    first_name TEXT NOT NULL DEFAULT '',
                    subscribed INTEGER NOT NULL DEFAULT 0,
                    joined_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    series TEXT NOT NULL,
                    season TEXT NOT NULL DEFAULT '',
                    episode TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL DEFAULT '',
                    poster_url TEXT NOT NULL DEFAULT '',
                    watch_url TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    channel_id TEXT NOT NULL DEFAULT '',
                    channel_message_id INTEGER,
                    channel_message_link TEXT NOT NULL DEFAULT '',
                    published_by INTEGER NOT NULL,
                    published_at TEXT NOT NULL,
                    UNIQUE(platform, series, season, episode)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS notification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(episode_id) REFERENCES episodes(id),
                    UNIQUE(episode_id, user_id)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_users_subscribed ON users(subscribed)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_episode_series ON episodes(series)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_episode_platform ON episodes(platform)")
            con.commit()
        finally:
            con.close()

def save_user(user):
    now = datetime.now(timezone.utc).isoformat()
    with db_lock:
        con = connect_db()
        try:
            con.execute("""
                INSERT INTO users(user_id, username, first_name, subscribed, joined_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    updated_at=excluded.updated_at
            """, (user.id, user.username or "", user.first_name or "", now, now))
            con.commit()
        finally:
            con.close()

def set_subscription(user_id, enabled):
    with db_lock:
        con = connect_db()
        try:
            con.execute(
                "UPDATE users SET subscribed=?, updated_at=? WHERE user_id=?",
                (int(enabled), datetime.now(timezone.utc).isoformat(), user_id)
            )
            con.commit()
        finally:
            con.close()

def get_subscribers():
    with db_lock:
        con = connect_db()
        try:
            return [r["user_id"] for r in con.execute(
                "SELECT user_id FROM users WHERE subscribed=1"
            ).fetchall()]
        finally:
            con.close()

def save_episode(data, admin_id, channel_message_id=None, channel_message_link=""):
    now = datetime.now(timezone.utc).isoformat()
    with db_lock:
        con = connect_db()
        try:
            cur = con.execute("""
                INSERT INTO episodes(
                    platform, series, season, episode, title, release_date,
                    poster_url, watch_url, description, channel_id,
                    channel_message_id, channel_message_link, published_by, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["platform"], data["series"], data["season"], data["episode"],
                data["title"], data["release_date"], data["poster_url"],
                data["watch_url"], data["description"], CHANNEL_ID,
                channel_message_id, channel_message_link, admin_id, now
            ))
            con.commit()
            return cur.lastrowid
        finally:
            con.close()

def log_delivery(episode_id, user_id, status, error=""):
    with db_lock:
        con = connect_db()
        try:
            con.execute("""
                INSERT INTO notification_log(episode_id, user_id, status, sent_at, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(episode_id, user_id) DO UPDATE SET
                    status=excluded.status, sent_at=excluded.sent_at, error=excluded.error
            """, (
                episode_id, user_id, status,
                datetime.now(timezone.utc).isoformat(), error[:500]
            ))
            con.commit()
        finally:
            con.close()

def get_stats():
    with db_lock:
        con = connect_db()
        try:
            total = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
            subs = con.execute("SELECT COUNT(*) n FROM users WHERE subscribed=1").fetchone()["n"]
            eps = con.execute("SELECT COUNT(*) n FROM episodes").fetchone()["n"]
            archived = con.execute(
                "SELECT COUNT(*) n FROM episodes WHERE channel_message_id IS NOT NULL"
            ).fetchone()["n"]
            return total, subs, eps, archived
        finally:
            con.close()

def search_episodes(term):
    pattern = f"%{term}%"
    with db_lock:
        con = connect_db()
        try:
            return con.execute("""
                SELECT * FROM episodes
                WHERE series LIKE ? OR platform LIKE ? OR title LIKE ?
                ORDER BY id DESC LIMIT 10
            """, (pattern, pattern, pattern)).fetchall()
        finally:
            con.close()

def recent_episodes():
    with db_lock:
        con = connect_db()
        try:
            return con.execute(
                "SELECT * FROM episodes ORDER BY id DESC LIMIT 10"
            ).fetchall()
        finally:
            con.close()

# ============================================================
# FORMATTING / VALIDATION
# ============================================================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def valid_url(value):
    try:
        p = urlparse(value)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def parse_episode(raw):
    fields = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip().lower()] = v.strip()

    required = ["platform", "series", "episode", "watch link"]
    missing = [k for k in required if not fields.get(k) or fields[k] == "-"]
    if missing:
        raise ValueError("আবশ্যক তথ্য দিন: " + ", ".join(missing))

    watch = fields["watch link"]
    if not valid_url(watch):
        raise ValueError("Watch Link-এ সঠিক http:// অথবা https:// URL দিন।")

    poster = fields.get("poster", "")
    if poster == "-":
        poster = ""
    if poster and not valid_url(poster):
        raise ValueError("Poster URL সঠিক নয়। না থাকলে Poster: - দিন।")

    def optional(key):
        value = fields.get(key, "")
        return "" if value == "-" else value

    return {
        "platform": fields["platform"],
        "series": fields["series"],
        "season": optional("season"),
        "episode": fields["episode"],
        "title": optional("title"),
        "release_date": optional("release date"),
        "poster_url": poster,
        "watch_url": watch,
        "description": optional("description")
    }

def episode_caption(d):
    return (
        "🆕 NEW EPISODE ALERT\n\n"
        f"📺 Platform: {d['platform']}\n"
        f"🎞 Series: {d['series']}\n"
        + (f"📚 Season: {d['season']}\n" if d["season"] else "")
        + f"🔢 Episode: {d['episode']}\n"
        + (f"🎬 Title: {d['title']}\n" if d["title"] else "")
        + (f"📅 Release Date: {d['release_date']}\n" if d["release_date"] else "")
        + (f"\n📝 {d['description']}\n" if d["description"] else "")
        + "\n📢 OTT Episode Archive"
    )

def watch_markup(url):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ Watch Officially", url=url)
    ]])

def user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Subscribe", callback_data="subscribe"),
         InlineKeyboardButton("🔕 Unsubscribe", callback_data="unsubscribe")],
        [InlineKeyboardButton("📺 Platforms", callback_data="platforms"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Publish Episode", callback_data="admin_publish")],
        [InlineKeyboardButton("🔎 Search Episodes", callback_data="admin_search")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("🗂 Recent Episodes", callback_data="admin_recent")]
    ])

def channel_post_link(chat_id, message_id):
    # Public channels use t.me/username/message_id; private channel IDs use t.me/c/<id>/<message_id>.
    if not str(chat_id).startswith("-100"):
        return ""
    internal_id = str(chat_id)[4:]
    return f"https://t.me/c/{internal_id}/{message_id}"

# ============================================================
# TELEGRAM COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        "👋 স্বাগতম!\n\nAll OTT Episode Notification Bot.\n"
        "নতুন Episode-এর আপডেট পেতে Subscribe চাপুন।",
        reply_markup=user_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — Main Menu\n/help — Help\n/platforms — OTT Platforms\n"
        "/admin — Admin Panel\n/cancel — Cancel Admin action"
    )

async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📺 Supported OTT Platforms:\n" + "\n".join("• " + p for p in PLATFORMS)
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin access only.")
        return
    await update.message.reply_text("🛠 Admin Panel", reply_markup=admin_keyboard())

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("mode", None)
    await update.message.reply_text("❌ Cancelled.")

# ============================================================
# CALLBACKS
# ============================================================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid, action = q.from_user.id, q.data

    if action in ("subscribe", "unsubscribe"):
        save_user(q.from_user)
        set_subscription(uid, action == "subscribe")
        status = "✅ Notification চালু হয়েছে।" if action == "subscribe" else "🔕 Notification বন্ধ হয়েছে।"
        await q.edit_message_text(status, reply_markup=user_keyboard())
        return

    if action == "platforms":
        await q.edit_message_text(
            "📺 Platforms:\n" + "\n".join("• " + p for p in PLATFORMS),
            reply_markup=user_keyboard()
        )
        return
    if action == "help":
        await q.edit_message_text("নতুন Episode পেতে Subscribe করুন।", reply_markup=user_keyboard())
        return

    if not action.startswith("admin_"):
        return
    if not is_admin(uid):
        await q.edit_message_text("⛔ Access denied.")
        return

    if action == "admin_publish":
        context.user_data["mode"] = "publish"
        await q.edit_message_text(
            "এক মেসেজে এই Format পাঠান:\n\n"
            "Platform: Dangal Play\nSeries: Example Serial\nSeason: 1\n"
            "Episode: 25\nTitle: New Beginning\nRelease Date: 01 Nov 2026\n"
            "Poster: https://example.com/poster.jpg\n"
            "Watch Link: https://official.example.com/episode\n"
            "Description: New episode available\n\n"
            "Optional field না থাকলে - লিখুন। /cancel দিয়ে বাতিল করুন।"
        )
    elif action == "admin_search":
        context.user_data["mode"] = "search"
        await q.edit_message_text("Series name / Platform / Title লিখে Search করুন।")
    elif action == "admin_stats":
        total, subs, eps, archived = get_stats()
        await q.edit_message_text(
            f"📊 DATABASE STATISTICS\n\n👥 Users: {total}\n🔔 Subscribers: {subs}\n"
            f"🎬 Episodes: {eps}\n📢 Channel archived: {archived}",
            reply_markup=admin_keyboard()
        )
    elif action == "admin_recent":
        rows = recent_episodes()
        if not rows:
            msg = "এখনও কোনো Episode নেই।"
        else:
            lines = []
            for r in rows:
                line = f"• {r['platform']} | {r['series']} | S{r['season'] or '-'} E{r['episode']}"
                if r["channel_message_link"]:
                    line += f"\n  Archive: {r['channel_message_link']}"
                lines.append(line)
            msg = "🗂 RECENT EPISODES\n\n" + "\n".join(lines)
        await q.edit_message_text(msg, reply_markup=admin_keyboard(), disable_web_page_preview=True)

# ============================================================
# PUBLISH: CHANNEL ARCHIVE FIRST, THEN SQLITE + USERS
# ============================================================
async def publish_episode(update: Update, context: ContextTypes.DEFAULT_TYPE, data):
    archive_message = None

    if CHANNEL_ID:
        try:
            caption = episode_caption(data)
            markup = watch_markup(data["watch_url"])
            if data["poster_url"]:
                archive_message = await context.bot.send_photo(
                    chat_id=CHANNEL_ID, photo=data["poster_url"],
                    caption=caption, reply_markup=markup
                )
            else:
                archive_message = await context.bot.send_message(
                    chat_id=CHANNEL_ID, text=caption, reply_markup=markup,
                    disable_web_page_preview=True
                )
        except Exception as exc:
            log.exception("Channel archive post failed")
            await update.message.reply_text(
                "❌ Channel-এ Episode Archive করা যায়নি, তাই publish থামানো হয়েছে।\n"
                f"কারণ: {exc}\n\nBot-কে Channel Admin করুন এবং Post Messages permission দিন।"
            )
            return

    channel_message_id = archive_message.message_id if archive_message else None
    channel_link = (
        channel_post_link(CHANNEL_ID, channel_message_id)
        if archive_message else ""
    )

    try:
        episode_id = save_episode(
            data, update.effective_user.id, channel_message_id, channel_link
        )
    except sqlite3.IntegrityError:
        # If the archive post already went through, mention it to the admin.
        extra = f"\nChannel post: {channel_link}" if channel_link else ""
        await update.message.reply_text(
            "⚠️ এই Platform/Series/Season/Episode আগে SQLite-এ আছে। "
            "Duplicate entry আটকানো হয়েছে." + extra,
            reply_markup=admin_keyboard()
        )
        return

    sent, failed = 0, 0
    text = episode_caption(data)
    markup = watch_markup(data["watch_url"])

    for subscriber_id in get_subscribers():
        try:
            if data["poster_url"]:
                await context.bot.send_photo(
                    chat_id=subscriber_id, photo=data["poster_url"],
                    caption=text, reply_markup=markup
                )
            else:
                await context.bot.send_message(
                    chat_id=subscriber_id, text=text, reply_markup=markup,
                    disable_web_page_preview=True
                )
            sent += 1
            log_delivery(episode_id, subscriber_id, "sent")
        except Exception as exc:
            failed += 1
            log_delivery(episode_id, subscriber_id, "failed", str(exc))
            log.warning("User notification failed for %s: %s", subscriber_id, exc)

    archive_info = channel_link or ("Channel not configured" if not CHANNEL_ID else "Channel post saved")
    await update.message.reply_text(
        "✅ EPISODE PUBLISHED\n\n"
        f"🗃 SQLite record: Saved (ID {episode_id})\n"
        f"📢 Telegram Channel: {archive_info}\n"
        f"🔔 User notifications sent: {sent}\n"
        f"⚠️ Failed notifications: {failed}",
        reply_markup=admin_keyboard(),
        disable_web_page_preview=True
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if not mode:
        return
    if not is_admin(update.effective_user.id):
        return

    if mode == "search":
        term = (update.message.text or "").strip()
        if not term:
            await update.message.reply_text("Search term লিখুন।")
            return
        rows = search_episodes(term)
        context.user_data.pop("mode", None)
        if not rows:
            await update.message.reply_text("কোনো Episode পাওয়া যায়নি।", reply_markup=admin_keyboard())
            return
        output = []
        for r in rows:
            item = f"🎞 {r['series']} | {r['platform']} | S{r['season'] or '-'} E{r['episode']}"
            if r["title"]:
                item += f"\n🎬 {r['title']}"
            if r["channel_message_link"]:
                item += f"\n📢 Archive: {r['channel_message_link']}"
            item += f"\n▶️ Watch: {r['watch_url']}"
            output.append(item)
        await update.message.reply_text(
            "🔎 SEARCH RESULTS\n\n" + "\n\n".join(output),
            reply_markup=admin_keyboard(),
            disable_web_page_preview=True
        )
        return

    if mode == "publish":
        try:
            data = parse_episode(update.message.text or "")
        except ValueError as exc:
            await update.message.reply_text(f"⚠️ {exc}\nসঠিক Format-এ আবার পাঠান, অথবা /cancel লিখুন।")
            return
        context.user_data.pop("mode", None)
        await publish_episode(update, context, data)

# ============================================================
# RENDER HEALTH ENDPOINT
# ============================================================
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"status": "running", "service": "OTT Channel + SQLite Bot"})

@web_app.get("/health")
def health():
    return jsonify({"status": "healthy", "database": "sqlite"})

def run_web():
    web_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

# ============================================================
# MAIN
# ============================================================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing in Environment Variables.")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS is missing. Add your numeric Telegram user ID.")
    if not CHANNEL_ID:
        log.warning("CHANNEL_ID is empty. Channel archive is disabled until configured.")

    init_db()
    threading.Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("platforms", platforms_cmd))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot starting with SQLite database: %s", DB_PATH)
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
