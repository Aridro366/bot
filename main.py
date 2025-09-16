import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
print("Token loaded:", token)  # For debugging

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to Royal Empire @{member.name}.. Need help? write '!Help' in https://discord.com/channels/1396670355422056609/1396801885322739743 ")

bad_words = ["shit", "bullshit", "fuck", "fucking", "fucked", "damn", "bitch", "bitches",
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
    "bit.ly", "tinyurl", "goo.gl", "http", "www", "click here", "join now", "subscribe", "adult", "xxxvideos", "escort", "camgirl", "onlyfans"]
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    msg_content = message.content.lower()
    for word in bad_words:
        if word in msg_content:
           await message.delete()
           await message.channel.send(f"{message.author.mention} -Plz avoid using inappropriate words!")

    if "!help" in message.content.lower():
        await message.channel.send(f" Hello {message.author.mention}! Welcome to the server \n You can take roles from https://discord.com/channels/1396670355422056609/1396726703564525688 \n and ping Staff in https://discord.com/channels/1396670355422056609/1396801885322739743 for further assistance")

    await bot.process_commands(message)


bot.run(token, log_handler=handler, log_level=logging.DEBUG)