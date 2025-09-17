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
bad_words = ["shit", "fuck", "bitch", "asshole", "nude", "sex", "porn", "slut", "cunt"]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-Spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30*60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Timeout Helpers ----------------
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
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")

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
    timestamps = user_messages[message.author.id]
    timestamps.append(now)
    if len(timestamps) == SPAM_LIMIT and (now - timestamps[0]).total_seconds() <= TIME_FRAME:
        user_warnings[message.author.id] += 1
        warnings = user_warnings[message.author.id]
        if warnings < MAX_WARNINGS:
            await message.channel.send(f"{message.author.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}.")
        else:
            until = datetime.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            ok, err = await try_apply_timeout(message.author, until, "Exceeded spam warnings")
            if ok:
                user_warnings[message.author.id] = 0
                await message.channel.send(f"{message.author.mention} timed out for 30 minutes due to spamming.")
            else:
                await message.channel.send(f"⚠ Timeout failed: {err}")
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.send(f"❌ Error: {error}")

# ---------------- Moderation Commands ----------------
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👤 {member.mention} kicked. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🛑 {member.mention} banned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Unbanned {user}")
    except Exception as e:
        await ctx.send(f"❌ Failed: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason"):
    until = datetime.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} minutes.")
    else:
        await ctx.send(f"❌ Failed: {err}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    ok, err = await try_remove_timeout(member)
    if ok:
        await ctx.send(f"✅ {member.mention} removed from timeout.")
    else:
        await ctx.send(f"❌ Failed: {err}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount+1)
    await ctx.send(f"🧹 Cleared {amount} messages.", delete_after=5)

# ---------------- Music Commands ----------------
@bot.command()
async def join(ctx):
    if ctx.guild.voice_client is None:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
            await ctx.send(f"✅ Joined {ctx.author.voice.channel.name}")
        else:
            await ctx.send("❌ You must be in a voice channel!")

@bot.command()
async def leave(ctx):
    vc = ctx.guild.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("❌ Not in a voice channel.")

@bot.command()
async def play(ctx, *, search: str):
    """Play a YouTube video in your voice channel."""
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel!")
        return

    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client
    if not vc:
        vc = await channel.connect()

    # yt-dlp options
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "no_warnings": True,
        "default_search": "auto",  # 'auto' detects URLs or searches
        "source_address": "0.0.0.0",
        "extract_flat": True  # avoids downloading the full info to speed up
    }

    try:
        # Run yt-dlp in a thread to prevent blocking
        info = await asyncio.to_thread(
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(search, download=False)
        )
        if info is None:
            await ctx.send("❌ Could not find the video.")
            return

        # Handle search results
        if "entries" in info:
            info = info["entries"][0]
            if info is None:
                await ctx.send("❌ Could not find any video results.")
                return

        url2 = info.get("url")
        title = info.get("title", "Unknown title")
        if url2 is None:
            await ctx.send("❌ Could not extract audio URL.")
            return

    except Exception as e:
        await ctx.send(f"❌ Could not extract video info: {e}")
        return

    # Stop current if playing
    if vc.is_playing():
        vc.stop()

    # Play audio
    vc.play(discord.FFmpegPCMAudio(source=url2, executable="ffmpeg"))
    await ctx.send(f"▶️ Now playing: **{title}**")

@bot.command()
async def stop(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏹ Music stopped.")
    else:
        await ctx.send("❌ No music playing.")

# ---------------- Utility ----------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency*1000)}ms")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Help - Ultimate Bot", color=discord.Color.blurple())
    embed.add_field(name="Moderation", value="!kick, !ban, !unban, !timeout, !remove_timeout, !clear, !lock, !unlock", inline=False)
    embed.add_field(name="Music", value="!join, !leave, !play <url>, !stop", inline=False)
    embed.add_field(name="Utility", value="!ping", inline=False)
    await ctx.send(embed=embed)

# ---------------- Run ----------------
keep_alive()
bot.run(TOKEN)