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
bad_words = [
    "shit", "bullshit", "fuck", "fucking", "fucked", "damn", "bitch", "bitches",
    "ass", "asshole", "crap", "dick", "dicks", "piss", "pissed", "hell",
    "cock", "cocksucker", "cum", "naked", "nude", "slut", "whore", "fag",
    "faggot", "retard", "idiot", "stupid", "dumb", "moron", "loser", "bastard",
    "twat", "prick", "bloody", "bugger", "bollocks", "arse", "shithead",
    "motherfucker", "son of a bitch", "jerk", "suck", "sucks", "sucker",
    "sexy", "porn", "sex", "semen", "orgy", "rape", "hooker", "prostitute",
    "anal", "beastiality", "incest", "masturbate", "penis", "vagina", "tit",
    "tits", "boobs", "clit", "pussy", "twat", "cumshot", "hardcore",
    "xxx", "fuckface", "shitfuck", "assface", "shitbag", "cunt", "slutty",
    "whorehouse", "cockhead", "nigger", "chink", "spic", "kike", "beaner",
    "redneck", "hillbilly", "terrorist", "bomb", "kill", "murder", "weapon",
    "gun", "knife", "hate", "racist", "extremist", "pedophile", "child abuse",
    "scam", "phishing", "clickbait", "malware", "virus", "spyware", "hack",
    "darkweb", "botnet", "free money", "win cash", "get rich", "visit this site",
    "bit.ly", "tinyurl", "goo.gl", "http", "www", "click here", "join now",
    "subscribe", "adult", "xxxvideos", "escort", "camgirl", "onlyfans"
]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# ---------------- Anti-Spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

# ---------------- Music Queues ----------------
queues = defaultdict(asyncio.Queue)

def get_queue(guild_id):
    return queues[guild_id]

# ---------------- Timeout abstraction ----------------
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
            continue
    return False, f"No compatible timeout method found. Last error: {last_exc}"

async def try_remove_timeout(member: discord.Member):
    attempts = [
        lambda: getattr(member, "timeout")(None),
        lambda: member.edit(communication_disabled_until=None, reason="Timeout removed by staff")
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
            continue
    return False, f"No compatible un-timeout method found. Last error: {last_exc}"

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    try:
        await member.send("Welcome! Type !help for commands.")
    except Exception:
        logger.info(f"Could not DM new member: {member}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Admin bypass
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
    timestamps = user_messages[message.author.id]
    timestamps.append(now)

    if len(timestamps) == SPAM_LIMIT and (now - timestamps[0]).total_seconds() <= TIME_FRAME:
        await handle_spam(message)

    await bot.process_commands(message)

async def handle_spam(message):
    user = message.author
    if user.guild_permissions.administrator:
        return

    user_warnings[user.id] += 1
    warnings = user_warnings[user.id]

    if warnings < MAX_WARNINGS:
        await message.channel.send(f"{user.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}.")
    else:
        try:
            await message.channel.send(f"{user.mention}, timed out for 30 minutes due to spam.")
            until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            ok, err = await try_apply_timeout(user, until, "Exceeded spam warnings")
            if ok: user_warnings[user.id] = 0
            else: await message.channel.send(f"⚠ Timeout failed: {err}")
        except:
            pass

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
        logger.exception("Unhandled error")

# ---------------- Commands ----------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(title="Help - Bot", description="Available commands:", color=discord.Color.blurple())
    # Moderation
    embed.add_field(name="!kick @user [reason]", value="Kick a member", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member", inline=False)
    embed.add_field(name="!unban <user_id>", value="Unban by user ID", inline=False)
    embed.add_field(name="!timeout @user <minutes> [reason]", value="Timeout a member", inline=False)
    embed.add_field(name="!remove_timeout @user", value="Remove timeout", inline=False)
    embed.add_field(name="!clear <amount>", value="Clear messages", inline=False)
    embed.add_field(name="!lock", value="Lock the channel", inline=False)
    embed.add_field(name="!unlock", value="Unlock the channel", inline=False)
    # Music
    embed.add_field(name="!join", value="Join voice channel", inline=False)
    embed.add_field(name="!leave", value="Leave voice channel", inline=False)
    embed.add_field(name="!play <url or search>", value="Play music from YouTube", inline=False)
    embed.add_field(name="!stop", value="Stop music", inline=False)
    # Other
    embed.add_field(name="!ping", value="Check bot latency", inline=False)
    await ctx.send(embed=embed)

# ---------------- Moderation Commands ----------------
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
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} minutes. Reason: {reason}")
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
        await m.delete(delay=5)
    except Exception as e:
        await ctx.send(f"❌ Failed to clear messages: {e}")

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

# ---------------- Music Commands ----------------
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel!")
        return
    channel = ctx.author.voice.channel
    if ctx.guild.voice_client is None:
        await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")
    else:
        await ctx.send("❌ Already connected to a voice channel.")

@bot.command()
async def leave(ctx):
    if ctx.guild.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("❌ I am not in a voice channel.")

@bot.command()
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel!")
        return

    voice_client = ctx.guild.voice_client
    if not voice_client:
        voice_client = await ctx.author.voice.channel.connect()

    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,
        "noplaylist": True,
        "ignoreerrors": True,
        "no_warnings": True,
        "default_search": "ytsearch",
        "user_agent": "Mozilla/5.0"
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search, download=False)
            if "entries" in info:
                info = info["entries"][0]
            url2 = info["url"]
            title = info.get("title", "Unknown title")
    except Exception as e:
        await ctx.send(f"❌ Could not extract video info: {e}")
        return

    if voice_client.is_playing():
        voice_client.stop()

    voice_client.play(discord.FFmpegPCMAudio(source=url2, executable="ffmpeg"))
    await ctx.send(f"▶ Now playing: *{title}*")

@bot.command()
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏹ Music stopped.")
    else:
        await ctx.send("❌ No music is playing.")

# ---------------- Run bot ----------------
keep_alive()
bot.run(TOKEN)