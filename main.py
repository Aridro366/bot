import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import os
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv
import os
import itertools
import asyncio
from keep_alive import keep_alive

load_dotenv()  # loads .env variables
TOKEN = os.getenv("DISCORD_TOKEN")


# --- Intents ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

guild_config = {}  # stores guild-specific settings like log channel

# --- Bot Setup ---
bot = commands.Bot(command_prefix="!", intents=intents)
keep_alive()
# --- Database setup ---
conn = sqlite3.connect("botdata.db")
c = conn.cursor()

# Create tables
c.execute("""CREATE TABLE IF NOT EXISTS warnings (
    guild_id INTEGER,
    user_id INTEGER,
    count INTEGER,
    last_warn TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS config (
    guild_id INTEGER PRIMARY KEY,
    join_msg TEXT,
    join_channel_id INTEGER,
    auto_role_id INTEGER,
    log_channel_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS badwords (
    guild_id INTEGER,
    word TEXT
)""")
conn.commit()

# --- Helper Functions ---
def get_warns(guild_id, user_id):
    c.execute("SELECT count FROM warnings WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    return row[0] if row else 0

def add_warn(guild_id, user_id):
    now = datetime.utcnow().isoformat()
    current = get_warns(guild_id, user_id)
    if current == 0:
        c.execute("INSERT INTO warnings VALUES (?, ?, ?, ?)", (guild_id, user_id, 1, now))
    else:
        c.execute("UPDATE warnings SET count=?, last_warn=? WHERE guild_id=? AND user_id=?", (current + 1, now, guild_id, user_id))
    conn.commit()
    return current + 1

def remove_warn(guild_id, user_id):
    current = get_warns(guild_id, user_id)
    if current > 0:
        c.execute("UPDATE warnings SET count=? WHERE guild_id=? AND user_id=?", (current - 1, guild_id, user_id))
        conn.commit()
        return True
    return False

def get_config(guild_id):
    c.execute("SELECT join_msg, join_channel_id, auto_role_id, log_channel_id FROM config WHERE guild_id=?", (guild_id,))
    return c.fetchone()

def add_badword(guild_id, word):
    c.execute("INSERT INTO badwords VALUES (?, ?)", (guild_id, word.lower()))
    conn.commit()

def remove_badword_db(guild_id, word):
    c.execute("DELETE FROM badwords WHERE guild_id=? AND word=?", (guild_id, word.lower()))
    conn.commit()

def get_badwords(guild_id):
    c.execute("SELECT word FROM badwords WHERE guild_id=?", (guild_id,))
    return [row[0] for row in c.fetchall()]

async def log_action(guild, message):
    cfg = get_config(guild.id)
    if cfg and cfg[3]:
        channel = guild.get_channel(cfg[3])
        if channel:
            await channel.send(message)

# --- Events ---
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

@bot.event
async def on_member_join(member):
    cfg = get_config(member.guild.id)
    if cfg:
        join_msg, join_channel_id, auto_role_id, _ = cfg
        if join_channel_id:
            channel = member.guild.get_channel(join_channel_id)
            if channel and join_msg:
                msg = join_msg.replace("{user}", member.mention)
                await channel.send(msg)
        if auto_role_id:
            role = member.guild.get_role(auto_role_id)
            if role:
                await member.add_roles(role)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Skip admins
    if message.author.guild_permissions.administrator:
        return

    # Bad words filter
    badwords = get_badwords(message.guild.id)
    if any(word in message.content.lower() for word in badwords):
        await message.delete()
        warns = add_warn(message.guild.id, message.author.id)
        await message.channel.send(f"{message.author.mention} Warning {warns}/3 for using bad words!")
        await log_action(message.guild, f"{message.author} warned for bad word. Total warns: {warns}")
        if warns >= 3:
            await message.author.timeout(timedelta(hours=12), reason="Accumulated 3 warnings")
            await message.channel.send(f"{message.author.mention} has been timed out for 12 hours!")
        return

    # Link filter
    if "http://" in message.content.lower() or "https://" in message.content.lower():
        await message.delete()
        warns = add_warn(message.guild.id, message.author.id)
        await message.channel.send(f"{message.author.mention} Warning {warns}/3 for posting links!")
        await log_action(message.guild, f"{message.author} warned for posting links. Total warns: {warns}")
        if warns >= 3:
            await message.author.timeout(timedelta(hours=12), reason="Accumulated 3 warnings")
            await message.channel.send(f"{message.author.mention} has been timed out for 12 hours!")
        return

    await bot.process_commands(message)


# Define a list of cool mod statuses
statuses = [
    discord.Game("🛡️ Watching the server"),
    discord.Activity(type=discord.ActivityType.watching, name="for rule breakers"),
    discord.Activity(type=discord.ActivityType.listening, name="your complaints"),
    discord.Game("⚡ Enforcing the rules"),
    discord.Activity(type=discord.ActivityType.watching, name="everyone misbehaving"),
    discord.Game("🚨 Catching rule violators"),
    discord.Activity(type=discord.ActivityType.listening, name="server chaos"),
]

# Create an iterator to cycle through the statuses
status_cycle = itertools.cycle(statuses)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    change_status.start()  # Start the background task for changing statuses
    await bot.tree.sync()  # Sync slash commands

# Background task to change status every 5 minutes
@tasks.loop(minutes=5)
async def change_status():
    current_status = next(status_cycle)
    await bot.change_presence(activity=current_status)

# --- Slash Commands ---

# --- Moderation ---
@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="The member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member} has been kicked!")
        await log_action(interaction.guild, f"{member} was kicked by {interaction.user} Reason: {reason}")
    except:
        await interaction.response.send_message("Failed to kick member.", ephemeral=True)


