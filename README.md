# OTT Notification Bot — Telegram Channel + SQLite

## How the two-part archive works
- Telegram Channel stores the actual archive posts (episode caption, poster if supplied, and official watch button).
- SQLite stores searchable episode metadata, channel message ID/link, users, subscriptions, and notification delivery logs.
- Admin publishes once. The bot posts to the archive channel first, saves the record in SQLite, then sends notifications to subscribed users.

A Telegram channel is not a relational database and cannot replace SQLite search/indexing. It is used as a durable human-readable archive, while SQLite stores structured metadata.

## Files
- bot.py
- requirements.txt
- render.yaml
- README.md

## Render setup
1. Upload these files to your GitHub repository.
2. Create a Render Web Service from that repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python bot.py`
5. Add Environment Variables:
   - `BOT_TOKEN`: token from @BotFather
   - `ADMIN_IDS`: numeric Telegram user ID (multiple IDs comma-separated)
   - `CHANNEL_ID`: archive channel username, e.g. `@YourOTTArchive`, or numeric channel ID
   - `DB_PATH`: `/var/data/ott_bot.db`
6. Attach a Render Persistent Disk to the service and set its mount path to `/var/data`. The free plan may not include persistent disks; check Render's current plan limits.
7. Add the bot to the archive channel as an administrator and grant permission to post messages.
8. Deploy. Start the bot in Telegram with `/start`, then press Subscribe.

## Admin use
- Send `/admin`
- Choose `Publish Episode`
- Send one message:

Platform: Dangal Play
Series: Example Serial
Season: 1
Episode: 25
Title: New Beginning
Release Date: 01 Nov 2026
Poster: https://example.com/poster.jpg
Watch Link: https://official.example.com/episode
Description: New episode available

Required: Platform, Series, Episode, Watch Link.
Use `-` for optional fields without values.

## Admin search
- `/admin` -> `Search Episodes`
- Send part of a series name, platform, or title.
- Results show the saved episode details, official watch URL, and channel archive link (when available).

## Important
- This is Manual Admin + Automatic Notification. It does not independently detect new episodes inside OTT apps.
- The bot must be an admin in the archive channel with permission to post.
- Channel archive post happens before SQLite save and user notifications. If the channel post fails, publishing is stopped.
- SQLite is auto-created. On Render, use a Persistent Disk mounted at `/var/data` for data persistence. Without persistent storage, SQLite data can be lost on redeploy/restart.
- Use official watch links and only poster/media sources you are authorized to share.
