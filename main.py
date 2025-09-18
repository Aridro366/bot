import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re
from discord import ui, Embed, Interaction
from discord.ui import View, Button
from discord import app_commands
from discord import Embed, Color
from flask import Flask
import threading

app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=10000)

threading.Thread(target=run).start()

# ---------------- Load environment ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in .env")

# ---------------- Bot setup ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------- Anti-spam ----------------
SPAM_LIMIT = 5
TIME_FRAME = 10  # seconds
MAX_WARNINGS = 3
TIMEOUT_DURATION = 30 * 60  # 30 minutes

user_messages = defaultdict(lambda: deque(maxlen=SPAM_LIMIT))
user_warnings = defaultdict(int)

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
    
    # Anti-spam logic
    now = datetime.now()
    user_id = message.author.id
    timestamps = user_messages[user_id]
    timestamps.append(now)

    if len(timestamps) == SPAM_LIMIT and (now - timestamps[0]).total_seconds() <= TIME_FRAME:
        user_warnings[user_id] += 1
        warnings = user_warnings[user_id]

        if warnings < MAX_WARNINGS:
            await message.channel.send(f"{message.author.mention}, you are spamming! Warning {warnings}/{MAX_WARNINGS}.")
        else:
            until = datetime.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
            try:
                await message.author.edit(communication_disabled_until=until)
                await message.channel.send(f"{message.author.mention}, you have been timed out for 30 minutes due to repeated spamming.")
                user_warnings[user_id] = 0
            except discord.Forbidden:
                await message.channel.send(f"⚠ I cannot timeout {message.author.mention}.")
    await bot.process_commands(message)

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
    guild = ctx.guild
    try:
        # Fetch the list of banned users
        banned_users = await guild.bans()
        user = discord.Object(id=user_id)
        for ban_entry in banned_users:
            if ban_entry.user.id == user_id:
                await guild.unban(user)
                await ctx.send(f"✅ Successfully unbanned <@{user_id}>")
                return
        # If not found in banned list
        await ctx.send(f"❌ Cannot unban <@{user_id}> — user is not banned.")
    except Exception as e:
        await ctx.send(f"❌ Failed to unban: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    try:
        await member.edit(communication_disabled_until=until)
        await ctx.send(f"⏱ {member.mention} timed out for {minutes} minute(s). Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to timeout: {e}")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def remove_timeout(ctx, member: discord.Member):
    try:
        await member.edit(communication_disabled_until=None)
        await ctx.send(f"✅ {member.mention} removed from timeout.")
    except Exception as e:
        await ctx.send(f"❌ Failed to remove timeout: {e}")

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

# ---------------- Help View ----------------
class HelpView(View):
    def _init_(self):
        super()._init_(timeout=None)
        # Buttons for categories
        self.add_item(Button(label="Moderation", style=discord.ButtonStyle.primary, custom_id="mod"))
        self.add_item(Button(label="Utility", style=discord.ButtonStyle.success, custom_id="util"))
        self.add_item(Button(label="Home", style=discord.ButtonStyle.secondary, custom_id="home"))

    @discord.ui.button(label="Moderation", style=discord.ButtonStyle.primary, custom_id="mod")
    async def moderation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🛡 Moderation Commands",
            color=discord.Color.red()
        )
        embed.add_field(name="Kick", value="!kick @user [reason] - Kick a member", inline=False)
        embed.add_field(name="Ban", value="!ban @user [reason] - Ban a member", inline=False)
        embed.add_field(name="Timeout", value="!timeout @user <minutes> [reason] - Timeout member", inline=False)
        embed.add_field(name="Warn", value="!warn @user [reason] - Issue warning", inline=False)
        embed.add_field(name="softban", value="!softban @user [reason] - softban a member", inline=False)
        embed.add_field(name="unban", value="!unban @user [reason] - unban a member", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Utility", style=discord.ButtonStyle.success, custom_id="util")
    async def utility_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚙ Utility Commands",
            color=discord.Color.green()
        )
        embed.add_field(name="Ping", value="!ping - Check bot latency", inline=False)
        embed.add_field(name="User Info", value="!userinfo @user - Get user info (Admin only)", inline=False)
        embed.add_field(name="Role Info", value="!roleinfo @role - Get role info (Admin only)", inline=False)
        embed.add_field(name="Announcement", value="!announcement <message> - Send a professional announcement", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Home", style=discord.ButtonStyle.secondary, custom_id="home")
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📜 Royal Empire Bot - Help Menu",
            description="Click the buttons below to see categories.",
            color=discord.Color.blurple()
        )
        await interaction.response.edit_message(embed=embed, view=self)

# ---------------- Slash /help ----------------
@bot.tree.command(name="help", description="Show the interactive help menu")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Royal Empire Bot - Help Menu",
        description="Click the buttons below to see categories.",
        color=discord.Color.blurple()
    )
    view = HelpView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ---------------- !help ----------------
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📜 Royal Empire Bot - Help Menu",
        description="Click the buttons below to see categories.",
        color=discord.Color.blurple()
    )
    view = HelpView()
    await ctx.send(embed=embed, view=view)

