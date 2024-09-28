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
#sys.path.append('./')
from modules.datamanager import ScumLogDataManager
from modules.logparser import LoginParser, KillParser, BunkerParser
from modules.sftploader import ScumSFTPLogParser
from modules.output import Output
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
HELP_COMMAND = os.getenv("BOT_HELP_COMMAND")


if LOG_CHECK_INTERVAL is None:
    LOG_CHECK_INTERVAL = 60.0
else:
    LOG_CHECK_INTERVAL = float(LOG_CHECK_INTERVAL)

if HELP_COMMAND is None:
    HELP_COMMAND = "buffi"

WEAPON_LOOKUP = {
    "Compound_Bow_C": "compund bow"
}

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix="!",intents=intents)
lp: None

logging = Output()

@client.event
async def on_ready():
    """Function is called when bot is ready"""
    global lp
    guild = None
    for guild in client.guilds:
        if guild.name == GUILD:
            break

    if guild is not None:
        logging.info(
            f'{client.user} is connected to the following guild:\n'
            f'{guild.name}(id: {guild.id})\n'
            f'Starting log parser.'
        )
    #call database manager to initialize db
    ScumLogDataManager(DATABASE_FILE)

    # Open SFTP connection to the game server
    lp = ScumSFTPLogParser(server=SFTP_SERVER, port=SFTP_PORT, passwd=SFTP_PASSWORD,
                           user=SFTP_USER, logdirectoy=LOG_DIRECTORY,
                           database=DATABASE_FILE, debug_callback=None)

    # Start the loop that checks log files periodically
    if not log_parser_loop.is_running():
        log_parser_loop.start()

def _convert_time(in_sec: int):
    days = 0
    hours = 0
    minutes = 0
    seconds = in_sec

    days = int(in_sec / 86400)
    seconds = in_sec % 86400

    hours = int(seconds / 3600)
    seconds = seconds % 3600

    minutes = int(seconds / 60)
    seconds = int(seconds % 60)

    return f"{days:02d}d {hours:02d}:{minutes:02d}:{seconds:02d}"

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
                    msg_str = f"Player: {msg['username']}, logged "
                    msg_str += f"{msg['state']} @ [X={msg['coordinates']['x']} "
                    msg_str += f"Y={msg['coordinates']['y']} Z={msg['coordinates']['z']}]"
                    msg_str += f"(https://scum-map.com/en/map/place/{msg['coordinates']['x']}"
                    msg_str += f",{msg['coordinates']['y']},3)"
                    await channel.send(msg_str)
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

                    bunker_data = dbconnection.get_active_bunkers(msg['name'])
                    if len(bunker_data) == 0:
                        bunker_data.append({"active": 0})
                    print(bunker_data)
                    print(msg)
                    print(msg["active"] and len(msg["since"]) > 0 and \
                       len(msg["coordinates"]) > 0 and \
                       len(msg["next"]) == 0 and bunker_data[0]['active'] == 0)
                    print(msg["active"] and bunker_data[0]['active'] == 0)
                    if msg["active"] and bunker_data[0]['active'] == 0:
                        msg_str = f"Bunker {msg['name']} was activated. "
                        if len(msg["coordinates"]) != 0:
                            msg_str += f"[Coordinates @ X={msg['coordinates']['x']} "
                            msg_str += f"Y={msg['coordinates']['y']} "
                            msg_str += f"Z={msg['coordinates']['z']}]"
                            msg_str += "(https://scum-map.com/en/map/place/"
                            msg_str += f"{msg['coordinates']['x']}"
                            msg_str += f",{msg['coordinates']['y']},3)"
                        elif len(bunker_data[0]['coordinates']) != 0:
                            msg_str += f"[Coordinates @ X={bunker_data[0]['coordinates']['x']} "
                            msg_str += f"Y={bunker_data[0]['coordinates']['y']} "
                            msg_str += f"Z={bunker_data[0]['coordinates']['z']}]"
                            msg_str += "(https://scum-map.com/en/map/place/"
                            msg_str += f"{bunker_data[0]['coordinates']['x']}"
                            msg_str += f",{bunker_data[0]['coordinates']['y']},3)"
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

    if datetime.now().hour == 0 and datetime.now().minute == 0:
        db.discard_old_logfiles(30*86400)
    db.close()

@log_parser_loop.error
async def on_loop_error(error):
    """Error handler for the loop"""
    logging.error(f"Error during loop occoured: {error}")
    if log_parser_loop.failed() and not log_parser_loop.is_running():
        log_parser_loop.start()
    elif log_parser_loop.failed and log_parser_loop.is_running():
        log_parser_loop.restart()
    else:
        pass

@client.command(name="lifetime")
async def command_lifetime(ctx, player: str = None):
    """Command to check server liftime of players"""
    msg_str = None
    db = ScumLogDataManager(DATABASE_FILE)
    if player:
        logging.info(f"Get server lifetime for player {player}")
        player_stat = db.get_player_status(player)
        if len(player_stat) > 0:
            lifetime = _convert_time(player_stat[0]["lifetime"])
            msg_str = f"Player {player} lives on server for {lifetime}."
        else:
            msg_str = f"Player {player} has no life on this server."
    else:
        logging.info("Getting all players that visited the server")
        # msg_str = "Not yet implemented to get all players."
        player_stat = db.get_player_status()
        msg_str = "Following players have a liftime on this server:\n"
        for p in player_stat:
            lifetime = _convert_time(p["lifetime"])
            msg_str += f"{p['name']} lives for {lifetime} on this server.\n"

    await ctx.send(msg_str)
    db.close()

