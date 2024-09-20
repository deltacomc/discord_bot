"""
    @Author: Thorsten liepert <thorsten@liepert.dev>
    @Date: 06.09.2024
    @CLicense: MIT
    @Description: Parser for log file entries
"""
# pylint: disable=broad-exception-caught
import re
import json

import hashlib

from modules.output import Output

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