@bot.tree.command(name="unban", description="Unban a member by ID")
@app_commands.describe(user_id="ID of the user to unban")
async def unban(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"{user} has been unbanned!")
        await log_action(interaction.guild, f"{user} was unbanned by {interaction.user}")
    except:
        await interaction.response.send_message("Failed to unban member.", ephemeral=True)

@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return
    warns = add_warn(interaction.guild.id, member.id)
    await interaction.response.send_message(f"{member.mention} has been warned! Total warns: {warns}")
    await log_action(interaction.guild, f"{member} warned by {interaction.user}. Reason: {reason}")
    if warns >= 3:
        await member.timeout(timedelta(hours=12), reason="Accumulated 3 warnings")
        await interaction.channel.send(f"{member.mention} has been timed out for 12 hours!")

@bot.tree.command(name="removewarn", description="Remove a warning from a member")
@app_commands.describe(member="Member to remove warning")
async def removewarn(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return
    success = remove_warn(interaction.guild.id, member.id)
    if success:
        await interaction.response.send_message(f"Removed 1 warning from {member.mention}.")
    else:
        await interaction.response.send_message(f"{member.mention} has no warnings.")

@bot.tree.command(name="showwarn", description="Show warnings of a member")
@app_commands.describe(member="Member to check")
async def showwarn(interaction: discord.Interaction, member: discord.Member):
    warns = get_warns(interaction.guild.id, member.id)
    await interaction.response.send_message(f"{member.mention} has {warns} warning(s).")

# --- Info Commands ---
@bot.tree.command(name="avatar", description="Get member avatar")
@app_commands.describe(member="Member to get avatar")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    await interaction.response.send_message(member.avatar.url)

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="serverinfo", description="Get server info")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"{g.name}", description=f"ID: {g.id}", color=discord.Color.blue())
    embed.add_field(name="Members", value=g.member_count)
    embed.add_field(name="Owner", value=g.owner)
    embed.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roleinfo", description="Get info about a role (admin only)")
@app_commands.describe(role="Role to check")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    embed = discord.Embed(title=role.name, color=role.color)
    embed.add_field(name="ID", value=role.id)
    embed.add_field(name="Members", value=len(role.members))
    embed.add_field(name="Mentionable", value=role.mentionable)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="memberinfo", description="Get info about a member (admin only)")
