"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description:
"""

import os
import re
import stat
from datetime import datetime
from ftplib import FTP

import asyncio
import threading

import hashlib
import chardet
import paramiko


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
            with open("scum_log_parser_ts.txt", "r") as _fp:
                self.current_timestamp = int(_fp.read())
        else:
            self.current_timestamp = 0

    def _scum_log_parser_store_timestamp(self):
        with open("scum_log_parser_ts.txt", "w") as _fp:
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
            for line in range(len(self.current_log)):
                if line >= self.current_timestamp:
                    ret_val.append(self.current_log[line])

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
    _loop: None
    _thr: None

    # Dateipfade zum Speichern des Zeitstempels des letzten Abrufs und der Hashes der gesendeten Logdateien
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
        if self.debug_message is not None:
            self.debug_message("Try to conect to SFTP-Server.....")

        self.connect_p = paramiko.SSHClient()
        self.connect_p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connect_p.connect(hostname=self.sftp_server, port=self.sftp_port,
                               username=self.sftp_user, password=self.sftp_password,
                               allow_agent=False,look_for_keys=False)

        self.connect_sftp_p = self.connect_p.open_sftp()


    def _retrieve_files(self):
        if self.connect_sftp_p is None:
            self._open_connection()
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

    def _retrive_file_content(self):
        self.new_log_data = {}

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

                    if file_hash not in self.log_hashes:
                        self.new_log_data.update({latest_file: [filtered_content, self.sent_entries]})
                        self.log_hashes.add(file_hash)
                        if self.debug_message is not None:
                            self.debug_message(f"Neue Logdatei erkannt: {latest_file}")

        self.update_log_hashes(self.log_hashes)

        return self.new_log_data

    def _call_async_callback(self, message):
        if not self._thr.is_alive():
            self._thr.start()
        future = asyncio.run_coroutine_threadsafe(self.debug_message, self._loop)
        return future.result()

    def filter_game_version(self, content):
        lines = content.splitlines()
        filtered_lines = [line for line in lines if "Game version:" not in line]
        return "\n".join(filtered_lines) if any(line.strip() for line in filtered_lines) else None

    def generate_file_hash(self, content):
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def hash_string(self, s):
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

    def get_last_fetch_time(self):
        if os.path.exists(self.LAST_FETCH_FILE):
            with open(self.LAST_FETCH_FILE, 'r', encoding='UTF-8') as f:
                timestamp = f.read().strip()
                return datetime.fromisoformat(timestamp) if timestamp else datetime.min
        return datetime.min

    def update_last_fetch_time(self):
        with open(self.LAST_FETCH_FILE, 'w', encoding='UTF-8') as f:
            f.write(datetime.now().isoformat())

    def get_existing_log_hashes(self):
        if os.path.exists(self.LOG_HASHES_FILE):
            with open(self.LOG_HASHES_FILE, 'r', encoding='UTF-8') as f:
                return set(line.strip() for line in f)
        return set()

    def update_log_hashes(self,hashes):
        with open(self.LOG_HASHES_FILE, 'w', encoding='UTF-8') as f:
            f.write('\n'.join(hashes))

    def get_sent_entries(self):
        if os.path.exists(self.SENT_ENTRIES_FILE):
            with open(self.SENT_ENTRIES_FILE, 'r', encoding='UTF-8') as f:
                return set(line.strip() for line in f)
        return set()

    def update_sent_entries(self, entries):
        with open(self.SENT_ENTRIES_FILE, 'w', encoding='UTF-8') as f:
            f.write('\n'.join(entries))

    def scum_log_parse(self) -> str:
        """parse log"""
        self._retrieve_files()
        return self._retrive_file_content()

    def _debug_to_stdout(self, msg):
        print(msg)

class parser:
    log_regex = ""
    log_pattern = None

    def parse(self, string) -> dict:
        return self.log_pattern.match(str.strip(string))

    def _hash_string(self, s):
        return hashlib.sha256(s.encode('utf-8')).hexdigest()


class login_parser(parser):

    def __init__(self) -> None:
        super().__init__()
        self.log_regex = r"^([0-9.-]*):\s'([0-9.]*)\s([0-9]*):([0-9A-Za-z]*)\([0-9]+\)'\slogged ([in|out]+)\sat:\sX=([0-9.-]*)\sY=([0-9.-]*)\sZ=([0-9.-]*)"
        self.log_pattern = re.compile(self.log_regex)


    def parse(self, string) -> dict:
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
