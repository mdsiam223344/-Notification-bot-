# OTT Notification Bot

## Telegram Channel Link Update 
## OTT Perform Name
#  <img width="50" height="50" alt="362786e31ce14afa5d9cfdf21b53901ef196a414e0d502ec2cd1fa069bb0e735" src="https://github.com/user-attachments/assets/75cfbf2c-87ed-4486-8e3a-17d5b1998326" />
JioHotstar
# <img width="50" height="50" alt="fdc553e6e109e9795b25750ae34eb55517e50ec42b881ba609e7f02fdd0602de" src="https://github.com/user-attachments/assets/65689198-fc4c-4ffe-8640-2e1336e9f258" />
ZEE5
# <img width="50" height="50" alt="7a2933d77a200adbacb200c0d696389fb73b4235b935ba9d4d1cbbb7933a8a33" src="https://github.com/user-attachments/assets/3795b18a-7afa-40d0-845e-97f624d91adf" />
 SonyLIV
# <img width="50" height="50" alt="4ccfaea6d4a6a966a6e4b0909a2f83de9ef9b16d49be2e9afcfbb6e362c59e6b" src="https://github.com/user-attachments/assets/868cbf9f-5008-4026-b818-40efc432361a" />
 Sun NXT
# <img width="50" height="50" alt="a82a468ad49dd7a48a7dac8707c8d5535d33a4539f04ddc57cbf1d03f9701849" src="https://github.com/user-attachments/assets/ea0e4fd4-faac-4254-a06d-adf03d9e4990" />
 Dangal Play
# <img width="50" height="50" alt="163db2e8442bbd2ace536f6f028e8212d2bd362ddebf874448b1eefe3b369604" src="https://github.com/user-attachments/assets/b8a35fb4-a764-48b5-b29c-73b9e28b814e" />
 Netflix
# <img width="50" height="50" alt="5ab8cb93d565f3c049170ddca66e2cf04c9c04b85d295cf3a74784d1ad3e9985" src="https://github.com/user-attachments/assets/251d0ea4-97c8-4629-81a1-eac2343bfefb" />
 Amazon Prime Video
# <img width="50" height="50" alt="3225801071fea46b3b93904240bb4bf176f8bf8d57908bce1fed559931d15ab6" src="https://github.com/user-attachments/assets/3b8fd838-500f-4915-831a-e1d428f30cd1" />
 Hoichoi

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