@app_commands.describe(member="Member to check")
async def memberinfo(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    embed = discord.Embed(title=str(member), color=discord.Color.green())
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined", value=member.joined_at)
    embed.add_field(name="Top Role", value=member.top_role)
    embed.set_thumbnail(url=member.avatar.url)
    await interaction.response.send_message(embed=embed)

# --- Config Commands ---
@bot.tree.command(name="setjoinmsg", description="Set welcome message")
@app_commands.describe(message="Welcome message. Use {user} for mention")
async def setjoinmsg(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO config (guild_id, join_msg) VALUES (?, ?)", (interaction.guild.id, message))
    conn.commit()
    await interaction.response.send_message("Join message set!")

@bot.tree.command(name="setjoinchannel", description="Set welcome channel")
@app_commands.describe(channel="Channel for welcome message")
async def setjoinchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO config (guild_id, join_channel_id) VALUES (?, ?)", (interaction.guild.id, channel.id))
    conn.commit()
    await interaction.response.send_message("Join channel set!")

@bot.tree.command(name="setautorole", description="Set auto role for new members")
@app_commands.describe(role="Role to assign")
async def setautorole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    c.execute("INSERT OR REPLACE INTO config (guild_id, auto_role_id) VALUES (?, ?)", (interaction.guild.id, role.id))
    conn.commit()
    await interaction.response.send_message(f"Auto role set to {role.name}!")

# --- Bad Word Management ---
@bot.tree.command(name="addbadword", description="Add a bad word")
@app_commands.describe(word="Word to block")
async def addbadword(interaction: discord.Interaction, word: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    add_badword(interaction.guild.id, word)
    await interaction.response.send_message(f"Added bad word: {word}")

@bot.tree.command(name="removebadword", description="Remove a bad word")
@app_commands.describe(word="Word to remove")
async def removebadword(interaction: discord.Interaction, word: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not admin!", ephemeral=True)
        return
    remove_badword_db(interaction.guild.id, word)
    await interaction.response.send_message(f"Removed bad word: {word}")

# --- Fun Commands ---
@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"🎲 {result}!")

# At the bottom of bot.py before bot.run(TOKEN)
async def load_cogs():
    for ext in ["roast", "joke"]:
        try:
            await bot.load_extension(ext)
            print(f"Loaded {ext} cog.")
        except Exception as e:
            print(f"Failed to load {ext}: {e}")

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    await load_cogs()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

@bot.tree.command(name="help", description="Show all available commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Help Menu",
        description="Here are all the available commands:",
        color=discord.Color.blurple()
    )

    # Moderation Commands
    embed.add_field(
        name="⚔️ Moderation",
        value=(
            "/ban — Ban a user\n"
            "/unban — Unban a user\n"
            "/kick — Kick a user\n"
            "/warn — Warn a user\n"
            "/removewarn — Remove a warning\n"
            "/showwarn — Show warnings of a user\n"
            "/purge — Delete messages\n"
            "/timeban — Temporarily ban a user\n"
        ),
        inline=False
    )

    # Utility Commands
    embed.add_field(
        name="🛠️ Utility",
        value=(
            "/help — Show this menu\n"
            "/avatar — Get a user’s avatar\n"
            "/ping — Check bot latency\n"
            "/serverinfo — Show server info\n"
            "/roleinfo — Show role info (Admin)\n"
            "/memberinfo — Show member info (Admin)\n"
        ),
        inline=False
    )

    # Setup Commands
    embed.add_field(
        name="⚙️ Setup",
        value=(
            "/setjoinmsg — Set a welcome message\n"
            "/setjoinchannel — Set welcome channel\n"
            "/setautorole — Set autorole for new members\n"
            "/setlogchannel — Set moderation log channel\n"
            "/addbadword — Add a bad word filter\n"
            "/removebadword — Remove a bad word filter\n"
        ),
        inline=False
    )

    # Fun Commands
    embed.add_field(
        name="🎉 Fun",
        value=(
            "/coinflip — Flip a coin\n"
            "/roast — Roast someone\n"
            "/joke — Tell a joke\n"
        ),
        inline=False
    )

    embed.set_footer(text="✅ Use slash commands for the best experience!")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/AnJ3wZBQab"))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# =====================================================
# 🧹 PURGE COMMAND
# =====================================================
@bot.tree.command(name="purge", description="Delete a number of messages from the channel")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, number: int):
    if number < 1:
        return await interaction.response.send_message("⚠️ Number must be greater than 0.", ephemeral=True)

    # Acknowledge immediately (avoid 3s timeout)
    await interaction.response.defer(ephemeral=True)

    deleted = await interaction.channel.purge(limit=number)
    await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)


# =====================================================
# 📢 ANNOUNCE COMMAND
# =====================================================
@bot.tree.command(name="announce", description="Send an announcement to a channel")
@app_commands.checks.has_permissions(manage_messages=True)
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, *, message: str):
    # Send plain text instead of embed
    await channel.send(message)
    await interaction.response.send_message(f"✅ Announcement sent to {channel.mention}", ephemeral=True)


