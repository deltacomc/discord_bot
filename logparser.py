"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: Get logfiles from server and over parser for various log file types
"""

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


class ScumFtpLogparser:
    """Class representing a a log parser"""
    ftp_server = ""
    ftp_user = ""
    ftp_password = ""
    connect_p = None
    current_log = []
    current_timestamp = 0
    logfile = "test.txt"


    def __init__(self, server, user, passwd, logfile) -> None:
        self.ftp_server = server
        self.ftp_user = user
        self.ftp_password = passwd
        self.logfile = logfile
        self.connect_p = FTP(server,user=user,passwd=passwd)
        self._scum_log_parser_load_timestamp()

    def _scum_log_parser_load_timestamp(self):
        if os.path.exists("scum_log_parser_ts.txt"):
            with open("scum_log_parser_ts.txt", "r", encoding="utf-8") as _fp:
                self.current_timestamp = int(_fp.read())
        else:
            self.current_timestamp = 0

    def _scum_log_parser_store_timestamp(self):
        with open("scum_log_parser_ts.txt", "w", encoding="utf-8") as _fp:
            _fp.write(str(self.current_timestamp))

    def _scum_log_parser_retrive(self):
        self.connect_p.login(user=self.ftp_user, passwd=self.ftp_password)
        self.connect_p.retrlines(f"RETR {self.logfile}", callback=self._scum_ftp_logparser_getline)

    def _scum_ftp_logparser_getline(self, string: str):
        self.current_log.append(string)

    def scum_log_parse(self) -> str:
        """parse log"""
        ret_val = []
        self._scum_log_parser_retrive()
        if self.current_timestamp < len(self.current_log):
            # pylint: disable=unused-variable
            for count, line in enumerate(self.current_log):
                if line >= self.current_timestamp:
                    ret_val.append(self.current_log[line])
            # pylint: enable=unused-variable
            self.current_timestamp = len(self.current_log)
            self._scum_log_parser_store_timestamp()
        self.current_log = []

        return ret_val

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
    log_hashes :set
    new_log_data = {}
    sent_entries :set
    debug_message = None
    _retry : False

    # Dateipfade zum Speichern des Zeitstempels des letzten
    # Abrufs und der Hashes der gesendeten Logdateien
    LAST_FETCH_FILE = 'last_fetch_time.txt'
    LOG_HASHES_FILE = 'log_hashes.txt'
    SENT_ENTRIES_FILE = 'sent_entries.txt'

    def __init__(self, server, port, user, passwd, logdirectoy, debug_callback=None) -> None:
        self.sftp_server = server
        self.sftp_user = user
        self.sftp_password = passwd
        self.sftp_port = port
        self.logdirectory = logdirectoy

        if debug_callback is not None:
            self.debug_message = debug_callback
        else:
            self.debug_message = self._debug_to_stdout

        self.last_fetch_time = self.get_last_fetch_time()
        self.log_hashes = self.get_existing_log_hashes()
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
            if not self._retry:
                # try agin if SSHException
                self._open_connection()
                self._retry = True
            else:
                # try agin if SSHException
                self._retry = False


    def _retrieve_files(self):
        if self.connect_sftp_p is None:
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
            self._open_connection()
            if not self._retry:
                self._retry = True
                self._retrieve_files()
            else:
                # already tried once so we don't retry and continue
                self._retry = False

    def _retrive_file_content(self):
        if self.connect_sftp_p is None:
            self._open_connection()
        self.new_log_data = {}
        try:


            for base_name, (latest_file, _) in self.file_groups.items():
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
                            self.log_hashes.add(file_hash)
                            if self.debug_message is not None:
                                self.debug_message(f"Neue Logdatei erkannt: {latest_file}")

            self.update_log_hashes(self.log_hashes)
            # pylint: enable=line-too-long
        except paramiko.ssh_exception.SSHException as e:
            # Something went wrong with the connection
            # Try to reopen and rety
            self._open_connection()
            if not self._retry:
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

    def get_last_fetch_time(self):
        """retruns the timestamp of the last time
        a file was from the server"""
        if os.path.exists(self.LAST_FETCH_FILE):
            with open(self.LAST_FETCH_FILE, 'r', encoding='UTF-8') as f:
                timestamp = f.read().strip()
                return datetime.fromisoformat(timestamp) if timestamp else datetime.min
        return datetime.min

    def update_last_fetch_time(self):
        """Updates the last fetched file"""
        with open(self.LAST_FETCH_FILE, 'w', encoding='UTF-8') as f:
            f.write(datetime.now().isoformat())

    def get_existing_log_hashes(self):
        """loads hashes of already read files"""
        if os.path.exists(self.LOG_HASHES_FILE):
            with open(self.LOG_HASHES_FILE, 'r', encoding='UTF-8') as f:
                return set(line.strip() for line in f)
        return set()

    def update_log_hashes(self,hashes):
        """update has file of already read files"""
        with open(self.LOG_HASHES_FILE, 'w', encoding='UTF-8') as f:
            f.write('\n'.join(hashes))

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
        super().__init__()
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
                "hash":  self._hash_string(string)
            }
        return ret_val

class KillParser(Parser):
    """implementation of parser for the kill log file type"""

    def __init__(self) -> None:
        super().__init__()
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
                "event": json.loads(result.group(2))
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