# ---------------- Ready & Sync ----------------
@bot.event
async def on_ready():
    print(f"Bot online as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

WELCOME_CHANNEL_ID = 1405986494858137755 # Replace with your channel ID

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        msg = f"""
🎉 Welcome to Royals Empire 🍻
━━━━━━━━━━━━━━━━━━━
Hey {member.mention} 👑
You’ve just stepped into the kingdom of vibes, loyalty, and legends.  
We're hyped to have you with us!

✨ Make sure to:
🔹 Read the rules in <#1396670355858391092>
🔹 Get your roles from <#1396726703564525688>
🔹 Say hi in <#1396801885322739743>
______________________________
Need help? Ping our Staff!
"""
        await channel.send(msg)

@bot.command()
@commands.has_permissions(administrator=True)
async def announce(ctx, *, content):
    """Usage: !announce Title | Your message"""
    try:
        # Split title and message
        if "|" in content:
            title, message = map(str.strip, content.split("|", 1))
        else:
            await ctx.send("❌ Format: !announce Title | Your message")
            return

        embed = discord.Embed(title=title, description=message, color=discord.Color.gold())
        embed.set_footer(text=f"Announcement by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Failed to send announcement: {e}")

@bot.command(name="ping")
async def ping(ctx):
    """Ping-Pong latency check"""
    # Bot replies with !pong
    msg = await ctx.send("!pong")
    
    # Calculate latency based on message creation time
    latency_ms = (msg.created_at - ctx.message.created_at).total_seconds() * 1000
    await ctx.send(f"Latency: {int(latency_ms)}ms")


# ------------------ Enhanced Moderation ------------------
user_warnings = {}

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    """Warn a member"""
    user_id = member.id
    if user_id not in user_warnings:
        user_warnings[user_id] = []
    user_warnings[user_id].append(f"{reason} (by {ctx.author})")
    await ctx.send(f"⚠ {member.mention} has been warned. Reason: {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def softban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        await member.unban(reason="Softban completed")
        await ctx.send(f"🔹 {member.mention} has been softbanned. Reason: {reason}")
    except Exception as e:
        await ctx.send(f"❌ Failed to softban {member}: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Auto delete Discord invites
    if re.search(r"(discord\.gg/|discordapp\.com/invite/)", message.content):
        try:
            await message.delete()
            await message.channel.send(f"❌ {message.author.mention}, invite links are not allowed.", delete_after=5)
        except:
            pass
    await bot.process_commands(message)

# ------------------ Utility Commands ------------------

@bot.command()
@commands.has_permissions(administrator=True)
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author  # Default to command author if no member mentioned
    embed = discord.Embed(title=f"User Info - {member}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.avatar.url if member.avatar else discord.Embed.Empty)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Display Name", value=member.display_name, inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="Bot?", value=member.bot, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.green())
    embed.add_field(name="Server ID", value=guild.id)
    embed.add_field(name="Owner", value=guild.owner)
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.channels))
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Created At", value=guild.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member}'s Avatar", color=discord.Color.purple())
    embed.set_image(url=member.avatar.url if member.avatar else "")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def roleinfo(ctx, role: discord.Role):
    embed = discord.Embed(title=f"Role Info - {role.name}", color=role.color)
    embed.add_field(name="ID", value=role.id, inline=True)
    embed.add_field(name="Color", value=str(role.color), inline=True)
    embed.add_field(name="Hoisted", value=role.hoist, inline=True)
    embed.add_field(name="Mentionable", value=role.mentionable, inline=True)
    embed.add_field(name="Position", value=role.position, inline=True)
    embed.add_field(name="Members", value=len(role.members), inline=True)
    await ctx.send(embed=embed)

# ---------------- Warnings System ----------------
SPAM_WARNINGS = 3
TIMEOUT_DURATION = 60  # minutes
user_warnings = defaultdict(int)  # {user_id: warning_count}

# ---------------- Chat & Link Filters ----------------
# Slang words (common bad words)
bad_words = [
    "fuck", "bitch", "ass", "dick", "piss", "crap", "nude",
    "porn", "sex", "slut", "whore", "fag", 
    # add more if needed
]
bad_patterns = [re.compile(re.escape(word), re.IGNORECASE) for word in bad_words]

# Simple link regex
link_pattern = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)

# ---------------- Events ----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ignore admins
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # Check for bad words
    for pat in bad_patterns:
        if pat.search(message.content):
            await warn_user(message, reason="Using bad language")
            await message.delete()
            return

    # Check for links
    if link_pattern.search(message.content):
        await warn_user(message, reason="Posting a link")
        await message.delete()
        return

    await bot.process_commands(message)

async def warn_user(message, reason="Violation"):
    user = message.author
    user_warnings[user.id] += 1
    warnings = user_warnings[user.id]

    if warnings < SPAM_WARNINGS:
        await message.channel.send(
            f"⚠ {user.mention}, you have {warnings}/{SPAM_WARNINGS} warnings for: {reason}"
        )
    else:
        # Timeout user for 1 hour
        until = timedelta(minutes=TIMEOUT_DURATION)
        try:
            await user.timeout(until, reason="Reached 3 warnings")
            await message.channel.send(
                f"⏱ {user.mention} has been timed out for {TIMEOUT_DURATION} minutes due to repeated offenses."
            )
            user_warnings[user.id] = 0  # reset warnings
        except Exception as e:
            await message.channel.send(f"❌ Failed to timeout {user.mention}: {e}")

# ---------------- Run Bot ----------------

bot.run(TOKEN)
