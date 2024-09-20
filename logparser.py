"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: Get logfiles from server and over parser for various log file types
"""
# pylint: disable=broad-exception-caught
import os
import re
import stat
import json
from datetime import datetime
from ftplib import FTP

import hashlib
import chardet
import paramiko
import paramiko.ssh_exception

from modules.output import output
from datamanager import ScumLogDataManager

class ScumSFTPLogParser:
    """Class representing a a log parser"""
    sftp_server = ""
    sftp_user = ""
    sftp_password = ""
    sftp_port = 22
    connect_p = None
    connect_sftp_p = None
    current_log = []
    current_timestamp = 0
    logdirectory = "/"
    last_fetch_time = 0
    file_groups = {}
    log_hashes: set
    log_file_hashes: dict
    new_log_data = {}
    sent_entries: set
    debug_message = None
    _retry= False
    _database: str = None
    # Dateipfade zum Speichern des Zeitstempels des letzten
    # Abrufs und der Hashes der gesendeten Logdateien
    LAST_FETCH_FILE = 'last_fetch_time.txt'
    LOG_HASHES_FILE = 'log_hashes.txt'
    SENT_ENTRIES_FILE = 'sent_entries.txt'

    def __init__(self, server, port, user, passwd, logdirectoy, database=None, debug_callback=None) -> None:
        self.sftp_server = server
        self.sftp_user = user
        self.sftp_password = passwd
        self.sftp_port = port
        self.logdirectory = logdirectoy

        self._database = database

        if debug_callback is not None:
            self.debug_message = debug_callback
        else:
            self.debug_message = self._debug_to_stdout

        self.last_fetch_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        self.get_existing_log_hashes()

        self.sent_entries = self.get_sent_entries()

        self._open_connection()

    def _open_connection(self):
        try:
            if self.debug_message is not None:
                self.debug_message("Try to conect to SFTP-Server.....")

            self.connect_p = paramiko.SSHClient()
            self.connect_p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.connect_p.connect(hostname=self.sftp_server, port=self.sftp_port,
                                   username=self.sftp_user, password=self.sftp_password,
                                   allow_agent=False,look_for_keys=False)

            self.connect_sftp_p = self.connect_p.open_sftp()
        except paramiko.ssh_exception.SSHException as e:
            print (f"SSHException catched. Message print {e}")
            self.connect_p = None
        except Exception as e:
            print (f"Unspecified exception catched. Message print {e}")
            self.connect_p = None

    def _check_transport_alive(self):
        return self.connect_p.get_transport().is_alive()

    def _check_transport_active(self):
        return self.connect_p.get_transport().is_active()

    def _check_connection_alive(self):
        ret_val = True
        try:
            if self._check_transport_alive() and self._check_transport_active():
                transport = self.connect_p.get_transport()
                transport.send_ignore()
            else:
                ret_val = False
        except EOFError as e:
            print(e)
            self.connect_p.close()
            ret_val = False

        return ret_val

    def _retrieve_files(self):
        print("retrive file listing")
        if self.connect_sftp_p is None or not self._check_connection_alive():
            self._open_connection()
        try:
            for entry in self.connect_sftp_p.listdir_attr(self.logdirectory):
                entry_path = f"{self.logdirectory}/{entry.filename}"
                if not stat.S_ISDIR(entry.st_mode):
                    if entry.filename.endswith(".log") and \
                       datetime.fromtimestamp(entry.st_mtime) > self.last_fetch_time:
                        base_name = re.match(r'(.+?)_(\d{14})\.log$', entry.filename)
                        if base_name:
                            base_name = base_name.group(1)
                            if base_name not in self.file_groups or \
                               entry.st_mtime > self.file_groups[base_name][1]:
                                self.file_groups.update({base_name:  [entry_path, entry.st_mtime]})
        except paramiko.ssh_exception.SSHException as e:
            # Something went wrong with the connection
            # Try to reopen and rety
            print(e)
            self._open_connection()
            if not self._retry and self.connect_p is not None:
                self._retry = True
                self._retrieve_files()
            else:
                # already tried once so we don't retry and continue
                self._retry = False

    def _retrive_file_content(self):
        print("retrive file content")
        if self.connect_sftp_p is None or not self._check_connection_alive():
            self._open_connection()
        self.new_log_data = {}
        try:
            # pylint: disable=unused-variable
            for base_name, (latest_file, _) in self.file_groups.items():
            # pylint: enable=unused-variable
                with self.connect_sftp_p.open(latest_file) as file:
                    raw_content = file.read()
                    result = chardet.detect(raw_content)
                    encoding = result['encoding']
                    try:
                        content = raw_content.decode(encoding)
                    except (UnicodeDecodeError, TypeError):
                        content = raw_content.decode('utf-8', errors='replace')
                    filtered_content = self.filter_game_version(content)

                    if filtered_content:
                        file_hash = self.generate_file_hash(filtered_content)
            # pylint: disable=line-too-long
                        if file_hash not in self.log_hashes:
                            self.new_log_data.update({latest_file: [filtered_content, self.sent_entries]})
                            self.update_log_hashes({"hash":file_hash, "name": latest_file})
                            if self.debug_message is not None:
                                self.debug_message(f"Neue Logdatei erkannt: {latest_file}")

            # pylint: enable=line-too-long
        except paramiko.ssh_exception.SSHException as e:
            # Something went wrong with the connection
            # Try to reopen and rety
            self._open_connection()
            if not self._retry and self.connect_p is not None:
                self._retry = True
                self._retrive_file_content()
            else:
                # already tried once so we don't retry and continue
                self._retry = False
        return self.new_log_data

    def filter_game_version(self, content):
        """Filter game version from log file"""
        lines = content.splitlines()
        filtered_lines = [line for line in lines if "Game version:" not in line]
        return "\n".join(filtered_lines) if any(line.strip() for line in filtered_lines) else None

    def generate_file_hash(self, content):
        """Return sha256 hash of given content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def hash_string(self, s):
        """return sha256 hash of gicen string"""
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

    def get_existing_log_hashes(self) -> None:
        """loads hashes of already read files"""
        db = ScumLogDataManager(self._database)
        self.log_hashes = set()
        self.log_file_hashes = db.get_log_file_hashes()
        for hash in self.log_file_hashes:
            self.log_hashes.add(hash)

    def update_log_hashes(self, hash: dict):
        """update has file of already read files"""
        db = ScumLogDataManager(self._database)
        self.log_file_hashes.update({hash["hash"]: hash["name"]})
        self.log_hashes.add(hash["hash"])
        db.update_log_file_hash(hash["hash"], hash["name"])
        db.close()

    def get_sent_entries(self):
        """load hashes of already sent messages (deprecated)"""
        if os.path.exists(self.SENT_ENTRIES_FILE):
            with open(self.SENT_ENTRIES_FILE, 'r', encoding='UTF-8') as f:
                return set(line.strip() for line in f)
        return set()

    def update_sent_entries(self, entries):
        """update hashes of already sent hashes (deprecated)"""
        with open(self.SENT_ENTRIES_FILE, 'w', encoding='UTF-8') as f:
            f.write('\n'.join(entries))

    def scum_log_parse(self) -> str:
        """parse log"""
        self._retrieve_files()
        return self._retrive_file_content()

    def _debug_to_stdout(self, msg):
        print(msg)

