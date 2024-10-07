# SCUM Discord Bot

preliminary readme

## Supported commands

    * !online <user> - Returns if a user is online or not. <user> is optional.
    * !lastseen <user> - Returns if a user is online or not and lasst seen time if offline.
    * !bunkers <bunker> - Returns if bunker is active. <bunker> is optional.
    * !lifetime <user> - Returns the lifetime of a player on the Server. <user> is optional.
    * !config <config key> <config value> - configure some bot setting during runtime. (Only for role BOT_USER_ADMIN_ROLE)
      valid keys and values:
        -> reply: private or same_channel - when private will respond via DM. same_channel reply to same channel.
        -> publish_login: 0 = disable, 1 = enable. When enabled will report logins to SCUM_LOG_FEED_CHANNEL
        -> publish_bunkers: 0 = disable, 1 = enable. When enabled will report bunker activations to SCUM_LOG_FEED_CHANNEL
        -> publish_kills: 0 = disable, 1 = enable. When enabled will report kills to SCUM_LOG_FEED_CHANNEL

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

BOT_HELP_COMMAND= # Command to print bot help (default: buffi)
BOT_USER_ADMIN_ROLE= # Admin role that is allowed to modify bot runtime configuration (default: sbot_admin)
                     # Role has to be created on server.

```

## Build and run docker
```
    docker build -t scum_bot .
    docker run --name scum_bot -d -v ".env:/app/.env" -v "db.sqlite3:/app/db.sqlite3" scum_bot
```
