# SCUM Discord Bot

preliminary readme

## Supported commands

    * !online <user> - Returns if a user is online or not
    * !lastseen <user> - Returns if a user is online or not and lasst seen time if offline
    * !bunkers <bunker> - Returns if bunker is active. <bunker> is optional.

## configure env-file
```
DISCORD_TOKEN = "<discord-token>"
DISCORD_GUILD = "<server-name>"

SCUM_LOG_FEED_CHANNEL = "<channel-id>"

DATABASE_FILE = "/app/db.sqlite3"

SFTP_HOST= # SFTP-Host
SFTP_PORT= # SFTP-Port
SFTP_USERNAME= # SFTP-User
SFTP_PASSWORD= # SFTP-Passwort
LOG_DIRECTORY= # Path to logfiles
LOG_CHECK_INTERVAL= 60 # Interval in which bot will check server log files (default: 60 seconds)

BOT_HELP_COMMAND= # Command to print bot help (default: buff)

```

## Build and run docker
```
    docker build -t scum_bot .
    docker run --name scum_bot -d -v ".env:/app/.env" -v "db.sqlite3:/app/db.sqlite3" scum_bot
```
