"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: Get logfiles from sftp server
"""
# pylint: disable=broad-exception-caught
import re
import stat
from datetime import datetime

import hashlib
import chardet
import paramiko
import paramiko.ssh_exception

from modules.output import Output
from modules.datamanager import ScumLogDataManager

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

        self.sent_entries = set()

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

    def scum_log_parse(self) -> str:
        """parse log"""
        self._retrieve_files()
        return self._retrive_file_content()

    def _debug_to_stdout(self, msg):
        print(msg)

# pylint: enable=line-too-long
