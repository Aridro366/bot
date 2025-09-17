import os
import re
import logging
from datetime import datetime, timedelta
from threading import Thread
from collections import defaultdict, deque
from flask import Flask
from dotenv import load_dotenv
import discord
from discord.ext import commands
import asyncio

# ---------------- Keep alive server ----------------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------- Configuration ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in .env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
logger.addHandler(file_handler)

# ---------------- Intents & Bot ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

try:
    bot.remove_command("help")
except Exception:
    pass

# ---------------- Bad words filter ----------------
bad_words = [
    "shit", "fuck", "bitch", "ass", "dumb", "idiot", "nigger", "spic",
    "kill", "murder", "rape", "porn", "sex", "camgirl", "escort"
]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music setup ----------------
VOICE_SUPPORTED = True
try:
    import yt_dlp
    from discord import FFmpegOpusAudio
except ModuleNotFoundError:
    VOICE_SUPPORTED = False
    print("⚠ Music/voice not supported. Missing yt_dlp or PyNaCl.")

queues = defaultdict(asyncio.Queue)

def get_queue(guild_id):
    return queues[guild_id]

# ---------------- Timeout helpers ----------------
async def try_apply_timeout(member: discord.Member, until_dt, reason: str):
    attempts = [
        lambda: getattr(member, "timeout")(until_dt),
        lambda: getattr(member, "timeout")(timed_out_until=until_dt, reason=reason),
        lambda: getattr(member, "timeout")(until=until_dt, reason=reason),
        lambda: member.edit(communication_disabled_until=until_dt, reason=reason)
    ]
    last_exc = None
    for attempt in attempts:
        try:
            coro = attempt()
            if coro is None: continue
            await coro
            return True, None
        except Exception as e:
            last_exc = e
    return False, f"No compatible timeout method found. Last error: {last_exc}"

async def try_remove_timeout(member: discord.Member):
    attempts = [
        lambda: getattr(member, "timeout")(None),
        lambda: member.edit(communication_disabled_until=None, reason="Timeout removed")
    ]
    last_exc = None
    for attempt in attempts:
        try:
            coro = attempt()
            if coro is None: continue
            await coro
            return True, None
        except Exception as e:
            last_exc = e
    return False, f"No compatible remove-timeout method found. Last error: {last_exc}"

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    try:
        await member.send("Welcome! Type !help in the server for commands.")
    except Exception:
        logger.info(f"Could not DM new member: {member}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignore admins
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # Bad word filter
    for pat in bad_patterns:
        if pat.search(message.content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠ Please avoid offensive language.", delete_after=6)
            except:
                pass
            return

    # Anti-spam
    now = datetime.now()
    user_id = message.author.id
    timestamps = user_messages[user_id]
    timestamps.append(now)
    if len(timestamps) == SPAM_LIMIT:
        if (now - timestamps[0]).total_seconds() <= TIME_FRAME:
            await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author
    user_id = user.id
    user_warnings[user_id] += 1
    warnings = user_warnings[user_id]

    if warnings < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}.")
    else:
        until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
        ok, err = await try_apply_timeout(user, until, "Exceeded spam warnings")
        if ok:
            user_warnings[user_id] = 0
            await message.channel.send(f"{user.mention} has been timed out for 30 minutes due to spamming.")
        else:
            await message.channel.send(f"⚠ Timeout failed: {err}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument. Check your command usage.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.exception(error)
        await ctx.send(f"❌ An error occurred: {error}")

# ---------------- Moderation Commands ----------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency*1000)}ms")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👤 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to kick: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🛑 {member.mention} banned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to ban: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user} (ID: {user_id})")
    except Exception as e:
        await ctx.send(f"❌ Failed to unban: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} min. Reason: {reason}")
    else:
        await ctx.send(f"❌ Failed to timeout: {err}")

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
    try:
        await ctx.channel.purge(limit=amount+1)
        await ctx.send(f"🧹 Cleared {amount} messages.", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Failed to clear: {e}")

# ---------------- Lock/Unlock ----------------
@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked.")

@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked.")

# ---------------- Music Commands (optional) ----------------
if VOICE_SUPPORTED:
    @bot.command()
    async def join(ctx):
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
            await ctx.send(f"✅ Joined {channel}")
        else:
            await ctx.send("❌ You are not in a voice channel.")

    @bot.command()
    async def leave(ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("✅ Left voice channel.")
        else:
            await ctx.send("❌ I am not in a voice channel.")

    @bot.command()
    async def play(ctx, url):
        if not ctx.voice_client:
            await ctx.send("❌ I am not in a voice channel.")
            return
        ydl_opts = {'format': 'bestaudio'}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            url2 = info['url']
            ctx.voice_client.stop()
            ctx.voice_client.play(discord.FFmpegPCMAudio(url2))
            await ctx.send(f"▶ Now playing: {info['title']}")
        except Exception as e:
            await ctx.send(f"❌ Error playing music: {e}")

    @bot.command()
    async def stop(ctx):
        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.send("⏹ Music stopped.")
        else:
            await ctx.send("❌ Not playing anything.")

    @bot.command()
    async def pause(ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸ Music paused.")
        else:
            await ctx.send("❌ Not playing anything.")

    @bot.command()
    async def resume(ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶ Music resumed.")
        else:
            await ctx.send("❌ Not paused.")

# ---------------- Run bot ----------------
if __name__ == "__main__":
    keep_alive()
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {e}")
        logging.exception("Bot startup error")