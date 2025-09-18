# main.py
import os
import re
import logging
import base64
from datetime import datetime, timedelta
from threading import Thread
from collections import defaultdict, deque
from dotenv import load_dotenv
from flask import Flask
import asyncio
import yt_dlp
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

# ---------------- Keep Alive (Flask) ----------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run_keep_alive():
    app.run(host="0.0.0.0", port=8080)

def start_keep_alive():
    t = Thread(target=run_keep_alive, daemon=True)
    t.start()

# ---------------- Env & Cookies handling ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("ERROR: DISCORD_TOKEN not found in .env or environment variables")

# If you prefer cookie-file in repo, commit cookies.txt (Netscape format).
# Recommended: store base64 of cookies.txt in COOKIES_B64 env var on Render for reliability.

COOKIES_B64 = os.getenv("COOKIES_B64")

# Try to write cookies.txt from COOKIES_B64 at startup (if provided)
if COOKIES_B64:
    try:
        decoded = base64.b64decode(COOKIES_B64)
        with open("cookies.txt", "wb") as f:
            f.write(decoded)
        print("✅ cookies.txt created from COOKIES_B64 env var")
    except Exception as e:
        print("❌ Failed to write cookies.txt from COOKIES_B64:", e)
else:
    print("ℹ COOKIES_B64 not set; will look for cookies.txt in repo (if needed)")

# Debug: list files in CWD so Render logs show what's present
try:
    print("PWD:", os.getcwd())
    print("FILES:", os.listdir("."))
    print("cookies.txt exists:", os.path.exists("cookies.txt"))
    if os.path.exists("cookies.txt"):
        with open("cookies.txt", "r", errors="ignore") as fh:
            print("cookies.txt head:")
            for i, line in enumerate(fh):
                print(i+1, line.strip())
                if i >= 9:
                    break
except Exception as e:
    print("Debug listing failed:", e)

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
logger.addHandler(file_handler)

# ---------------- Intents & Bot ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------- Bad words / Patterns ----------------
bad_words = [
    "shit","fuck","bitch","asshole","dumb","idiot","nude","porn","sex","cum","slut"
]
bad_patterns = [re.compile(re.escape(w), re.IGNORECASE) for w in bad_words]

# ---------------- Anti-spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music Queues ----------------
queues = defaultdict(asyncio.Queue)
now_playing = {}  # guild_id -> info dict

def get_queue(guild_id: int):
    return queues[guild_id]

# ---------------- Timeout abstraction ----------------
async def try_apply_timeout(member: discord.Member, until_dt, reason: str):
    """Try common ways to timeout (edit member or modern timeout API)."""
    try:
        # modern discord.py: member.timeout(...)
        # but we'll try edit fallback
        await member.edit(communication_disabled_until=until_dt, reason=reason)
        return True, None
    except Exception as e:
        logger.exception("Timeout failed")
        return False, str(e)

async def try_remove_timeout(member: discord.Member):
    try:
        await member.edit(communication_disabled_until=None, reason="Timeout removed")
        return True, None
    except Exception as e:
        logger.exception("Remove timeout failed")
        return False, str(e)

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    logger.info("Bot ready")

@bot.event
async def on_member_join(member):
    # gentle welcome DM (best-effort)
    try:
        await member.send("Welcome! Type !help in the server for commands.")
    except Exception:
        logger.info("Could not DM new member")