class Parser:
    """Abstract class for log data parser"""
    log_regex = ""
    log_pattern = None

    def parse(self, string) -> dict:
        """parse given string and return re-object"""
        return self.log_pattern.match(str.strip(string))

    def _hash_string(self, s):
        return hashlib.sha256(s.encode('utf-8')).hexdigest()


class LoginParser(Parser):
    """implementation of parser for the login log file type"""

    def __init__(self) -> None:
        # super().__init__()
        # pylint: disable=line-too-long
        self.log_regex = r"^([0-9.-]*):\s'([0-9.]*)\s([0-9]*):([0-9A-Za-z]*)\([0-9]+\)'\slogged ([in|out]+)\sat:\sX=([0-9.-]*)\sY=([0-9.-]*)\sZ=([0-9.-]*)"
        self.log_pattern = re.compile(self.log_regex)
        # pylint: enable=line-too-long

    def parse(self, string) -> dict:
        """implementation of the parser method for login log file type"""
        ret_val = {}
        result = super().parse(string)
        if result is not None:
            ret_val = {
                "timestamp" : result.group(1),
                "ipaddress":  result.group(2),
                "steamID" : result.group(3),
                "username" : result.group(4),
                "state" : result.group(5),
                "coordinates" :{
                    "x" : result.group(6),
                    "y" : result.group(7),
                    "z" : result.group(8),
                },
                "hash": self._hash_string(string)
            }
        return ret_val

class KillParser(Parser):
    """implementation of parser for the kill log file type"""

    def __init__(self) -> None:
        # super().__init__()
        # pylint: disable=line-too-long
        self.log_regex = r"^([0-9.-]*):\s({.*)$"
        self.log_pattern = re.compile(self.log_regex)
        # pylint: enable=line-too-long

    def parse(self, string) -> dict:
        """implementation of the parser method for login log file type"""
        ret_val = {}
        result = super().parse(string)
        if result is not None:
            ret_val = {
                "timestamp" : result.group(1),
                "event": json.loads(result.group(2)),
                "hash": self._hash_string(string)
            }

        # Event Structure will be like
        # {
        #     "Killer": {
        #         "ServerLocation": {
        #             "X": -793052.3125,
        #             "Y": -278619.875,
        #             "Z": 16720.08984375
        #         },
        #         "ClientLocation": {
        #             "X": -793052.3125,
        #             "Y": -278619.875,
        #             "Z": 16720.08984375
        #         },
        #         "IsInGameEvent": false,
        #         "ProfileName": "didiann",
        #         "UserId": "76561197970306734",
        #         "HasImmortality": false
        #     },
        #     "Victim": {
        #         "ServerLocation": {
        #             "X": -797193.5,
        #             "Y": -278922.4375,
        #             "Z": 16720.01953125
        #         },
        #         "ClientLocation": {
        #             "X": -797191.5,
        #             "Y": -278923.71875,
        #             "Z": 16720.0703125
        #         },
        #         "IsInGameEvent": false,
        #         "ProfileName": "Punisher",
        #         "UserId": "76561197986649167"
        #     },
        #     "Weapon": "Compound_Bow_C [Projectile]",
        #     "TimeOfDay": "19:58:06"
        # }

        return ret_val

