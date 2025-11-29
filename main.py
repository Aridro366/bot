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
LOG_CHANNEL_ID = 1443591110642499594
MOD_LOG = 1443595332393897984
SUPPORT_CHANNEL_ID = 1443442650673057894

# Staff IDs
STAFF_IDS = [1314811739837038675 , 
             1303751390505734174
        ]  # Add more IDs as needed

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

    # Remove AFK when user speaks
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

    # Notify if mentioned someone AFK
    if message.mentions:
        for user in message.mentions:
            if is_afk(guild_id, user.id):
                data = afk_data[guild_id][user.id]
                duration = format_duration(time.time() - data["time"])
                await message.reply(
                    f"⚠️ **{user.display_name}** is AFK!\n"
                    f"📌 Reason: {data['reason']}\n"
                    f"⏱ AFK for: **{duration}**"
                )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Process commands
    await bot.process_commands(message)

    # Respond when mentioned
    if bot.user in message.mentions:
        response = (
            f"Yo {message.author.mention} 😎,\n\n"
            "I'm **Royal Store Bot**, just your friendly helper around here.\n"
            "Made by a decent dude named **Arideep**, keeping this store running smooth ⚡.\n\n"
            "I can help you with stuff like:\n"
            "🛒 Orders & receipts\n"
            "💸 Payment confirmations\n"
            "🎫 Tickets & staff support\n\n"
            "Need something? Don’t hesitate—ping the staff or drop a ticket. "
            "We got you covered 👍\n\n"
            "Now go explore, grab some deals, and have fun around here 🌟"
        )
        await message.channel.send(response)


# -------------------- STATUS ROTATION --------------------
fun_texts = [
    "Chilling 😎", "Protecting the server 🛡️", "Cooking some code 🍳",
    "Watching over the members 👀", "Booting in the cloud ☁️",
    "Debugging myself 🐞", "Serving chaos and order ⚖️",
    "Online and active ⚡", "looking for orders!!" , "need help?? ping me!!"
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

# Staff-only command example
@bot.command()
async def say(ctx, *, message):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    await ctx.message.delete()
    await ctx.send(message)

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
def staff_only_slash(interaction):
    return interaction.user.id in STAFF_IDS

@bot.tree.command(name="say", description="Make the bot say something")
async def slash_say(interaction: discord.Interaction, message: str):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    await interaction.response.send_message(message)

@bot.tree.command(name="announce", description="Send an announcement")
async def slash_announce(interaction: discord.Interaction, message: str):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

# -------------------- MODERATION COMMANDS --------------------
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ {member.mention} has been banned.")
        # Log mod action
        await MOD_LOG(ctx, "Ban", member, reason)
    except discord.Forbidden:
        await ctx.send("❌ I do not have permission to ban this member.")
    except discord.HTTPException:
        await ctx.send("❌ Failed to ban member.")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ {member.mention} has been kicked.")
        await MOD_LOG(ctx, "Kick", member, reason)
    except discord.Forbidden:
        await ctx.send("❌ I do not have permission to kick this member.")
    except discord.HTTPException:
        await ctx.send("❌ Failed to kick member.")

@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason=None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        duration = timedelta(minutes=minutes)
        await member.edit(timed_out_until=discord.utils.utcnow() + duration, reason=reason)
        await ctx.send(f"⏱️ {member.mention} has been timed out for {minutes} minutes.")
        await MOD_LOG(ctx, "Timeout", member, reason, duration=minutes)
    except discord.Forbidden:
        await ctx.send("❌ I do not have permission to timeout this member.")
    except discord.HTTPException:
        await ctx.send("❌ Failed to timeout member.")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason=None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"✅ {user} has been unbanned.")
        await MOD_LOG(ctx, "Unban", user, reason)
    except discord.NotFound:
        await ctx.send(f"❌ User with ID {user_id} is not banned.")
    except discord.Forbidden:
        await ctx.send("❌ I do not have permission to unban this user.")
    except discord.HTTPException:
        await ctx.send("❌ Failed to unban user.")

# -------------------- QR COMMANDS --------------------
@bot.command(name="QR")
async def qr_prefix(ctx, number: int):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    file_path = os.path.join("qrs", f"QR{number}.png")
    if os.path.isfile(file_path):
        await ctx.send(file=File(file_path))
    else:
        await ctx.send(f"❌ QR{number} not found!")

@bot.tree.command(name="qr", description="Send your Paytm QR")
@app_commands.describe(number="Which QR to send (1, 2, 3...)")
async def slash_qr(interaction: discord.Interaction, number: int):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    file_path = os.path.join("qrs", f"QR{number}.png")
    if os.path.isfile(file_path):
        await interaction.response.send_message(file=File(file_path))
    else:
        await interaction.response.send_message(f"❌ QR{number} not found!", ephemeral=True)

# -------------------- PAYMENT CONFIRMATION --------------------
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
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1443532706167394366/1443648455850594507/file_0000000083987209a5c2fc9ed6b956a4.png?ex=6929d5e5&is=69288465&hm=49467e5d26540322bd6967d0cda522bb09bdba41af7691878f6967df83bfe72b")
    await channel.send(embed=embed)

@bot.command(name="pp")
async def pp_prefix(ctx, buyer: discord.Member = None):
    if not staff_only(ctx):
        return await ctx.send("❌ You are not allowed to use this command.")
    try:
        await ctx.message.delete()
    except:
        pass
    buyer = buyer or ctx.author
    await send_payment_confirmation(ctx.channel, buyer)

@bot.tree.command(name="pp", description="Send payment confirmation for an order")
@app_commands.describe(buyer="Buyer who made the payment")
async def pp_slash(interaction: discord.Interaction, buyer: discord.Member = None):
    if not staff_only_slash(interaction):
        return await interaction.response.send_message("❌ You are not allowed to use this command.", ephemeral=True)
    await interaction.response.send_message("✅ Payment confirmation sent.", ephemeral=True)
    buyer = buyer or interaction.user
    await send_payment_confirmation(interaction.channel, buyer)

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
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
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


# -------------------- RUN BOT --------------------
ALLOWED_GUILDS = [GUILD_ID]
@bot.event
async def on_guild_join(guild):
    if guild.id not in ALLOWED_GUILDS:
        await guild.leave()

bot.run(TOKEN)
