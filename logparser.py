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
    current_log = []
    current_timestamp = 0
    logdirectory = "/"
    last_fetch_time = 0
    file_groups = {}

    debug_message = None

    def __init__(self, server, user, passwd, logdirectoy, debug_callback=None) -> None:
        self.sftp_server = server
        self.sftp_user = user
        self.sftp_password = passwd
        self.logdirectory = logdirectoy

        if debug_callback is not None:
            self.debug_message = debug_callback

        if self.debug_message is not None:
            self.debug_message("Try to conect to SFTP-Server.....")

        self.connect_p = paramiko.SSHClient()
        self.connect_p.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connect_p.connect(self.sftp_server, port=self.sftp_port,
                               username=self.sftp_user, password=self.sftp_password)

        self.self.connect_p = self.connect_p.open_sftp()

    def _retrieve_files(self):
        for entry in self.connect_p.listdir_attr(self.logdirectory):
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

class parser:
    log_regex: str

    def parse(self, string) -> dict:
        return re.match(self.log_regex, string)

class login_parser(parser):

    def __init__(self) -> None:
        super().__init__()
        self.log_regex = r"^([0-9.-]*):\s'([0-9.]*)\s([0-9]*):([0-9A-Za-z]*)(.*)'\slogged\sin\sat:\sX=([0-9\-.]*)\sY=([0-9\-.]*)\sZ=([0-9\-.]*)"

    def parse(self, string) -> dict:
        result = super().parse(string).groupdict()

        return result