class BunkerParser(Parser):
    """implementation of parser for the kill log file type"""
    # pylint: disable=line-too-long

    bunkerRegex = {
        # 2024.09.10-02.33.17: [LogBunkerLock] D2 Bunker is Active. Activated 00h 00m 00s ago. X=-243813.062 Y=568471.812 Z=72278.109
        "Active" : r"^([0-9.-]*):\s\[[A-Za-z]+\]\s([A-Z]{1}[0-9]{1})[A-Za-z\s.]+([0-9]{2})h ([0-9]{2})m ([0-9]{2})s[A-Za-z\s.]+\sX=([0-9.-]*)\sY=([0-9.-]*)\sZ=([0-9.-]*)$",
        # 2024.09.10-02.33.17: [LogBunkerLock] Z1 Bunker is Locked. Locked 00h 00m 00s ago, next Activation in 25h 47m 38s. X=-564608.062 Y=-724692.062 Z=15077.148
        "Locked" : r"^([0-9.-]*):\s\[[A-Za-z]+\]\s([A-Z]{1}[0-9]{1})[A-Za-z\s.]+([0-9]{2})h ([0-9]{2})m ([0-9]{2})s[A-Za-z\s,.]+([0-9]{2})h ([0-9]{2})m ([0-9]{2})s.\sX=([0-9.-]*)\sY=([0-9.-]*)\sZ=([0-9.-]*)$",
        # 2024.09.10-02.32.59: [LogBunkerLock] B3 Bunker Activated 17h 35m 35s ago
        "Activated" : r"^([0-9.-]*):\s\[[A-Za-z]+\]\s([A-Z]{1}[0-9]{1})[A-Za-z\s.]+([0-9]{2})h ([0-9]{2})m ([0-9]{2})s[A-Za-z\s.]+$",
        # 2024.09.10-04.20.55: [LogBunkerLock] D2 Bunker Deactivated
        "Deactivated" : r"^([0-9.-]*):\s\[[A-Za-z\s]+\]\s([A-Z]{1}[0-9]{1})\s[A-Za-z\s]+$",
    }

    # def __init__(self) -> None:
    #     super().__init__()


    def parse(self, string) -> dict:
        """implementation of the parser method for login log file type"""
        retval = {
            "name": str,
            "active": bool,
            "timestamp": str,
            "hash": str,
            "since": {
                "h": int,
                "m": int,
                "s": int,
            },
            "next": {
                "h": int,
                "m": int,
                "s": int,
            },
            "coordinates": {
                "x": float,
                "y": float,
                "z": float,
            },
        }
        if "Active" in string:
            self.log_regex = self.bunkerRegex["Active"]
        elif "Locked" in string:
            self.log_regex = self.bunkerRegex["Locked"]
        elif "Activated" in string:
            self.log_regex = self.bunkerRegex["Activated"]
        elif "Deactivated" in string:
            self.log_regex = self.bunkerRegex["Deactivated"]
        else:
            retval = {}

        self.log_pattern = re.compile(self.log_regex)
        result = super().parse(string)
        if result:
            if "Active" in string:
                retval.update({
                    "name": result.group(2),
                    "active": True,
                    "timestamp": result.group(1),
                    "hash": self._hash_string(string),
                    "since": {
                        "h": result.group(3),
                        "m": result.group(4),
                        "s": result.group(5),
                    },
                    "next": {},
                    "coordinates": {
                        "x": result.group(6),
                        "y": result.group(7),
                        "z": result.group(8),
                    }
                }
                )
            elif "Locked" in string:
                retval.update({
                    "name": result.group(2),
                    "active": False,
                    "timestamp": result.group(1),
                    "hash": self._hash_string(string),
                    "since": {
                        "h": result.group(3),
                        "m": result.group(4),
                        "s": result.group(5),
                    },
                    "next": {
                        "h": result.group(6),
                        "m": result.group(7),
                        "s": result.group(8),
                    },
                    "coordinates": {
                        "x": result.group(9),
                        "y": result.group(10),
                        "z": result.group(11),
                    }
                }
                )
            elif "Activated" in string:
                retval.update({
                    "name": result.group(2),
                    "active": True,
                    "timestamp": result.group(1),
                    "hash": self._hash_string(string),
                    "since": {
                        "h": result.group(3),
                        "m": result.group(4),
                        "s": result.group(5),
                    },
                    "next": {},
                    "coordinates": {}
                }
                )
            elif "Deactivated" in string:
                retval.update({
                    "name": result.group(2),
                    "active": False,
                    "timestamp": result.group(1),
                    "hash": self._hash_string(string),
                    "since": {},
                    "next": {},
                    "coordinates": {}
                }
                )
            else:
                retval = {}
        else:
            retval = {}

        return retval

# pylint: enable=line-too-long
