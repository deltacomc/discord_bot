"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 09.09.2024
    @CLicense: MIT
    @Description:
"""
import sqlite3
from datetime import datetime

SCHEMA_VERSION = 100

class scumLogDataManager:
    db = None
    db_file = ""

    def __init__(self, dbName) -> None:
        self.db_file = dbName
        self.db = sqlite3.connect(dbName)
        self._check_schema()

    def _check_schema(self):
        cursor = self.db.cursor()
        try:
            schema_version = cursor.execute("SELECT schema_version FROM scum_schema WHERE name = 'schema'")
            if schema_version.fetchone() == SCHEMA_VERSION:
                return True
            else:
                return False
        except sqlite3.Error as e:
            print(e)
            self._init_schema()
            return True

    def _init_schema(self):
            cursor = self.db.cursor()
            ## Table does not exists so we create out tables
            cursor.execute("CREATE TABLE IF NOT EXISTS player (id INTEGER PRIMARY KEY, timestamp INTEGER, steamid INTEGER,\
                           username TEXT, loggedin BOOL, coordinates_x REAL, coordinates_y REAL, coordinates_z REAL \
                           login_timestamp INTEGER, logout_timestamp INTEGER)")

            cursor.execute("CREATE TABLE IF NOT EXISTS message_send (hash INTEGER PRIMARY KEY, timestamp REAL)")

            cursor.execute("CREATE TABLE IF NOT EXISTS scum_schema (name TEXT, schema_version INTEGER PRIMARY KEY)")

            cursor.execute("INSERT INTO scum_schema (name, schema_version) VALUES ('schema', 100)")
            self.db.commit()

    def storeMessageSend(self, messageHash):
        cursor = self.db.cursor()
        cursor.execute("SELECT hash FROM message_send")
        if cursor.rowcount > 0:
            print ("Hash already stored. Not updating database.")
        else:
            cursor.execute(f"INSERT INTO message_send (hash, timesatmp) VALUES ({messageHash}, {datetime.timestamp()})")

    def checkMessageSend(self, messageHash):
        """Will check if a messages is already sent.
            Return True if it isn't stored
            Return False if it is already stored in database"""
        cursor = self.db.cursor()
        cursor.execute(f"SELECT hash FROM message_send WHERE 'hash' = {messageHash}")
        if cursor.rowcount > 0:
            hashes = cursor.fetchall()
            for hash in hashes:
                if hash == messageHash:
                    return False
        else:
            return True
