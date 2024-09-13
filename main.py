#! /usr/bin/env python3
"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: A Discord bot that will handle log files generated by a SCUM server
                  and will send various events to discord.
"""
# pylint: disable=global-statement
import os
import sys
import random
import traceback

from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv

# pylint: disable=wrong-import-position
sys.path.append('./')
from logparser import ScumSFTPLogParser, LoginParser, KillParser, BunkerParser
from datamanager import ScumLogDataManager
# pylint: enable=wrong-import-position

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("DISCORD_GUILD")
SFTP_SERVER = os.getenv("SFTP_HOST")
SFTP_PORT = os.getenv("SFTP_PORT")
SFTP_USER = os.getenv("SFTP_USERNAME")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD")

DEBUG_CHANNEL = os.getenv("DEBUG_CHANNEL")
LOG_FEED_CHANNEL = os.getenv("SCUM_LOG_FEED_CHANNEL")
LOG_DIRECTORY = os.getenv("LOG_DIRECTORY")
DATABASE_FILE = os.getenv("DATABASE_FILE")
LOG_CHECK_INTERVAL = os.getenv("LOG_CHECK_INTERVAL")

if LOG_CHECK_INTERVAL is None:
    LOG_CHECK_INTERVAL = 60.0

WEAPON_LOOKUP = {
    "Compound_Bow_C": "compund bow"
}

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix="!",intents=intents)
lp: None

@client.event
async def on_ready():
    """Function is called when bot is ready"""
    global lp
    guild = None
    for guild in client.guilds:
        if guild.name == GUILD:
            break

    if guild is not None:
        print(
            f'{client.user} is connected to the following guild:\n'
            f'{guild.name}(id: {guild.id})\n'
            f'Starting log parser.'
        )
    # Open SFTP connection to the game server
    lp = ScumSFTPLogParser(server=SFTP_SERVER, port=SFTP_PORT, passwd=SFTP_PASSWORD,
                           user=SFTP_USER, logdirectoy=LOG_DIRECTORY, debug_callback=None)
    # Start the loop that checks log files periodically
    log_parser_loop.start()

async def send_debug_message(message):
    """Function will send debug messages"""
    channel = client.get_channel(int(DEBUG_CHANNEL))
    await channel.send(message)

async def handle_login(msgs, file, dbconnection):
    """parse messages from login log files"""
    channel = client.get_channel(int(LOG_FEED_CHANNEL))
    p = LoginParser()
    for m in msgs[file]:
        if not isinstance(m,set):
            for mm in str.split(m,"\n"):
                msg = p.parse(mm)
                if msg and dbconnection.check_message_send(msg["hash"]):
                    # pylint: disable=line-too-long
                    await channel.send(f"Player: {msg['username']}, logged {msg['state']} @ X={msg['coordinates']['x']} Y={msg['coordinates']['y']} Z={msg['coordinates']['z']}")
                    dbconnection.store_message_send(msg["hash"])
                    dbconnection.update_player(msg)
                    # pylint: enable=line-too-long

async def handle_kills(msgs, file, dbconnection):
    """function to construct and send kill messages"""
    channel = client.get_channel(int(LOG_FEED_CHANNEL))
    player_insults = [
        'bad boy',
        'savage',
        'bandit',
        'hero',
        'murderer'
    ]

    player_insult = random.choice(player_insults)
    p = KillParser()
    for m in msgs[file]:
        if not isinstance(m,set):
            for mm in str.split(m,"\n"):
                msg = p.parse(mm)
                if msg and dbconnection.check_message_send(msg["hash"]):
                    if msg["event"]["Weapon"] in WEAPON_LOOKUP:
                        weapon = WEAPON_LOOKUP[[msg["event"]["Weapon"]]]
                    else:
                        weapon = msg["event"]["Weapon"]
                    msg_str = f"Player {msg['event']['Killer']['ProfileName']} "
                    msg_str += f"was a {player_insult} "
                    msg_str += f"and killed {msg['event']['Victim']['ProfileName']} "
                    msg_str += f"with a {weapon}."

                    await channel.send(msg_str)
                    dbconnection.store_message_send(msg["hash"])

async def handle_bunkers(msgs, file, dbconnection):
    """handle bunker events"""
    channel = client.get_channel(int(LOG_FEED_CHANNEL))
    p = BunkerParser()
    for m in msgs[file]:
        if not isinstance(m,set):
            for mm in str.split(m,"\n"):
                msg = p.parse(mm)
                if msg and dbconnection.check_message_send(msg["hash"]):
                    # Bunker activaed
                    if msg["active"] and len(msg["since"]) > 0 and \
                       len(msg["coordinates"]) > 0 and \
                       len(msg["next"]) == 0:
                        msg_str = f"Bunker {msg['name']} was activated. "
                        msg_str += f"Coordinates @ X={msg['coordinates']['x']} "
                        msg_str += f"Y={msg['coordinates']['y']} "
                        msg_str += f"Z={msg['coordinates']['z']}"
                        await channel.send(msg_str)
                    dbconnection.update_bunker_status(msg)
                    dbconnection.store_message_send(msg["hash"])

@tasks.loop(seconds=LOG_CHECK_INTERVAL)
async def log_parser_loop():
    """Loop to parse logfiles and handle outputs"""
    db = ScumLogDataManager(DATABASE_FILE)
    await client.wait_until_ready()
    msgs = lp.scum_log_parse()
    if len(msgs) > 0:
        for file_key in msgs:
            if "login" in file_key:
                await handle_login(msgs, file_key, db)
            elif "kill" in file_key and "event" not in file_key:
                await handle_kills(msgs, file_key, db)
            elif "gameplay" in file_key:
                await handle_bunkers(msgs, file_key, db)

@client.command(name='bunkers')
async def command_bunkers(ctx, bunker: str = None):
    """Command to check Active bunkers"""
    msg_str = None
    db = ScumLogDataManager(DATABASE_FILE)
    if bunker:
        print(f"Will get data for Bunker {bunker}")
        b = db.get_active_bunkers(bunker)
        if len(b) > 0:
            if b[0]["active"] == 0:
                msg_str = f"Bunker {bunker} is not active."
                if b[0]["next"] > 0:
                    _next = b[0]["timestamp"] + b[0]["next"]
                    msg_str += "\nWill be active @ "
                    msg_str += f"{datetime.fromtimestamp(_next).strftime('%d.%m.%Y - %H:%M:%S')}"
            else:
                msg_str =f"Bunker {bunker} is active.\n"
                msg_str += f"@ Coordinates X={b[0]['coordinates']['x']} "
                msg_str += f"Y={b[0]['coordinates']['y']} "
                msg_str += f"Z={b[0]['coordinates']['z']}"
        else:
            msg_str = f"Bunker {bunker} does not exist."
    else:
        print("No bunker given, will get all active bunkers.")
        b = db.get_active_bunkers(None)
        if len(b) > 0:
            msg_str = "Following Bunkers are active.\n"
            for bunk in b:
                msg_str += f"Bunker {bunk['name']} is active.\n"
                msg_str += f"@ Coordinates X={bunk['coordinates']['x']} "
                msg_str += f"Y={bunk['coordinates']['y']} "
                msg_str += f"Z={bunk['coordinates']['z']}\n"
        else:
            msg_str = "No active bunkers found."

    await ctx.send(msg_str)

@client.command(name='online')
async def player_online(ctx, player: str):
    """Command to check if player is online"""
    message = ""
    print(f"Get status for player {player}")
    db = ScumLogDataManager(DATABASE_FILE)
    player_status = db.get_player_status(player)

    if len(player_status) == 0:
        message = f"Error: Player {player} does not exists in Database"
    else:
        if len(player_status) > 1:
            message = f"Multiple players with Name {player} found.\n"
            for p in player_status:
                if p[player]["status"] == 0:
                    state = "offline"
                else:
                    state = "online"
                message += f"{player} is currently {p[player]['status']}"
        else:
            if player_status[0][player]["status"] == 0:
                state = "offline"
            else:
                state = "online"
            message = f"Player: {player} is currently {state}."

    await ctx.send(message)

@client.command(name='lastseen')
async def player_lastseen(ctx, player: str):
    """Function to check last seen of a player"""
    message = ""
    local_timezone = ZoneInfo('Europe/Berlin')
    print(f"Get status for player {player}")
    db = ScumLogDataManager(DATABASE_FILE)
    player_status = db.get_player_status(player)

    if len(player_status) == 0:
        message = f"Error: Player {player} does not exists in Database"
    else:
        if len(player_status) > 1:
            message = f"Multiple players with Name {player} found.\n"
            for p in player_status:
                if p[player]["status"] == 0:
                    state = "offline"
                    lasstseen = datetime.fromtimestamp(player_status[0][player]["logout_timestamp"],
                                                       local_timezone).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    state = "online"
                    lasstseen = "now"
                message += f"Player: {player} is currently {state} and was last seen {lasstseen}."
        else:
            if player_status[0][player]["status"] == 0:
                state = "offline"
                lasstseen = datetime.fromtimestamp(player_status[0][player]["logout_timestamp"],
                                                   local_timezone).strftime('%Y-%m-%d %H:%M:%S')
            else:
                state = "online"
                lasstseen = "now"

            message = f"Player: {player} is currently {state} and was last seen {lasstseen}."

    await ctx.send(message)

@client.command(name='99')
async def nine_nine(ctx):
    """Print a quote from Brookly 9-9"""
    brooklyn_99_quotes = [
        'I\'m the human form of the 💯 emoji.',
        'Bingpot!',
        (
            'Cool. Cool cool cool cool cool cool cool, '
            'no doubt no doubt no doubt no doubt.'
        ),
    ]

    response = random.choice(brooklyn_99_quotes)
    await ctx.send(response)

@client.command(name='\\/')
async def spock(ctx):
    """Function post a Star Trek quote"""
    star_trek_quotes = [
        'Live long and prosper',
        'To boldly go where no one has gone before',
        (
            'Heading,  '
            'the third star from the left and follow the bow!'
        ),
    ]

    response = random.choice(star_trek_quotes)
    await ctx.send(response)


@client.command(name='roll_dice', help='Simulates rolling dice.')
async def roll(ctx, number_of_dice: int, number_of_sides: int):
    """Yeah, rolling a dice"""
    dice = [
        str(random.choice(range(1, number_of_sides + 1)))
        for _ in range(number_of_dice)
    ]
    await ctx.send(', '.join(dice))

@client.command(name='create-channel')
@commands.has_role('admin')
async def create_channel(ctx, channel_name='real-python'):
    """Function create a new channel"""
    guild = ctx.guild
    existing_channel = discord.utils.get(guild.channels, name=channel_name)
    if not existing_channel:
        print(f'Creating a new channel: {channel_name}')
        await guild.create_text_channel(channel_name)

@client.event
async def on_command_error(ctx, error):
    """Is called when commands have errors"""
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"'{error.param.name}' is a required argument.")
    else:
        # All unhandled errors will print their original traceback
        print(f'Ignoring exception in command {ctx.command}:', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

client.run(TOKEN)
