# bot.py
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
import yt_dlp

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

# ---------------- Load token ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("ERROR: DISCORD_TOKEN not found in .env")

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
logger.addHandler(file_handler)

# ---------------- Intents ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------- Bad words ----------------
bad_words = ["shit", "fuck", "bitch", "ass", "dumb", "idiot", "porn", "sex", "nude"]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60
user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music ----------------
queues = defaultdict(asyncio.Queue)
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

def get_queue(guild_id):
    return queues[guild_id]

# ---------------- Timeout ----------------
async def try_apply_timeout(member: discord.Member, until_dt, reason: str):
    try:
        await member.edit(communication_disabled_until=until_dt, reason=reason)
        return True, None
    except Exception as e:
        return False, str(e)

async def try_remove_timeout(member: discord.Member):
    try:
        await member.edit(communication_disabled_until=None, reason="Timeout removed")
        return True, None
    except Exception as e:
        return False, str(e)

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # Bad word filter
    for pat in bad_patterns:
        if pat.search(message.content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠ Avoid offensive language.", delete_after=6)
            except:
                pass
            return

    # Spam check
    now = datetime.now()
    user_id = message.author.id
    timestamps = user_messages[user_id]
    timestamps.append(now)
    if len(timestamps) == SPAM_LIMIT and (now - timestamps[0]).total_seconds() <= TIME_FRAME:
        await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author
    user_warnings[user.id] += 1
    warnings = user_warnings[user.id]
    if warnings < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, spamming! Warning {warnings}/{MAX_WARNINGS}")
    else:
        until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
        ok, err = await try_apply_timeout(user, until, "Spam")
        if ok:
            user_warnings[user.id] = 0
            await message.channel.send(f"{user.mention} timed out for 30 minutes.")
        else:
            await message.channel.send(f"Timeout failed: {err}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.send(f"❌ Error: {error}")

# ---------------- Commands ----------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! 🏓 {round(bot.latency*1000)}ms")

@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="Help", description="Commands", color=discord.Color.blurple())
    commands_list = [
        ("!kick @user [reason]", "Kick a member"),
        ("!ban @user [reason]", "Ban a member"),
        ("!timeout @user <minutes>", "Timeout a member"),
        ("!remove_timeout @user", "Remove timeout"),
        ("!clear <amount>", "Clear messages"),
        ("!lock", "Lock channel"),
        ("!unlock", "Unlock channel"),
        ("!join", "Join voice channel"),
        ("!leave", "Leave voice channel"),
        ("!play <url>", "Play music"),
        ("!pause", "Pause music"),
        ("!resume", "Resume music"),
        ("!stop", "Stop music"),
        ("!queue_list", "Show music queue"),
        ("!ping", "Check latency")
    ]
    for name, desc in commands_list:
        embed.add_field(name=name, value=desc, inline=False)
    await ctx.send(embed=embed)

# ---------------- Moderation ----------------
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason"):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} kicked.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} banned.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, "Timeout")
    if ok:
        await ctx.send(f"{member.mention} timed out for {minutes} min.")
    else:
        await ctx.send(f"Failed: {err}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    ok, err = await try_remove_timeout(member)
    if ok:
        await ctx.send(f"{member.mention} removed from timeout.")
    else:
        await ctx.send(f"Failed: {err}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount+1)
    m = await ctx.send(f"Cleared {amount} messages.")
    await m.delete(delay=5)

@bot.command()
@commands.has_permissions(administrator=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("Channel locked.")

@bot.command()
@commands.has_permissions(administrator=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("Channel unlocked.")

# ---------------- Music ----------------


# Music queues per guild
queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]

# ---------------- Music play command ----------------
@bot.command()
async def play(ctx, *, url):
    """Play a song from YouTube."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ You must be in a voice channel!")
        return

    channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client

    # Connect or move bot
    if not voice_client:
        voice_client = await channel.connect()
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    # YT-DLP options
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "no_warnings": True,
        "default_search": "ytsearch",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    }

    # Extract video info safely
    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                await ctx.send("❌ Could not extract video info.")
                return

            # Handle search result
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            elif "entries" in info and not info["entries"]:
                await ctx.send("❌ No results found.")
                return

            audio_url = info.get("url")
            if not audio_url:
                await ctx.send("❌ Failed to get audio URL.")
                return

    except Exception as e:
        await ctx.send(f"❌ Error extracting video info: {e}")
        return

    # Stop current audio
    if voice_client.is_playing():
        voice_client.stop()

    # Play audio
    try:
        voice_client.play(
            discord.FFmpegPCMAudio(audio_url),
            after=lambda e: print(f"Player error: {e}" if e else None)
        )
        await ctx.send(f"▶ Now playing: {info.get('title', 'Unknown')}")
    except Exception as e:
        await ctx.send(f"❌ Could not play audio: {e}")

# ---------------- Stop command ----------------
@bot.command()
async def stop(ctx):
    """Stop the current audio and clear the queue."""
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏹ Stopped playback.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

# ---------------- Join command ----------------
@bot.command()
async def join(ctx):
    """Make the bot join your voice channel."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ You must be in a voice channel!")
        return

    channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client

    if not voice_client:
        await channel.connect()
        await ctx.send(f"✅ Connected to {channel.name}")
    else:
        await ctx.send("❌ I'm already in a voice channel!")

# ---------------- Leave command ----------------
@bot.command()
async def leave(ctx):
    """Make the bot leave the voice channel."""
    voice_client = ctx.guild.voice_client
    if voice_client:
        await voice_client.disconnect()
        await ctx.send("👋 Disconnected from the voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel!")
# ---------------- Run bot ----------------
keep_alive()
bot.run(TOKEN)