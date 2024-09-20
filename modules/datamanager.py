"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 09.09.2024
    @CLicense: MIT
    @Description:
"""
# pylint: disable=line-too-long
import sqlite3
from datetime import datetime
from modules.output import Output

SCHEMA_VERSION = 103

class ScumLogDataManager:
    """Manage Database access for bot"""
    db = None
    db_file = ""
    logging: Output

    def __init__(self, db_name) -> None:
        self.logging = Output(_stderr = False)
        self.db_file = db_name
        self.db = sqlite3.connect(db_name)
        self._check_schema()

    def _check_schema(self):
        cursor = self.db.cursor()
        try:
            schema_version = cursor.execute("SELECT schema_version FROM scum_schema WHERE name = 'schema'")
            ver = schema_version.fetchone()
            if ver[0] >= SCHEMA_VERSION:
                return True
            elif ver[0] < SCHEMA_VERSION:
                self._update_schema()
                return True
            else:
                return False
        except sqlite3.Error as e:
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

    def _init_schema(self):
        cursor = self.db.cursor()
        ## Table does not exists so we create out tables
        cursor.execute("CREATE TABLE IF NOT EXISTS player (id INTEGER PRIMARY KEY, timestamp INTEGER, steamid INTEGER,\
                       username TEXT, loggedin BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL, \
                       login_timestamp INTEGER, logout_timestamp INTEGER, server_lifetime INTEGER)")

        cursor.execute("CREATE TABLE IF NOT EXISTS bunkers (id INTEGER PRIMARY KEY, timestamp INTEGER, \
                       name TEXT, active BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL, \
                       since INTEGER, next INTEGER)")

        cursor.execute("CREATE TABLE IF NOT EXISTS message_send (hash TEXT PRIMARY KEY, timestamp REAL)")

        cursor.execute("CREATE TABLE IF NOT EXISTS log_hashes (timestamp REAL, hash TEXT PRIMARY KEY, file TEXT)")

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
                           coordinates_y, coordinates_z, login_timestamp, logout_timestamp) \
                           VALUES ({self._get_timestamp(player['timestamp'])}, {player['steamID']}, '{player['username']}', \
                           {state}, {player['coordinates']['x']}, {player['coordinates']['y']}, {player['coordinates']['z']}, \
                           {loggedin_timestamp}, {loggedout_timestamp}, 0)")
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
                               login_timestamp = {loggedin_timestamp} \
                               WHERE steamid == '{player['steamID']}'")

            else:
                state = False
                login_ts = player_data[0][8]       
                loggedout_timestamp = self._get_timestamp(player['timestamp'])
                server_lifetime = loggedout_timestamp - login_ts
                server_lifetime_all = server_lifetime + player_data[0][10]
                cursor.execute(f"UPDATE player SET  \
                               timestamp = {self._get_timestamp(player['timestamp'])}, \
                               loggedin = {state}, \
                               coordinates_x = {player['coordinates']['x']}, \
                               coordinates_y = {player['coordinates']['y']}, \
                               coordinates_z ={player['coordinates']['z']}, \
                               logout_timestamp = {loggedout_timestamp}, \
                               server_lifetime = {server_lifetime_all} \
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
            self.logging.info("Bunker not in Database")
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

    def get_player_status(self, player_ame) -> list:
        """get player data from database"""
        ret_val = []
        cursor = self.db.cursor()
        cursor.execute(f"SELECT * FROM player WHERE username = '{player_ame}'")
        player_data = cursor.fetchall()

        if len(player_data) == 0:
            ret_val = []
        elif len(player_data) > 1:
            self.logging.info("Found more than one Player with that name.")
            for p in player_data:
                ret_val.append({p[3]: {
                               "status": p[4],
                               "login_timestamp" : p[8],
                               "logout_timestamp" : p[9],
                               "lifetime": p[10]
                               }})
        else:
            self.logging.info("One Player found.")
            ret_val.append({player_data[0][3]: {
                "status": player_data[0][4],
                "login_timestamp" : player_data[0][8],
                "logout_timestamp" : player_data[0][9],
                "lifetime": p[0][10]
                }})

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
                self.logging.info("Found more than one Bunker with that name.")
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
                self.logging.info("One Bunker found.")
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
            elif len(bunker_data) > 1:
                # 1, 1726252409, 'C1', 1, -393614.781, 216967.266, 59906.152, 0, 0
                self.logging.info("Got all Bunker Data")
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

    def raw(self, query: str) -> object:
        cursor = self.db.cursor()
        ret = cursor.execute(query)
        return ret.fetchall()

    def update_log_file_hash(self, hash: str, file: str) -> None:
        curr_time = datetime.timestamp(datetime.now())
        query = f"SELECT hash FROM log_hashes WHERE hash = '{hash}'"
        repl = self.raw(query)
        if len(repl) == 0:
            query = "INSERT INTO log_hashes (timestamp, hash, file) "
            query += f"VALUES ({curr_time}, '{hash}', '{file}')"
            repl = self.raw(query)
            self.db.commit()

    def get_log_file_hashes(self) -> dict:
        retval= dict()
        query = f"SELECT * FROM log_hashes"
        repl = self.raw(query)
        for item in repl:
            retval.update({item[1]: item[2]})

        return retval

    def close(self) -> None:
        self.db.close()

# pylint: enable=line-too-long