@client.command(name='bunkers')
async def command_bunkers(ctx, bunker: str = None):
    """Command to check Active bunkers"""
    msg_str = None
    db = ScumLogDataManager(DATABASE_FILE)
    if bunker:
        logging.info(f"Will get data for Bunker {bunker}")
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
                msg_str += f"@ [Coordinates X={b[0]['coordinates']['x']} "
                msg_str += f"Y={b[0]['coordinates']['y']} "
                msg_str += f"Z={b[0]['coordinates']['z']}]"
                msg_str += f"(https://scum-map.com/en/map/place/{b[0]['coordinates']['x']}"
                msg_str += f",{b[0]['coordinates']['y']},3)"
        else:
            msg_str = f"Bunker {bunker} does not exist."
    else:
        logging.info("No bunker given, will get all active bunkers.")
        b = db.get_active_bunkers(None)
        if len(b) > 0:
            msg_str = "Following Bunkers are active.\n"
            for bunk in b:
                msg_str += f"Bunker {bunk['name']} is active.\n"
                msg_str += f"@ [Coordinates X={bunk['coordinates']['x']} "
                msg_str += f"Y={bunk['coordinates']['y']} "
                msg_str += f"Z={bunk['coordinates']['z']}]"
                msg_str += f"(https://scum-map.com/en/map/place/{b[0]['coordinates']['x']}"
                msg_str += f",{b[0]['coordinates']['y']},3)\n"
        else:
            msg_str = "No active bunkers found."

    await ctx.send(msg_str)
    db.close()

@client.command(name='online')
async def player_online(ctx, player: str = None):
    """Command to check if player is online"""
    message = ""
    local_timezone = ZoneInfo('Europe/Berlin')
    logging.info(f"Get status for player {player}")
    db = ScumLogDataManager(DATABASE_FILE)
    if player:
        player_status = db.get_player_status(player)

        if len(player_status) == 0:
            message = f"Error: Player {player} does not exists in Database"
        else:
            if len(player_status) > 1:
                message = f"Multiple players with Name {player} found.\n"
                for p in player_status:
                    if p["status"] == 0:
                        state = "offline"
                    else:
                        state = "online"
                    message += f"{player} is currently {p['status']}"
            else:
                if player_status[0]["status"] == 0:
                    state = "offline"
                else:
                    state = "online"
                message = f"Player: {player} is currently {state}."
    else:
        player_status = db.get_player_status()
        if len(player_status) > 0:
            message = "Follwoing Players are online:\n"
            for p in player_status:
                if p["status"] == 1:
                    login = datetime.fromtimestamp(p['login_timestamp'],
                                                    local_timezone).strftime('%d.%m.%Y %H:%M:%S')
                    message += f"{p['name']} is online since {login}\n"
        else:
            message = "No players are online at the moment."

    await ctx.send(message)
    db.close()

@client.command(name='lastseen')
async def player_lastseen(ctx, player: str):
    """Function to check last seen of a player"""
    message = ""
    local_timezone = ZoneInfo('Europe/Berlin')
    logging.info(f"Get status for player {player}")
    db = ScumLogDataManager(DATABASE_FILE)
    player_status = db.get_player_status(player)

    if len(player_status) == 0:
        message = f"Error: Player {player} does not exists in Database"
    else:
        if len(player_status) > 1:
            message = f"Multiple players with Name {player} found.\n"
            for p in player_status:
                if p["status"] == 0:
                    state = "offline"
                    lasstseen = datetime.fromtimestamp(p["logout_timestamp"],
                                                       local_timezone).strftime('%d.%m.%Y %H:%M:%S')
                else:
                    state = "online"
                    lasstseen = "now"
                message += f"Player: {player} is currently {state} and was last seen {lasstseen}."
        else:
            if player_status[0]["status"] == 0:
                state = "offline"
                lasstseen = datetime.fromtimestamp(player_status[0]["logout_timestamp"],
                                                   local_timezone).strftime('%Y-%m-%d %H:%M:%S')
            else:
                state = "online"
                lasstseen = "now"

            message = f"Player: {player} is currently {state} and was last seen {lasstseen}."

    await ctx.send(message)
    db.close()

@client.command(name=HELP_COMMAND)
async def bot_help(ctx):
    """Help command"""
    msg_str = f"Hi, {ctx.author}. My Name is {client.user}.\n"
    msg_str += "You can call me with following commands:\n"

    await ctx.send(msg_str)

    msg_str = "!online <player name> - I will tell you if the"
    msg_str += "player with <name> is online on the SCUM server\n"

    await ctx.send(msg_str)

    msg_str = "!lastseen <player name> - I will tell you when I have seen <playername>"
    msg_str += "on the SCUM Server\n"

    await ctx.send(msg_str)

    msg_str = "!bunkers <bunker name> - I will tell you if the <bunker name> is active.\n"
    msg_str += "But the <bunker name> is optional. Without I unveil the secret and give"
    msg_str += " you all active bunkers."

    await ctx.send(msg_str)

    msg_str = "I will also report bunker openening, kills and players joining to and disconnecting "
    msg_str += "from the SCUM Server."

    await ctx.send(msg_str)

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
        logging.info(f'Creating a new channel: {channel_name}')
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
        logging.error(f'Ignoring exception in command {ctx.command}:')
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

client.run(TOKEN)
