import os
import re
import logging
from datetime import datetime, timedelta
from threading import Thread
from collections import defaultdict, deque
from flask import Flask
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
import yt_dlp
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
    raise SystemExit("ERROR: DISCORD_TOKEN not found in .env")

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

# ---------------- Bad words list ----------------
bad_words = ["shit","fuck","bitch","ass","damn","crap","idiot","stupid"]  # shortened for brevity
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-Spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes
user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music Queue ----------------
queues = defaultdict(asyncio.Queue)
current_players = {}

# ---------------- Timeout helpers ----------------
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
                await message.channel.send(f"{message.author.mention} ⚠ Please avoid offensive language.", delete_after=6)
            except Exception:
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
    if user.guild_permissions.administrator:
        return
    user_warnings[user.id] += 1
    if user_warnings[user.id] < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {user_warnings[user.id]}/{MAX_WARNINGS}")
    else:
        await message.channel.send(f"{user.mention} timed out for 30 minutes due to spam!")
        until = datetime.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
        await try_apply_timeout(user, until, "Spam exceeded")
        user_warnings[user.id] = 0

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.send(f"❌ An error occurred: {error}")

# ---------------- Moderation ----------------
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👤 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to kick: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🛑 {member.mention} banned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to ban: {e}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency*1000)} ms")

# ---------------- Voice & Music ----------------
async def play_next(ctx, guild_id):
    if queues[guild_id].empty():
        current_players.pop(guild_id, None)
        return
    url = await queues[guild_id].get()
    vc = current_players[guild_id]
    ydl_opts = {"format": "bestaudio"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']
    source = await discord.FFmpegOpusAudio.from_probe(audio_url)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop))

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        vc = await channel.connect()
        current_players[ctx.guild.id] = vc
        await ctx.send(f"✅ Joined {channel.name}")
    else:
        await ctx.send("❌ You are not in a voice channel!")

@bot.command()
async def leave(ctx):
    vc = current_players.get(ctx.guild.id)
    if vc:
        await vc.disconnect()
        current_players.pop(ctx.guild.id)
        await ctx.send("✅ Left the voice channel")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")

@bot.command()
async def play(ctx, url):
    if ctx.guild.id not in current_players:
        await ctx.invoke(join)
    await queues[ctx.guild.id].put(url)
    await ctx.send(f"🎵 Added to queue: {url}")
    if not current_players[ctx.guild.id].is_playing():
        await play_next(ctx, ctx.guild.id)

@bot.command()
async def stop(ctx):
    vc = current_players.get(ctx.guild.id)
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏹ Stopped playback")
    else:
        await ctx.send("❌ Nothing is playing")

@bot.command()
async def queue_list(ctx):
    q = queues[ctx.guild.id]
    items = list(q._queue)
    if items:
        msg = "\n".join(f"{i+1}. {url}" for i, url in enumerate(items))
        await ctx.send(f"🎶 Queue:\n{msg}")
    else:
        await ctx.send("✅ Queue is empty")

# ---------------- Run ----------------
if __name__ == "_main_":
    keep_alive()
    bot.run(TOKEN)