# =====================================================
# 🚫 BAN COMMAND
# =====================================================
@bot.tree.command(name="ban", description="Ban a user with a reason")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, *, reason: str = "No reason provided"):
    # 1. DM the user
    try:
        await user.send(f"🚫 You were banned from {interaction.guild.name}\n**Reason:** {reason}")
    except:
        pass

    # 2. Ban user
    await interaction.guild.ban(user, reason=reason)

    # 3. Confirm in channel
    await interaction.response.send_message(f"✅ {user} has been banned.\n**Reason:** {reason}")

    # 4. Log in mod-log channel
    log_channel_id = guild_config.get(interaction.guild.id, {}).get("log_channel")
    if log_channel_id:
        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(
                title="🚫 User Banned",
                color=discord.Color.red()
            )
            embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"Guild: {interaction.guild.name}")
            await log_channel.send(embed=embed)


# =====================================================
# ⏳ TIMEBAN COMMAND
# =====================================================
@bot.tree.command(name="timeban", description="Ban a user for a number of days")
@app_commands.checks.has_permissions(ban_members=True)
async def timeban(interaction: discord.Interaction, user: discord.Member, reason: str, time: int):
    try:
        await user.send(f"⏳ You were time-banned from {interaction.guild.name} for {time} days.\n**Reason:** {reason}")
    except:
        pass
    await interaction.guild.ban(user, reason=reason)
    await interaction.response.send_message(f"✅ {user} has been banned for {time} days. Reason: {reason}")

    async def unban_later():
        await asyncio.sleep(time * 86400)  # days → seconds
        try:
            await interaction.guild.unban(user)
            await interaction.channel.send(f"🔓 {user} has been unbanned after {time} days.")
        except:
            pass

    bot.loop.create_task(unban_later())

# Set mod chaneel

# Command with channel as string (autocomplete)
@bot.tree.command(name="setlogchannel", description="Set the channel for moderation logs")
@app_commands.checks.has_permissions(administrator=True)
async def setlogchannel(interaction: discord.Interaction, channel: str):
    ch = interaction.guild.get_channel(int(channel))
    if not ch or not isinstance(ch, discord.TextChannel):
        return await interaction.response.send_message("⚠️ Invalid channel.", ephemeral=True)

    guild_config[interaction.guild.id] = {"log_channel": ch.id}
    await interaction.response.send_message(f"✅ Mod-log channel set to {ch.mention}", ephemeral=True)

# Autocomplete for the channel parameter
@setlogchannel.autocomplete("channel")
async def setlogchannel_autocomplete(interaction: discord.Interaction, current: str):
    choices = []
    for ch in interaction.guild.text_channels:
        if current.lower() in ch.name.lower():
            choices.append(app_commands.Choice(name=f"#{ch.name}", value=str(ch.id)))
    return choices[:25]  # max 25 options

# --- Run Bot ---
bot.run(TOKEN)


