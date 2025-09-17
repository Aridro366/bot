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
from discord import FFmpegPCMAudio

# ---------------- Keep Alive ----------------
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

# ---------------- Bad words ----------------
bad_words = ["shit","fuck","bitch","asshole","dumb","idiot","nude","porn","sex","cum","slut"]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-Spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30*60  # 30 minutes
user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music Queue ----------------
queues = defaultdict(asyncio.Queue)

# ---------------- Timeout abstraction ----------------
async def try_apply_timeout(member: discord.Member, until_dt, reason: str):
    try:
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

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignore admins
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    content = message.content

    # Bad word filter
    for pat in bad_patterns:
        if pat.search(content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} ⚠ Please avoid offensive language.", delete_after=6)
            except:
                pass
            return

    # Anti-spam
    now = datetime.now()
    user_id = message.author.id
    user_messages[user_id].append(now)
    timestamps = user_messages[user_id]

    if len(timestamps) == SPAM_LIMIT:
        if (now - timestamps[0]).total_seconds() <= TIME_FRAME:
            await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author
    if user.guild_permissions.administrator:
        return

    user_warnings[user.id] += 1
    warn = user_warnings[user.id]

    if warn < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {warn}/{MAX_WARNINGS}.")
    else:
        try:
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            ok, err = await try_apply_timeout(user, until, "Exceeded spam warnings")
            if ok:
                await message.channel.send(f"{user.mention} timed out for 30 minutes due to spam.")
                user_warnings[user.id] = 0
            else:
                await message.channel.send(f"⚠ Timeout failed: {err}")
        except:
            pass

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
async def help(ctx):
    embed = discord.Embed(title="Help - Moderation & Music Bot", color=discord.Color.blurple())
    embed.add_field(name="!kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="!timeout @user <minutes> [reason]", value="Timeout a member", inline=False)
    embed.add_field(name="!remove_timeout @user", value="Remove timeout", inline=False)
    embed.add_field(name="!clear <amount>", value="Clear messages", inline=False)
    embed.add_field(name="!lock", value="Lock channel", inline=False)
    embed.add_field(name="!unlock", value="Unlock channel", inline=False)
    embed.add_field(name="!ping", value="Check latency", inline=False)
    embed.add_field(name="!join", value="Join voice", inline=False)
    embed.add_field(name="!leave", value="Leave voice", inline=False)
    embed.add_field(name="!play <song/url>", value="Play music", inline=False)
    embed.add_field(name="!pause", value="Pause music", inline=False)
    embed.add_field(name="!resume", value="Resume music", inline=False)
    embed.add_field(name="!stop", value="Stop music", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member.mention} kicked. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member.mention} banned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    ok, err = await try_apply_timeout(member, until, reason)
    if ok:
        await ctx.send(f"{member.mention} timed out {minutes} min. Reason: {reason}")
    else:
        await ctx.send(f"❌ {err}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    ok, err = await try_remove_timeout(member)
    if ok:
        await ctx.send(f"{member.mention} removed from timeout")
    else:
        await ctx.send(f"❌ {err}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    try:
        await ctx.channel.purge(limit=amount+1)
        await ctx.send(f"🧹 Cleared {amount} messages", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ {e}")

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

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! Latency: {round(bot.latency*1000)}ms")

# ---------------- Music Commands ----------------
async def play_next(ctx, guild_id):
    if queues[guild_id].empty():
        await ctx.voice_client.disconnect()
        return

    url = await queues[guild_id].get()
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "default_search": "auto",
        "cookiefile": "cookies.txt"
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']
        ctx.voice_client.play(
            FFmpegPCMAudio(url2),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop)
        )
        await ctx.send(f"▶ Now playing: {info['title']}")
    except Exception as e:
        await ctx.send(f"❌ Could not play: {e}")
        await play_next(ctx, guild_id)

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
    else:
        await ctx.send("❌ You must be in a voice channel!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("❌ Not connected to voice channel!")

@bot.command()
async def play(ctx, *, search):
    guild_id = ctx.guild.id
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel!")
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    await queues[guild_id].put(search)
    if not ctx.voice_client.is_playing():
        await play_next(ctx, guild_id)
    else:
        await ctx.send(f"✅ Added to queue: {search}")

ydl_opts = {
    "format": "bestaudio",
    "quiet": True,
    "noplaylist": True,
    "ignoreerrors": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "user_agent": "Mozilla/5.0",
    "cookiefile": "cookies.txt"
}

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Paused")
    else:
        await ctx.send("❌ Nothing is playing")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶ Resumed")
    else:
        await ctx.send("❌ Nothing is paused")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[ctx.guild.id] = asyncio.Queue()
        await ctx.send("⏹ Stopped and cleared queue")
    else:
        await ctx.send("❌ Not connected to voice channel!")


if not os.path.exists("cookies.txt"):
    print("❌ cookies.txt file not found!")
else:
    print("✅ cookies.txt is loaded!")

# ---------------- Keep Alive ----------------
keep_alive()

# ---------------- Run Bot ----------------
bot.run(TOKEN)