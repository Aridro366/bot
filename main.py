import discord
from discord.ext import commands, tasks
from discord import app_commands, File
from discord.ui import View, Button
from datetime import datetime, timedelta
import time
import os
import asyncio
import random
import aiohttp
import io
import pytz
from dotenv import load_dotenv
from keep_alive import keep_alive
import re
from collections import defaultdict

import qrcode


keep_alive()

# -------------------- CONFIG --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# Local timezone
local_tz = pytz.timezone("Asia/Kolkata")

load_dotenv()
TOKEN = os.getenv("TOKEN")
PREFIX = "."
OWNER_ID = 1314811739837038675
GUILD_ID = 1443271947894128784
SCRIPT_LOG_ID_CHANNEL= 1443591110642499594
SUPPORT_CHANNEL_ID = 1443442650673057894
MOD_LOG_CHANNEL_ID = 1453322866199367741

# Staff IDs
STAFF_IDS = [1314811739837038675 , 
             1303751390505734174,
        ]  # Add more IDs as needed




user_message_cache = defaultdict(list)
# -------------------- BOT INIT --------------------
bot = commands.Bot(command_prefix=PREFIX, intents=intents , help_command=None)

# -------------------- AFK DATA --------------------
afk_data = {}  # {guild_id: {user_id: {"reason": str, "time": float}}}

def set_afk(guild_id, user_id, reason):
    if guild_id not in afk_data:
        afk_data[guild_id] = {}
    afk_data[guild_id][user_id] = {
        "reason": reason,
        "time": time.time()
    }

def remove_afk(guild_id, user_id):
    if guild_id in afk_data and user_id in afk_data[guild_id]:
        del afk_data[guild_id][user_id]

def is_afk(guild_id, user_id):
    return guild_id in afk_data and user_id in afk_data[guild_id]

def format_duration(seconds):
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

# -------------------- EVENTS --------------------


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(e)
    bot.loop.create_task(rotate_status())
    print("Status rotation started!")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    # ---- AFK REMOVE ----
    if is_afk(guild_id, user_id):
        start_time = afk_data[guild_id][user_id]["time"]
        reason = afk_data[guild_id][user_id]["reason"]
        afk_seconds = time.time() - start_time
        remove_afk(guild_id, user_id)
        await message.channel.send(
            f"🟢 **{message.author.display_name}** is back!\n"
            f"⏱ AFK Duration: **{format_duration(afk_seconds)}**\n"
            f"📌 Reason was: {reason}"
        )

    # ---- AFK MENTION CHECK ----
    for user in message.mentions:
        if is_afk(guild_id, user.id):
            data = afk_data[guild_id][user.id]
            duration = format_duration(time.time() - data["time"])
            await message.reply(
                f"⚠️ **{user.display_name}** is AFK!\n"
                f"📌 Reason: {data['reason']}\n"
                f"⏱ AFK for: **{duration}**"
            )

    # Process commands
    await bot.process_commands(message)

    # ---- FIX: Trigger ONLY when bot is directly tagged ----
    if message.mentions and message.mentions[0].id == bot.user.id and not message.reference:
        response = (
            f"Yo {message.author.mention} 😎,\n\n"
            "I'm **Royal Store Bot**, your chill assistant running things smoothly ⚡.\n\n"
            "I help with:\n"
            "🛒 Orders & receipts\n"
            "💸 Payment checks\n"
            "🎫 Tickets & support\n\n"
            "Need anything? Just ping staff or open a ticket — we got you 👍\n\n"
            "Enjoy your stay and grab some cool deals 🌟"
        )
        await message.channel.send(response)


# -------------------- STATUS ROTATION --------------------
fun_texts = [
    "Debugging myself 🐞", "looking for orders!!" , "need help?? ping me!!"
]

async def rotate_status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        total_members = sum(g.member_count for g in bot.guilds)
        await bot.change_presence(activity=discord.Game(name=f"Members: {total_members}"))
        await asyncio.sleep(10)
        random_text = random.choice(fun_texts)
        await bot.change_presence(activity=discord.Game(name=random_text))
        await asyncio.sleep(10)

# -------------------- PREFIX COMMANDS --------------------
@bot.command()
async def afk(ctx, *, reason="AFK"):
    set_afk(ctx.guild.id, ctx.author.id, reason)
    await ctx.send(f"🟡 **{ctx.author.display_name}** is now AFK: {reason}")

