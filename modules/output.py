"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: write log,debug,error output
"""

from datetime import datetime
import sys


class output:
    _stdout: bool = True
    _stderr: bool = True
    _file: str = None
    _max_level: int = 3


    DEBUG: int = 3
    ERROR: int = 2
    WARNING: int = 1
    INFO: int = 0

    def __init__(self, _filename= None, _stdout = True, _stderr = True):
        if _filename:
            self._file = _filename

        if self._stdout != _stdout:
            self._stdout = _stdout

        if self._stderr != _stderr:
            self._stderr = _stderr


    def _get_formated_message(self, _msg: str) -> str:
        current_data = datetime.strftime(datetime.now(), "%d.%m.%Y-%H:%M:%S")
        msg = f"{current_data}: {_msg}"
        return msg

    def write_to_file(self, _msg: str) -> bool:
        ret_val = False
        if self._file:
            with open(self._file, "a") as _output:
                resp = _output.write(self._get_formated_message(_msg)+"\n")
            if resp > 0:
                ret_val = True

        return ret_val

    def write_to_stdout(self, _msg: str) -> None:
        sys.stdout.write(self._get_formated_message(_msg)+"\n")

    def write_to_stderr(self, _msg: str) -> None:
        sys.stderr.write(self._get_formated_message(_msg)+"\n")

    def write_all_enabled(self, _msg: str) -> None:

        if self._file:
            self.write_to_file(_msg+"\n")

        if self._stdout:
            self.write_to_stdout(_msg+"\n")

        if self._stderr:
            self.write_to_stderr(_msg+"\n")

    def write_weighted_message(self, _msg: str, _level: int):
        if _level <= self._max_level:
            if self._file:
                self.write_to_file(_msg+"\n")

            if self._stdout:
                self.write_to_stdout(_msg+"\n")

            if self._stderr and _level >= self.ERROR:
                self.write_to_stderr(_msg+"\n")

    def info(self, _msg: str):
        self.write_weighted_message(_msg, self.INFO)

    def wrning(self, _msg: str):
        self.write_weighted_message(_msg, self.WARNING)

    def error(self, _msg: str):
        self.write_weighted_message(_msg, self.ERROR)

    def debug(self, _msg: str):
        self.write_weighted_message(_msg, self.DEBUG)
