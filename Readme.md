# SCUM Discord Bot

preliminary readme

## configure env-file
```
DISCORD_TOKEN = "<discord-token>"
DISCORD_GUILD = "<server-name>"

SCUM_KILL_FEED_CHANNEL = "<channel-id>"

DATABASE_FILE = "/app/db.sqlite3"

SFTP_HOST= # SFTP-Host
SFTP_PORT= # SFTP-Port
SFTP_USERNAME= # SFTP-User
SFTP_PASSWORD= # SFTP-Passwort
LOG_DIRECTORY= # Path to logfiles
```

## Build and run docker
```
    docker build -t scum_bot .
    docker run --name scum_bot -d -v ".env:/app/.env" -v "db.sqlite3:/app/db.sqlite3" scum_bot
```