@bot.event
async def on_message(message):
    # ignore bots
    if message.author.bot:
        return

    # admins bypass filters
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # bad word filter
    for pat in bad_patterns:
        if pat.search(message.content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠ Please avoid offensive language.", delete_after=6)
            except discord.Forbidden:
                logger.warning("Missing permission to delete/send message")
            except Exception:
                logger.exception("Error while deleting bad word message")
            return

    # anti-spam
    now = datetime.now()
    user_id = message.author.id
    user_messages[user_id].append(now)
    timestamps = user_messages[user_id]
    if len(timestamps) == SPAM_LIMIT and (now - timestamps[0]).total_seconds() <= TIME_FRAME:
        await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author
    if user.guild_permissions.administrator:
        return

    uid = user.id
    user_warnings[uid] += 1
    warnings = user_warnings[uid]
    if warnings < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}.")
    else:
        try:
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            ok, err = await try_apply_timeout(user, until, "Exceeded spam warnings")
            if ok:
                await message.channel.send(f"{user.mention} timed out for 30 minutes due to spamming.")
                user_warnings[uid] = 0
            else:
                await message.channel.send(f"⚠ Timeout failed: {err}")
        except Exception:
            logger.exception("Failed to timeout spamming user")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument. Check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.exception("Unhandled command error")
        try:
            await ctx.send(f"❌ An error occurred: {error}")
        except Exception:
            pass

# ---------------- Help (paginated) ----------------
help_pages = [
    {
        "title": "Help — Moderation",
        "description": "Moderation commands (admins/mods).",
        "fields": [
            ("!kick @user [reason]", "Kick a member"),
            ("!ban @user [reason]", "Ban a member"),
            ("!unban <user_id>", "Unban by user ID"),
            ("!timeout @user <minutes> [reason]", "Timeout a member"),
            ("!remove_timeout @user", "Remove timeout"),
            ("!clear <amount>", "Clear messages"),
            ("!lock", "Lock the channel"),
            ("!unlock", "Unlock the channel"),
        ],
    },
    {
        "title": "Help — Music",
        "description": "Music controls and queue.",
        "fields": [
            ("!join", "Bot joins your voice channel"),
            ("!leave", "Bot leaves voice channel"),
            ("!play <url or search>", "Play or queue a song (ytsearch supported)"),
            ("!skip", "Skip current song"),
            ("!pause", "Pause playback"),
            ("!resume", "Resume playback"),
            ("!stop", "Stop playback & clear queue"),
            ("!queue", "Show queued items"),
        ],
    },
    {
        "title": "Help — Utility",
        "description": "Other useful commands.",
        "fields": [
            ("!ping", "Check bot latency"),
            ("!poll \"Question\" \"Option1\" \"Option2\"...", "Create a poll"),
            ("!announce #channel message", "Send an announcement (admin)"),
        ],
    },
]

@bot.command(name="help")
async def help_cmd(ctx):
    page = 0
    embed = discord.Embed(title=help_pages[page]["title"], description=help_pages[page]["description"], color=discord.Color.blurple())
    for name, value in help_pages[page]["fields"]:
        embed.add_field(name=name, value=value, inline=False)
    help_msg = await ctx.send(embed=embed)
    await help_msg.add_reaction("⬅")
    await help_msg.add_reaction("➡")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["⬅", "➡"] and reaction.message.id == help_msg.id

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "➡":
                page = (page + 1) % len(help_pages)
            elif str(reaction.emoji) == "⬅":
                page = (page - 1) % len(help_pages)
            new_embed = discord.Embed(title=help_pages[page]["title"], description=help_pages[page]["description"], color=discord.Color.blurple())
            for name, value in help_pages[page]["fields"]:
                new_embed.add_field(name=name, value=value, inline=False)
            await help_msg.edit(embed=new_embed)
            await help_msg.remove_reaction(reaction.emoji, user)
        except asyncio.TimeoutError:
            try:
                await help_msg.clear_reactions()
            except Exception:
                pass
            break

