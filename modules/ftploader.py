"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: Get logfiles from ftp server
"""
import os
from ftplib import FTP

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
