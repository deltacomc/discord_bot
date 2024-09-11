"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 09.09.2024
    @CLicense: MIT
    @Description:
"""
# pylint: disable=line-too-long
import sqlite3
from datetime import datetime

SCHEMA_VERSION = 100

class ScumLogDataManager:
    """Manage Database access for bot"""
    db = None
    db_file = ""

    def __init__(self, db_name) -> None:
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
            print(e)
            self._init_schema()
            return True

    def _update_schema(self):
        # Call init to create none existing tables
        self._init_schema()
        # Update existing tables
        # check if new column exists that we want to add
        # check_column = f"SELECT COUNT(*) AS CNTREC FROM "
        # check_column += f"pragma_table_info('{tablename}') WHERE name='{column_name}'"
        # cursor = self.db.cursor()
        # cursor.execute(check_column)
        # result = cursor.fetchon()
        # if result == 0:
        # update table

    def _init_schema(self):
        cursor = self.db.cursor()
        ## Table does not exists so we create out tables
        cursor.execute("CREATE TABLE IF NOT EXISTS player (id INTEGER PRIMARY KEY, timestamp INTEGER, steamid INTEGER,\
                       username TEXT, loggedin BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL, \
                       login_timestamp INTEGER, logout_timestamp INTEGER)")

        cursor.execute("CREATE TABLE IF NOT EXISTS message_send (hash TEXT PRIMARY KEY, timestamp REAL)")

        cursor.execute("CREATE TABLE IF NOT EXISTS scum_schema (name TEXT, schema_version INTEGER PRIMARY KEY)")

        self._update_schema_version()

        self.db.commit()

    def _update_schema_version(self):
        print("Update Database Schema version.")
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

    def _discard_old_values(self, table, age_secs):
        age_timestamp = datetime.timestamp(datetime.now()) - age_secs
        statement = f"DELETE FROM {table} where timestamp < {age_timestamp}"
        cursor = self.db.cursor()
        cursor.execute(statement)
        self.db.commit()

    def store_message_send(self, message_hash):
        """store send message in database"""
        cursor = self.db.cursor()
        cursor.execute("SELECT hash FROM message_send")
        if cursor.rowcount > 0:
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
        cursor.execute(f"SELECT * FROM player WHERE steamid = '{player["steamID"]}'")
        player_data = cursor.fetchall()
        if len(player_data) > 1:
            print("Multiple entries found with same steamID")
            return False
        elif len(player_data) == 0:
            print("No User with steamID in Database")
            if player["state"] == "in":
                state = True
                loggedin_timestamp = self._get_timestamp(player["timestamp"])
                loggedout_timestamp = 0
            else:
                state = False
                loggedin_timestamp = 0
                loggedout_timestamp = self._get_timestamp(player["timestamp"])

            cursor.execute(f"INSERT INTO player (timestamp, steamid, username, loggedin, coordinates_x, \
                           coordinates_y, coordinates_z, login_timestamp, logout_timestamp) \
                           VALUES ({self._get_timestamp(player["timestamp"])}, {player["steamID"]}, '{player["username"]}', \
                           {state}, {player["coordinates"]["x"]}, {player["coordinates"]["y"]}, {player["coordinates"]["z"]}, \
                           {loggedin_timestamp}, {loggedout_timestamp})")
            self.db.commit()
            return True
        else:
            player_data = cursor.fetchall()

            if player["state"] == "in":
                state = True
                loggedin_timestamp = self._get_timestamp(player["timestamp"])
                cursor.execute(f"UPDATE player SET  \
                               timestamp = {self._get_timestamp(player["timestamp"])}, \
                               loggedin = {state}, \
                               coordinates_x = {player["coordinates"]["x"]}, \
                               coordinates_y = {player["coordinates"]["y"]}, \
                               coordinates_z = {player["coordinates"]["z"]}, \
                               login_timestamp = {loggedin_timestamp} \
                               WHERE steamid == '{player["steamID"]}'")

            else:
                state = False
                loggedout_timestamp = self._get_timestamp(player["timestamp"])
                cursor.execute(f"UPDATE player SET  \
                               timestamp = {self._get_timestamp(player["timestamp"])}, \
                               loggedin = {state}, \
                               coordinates_x = {player["coordinates"]["x"]}, \
                               coordinates_y = {player["coordinates"]["y"]}, \
                               coordinates_z ={player["coordinates"]["z"]}, \
                               logout_timestamp = {loggedout_timestamp} \
                               WHERE steamid == '{player["steamID"]}'")
            self.db.commit()
            return True

    def get_player_status(self, player_ame) -> list:
        """get player data from database"""
        ret_val = []
        cursor = self.db.cursor()
        cursor.execute(f"SELECT * FROM player WHERE username = '{player_ame}'")
        player_data = cursor.fetchall()

        if len(player_data) == 0:
            ret_val = []
        elif len(player_data) > 1:
            print("Found more than one Player with that name.")
            for p in player_data:
                ret_val.append({p[3]: {
                               "status": p[4],
                               "login_timestamp" : p[8],
                               "logout_timestamp" : p[9]
                               }})
        else:
            print("One Player found.")
            ret_val.append({player_data[0][3]: {
                "status": player_data[0][4],
                "login_timestamp" : player_data[0][8],
                "logout_timestamp" : player_data[0][9]
                }})

        return ret_val

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

# pylint: enable=line-too-long