# ---------------- Moderation commands ----------------
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👤 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        logger.exception("Kick failed")
        await ctx.send(f"❌ Failed to kick: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🛑 {member.mention} banned. Reason: {reason}")
    except Exception as e:
        logger.exception("Ban failed")
        await ctx.send(f"❌ Failed to ban: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user} (ID: {user_id})")
    except discord.NotFound:
        await ctx.send("❌ User ID not found.")
    except Exception as e:
        logger.exception("Unban failed")
        await ctx.send(f"❌ Failed to unban: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    if minutes < 0:
        await ctx.send("❌ Minutes must be positive.")
        return
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} minute(s). Reason: {reason}")
    else:
        await ctx.send(f"❌ Failed to timeout {member.mention}. {err}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    ok, err = await try_remove_timeout(member)
    if ok:
        await ctx.send(f"✅ {member.mention} removed from timeout.")
    else:
        await ctx.send(f"❌ Failed to remove timeout: {err}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("❌ Amount must be between 1 and 100.")
        return
    try:
        await ctx.channel.purge(limit=amount+1)
        m = await ctx.send(f"🧹 Cleared {amount} messages.")
        try:
            await m.delete(delay=5)
        except Exception:
            pass
    except Exception as e:
        logger.exception("Clear failed")
        await ctx.send(f"❌ Failed to clear messages: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Channel locked.")
    except Exception as e:
        logger.exception("Lock failed")
        await ctx.send(f"❌ Failed to lock: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    try:
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Channel unlocked.")
    except Exception as e:
        logger.exception("Unlock failed")
        await ctx.send(f"❌ Failed to unlock: {e}")

# ---------------- Music helper: yt-dlp extraction ----------------
YDL_OPTS_BASE = {
    "format": "bestaudio",
    "quiet": True,
    "noplaylist": True,
    "ignoreerrors": True,
    "no_warnings": True,
    "default_search": "auto",  # auto detect URLs or search terms
    "source_address": "0.0.0.0",  # force IPv4
    # "user_agent": "Mozilla/5.0 ...",  # optional customization
    # optionally add cookiefile if one exists on disk
}

if os.path.exists("cookies.txt"):
    YDL_OPTS_BASE["cookiefile"] = "cookies.txt"

FFMPEG_EXECUTABLE = os.getenv("FFMPEG_PATH", "ffmpeg")

async def run_ydl_extract(query: str):
    """Run yt-dlp.extract_info in a thread, return info or raise."""
    opts = dict(YDL_OPTS_BASE)
    # use to_thread to avoid blocking event loop
    def extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(query, download=False)
    info = await asyncio.to_thread(extract)
    return info

# ---------------- Music playback flow ----------------
async def play_next(ctx, guild_id: int):
    """Play next item in queue for guild. If queue empty, disconnect."""
    q = get_queue(guild_id)
    if q.empty():
        # disconnect after queue drained
        try:
            if ctx.voice_client:
                await ctx.voice_client.disconnect()
        except Exception:
            pass
        now_playing.pop(guild_id, None)
        return

    query = await q.get()
    try:
        info = await run_ydl_extract(query)
    except Exception as e:
        await ctx.send(f"❌ Could not extract info for {query}: {e}")
        # try the next track
        return await play_next(ctx, guild_id)

    if not info:
        await ctx.send(f"❌ No results for: {query}")
        return await play_next(ctx, guild_id)

    # handle search results
    if "entries" in info:
        entries = info.get("entries") or []
        if len(entries) == 0:
            await ctx.send(f"❌ No results for: {query}")
            return await play_next(ctx, guild_id)
        info = entries[0]

    # Get audio URL
    audio_url = info.get("url")
    title = info.get("title", "Unknown title")
    if not audio_url:
        await ctx.send(f"❌ Could not get audio URL for: {title}")
        return await play_next(ctx, guild_id)

    # record now playing
    now_playing[guild_id] = {"title": title, "requester": ctx.author.display_name}

    # ensure voice client present
    if not ctx.voice_client:
        # try to connect to the author's channel
        if ctx.author.voice and ctx.author.voice.channel:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ I'm not connected to a voice channel.")
            return

    def _after_play(error):
        if error:
            logger.exception("Player error: %s", error)
        fut = asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop)
        try:
            fut.result()
        except Exception:
            logger.exception("play_next scheduling failed")

    # create ffmpeg source and play
    try:
        source = FFmpegPCMAudio(source=audio_url, executable=FFMPEG_EXECUTABLE)
        # stop existing if any
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        ctx.voice_client.play(source, after=_after_play)
        await ctx.send(f"▶ Now playing: *{title}*")
    except Exception as e:
        await ctx.send(f"❌ Failed to play {title}: {e}")
        logger.exception("Failed to play audio")
        return await play_next(ctx, guild_id)

# ---------------- Music commands ----------------
@bot.command()
async def join(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        vc = ctx.guild.voice_client
        try:
            if not vc:
                await channel.connect()
                await ctx.send(f"✅ Joined {channel.name}")
            else:
                await ctx.send("❌ I'm already connected to a voice channel.")
        except Exception as e:
            logger.exception("Join failed")
            await ctx.send(f"❌ Failed to join: {e}")
    else:
        await ctx.send("❌ You must be in a voice channel to invite me.")

@bot.command()
async def leave(ctx):
    vc = ctx.guild.voice_client
    if vc:
        try:
            await vc.disconnect()
            await ctx.send("👋 Left the voice channel.")
        except Exception as e:
            logger.exception("Leave failed")
            await ctx.send(f"❌ Failed to leave: {e}")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")

@bot.command()
async def play(ctx, *, query: str):
    """Queue a song (URL or search)."""
    guild_id = ctx.guild.id
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ You must be in a voice channel!")
        return

    # connect if needed
    if not ctx.guild.voice_client:
        try:
            await ctx.author.voice.channel.connect()
        except Exception as e:
            logger.exception("Connect failed")
            await ctx.send(f"❌ Could not connect to voice channel: {e}")
            return

    await get_queue(guild_id).put(query)
    q = get_queue(guild_id)
    # if not playing, start playback
    if not ctx.voice_client.is_playing() and (guild_id not in now_playing or now_playing.get(guild_id) is None):
        # start first track
        await play_next(ctx, guild_id)
    else:
        await ctx.send(f"✅ Added to queue: {query}")

@bot.command()
async def skip(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭ Skipped current song.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

@bot.command()
async def pause(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸ Paused")
    else:
        await ctx.send("❌ Nothing is playing")

@bot.command()
async def resume(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶ Resumed")
    else:
        await ctx.send("❌ Nothing is paused")

@bot.command()
async def stop(ctx):
    vc = ctx.guild.voice_client
    if vc:
        vc.stop()
        queues[ctx.guild.id] = asyncio.Queue()
        now_playing.pop(ctx.guild.id, None)
        await ctx.send("⏹ Stopped and cleared queue")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")

@bot.command(name="queue")
async def queue_list(ctx):
    q = get_queue(ctx.guild.id)
    if q.empty():
        await ctx.send("📭 Queue is empty.")
        return
    items = list(q._queue)
    text = ""
    for i, item in enumerate(items, start=1):
        text += f"{i}. {item}\n"
    await ctx.send(f"📜 Queue:\n{text}")

# ---------------- Poll & Announce (small extras) ----------------
@bot.command()
@commands.has_permissions(administrator=True)
async def announce(ctx, channel: discord.TextChannel, *, message: str):
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"By {ctx.author}", icon_url=getattr(ctx.author.display_avatar, "url", None))
    await channel.send(embed=embed)
    await ctx.send(f"✅ Announcement sent in {channel.mention}")

@bot.command()
async def poll(ctx, question: str, *options):
    if len(options) < 2 or len(options) > 10:
        await ctx.send("❌ Provide 2-10 options for a poll.")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    description = ""
    for i, opt in enumerate(options):
        description += f"{emojis[i]} {opt}\n"
    embed = discord.Embed(title=f"📊 {question}", description=description, color=discord.Color.green(), timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"Poll by {ctx.author}", icon_url=getattr(ctx.author.display_avatar, "url", None))
    msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

# ---------------- Utility ----------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

# ---------------- Start ----------------
if __name__ == "__main__":
    start_keep_alive()
    bot.run(TOKEN)