def staff_only(ctx):
    return ctx.author.id in STAFF_IDS


@bot.command()
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, message: str):
    try:
        await ctx.message.delete()
    except:
        pass
    
    # Rebuild the message manually so emojis don't break
    clean_msg = str(message).encode("utf-8").decode("utf-8")

    await ctx.send(clean_msg)



@bot.command()
async def announce(ctx, *, message):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    embed = discord.Embed(
        title="📢 Announcement",
        description=message,
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

# -------------------- SLASH COMMANDS --------------------
@bot.tree.command(name="afk", description="Set your AFK status")
async def slash_afk(interaction: discord.Interaction, reason: str = "AFK"):
    set_afk(interaction.guild.id, interaction.user.id, reason)
    await interaction.response.send_message(
        f"🟡 **{interaction.user.display_name}** is now AFK: {reason}", ephemeral=False
    )

# Staff-only slash commands

def staff_only_slash(interaction: discord.Interaction):
    staff_perms = interaction.user.guild_permissions
    return staff_perms.manage_roles or staff_perms.administrator


@bot.tree.command(name="say", description="Make the bot say something")
async def slash_say(interaction: discord.Interaction, message: str):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message(
            "❌ You are not allowed to use this command.",
            ephemeral=True
        )

    # allow emojis, mentions, formatting
    await interaction.response.send_message(message, allowed_mentions=discord.AllowedMentions.all())


# -------------------- THANKS COMMANDS --------------------
async def send_simple_thanks(channel: discord.TextChannel):
    paragraph = (
        "🎉 Thank you for your purchase! 🎉\n\n"
        "We truly appreciate your support and hope you enjoy your item. "
        "Your satisfaction is our priority, and our team is always here to help if you need any assistance. "
        "We look forward to serving you again in the future! "
    )
    await channel.send(paragraph)

@bot.command(name="thanks")
async def thanks_prefix(ctx):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        await ctx.message.delete()
    except:
        pass
    await send_simple_thanks(ctx.channel)

@bot.tree.command(name="thanks", description="Send a thank-you message at the end")
async def thanks_slash(interaction: discord.Interaction):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    await interaction.response.send_message("✅ Thanks message sent.", ephemeral=True)
    await send_simple_thanks(interaction.channel)

# -------------------- SERVER INFO --------------------
@bot.command(name="server_info")
async def server_info_cmd(ctx):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    guild = ctx.guild
    embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blurple(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    embed.add_field(name="Server ID", value=guild.id, inline=False)
    embed.add_field(name="Owner", value=guild.owner, inline=False)
    embed.add_field(name="Members", value=guild.member_count, inline=False)
    embed.add_field(name="Roles", value=len(guild.roles), inline=False)
    embed.add_field(name="Channels", value=len(guild.channels), inline=False)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    await ctx.send(embed=embed)

@bot.tree.command(name="server_info", description="Get detailed server info")
async def server_info_slash(interaction: discord.Interaction):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    guild = interaction.guild
    embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blurple(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    embed.add_field(name="Server ID", value=guild.id, inline=False)
    embed.add_field(name="Owner", value=guild.owner, inline=False)
    embed.add_field(name="Members", value=guild.member_count, inline=False)
    embed.add_field(name="Roles", value=len(guild.roles), inline=False)
    embed.add_field(name="Channels", value=len(guild.channels), inline=False)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    await interaction.response.send_message(embed=embed)

# -------------------- MEMBER INFO --------------------
@bot.command(name="member_info")
async def member_info_cmd(ctx, member: discord.Member = None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    member = member or ctx.author
    embed = discord.Embed(title=f"Member Info: {member}", color=discord.Color.green(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Display Name", value=member.display_name, inline=False)
    embed.add_field(name="Bot?", value=member.bot, inline=False)
    embed.add_field(name="Top Role", value=member.top_role, inline=False)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    await ctx.send(embed=embed)

@bot.tree.command(name="member_info", description="Get detailed member info")
@app_commands.describe(member="The member to get info for")
async def member_info_slash(interaction: discord.Interaction, member: discord.Member = None):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    member = member or interaction.user
    embed = discord.Embed(title=f"Member Info: {member}", color=discord.Color.green(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Display Name", value=member.display_name, inline=False)
    embed.add_field(name="Bot?", value=member.bot, inline=False)
    embed.add_field(name="Top Role", value=member.top_role, inline=False)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=False)
    await interaction.response.send_message(embed=embed)

# -------------------- DETAILED INFO --------------------
@bot.command(name="detailed_info")
async def detailed_info_cmd(ctx, member: discord.Member = None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    member = member or ctx.author
    guild = ctx.guild
    embed = discord.Embed(title=f"Detailed Info: {member}", color=discord.Color.purple(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Display Name", value=member.display_name, inline=True)
    embed.add_field(name="Bot?", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role, inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Server Name", value=guild.name, inline=True)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Total Members", value=guild.member_count, inline=True)
    await ctx.send(embed=embed)

@bot.tree.command(name="detailed_info", description="Get detailed info about a member + server")
@app_commands.describe(member="The member to get detailed info for")
async def detailed_info_slash(interaction: discord.Interaction, member: discord.Member = None):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    member = member or interaction.user
    guild = interaction.guild
    embed = discord.Embed(title=f"Detailed Info: {member}", color=discord.Color.purple(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Display Name", value=member.display_name, inline=True)
    embed.add_field(name="Bot?", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role, inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y %H:%M:%S"), inline=True)
    embed.add_field(name="Server Name", value=guild.name, inline=True)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Total Members", value=guild.member_count, inline=True)
    await interaction.response.send_message(embed=embed)


@bot.command(name="purge")
async def purge_prefix(ctx, amount: int):
    # Check if user is staff
    if ctx.author.id not in STAFF_IDS:
        return await ctx.send("❌ You are not allowed to use this command.", delete_after=5)

    # Validate amount
    if amount <= 0:
        return await ctx.send("❌ Please provide a number greater than 0.", delete_after=5)

    # Delete the command message first
    try:
        await ctx.message.delete()
    except:
        pass

    # Purge messages
    deleted = await ctx.channel.purge(limit=amount)
    confirmation = await ctx.send(f"✅ Deleted {len(deleted)} messages.")
    await confirmation.delete(delay=5)  # auto-delete confirmation


@bot.tree.command(
    name="give_receipt", 
    description="Give a purchase receipt to a member as a TXT file and log it"
)
@app_commands.describe(
    member="Member who purchased", 
    item="Purchased item", 
    price="Price"
)
async def give_receipt_slash(interaction: discord.Interaction, member: discord.Member, item: str, price: str):
    # Staff check
    if interaction.user.id not in STAFF_IDS:
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)

    # Generate receipt
    receipt_id = random.randint(1000, 9999)
    time_now = datetime.utcnow().astimezone(local_tz).strftime("%d %b %Y %H:%M:%S")
    receipt_text = (
        f"--- PURCHASE RECEIPT ---\n\n"
        f"Member: {member.name}#{member.discriminator}\n"
        f"Item: {item}\n"
        f"Price: {price}\n"
        f"Receipt ID: {receipt_id}\n"
        f"Issued by: {interaction.user.name}#{interaction.user.discriminator}\n"
        f"Time: {time_now}\n"
        f"------------------------"
    )
    file = discord.File(io.StringIO(receipt_text), filename=f"receipt_{receipt_id}.txt")

    # Send receipt to buyer DM
    try:
        await member.send(content="🧾 Here is your purchase receipt:", file=file)
        dm_status = "✅ Receipt sent to buyer DMs."
    except Exception:
        dm_status = "❌ Could not send receipt DM (buyer may have DMs disabled)."

    # Log in staff channel
    guild = bot.get_guild(GUILD_ID)
    log_channel = guild.get_channel(SCRIPT_LOG_ID_CHANNEL)
    if log_channel:
        embed = discord.Embed(
            title="🛒 Purchase Logged",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Buyer", value=member.mention, inline=True)
        embed.add_field(name="Item", value=item, inline=True)
        embed.add_field(name="Price", value=price, inline=True)
        embed.add_field(name="Receipt ID", value=receipt_id, inline=True)
        embed.add_field(name="Issued by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Time", value=time_now, inline=True)
        embed.set_footer(text="Store Bot")
        await log_channel.send(embed=embed)

    # Confirm in command (ephemeral)
    await interaction.response.send_message(f"Receipt created for {member.mention}. {dm_status}", ephemeral=True)


@bot.event
async def on_member_join(member):
    try:
        # ---- CONFIG ----
        WELCOME_CHANNEL_ID = 1443404889894948974  # your welcome channel ID
        PING_CHANNEL_IDS = [
        1443409906458951784,
        1443409287102599290,
        1443410881743552533,
        1443411776610898112,
        1443436150655287376,
        1449400155273957377,
        ]

        DELETE_AFTER = 2  # seconds
        GIF_URL = "https://cdn.discordapp.com/attachments/1443571210452467782/1444395990239936676/welcome.gif?ex=692c8e17&is=692b3c97&hm=540497f44cec782c13d1881dc85bd54f86cfa34a66892525983b7c6e8b8f3330"

        # ---- MEMBER COUNT ----
        member_count = len(member.guild.members)

        # ---- BIG WELCOME MSG (Server) ----
        msg = (
            f"👑 **Welcome to Royal Store, {member.mention}!**\n\n"
            f"🎉 You are now the **{member_count}th member** to join our community.\n"
            f"We’re excited to have you here!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💛 **What We Offer:**\n"
            "• ⚡ **Instant Delivery** — No waiting, no delays\n"
            "• 💸 **Best Prices** — Cheapest rates in the market\n"
            "• 🛡 **100% Safe & Verified** services\n"
            "• 🤝 **Trusted by many customers**\n"
            "• 🔒 **Secure payments & reliable support**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📩 If you need help with *anything*, feel free to open a ticket.\n"
            "Our team is always ready to assist you!\n\n"
            "✨ **Enjoy your stay at Royal Store!**"
        )

        # ---- EMBED (ONLY GIF) ----
        embed = discord.Embed(color=discord.Color.gold())
        embed.set_image(url=GIF_URL)

        # ---- SEND TO SERVER ----
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(content=msg, embed=embed)

        # ---- DM MESSAGE ----
        dm_msg = (
            f"👑 **Welcome to Royal Store, {member.mention}!**\n\n"
            f"You're our **{member_count}th member**, and we’re thrilled to have you join us.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💛 **What You Can Expect:**\n"
            "• ⚡ Instant & Smooth Delivery\n"
            "• 🛡 Safe & Secure Services\n"
            "• 💸 Best Pricing Guaranteed\n"
            "• 🤝 Trusted by many\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "If you need help or want to place an order, feel free to open a ticket anytime.\n"
            "Our staff is always here for you!\n\n"
            "✨ Enjoy your time at Royal Store!"
        )

        dm_embed = discord.Embed(color=discord.Color.gold())
        dm_embed.set_image(url=GIF_URL)

        try:
            await member.send(content=dm_msg, embed=dm_embed)
        except:
            pass  # user has DMs closed

    except Exception as e:
        print(f"Welcome Error: {e}")

    for channel_id in PING_CHANNEL_IDS:
        try:
            channel = await bot.fetch_channel(channel_id)
            msg = await channel.send(member.mention)
            asyncio.create_task(delete_later(msg, DELETE_AFTER))
        except Exception as e:
            print("JOIN PING FAILED:", channel_id, e)


async def delete_later(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

# -------------------- In-memory giveaways --------------------
active_giveaways = {}  # giveaway_id -> giveaway info

# -------------------- Time parser --------------------
def parse_time(time_str: str):
    pattern = r"(\d+)(s|m|h|d|w|mo)"
    match = re.fullmatch(pattern, time_str.lower())
    if not match:
        return None
    amount, unit = match.groups()
    amount = int(amount)
    return {
        "s": amount,
        "m": amount*60,
        "h": amount*3600,
        "d": amount*86400,
        "w": amount*604800,
        "mo": amount*2592000,
    }[unit]

def format_time(seconds):
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if mins > 0: parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

# -------------------- Giveaway Buttons --------------------
class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(emoji="🎉", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = active_giveaways.get(self.giveaway_id)
        if not giveaway:
            return await interaction.response.send_message("❌ Giveaway ended.", ephemeral=True)
        if interaction.user.id in giveaway["participants"]:
            return await interaction.response.send_message("⚠️ Already joined!", ephemeral=True)
        giveaway["participants"].append(interaction.user.id)
        await interaction.response.send_message(f"✅ You joined the giveaway!", ephemeral=True)
        await update_embed(giveaway)

# -------------------- Helper Functions --------------------
async def update_embed(giveaway, ended=False):
    time_left = max(0, int(giveaway["end_time"] - asyncio.get_event_loop().time()))
    
    title = f"🎁 {giveaway['prize']} 🎁"
    if ended:
        title = f"🏁 GIVEAWAY ENDED 🏁\n{title}"
    
    embed = discord.Embed(
        title=title,
        color=discord.Color.green()
    )
    
    embed.add_field(name="🎤 Hosted By", value=giveaway['host'].mention, inline=True)
    embed.add_field(name="🎯 Winners", value=str(giveaway['winners']), inline=True)
    embed.add_field(name="👥 Participants", value=str(len(giveaway['participants'])), inline=True)
    if not ended:
        embed.add_field(name="⏱ Time Left", value=format_time(time_left), inline=True)
    
    if giveaway.get("requirements"):
        embed.add_field(name="✅ Requirements", value=giveaway['requirements'], inline=True)
    
    if not ended:
        embed.set_footer(text="🎉 Click the button to join!")
    else:
        embed.set_footer(text="🏁 The giveaway has ended!")

    await giveaway["message"].edit(embed=embed)

async def announce_winner(giveaway, reroll=False):
    participants = giveaway["participants"]
    channel = giveaway["channel"]

    # Disable buttons
    if giveaway.get("view"):
        for child in giveaway["view"].children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await giveaway["message"].edit(view=giveaway["view"])

    # Update embed to show ended
    await update_embed(giveaway, ended=True)
    
    if participants:
        winners_list = random.sample(participants, min(giveaway["winners"], len(participants)))
        mentions = ", ".join([channel.guild.get_member(uid).mention for uid in winners_list])
        if reroll:
            await channel.send(f"🔄 Giveaway reroll! New winner(s): {mentions} 🎉")
        else:
            await channel.send(f"🏆 Winner(s): {mentions} 🎉")
    else:
        await channel.send(f"😢 No participants for **{giveaway['prize']}**.")

# -------------------- Slash Commands --------------------
@bot.tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(
    duration="Duration (e.g., 30s,5m,2h,1d,1w,1mo)",
    winners="Number of winners",
    prize="Prize name",
    requirements="Optional requirements"
)
async def giveaway_cmd(interaction: discord.Interaction, duration: str, winners: int, prize: str, requirements: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only staff can start giveaways.", ephemeral=True)

    seconds = parse_time(duration)
    if seconds is None:
        return await interaction.response.send_message("❌ Invalid duration! Use s,m,h,d,w,mo", ephemeral=True)

    giveaway_id = random.randint(100000, 999999)
    view = GiveawayView(giveaway_id)

    title = f"🎁 {prize} 🎁"
    embed = discord.Embed(title=title, color=discord.Color.green())
    embed.add_field(name="🎤 Hosted By", value=interaction.user.mention, inline=True)
    embed.add_field(name="🎯 Winners", value=str(winners), inline=True)
    embed.add_field(name="👥 Participants", value="0", inline=True)
    embed.add_field(name="⏱ Duration", value=duration, inline=True)
    if requirements:
        embed.add_field(name="✅ Requirements", value=requirements, inline=True)
    embed.set_footer(text="🎉 Click the button to join!")

    msg = await interaction.channel.send(embed=embed, view=view)

    # Store giveaway
    end_time = asyncio.get_event_loop().time() + seconds
    active_giveaways[giveaway_id] = {
        "prize": prize,
        "channel": interaction.channel,
        "winners": winners,
        "participants": [],
        "end_time": end_time,
        "message": msg,
        "host": interaction.user,
        "view": view,
        "requirements": requirements
    }
    view.giveaway_id = giveaway_id

    await interaction.response.send_message(f"✅ Giveaway **{prize}** started!", ephemeral=True)

    # Countdown loop
    async def countdown():
        while True:
            giveaway = active_giveaways.get(giveaway_id)
            if not giveaway:
                break
            time_left = int(giveaway["end_time"] - asyncio.get_event_loop().time())
            if time_left <= 0:
                active_giveaways.pop(giveaway_id, None)
                await announce_winner(giveaway)
                break
            await update_embed(giveaway)
            await asyncio.sleep(5)

    bot.loop.create_task(countdown())

# -------------------- Reroll --------------------
@bot.tree.command(name="reroll", description="Reroll the latest giveaway")
async def reroll_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only staff can reroll.", ephemeral=True)
    if not active_giveaways:
        return await interaction.response.send_message("❌ No active giveaways.", ephemeral=True)
    giveaway_id = max(active_giveaways.keys())
    giveaway = active_giveaways[giveaway_id]
    await announce_winner(giveaway, reroll=True)
    await interaction.response.send_message(f"🔄 Giveaway **{giveaway['prize']}** rerolled.", ephemeral=True)

# -------------------- Manual Winner --------------------
@bot.tree.command(name="choose", description="Choose a specific winner for the latest giveaway")
@app_commands.describe(member="Member to choose as winner")
async def choose_cmd(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only staff can do this.", ephemeral=True)
    if not active_giveaways:
        return await interaction.response.send_message("❌ No active giveaways.", ephemeral=True)
    giveaway_id = max(active_giveaways.keys())
    giveaway = active_giveaways[giveaway_id]
    await giveaway["channel"].send(f"🏆 Manual winner chosen: {member.mention} 🎉")
    # Update embed as ended
    await update_embed(giveaway, ended=True)
    await interaction.response.send_message(f"✅ {member.mention} chosen as winner.", ephemeral=True)



def parse_time_simple(time_str: str):
    match = re.fullmatch(r"(\d+)(s|m|h|d|w|mo)", time_str.lower())
    if not match:
        return None

    val, unit = match.groups()
    val = int(val)

    return {
        "s": val,
        "m": val * 60,
        "h": val * 3600,
        "d": val * 86400,
        "w": val * 604800,
        "mo": val * 2592000
    }[unit]

def format_time(sec):
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def get_update_interval(seconds_left):
    if seconds_left >= 15 * 86400:
        return 86400       # 1 day
    elif seconds_left >= 86400:
        return 3600        # 1 hour
    elif seconds_left >= 10 * 3600:
        return 600         # 10 minutes
    elif seconds_left >= 3600:
        return 300         # 5 minutes
    elif seconds_left >= 600:
        return 60          # 1 minute
    elif seconds_left >= 60:
        return 10          # 10 seconds
    else:
        return 1           # last minute

@bot.command(name="timer")
async def timer_cmd(ctx, duration: str):
    total_seconds = parse_time_simple(duration)
    if not total_seconds or total_seconds <= 0:
        return await ctx.send("❌ Use format: `10s`, `5m`, `2h`, `1d`, `15d`")

    end_time = asyncio.get_event_loop().time() + total_seconds

    msg = await ctx.send(
        f"⏱ **Timer Started**\n"
        f"⏳ Time Left: `{format_time(total_seconds)}`"
    )

    while True:
        remaining = int(end_time - asyncio.get_event_loop().time())
        if remaining <= 0:
            break

        interval = get_update_interval(remaining)

        try:
            await msg.edit(
                content=(
                    f"⏱ **Timer Running**\n"
                    f"⏳ Time Left: `{format_time(remaining)}`"
                )
            )
        except:
            return  # message deleted / no perms

        await asyncio.sleep(interval)

    await msg.edit(
        content=f"⏰ **TIME UP!**\n{ctx.author.mention} your timer has ended."
    )


# MOds

async def send_mod_log(guild, action, moderator, target, reason=None, duration=None):
    channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title=f"🔨 {action}",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="User", value=f"{target} ({target.id})", inline=False)
    embed.add_field(name="Moderator", value=moderator.mention, inline=False)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duration", value=duration, inline=False)

    await channel.send(embed=embed)


async def try_dm(user, message):
    try:
        await user.send(message)
    except:
        pass


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if member.top_role >= ctx.author.top_role:
        return await ctx.send("❌ You cannot ban this user.")

    await try_dm(
        member,
        f"🔨 You were **BANNED** from **{ctx.guild.name}**\n📄 Reason: {reason}"
    )

    await member.ban(reason=reason)
    await ctx.send(f"✅ {member.mention} banned.")
    await send_mod_log(ctx.guild, "Ban", ctx.author, member, reason)


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    if member.top_role >= ctx.author.top_role:
        return await ctx.send("❌ You cannot kick this user.")

    await try_dm(
        member,
        f"👢 You were **KICKED** from **{ctx.guild.name}**\n📄 Reason: {reason}"
    )

    await member.kick(reason=reason)
    await ctx.send(f"✅ {member.mention} kicked.")
    await send_mod_log(ctx.guild, "Kick", ctx.author, member, reason)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    if member.top_role >= ctx.author.top_role:
        return await ctx.send("❌ You cannot timeout this user.")

    duration = timedelta(minutes=minutes)

    await member.edit(
        timed_out_until=discord.utils.utcnow() + duration,
        reason=reason
    )

    await try_dm(
        member,
        f"⏱ You were **TIMED OUT** in **{ctx.guild.name}**\n"
        f"🕒 Duration: {minutes} minutes\n📄 Reason: {reason}"
    )

    await ctx.send(f"⏱ {member.mention} timed out for {minutes} minutes.")
    await send_mod_log(ctx.guild, "Timeout", ctx.author, member, reason, f"{minutes} minutes")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    await try_dm(
        member,
        f"⚠️ You were **WARNED** in **{ctx.guild.name}**\n📄 Reason: {reason}"
    )

    await ctx.send(f"⚠️ {member.mention} warned.")
    await send_mod_log(ctx.guild, "Warn", ctx.author, member, reason)


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="No reason provided"):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
    except:
        return await ctx.send("❌ Invalid user ID or user not banned.")

    await ctx.send(f"✅ {user} unbanned.")
    await send_mod_log(ctx.guild, "Unban", ctx.author, user, reason)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don’t have permission.", ephemeral=True )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments.", ephemeral=True)
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument.", ephemeral=True)
    else:
        print(error)
# PAYMENT ___________________________________________________________________________________________________

UPI_ID = "bossakhil53@okicici"
PAYEE_NAME = "Royal Store"


async def send_payment_confirmation(channel: discord.TextChannel, buyer: discord.Member):
    embed = discord.Embed(
        title="💰 Payment Confirmed!",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="Order Status:",
        value=(
            "✅ Payment received\n\n"
            "The order is placed. Please be patient — our staff will deliver the product soon.\n"
            "❌ No need to ping our staff.\n\n"
            "⏱️ If you do not get any response, you may ping after 3 hours."
        ),
        inline=False
    )
    embed.set_footer(text="— Royal Store Bot")
    embed.set_thumbnail(
        url="https://cdn.discordapp.com/attachments/1443532706167394366/1443648455850594507/file_0000000083987209a5c2fc9ed6b956a4.png"
    )

    await channel.send(embed=embed)

class QRPaymentView(View):
    def __init__(self, buyer: discord.Member):
        super().__init__(timeout=None)
        self.buyer = buyer
        self.confirmed = False

    @discord.ui.button(
        label="Confirm Payment",
        emoji="✅",
        style=discord.ButtonStyle.green
    )
    async def confirm_payment(
        self,
        interaction: discord.Interaction,
        button: Button
    ):
        # Staff only
        if interaction.user.id not in STAFF_IDS:
            return await interaction.response.send_message(
                "❌ Only staff can confirm payments.",
                ephemeral=True
            )

        if self.confirmed:
            return await interaction.response.send_message(
                "⚠️ Payment already confirmed.",
                ephemeral=True
            )

        self.confirmed = True
        button.disabled = True
        await interaction.message.edit(view=self)

        await send_payment_confirmation(interaction.channel, self.buyer)

        await interaction.response.send_message(
            "✅ Payment confirmed successfully.",
            ephemeral=True
        )
@bot.command(name="qr")
async def qr_cmd(ctx, amount: int = None, buyer: discord.Member = None):
    if ctx.author.id not in STAFF_IDS:
        return await ctx.send("❌ Staff only command.")

    if amount is None or amount <= 0:
        return await ctx.send("❌ Usage: `=qr <amount> @buyer`")

    buyer = buyer or ctx.author

    # Create UPI link
    upi_url = (
        f"upi://pay?"
        f"pa={UPI_ID}"
        f"&pn={PAYEE_NAME}"
        f"&am={amount}"
        f"&cu=INR"
    )

    # Generate QR
    qr = qrcode.make(upi_url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    file = discord.File(buffer, filename=f"QR_{amount}.png")

    embed = discord.Embed(
        title="💳 UPI Payment",
        description=(
            f"**Buyer:** {buyer.mention}\n"
            f"**Amount:** ₹{amount}\n\n"
            "Scan the QR and complete the payment.\n"
            "Staff will confirm below."
        ),
        color=discord.Color.gold()
    )

    await ctx.send(
        embed=embed,
        file=file,
        view=QRPaymentView(buyer)
    )

# -------------------- RUN BOT --------------------
ALLOWED_GUILDS = [GUILD_ID]
@bot.event
async def on_guild_join(guild):
    if guild.id not in ALLOWED_GUILDS:
        await guild.leave()

bot.run(TOKEN)




