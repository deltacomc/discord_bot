"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 09.09.2024
    @CLicense: MIT
    @Description:
"""
# pylint: disable=line-too-long
import os
import sqlite3
from datetime import datetime
from modules.output import Output

SCHEMA_VERSION = 106

class ScumLogDataManager:
    """Manage Database access for bot"""
    db = None
    db_file = ""
    logging: Output

    def __init__(self, db_name) -> None:
        self.logging = Output(_stderr = False)
        self.db_file = db_name
        if not os.path.exists(self.db_file):
            # pylint: disable=unused-variable
            with open(self.db_file , "w", encoding="UTF-8") as fp:
                pass
            # pylint: enable=unused-variable

        self.db = sqlite3.connect(db_name)
        self._check_schema()

    def _check_schema(self):
        cursor = self.db.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS scum_schema (name TEXT, schema_version INTEGER PRIMARY KEY)")
        self.db.commit()
        try:
            schema_version = cursor.execute("SELECT schema_version FROM scum_schema WHERE name = 'schema'")
            ver = schema_version.fetchone()
            if ver is not None:
                if ver[0] >= SCHEMA_VERSION:
                    return True
                elif ver[0] < SCHEMA_VERSION:
                    self._update_schema()
                    return True
                else:
                    return False
            else:
                self._init_schema()
        except sqlite3.OperationalError as e:
            self.logging.error(e)
            self._init_schema()
            return True

    def _update_schema(self):
        # Call init to create none existing tables
        self._init_schema()
        # Update existing tables
        # check if new column exists that we want to add
        check_column = "SELECT COUNT(*) AS CNTREC FROM "
        check_column += "pragma_table_info('player') WHERE name='server_lifetime'"
        cursor = self.db.cursor()
        cursor.execute(check_column)
        result = cursor.fetchone()
        if result[0] == 0:
        # update table
            add_column = "ALTER TABLE player "
            add_column += "ADD server_lifetime INTEGER DEFAULT 0"
            cursor.execute(add_column)
            self.db.commit()

        check_column = "SELECT COUNT(*) AS CNTREC FROM "
        check_column += "pragma_table_info('player') WHERE name='drone'"
        cursor = self.db.cursor()
        cursor.execute(check_column)
        result = cursor.fetchone()
        if result[0] == 0:
        # update table
            add_column = "ALTER TABLE player "
            add_column += "ADD drone BOOL DEFAULT 0"
            cursor.execute(add_column)
            self.db.commit()

    def _init_schema(self):
        cursor = self.db.cursor()
        ## Table does not exists so we create out tables
        cursor.execute("CREATE TABLE IF NOT EXISTS player (id INTEGER PRIMARY KEY, timestamp INTEGER, steamid INTEGER,\
                       username TEXT, loggedin BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL, \
                       login_timestamp INTEGER, logout_timestamp INTEGER, server_lifetime INTEGER, drone BOOL)")

        cursor.execute("CREATE TABLE IF NOT EXISTS bunkers (id INTEGER PRIMARY KEY, timestamp INTEGER, \
                       name TEXT, active BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL, \
                       since INTEGER, next INTEGER)")

        cursor.execute("CREATE TABLE IF NOT EXISTS admin_audit (id INTEGER PRIMARY KEY, timestamp INTEGER, \
                       name TEXT, steamid INTEGER, type TEXT, action TEXT)")

        cursor.execute("CREATE TABLE IF NOT EXISTS message_send (hash TEXT PRIMARY KEY, timestamp REAL)")

        cursor.execute("CREATE TABLE IF NOT EXISTS log_hashes (timestamp REAL, hash TEXT PRIMARY KEY, file TEXT)")

        cursor.execute("CREATE TABLE IF NOT EXISTS config (config_key TEXT PRIMARY KEY, config_parameter TEXT)")

        cursor.execute("CREATE TABLE IF NOT EXISTS fame (steamid INTEGER PRIMARY KEY, points INTEGER)")

        cursor.execute("CREATE TABLE IF NOT EXISTS guild_members (name TEXT PRIMARY KEY, \
                       roles TEXT, bot_role TEXT)")

        cursor.execute("CREATE TABLE IF NOT EXISTS scum_schema (name TEXT, schema_version INTEGER PRIMARY KEY)")

        self._update_schema_version()

        self.db.commit()

    def _update_schema_version(self):
        self.logging.info("Update Database Schema version.")
        cursor = self.db.cursor()
        check_column = "SELECT COUNT(*) AS CNTREC FROM "
        check_column += "scum_schema WHERE name='schema'"
        cursor.execute(check_column)
        result = cursor.fetchone()
        if result[0] == 0:
            cursor.execute(f"INSERT INTO scum_schema (name, schema_version) VALUES ('schema', {SCHEMA_VERSION})")
        else:
            cursor.execute(f"UPDATE scum_schema SET schema_version={SCHEMA_VERSION} WHERE name = 'schema'")

    def _get_timestamp(self, string):
        return datetime.strptime(string, "%Y.%m.%d-%H.%M.%S").timestamp()

    def _get_time_delta(self, string):
        s = string.split(sep=":")
        retval = int(s[0])*3600 + int(s[1])*60 + int(s[2])
        return retval

    def _discard_old_values(self, table, age_secs):
        age_timestamp = datetime.timestamp(datetime.now()) - age_secs
        age_time = datetime.strftime(datetime.fromtimestamp(age_timestamp), "%d.%m.%Y %H:%M:%S")
        self.logging.info(f"Discarding values older than {age_time} from Table {table}")
        statement = f"DELETE FROM {table} where timestamp < {age_timestamp}"
        cursor = self.db.cursor()
        cursor.execute(statement)
        self.db.commit()

    def store_message_send(self, message_hash):
        """store send message in database"""
        cursor = self.db.cursor()
        cursor.execute(f"SELECT hash FROM message_send WHERE hash = '{message_hash}'")
        if len(cursor.fetchall()) > 0:
            print ("Hash already stored. Not updating database.")
        else:
            cursor.execute(f"INSERT INTO message_send (hash, timestamp) VALUES ('{message_hash}', {datetime.timestamp(datetime.now())})")
            self.db.commit()

    def check_message_send(self, message_hash):
        """Will check if a messages is already sent.
            Return True if it isn't stored
            Return False if it is already stored in database"""
        cursor = self.db.cursor()
        cursor.execute(f"SELECT hash FROM message_send WHERE hash = '{message_hash}'")

        if len(cursor.fetchall()) > 0:
            hashes = cursor.fetchall()
            for mhash in hashes:
                if mhash == message_hash:
                    return False
        else:
            return True

    def update_player(self, player):
        """update player data in database"""
        cursor = self.db.cursor()
        cursor.execute(f"SELECT * FROM player WHERE steamid = '{player['steamID']}'")
        player_data = cursor.fetchall()
        if len(player_data) > 1:
            self.logging.warning("Multiple entries found with same steamID")
            return False
        elif len(player_data) == 0:
            self.logging.warning("No User with steamID in Database")
            if player["state"] == "in":
                state = True
                loggedin_timestamp = self._get_timestamp(player['timestamp'])
                loggedout_timestamp = 0
            else:
                state = False
                loggedin_timestamp = 0
                loggedout_timestamp = self._get_timestamp(player['timestamp'])

            cursor.execute(f"INSERT INTO player (timestamp, steamid, username, loggedin, coordinates_x, \
                           coordinates_y, coordinates_z, login_timestamp, logout_timestamp, server_lifetime, drone) \
                           VALUES ({self._get_timestamp(player['timestamp'])}, {player['steamID']}, '{player['username']}', \
                           {state}, {player['coordinates']['x']}, {player['coordinates']['y']}, {player['coordinates']['z']}, \
                           {loggedin_timestamp}, {loggedout_timestamp}, 0, {player['drone']})")
            self.db.commit()
            return True
        else:
            if player["state"] == "in":
                state = True
                loggedin_timestamp = self._get_timestamp(player['timestamp'])
                cursor.execute(f"UPDATE player SET  \
                               timestamp = {self._get_timestamp(player['timestamp'])}, \
                               loggedin = {state}, \
                               coordinates_x = {player['coordinates']['x']}, \
                               coordinates_y = {player['coordinates']['y']}, \
                               coordinates_z = {player['coordinates']['z']}, \
                               login_timestamp = {loggedin_timestamp}, \
                               drone = {player['drone']} \
                               WHERE steamid == '{player['steamID']}'")

            else:
                state = False
                login_ts = player_data[0][8]
                was_drone = player['drone']
                player['drone'] = False
                loggedout_timestamp = self._get_timestamp(player['timestamp'])
                if login_ts > 0 and login_ts < loggedout_timestamp and not was_drone:
                    server_lifetime = loggedout_timestamp - login_ts
                    server_lifetime_all = server_lifetime + player_data[0][10]
                else:
                    server_lifetime_all = player_data[0][10]
                cursor.execute(f"UPDATE player SET  \
                               timestamp = {self._get_timestamp(player['timestamp'])}, \
                               loggedin = {state}, \
                               coordinates_x = {player['coordinates']['x']}, \
                               coordinates_y = {player['coordinates']['y']}, \
                               coordinates_z ={player['coordinates']['z']}, \
                               logout_timestamp = {loggedout_timestamp}, \
                               server_lifetime = {server_lifetime_all}, \
                               drone = {player['drone']} \
                               WHERE steamid == '{player['steamID']}'")
            self.db.commit()
            return True

    def update_bunker_status(self, bunker):
        """update bunker status in database"""
        cursor = self.db.cursor()
        cursor.execute(f"SELECT * FROM bunkers WHERE name = '{bunker['name']}'")
        bunker_data = cursor.fetchall()
        statement = None
        if len(bunker_data) == 0:
            self.logging.info(f"Bunker {bunker['name']} not in Database")
            if len(bunker["coordinates"]) != 0 and len(bunker["next"]) == 0 and bunker["active"]:
                statement = "INSERT INTO bunkers (name, timestamp, active, since, next,"
                statement += "coordinates_x, coordinates_y, coordinates_z) VALUES "
                statement += f"('{bunker['name']}', {self._get_timestamp(bunker['timestamp'])}, {bunker['active']},"
                statement += f"self._get_time_delta({bunker['since']['h']}:{bunker['since']['m']}:{bunker['since']['s']}),"
                statement += "0,"
                statement += f"{bunker['coordinates']['x']},{bunker['coordinates']['y']},{bunker['coordinates']['z']})"
            elif len(bunker["next"]) != 0 and not bunker["active"]:
                statement = "INSERT INTO bunkers (name, timestamp, active, since, next,"
                statement += "coordinates_x, coordinates_y, coordinates_z) VALUES "
                statement += f"('{bunker['name']}', {self._get_timestamp(bunker['timestamp'])}, {bunker['active']},"
                statement += f"{self._get_time_delta(bunker['since']['h']+':'+bunker['since']['m']+':'+bunker['since']['s'])},"
                statement += f"{self._get_time_delta(bunker['next']['h']+':'+bunker['next']['m']+':'+bunker['next']['s'])},"
                statement += f"{bunker['coordinates']['x']},{bunker['coordinates']['y']},{bunker['coordinates']['z']})"
            elif len(bunker["next"]) == 0 and len(bunker["coordinates"]) == 0 and bunker["active"]:
                statement = "INSERT INTO bunkers (name, timestamp, active, since, next,"
                statement += "coordinates_x, coordinates_y, coordinates_z) VALUES "
                statement += f"('{bunker['name']}', {self._get_timestamp(bunker['timestamp'])}, {bunker['active']},"
                statement += f"{self._get_time_delta(bunker['since']['h']+':'+bunker['since']['m']+':'+bunker['since']['s'])},"
                statement += "0, 0, 0, 0)"

            elif len(bunker["next"]) == 0 and len(bunker["since"]) == 0 and not bunker["active"]:
                statement = "INSERT INTO bunkers (name, timestamp, active, since, next,"
                statement += "coordinates_x, coordinates_y, coordinates_z) VALUES "
                statement += f"('{bunker['name']}', {self._get_timestamp(bunker['timestamp'])}, {bunker['active']},"
                statement += "0, 0, 0, 0, 0)"

        elif len(bunker_data) == 1:
            self.logging.info(f"Bunker {bunker['name']} in Database")
            if len(bunker["coordinates"]) > 0 and len(bunker["next"]) == 0 and bunker["active"]: # Active
                statement = "UPDATE bunkers SET "
                statement += f"timestamp = {self._get_timestamp(bunker['timestamp'])},"
                statement += f"active = {bunker['active']},"
                statement += f"since = {self._get_time_delta(bunker['since']['h']+':'+bunker['since']['m']+':'+bunker['since']['s'])},"
                statement += f"coordinates_x = {bunker['coordinates']['x']},"
                statement += f"coordinates_y = {bunker['coordinates']['y']},"
                statement += f"coordinates_z = {bunker['coordinates']['z']} "
                statement += f"WHERE name = '{bunker['name']}'"
            elif len(bunker["next"]) != 0 and not bunker["active"]: # Locked
                statement = "UPDATE bunkers SET "
                statement += f"timestamp = {self._get_timestamp(bunker['timestamp'])},"
                statement += f"active = {bunker['active']},"
                statement += f"since = {self._get_time_delta(bunker['since']['h']+':'+bunker['since']['m']+':'+bunker['since']['s'])},"
                statement += f"next = {self._get_time_delta(bunker['next']['h']+':'+bunker['next']['m']+':'+bunker['next']['s'])},"
                statement += f"coordinates_x = {bunker['coordinates']['x']},"
                statement += f"coordinates_y = {bunker['coordinates']['y']},"
                statement += f"coordinates_z = {bunker['coordinates']['z']} "
                statement += f"WHERE name = '{bunker['name']}'"
            elif len(bunker["next"]) == 0 and len(bunker["coordinates"]) == 0 and bunker["active"]: # Activated
                statement = "UPDATE bunkers SET "
                statement += f"timestamp = {self._get_timestamp(bunker['timestamp'])},"
                statement += f"active = {bunker['active']},"
                statement += f"since = {self._get_time_delta(bunker['since']['h']+':'+bunker['since']['m']+':'+bunker['since']['s'])} "
                statement += f"WHERE name = '{bunker['name']}'"
            elif len(bunker["next"]) == 0 and len(bunker["since"]) == 0 and not bunker["active"]: # Deactivated
                statement = "UPDATE bunkers SET "
                statement += f"timestamp = {self._get_timestamp(bunker['timestamp'])},"
                statement += f"active = {bunker['active']},"
                statement += "since = 0,"
                statement += "next = 0,"
                statement += "coordinates_x = 0,"
                statement += "coordinates_y = 0,"
                statement += "coordinates_z = 0 "
                statement += f"WHERE name = '{bunker['name']}'"
        else:
            self.logging.info(f"Not updateing database more than one bunker found with the same name {bunker['name']}")

        if statement:
            cursor.execute(''.join(statement))
            self.db.commit()

    def get_player_status(self, player_name = None) -> list:
        """get player data from database"""
        ret_val = []
        cursor = self.db.cursor()
        if player_name:
            cursor.execute(f"SELECT * FROM player WHERE username = '{player_name}'")
        else:
            cursor.execute("SELECT * FROM player")
        player_data = cursor.fetchall()

        if len(player_data) == 0:
            ret_val = []
        elif len(player_data) > 1:
            self.logging.info("Found more than one Player with that name.")
            for p in player_data:
                ret_val.append({
                               "name": p[3],
                               "status": p[4],
                               "login_timestamp" : p[8],
                               "logout_timestamp" : p[9],
                               "lifetime": p[10],
                               "drone": p[11]
                               })
        else:
            self.logging.info("One Player found.")
            ret_val.append({"name": player_data[0][3],
                "status": player_data[0][4],
                "login_timestamp" : player_data[0][8],
                "logout_timestamp" : player_data[0][9],
                "lifetime": player_data[0][10],
                "drone": player_data[0][11]
                })

        return ret_val

    def get_active_bunkers(self, bunker: str = None) -> list:
        """Get all or for one specific bunker the active state"""
        retval = []
        cursor = self.db.cursor()

        if bunker:
            cursor.execute(f"SELECT * FROM bunkers WHERE name = '{bunker.upper()}'")
            bunker_data = cursor.fetchall()
            if len(bunker_data) == 0:
                retval = []
            elif len(bunker_data) > 1:
                # 1, 1726252409, 'C1', 1, -393614.781, 216967.266, 59906.152, 0, 0
                self.logging.info(f"Found more than one Bunker with name {bunker}.")
                for p in bunker_data:
                    retval.append({
                            "name": p[2],
                            "timestamp": p[1],
                            "active": p[3],
                            "since" : p[7],
                            "next" : p[8],
                            "coordinates": {
                                "x": p[4],
                                "y": p[5],
                                "z": p[6]
                            }
                            })
            else:
                self.logging.info(f"One Bunker found for {bunker}.")
                retval.append({
                        "name": bunker_data[0][2],
                        "timestamp": bunker_data[0][1],
                        "active": bunker_data[0][3],
                        "since" : bunker_data[0][7],
                        "next" : bunker_data[0][8],
                        "coordinates": {
                            "x": bunker_data[0][4],
                            "y": bunker_data[0][5],
                            "z": bunker_data[0][6]
                        }
                    })
        else:
            cursor.execute("SELECT * FROM bunkers WHERE active = 1")
            bunker_data = cursor.fetchall()
            if len(bunker_data) == 0:
                retval = []
            else:
                # 1, 1726252409, 'C1', 1, -393614.781, 216967.266, 59906.152, 0, 0
                self.logging.info("Got data for all bunkers.")
                for p in bunker_data:
                    retval.append({
                            "name": p[2],
                            "timestamp": p[1],
                            "active": p[3],
                            "since" : p[7],
                            "next" : p[8],
                            "coordinates": {
                                "x": p[4],
                                "y": p[5],
                                "z": p[6]
                            }
                            })
        return retval

    def discard_aged_messages(self, age: int) -> None:
        """discard old send messages from table
           Parameters:
            age: int in seconds
        """
        self._discard_old_values("message_send", age)

    def discard_stale_players(self, age: int) -> None:
        """discard old send messages from table
           Parameters:
            age: int in seconds
        """
        self._discard_old_values("player", age)

    def discard_old_logfiles(self, age: int) -> None:
        """discard old log file hashes from table
           Parameters:
            age: int in seconds
        """
        self._discard_old_values("log_hashes", age)


    def discard_old_admin_audtis(self, age: int) -> None:
        """discard old log file hashes from table
           Parameters:
            age: int in seconds
        """
        self._discard_old_values("admin_audit", age)

    def raw(self, query: str) -> list[any]:
        """raw sql query"""
        cursor = self.db.cursor()
        ret = cursor.execute(query)
        return ret.fetchall()

    def update_log_file_hash(self, _hash: str, file: str) -> None:
        """update log file hash in database"""
        curr_time = datetime.timestamp(datetime.now())
        query = f"SELECT hash FROM log_hashes WHERE hash = '{_hash}'"
        repl = self.raw(query)
        if len(repl) == 0:
            query = "INSERT INTO log_hashes (timestamp, hash, file) "
            query += f"VALUES ({curr_time}, '{_hash}', '{file}')"
            repl = self.raw(query)
            self.db.commit()

    def get_log_file_hashes(self) -> dict:
        """get log file hash from database"""
        retval= {}
        query = "SELECT * FROM log_hashes"
        repl = self.raw(query)
        for item in repl:
            retval.update({item[1]: item[2]})

        return retval

    def save_config(self, config: dict):
        """Save config in database"""
        query = "SELECT * FROM config"
        reply = self.raw(query)
        db_config = {}
        for r in reply:
            db_config.update({r[0]: r[1]})
        for key in config:
            value = config[key]
            if key not in db_config:
                query = "INSERT INTO config (config_key, config_parameter) "
                query += f"VALUES ('{key}', '{value}')"
            else:
                if db_config[key] != str(value):
                    query = "UPDATE config SET config_parameter = "
                    query += f"'{value}' WHERE config_key = '{key}'"
                else:
                    # nothing to update
                    query = ""

            if query:
                self.raw(query)
                self.db.commit()

    def load_config(self) -> dict:
        """Save config in database"""
        query = "SELECT * FROM config"
        reply = self.raw(query)
        retval = {}
        for item in reply:
            retval.update({item[0]: item[1]})

        return retval

    def update_admin_audit(self, audit_data: dict) -> None:
        """store data in table admin_audit"""
        audit_data.update({'action': audit_data['action'].replace("'", "")})
        audit_timestamp = self._get_timestamp(audit_data["time"])
        query = "INSERT INTO admin_audit "
        query += "(timestamp, steamid, name, type, action) "
        query += f"VALUES ({audit_timestamp}, {audit_data['steamid']}, "
        query += f"'{audit_data['name']}', '{audit_data['type']}', '{audit_data['action']}'"
        query += ")"

        self.raw(query)
        self.db.commit()

    def get_admin_audit(self, by: str = None, value: str = None) -> list:
        """ get audit data """
        retval = []
        if by is None and value is None:
            query = "SELECT timestamp, steamid, name, type, action from admin_audit"
        elif by == "age" and value is not None:
            query = "SELECT timestamp, steamid, name, type, "
            query += f"action from admin_audit where timestamp >= {int(value)}"

        result = self.raw(query)
        for r in result:
            retval.append({
                "timestamp": r[0],
                "steamid": r[1],
                "username": r[2],
                "type": r[3],
                "action": r[4]
            })

        return retval

    def update_fame_points(self, _data: dict) -> None:
        """update fame points"""
        query = f"SELECT * from fame where steamid = {_data['steamid']}"
        sel = self.raw(query)
        print(sel)
        print(_data)
        if len(sel) == 0:
            query = "INSERT INTO fame (steamid, points) VALUES "
            query += f"({_data['steamid']}, {_data['points']})"
            self.raw(query)
        else:
            query = f"UPDATE fame SET steamid = {_data['steamid']} "
            query += f", points = {_data['points']}"
            self.raw(query)

        self.db.commit()

    def get_fame_points(self, name: str) -> dict:
        """ get fame points """
        retval = {}
        query = f"SELECT steamid from player where name = '{name}'"
        sel = self.raw(query)
        if len(sel) == 0:
            query = f"SELECT * from fame where steamid = {sel['steamid']}"
            sel_points = self.raw(query)
            retval.update({
                name: sel_points["points"]
            })
        return retval

    def update_guild_member(self, name: str, guild_role: str, bot_role: str) -> None:
        """ Update guild members"""
        query = "SELECT * FROM guild_members"
        res = self.raw(query)
        if len(res) == 0:
            query = "INSERT INTO guild_members (name, roles, bot_role)"
            query += f" VALUES ({name}, {guild_role}, {bot_role})"
        else:
            query = "UPDATE guild_members SET"
            query += f" roles='{guild_role}', bot_role='{bot_role}'"
            query += f" WHERE name='{name}'"

        self.raw(query)
        self.db.commit()

    def get_guild_member(self, name: str = "") -> dict:
        """ get guild members"""
        retval = {}
        if name != "":
            query = f"SELECT * FROM guild_members WHERE name='{name}'"
        else:
            query = "SELECT * FROM guild_members"

        res = self.raw(query)
        if len(res) != 0:
            for member in res:
                retval.update({
                    name: {
                        "guild_role": member[2],
                        "bot_role": member[3]
                    }
                })

        return retval

    def close(self) -> None:
        """close database connection"""
        self.db.commit()
        self.db.close()

# pylint: enable=line-too-long
