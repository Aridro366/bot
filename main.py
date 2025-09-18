import os
import io
import re   # ✅ Add this
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in .env")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # Remove default help

# IDs
WELCOME_CHANNEL_ID = 1234567890
TICKET_CREATION_CHANNEL_ID = 1234567890
TICKET_TRANSCRIPTS_CHANNEL_ID = 1234567890

# Bad words
bad_words = ["shit", "fuck", "bitch", "ass", "damn"]
bad_patterns = [re.compile(word, re.IGNORECASE) for word in bad_words]  # ✅ fixed

# Spam tracking
SPAM_LIMIT = 5
TIME_FRAME = 10
user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))

# ---------------- Events ----------------
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"Welcome {member.mention} to the server!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Bad word filter
    for pat in bad_patterns:
        if pat.search(message.content):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, no bad words!", delete_after=5)
            return
    await bot.process_commands(message)

# ---------------- Moderation ----------------
@bot.command()
async def kick(ctx, member: discord.Member, *, reason="No reason"):
    if ctx.author.guild_permissions.kick_members:
        await member.kick(reason=reason)
        await ctx.send(f"{member} kicked.")

@bot.command()
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    if ctx.author.guild_permissions.ban_members:
        await member.ban(reason=reason)
        await ctx.send(f"{member} banned.")

# ---------------- Help ----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Bot Help", description="Commands list:")
    embed.add_field(name="Moderation", value="kick, ban")
    await ctx.send(embed=embed)

bot.run(TOKEN)