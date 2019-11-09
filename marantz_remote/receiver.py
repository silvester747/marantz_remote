# -*- coding: utf-8 -*-

"""Main module."""

import re

from enum import Enum
from telnetlib import Telnet
from typing import Any, List, Optional, Pattern, Type


class StatusError(Exception):
    def __str__(self) -> str:
        return "Failed to retreive status. Your receiver may not support this feature."


class ReceiverConnection(object):
    connection: Telnet
    timeout: int

    def __init__(self, host: str, timeout: int = 1):
        self.connection = Telnet(host=host)
        self.timeout = timeout

    def __del__(self):
        self.connection.close()

    def get(self, command: bytes, responses: List[Pattern]) -> bytes:
        self.connection.write(command)
        return self.connection.expect(responses, self.timeout)

    def get_status(self, command: str, response_pattern: str, group: int = 1) -> str:
        command = command.encode("ascii")
        response = re.compile(f"{response_pattern}\r".encode("ascii"))

        _, match, _ = self.get(command, [response])
        if match:
            return match.group(group).decode("ascii")
        else:
            raise StatusError

    def write(self, command: str):
        self.connection.write(command.encode("ascii"))


class ReceiverBase(object):
    connection: ReceiverConnection

    def __init__(self, host: str, timeout: int = 1):
        self.connection = ReceiverConnection(host, timeout)


class Control(object):
    def __init__(self, name: str, status_command: Optional[str] = None,
                 response_prefix: Optional[str] = None, set_command: Optional[str] = None):
        self.status_command = status_command or f"{name}?"
        self.response_pattern = self._response_pattern(response_prefix or name)
        self.set_command = set_command or name

    def _response_pattern(self, response_prefix: str):
        return f"{response_prefix}(.*)"

    def __get__(self, instance: ReceiverBase, owner=None) -> str:
        return instance.connection.get_status(self.status_command, self.response_pattern)

    def __set__(self, instance: ReceiverBase, value: Any) -> None:
        instance.connection.write(f"{self.set_command}{value}")

    def __delete__(self, instance: ReceiverBase):
        pass

    def __set_name__(self, owner, name):
        pass


class EnumControl(Control):
    enum_type: Type[Enum]

    def __init__(self, *args, enum_type: Type[Enum], **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_type = enum_type

    def __get__(self, instance: ReceiverBase, owner=None) -> Enum:
        try:
            return self.enum_type(super().__get__(instance, owner))
        except ValueError:
            raise StatusError

    def __set__(self, instance: ReceiverBase, value: Enum) -> None:
        super().__set__(instance, value.value)


class NumericControl(Control):
    format_string: str
    digits: int

    def __init__(self, *args, digits: int = 2, **kwargs):
        super().__init__(*args, **kwargs)
        self.format_string = f"0{digits}"
        self.digits = digits

    def __set__(self, instance: ReceiverBase, value: int) -> None:
        if value < 0 or value >= 10 ** self.digits:
            raise ValueError
        super().__set__(instance, f"{value:{self.format_string}}")

    def _response_pattern(self, response_prefix: str):
        return f"{response_prefix}(\\s*\\d+)"

    def __get__(self, instance: ReceiverBase, owner=None) -> int:
        return int(super().__get__(instance, owner))


class VolumeControl(NumericControl):
    def __set__(self, instance: ReceiverBase, value: Any) -> None:
        if value == "+":
            Control.__set__(self, instance, "UP")
        elif value == "-":
            Control.__set__(self, instance, "DOWN")
        else:
            super().__set__(instance, value)


class InputSource(Enum):
    Phono = "PHONO"
    CD = "CD"
    DVD = "DVD"
    Bluray = "BD"
    TV = "TV"
    CblSat = "SAT/CBL"
    MediaPlayer = "MPLAY"
    Game = "GAME"
    Tuner = "TUNER"
    HDRadio = "HDRADIO"
    SiriusXM = "SIRIUSXM"
    Pandora = "PANDORA"
    InternetRadio = "IRADIO"
    Server = "SERVER"
    Favorites = "FAVORITES"
    Aux1 = "AUX1"
    Aux2 = "AUX2"
    Aux3 = "AUX3"
    Aux4 = "AUX4"
    Aux5 = "AUX5"
    Aux6 = "AUX6"
    Aux7 = "AUX7"
    OnlineMusic = "NET"
    Bluetooth = "BT"
    On = "ON"
    Off = "OFF"


class AudioInputSignal(Enum):
    Auto = "AUTO"
    HDMI = "HDMI"
    Digital = "DIGITAL"
    Analog = "ANALOG"
    Ch7dot1 = "7.1IN"
    ARC = "ARC"
    No = "NO"


class AutoStandby(Enum):
    Off = "OFF"
    In15Minutes = "15M"
    In30Minutes = "30M"
    In60Minutes = "60M"


class EcoMode(Enum):
    Off = "OFF"
    On = "ON"
    Auto = "AUTO"


class Power(Enum):
    Off = "OFF"
    On = "ON"


class Receiver(ReceiverBase):
    power = EnumControl("PW", enum_type=Power)
    main_zone_power = EnumControl("ZM", enum_type=Power)

    master_volume = VolumeControl("MV")

    channel_volume_front_left = VolumeControl("CVFL", status_command="CV?", set_command="CVFL ")
    channel_volume_front_right = VolumeControl("CVFR", status_command="CV?", set_command="CVFR ")
    channel_volume_center = VolumeControl("CVC", status_command="CV?", set_command="CVC ")
    channel_volume_subwoofer = VolumeControl("CVSW", status_command="CV?", set_command="CVSW ")
    channel_volume_subwoofer2 = VolumeControl("CVSW2", status_command="CV?", set_command="CVSW2 ")
    channel_volume_surround_left = VolumeControl("CVSL", status_command="CV?", set_command="CVSL ")
    channel_volume_surround_right = VolumeControl("CVSR", status_command="CV?", set_command="CVSR ")
    channel_volume_surround_back_left = VolumeControl("CVSBL", status_command="CV?", set_command="CVSBL ")
    channel_volume_surround_back_right = VolumeControl("CVSBR", status_command="CV?", set_command="CVSBR ")
    channel_volume_surround_back = VolumeControl("CVSB", status_command="CV?", set_command="CVSB ")
    channel_volume_front_height_left = VolumeControl("CVFHL", status_command="CV?", set_command="CVFHL ")
    channel_volume_front_height_right = VolumeControl("CVFHR", status_command="CV?", set_command="CVFHR ")
    channel_volume_top_front_left = VolumeControl("CVTFL", status_command="CV?", set_command="CVTFL ")
    channel_volume_top_front_right = VolumeControl("CVTFR", status_command="CV?", set_command="CVTFR ")
    channel_volume_top_middle_left = VolumeControl("CVTML", status_command="CV?", set_command="CVTML ")
    channel_volume_top_middle_right = VolumeControl("CVTMR", status_command="CV?", set_command="CVTMR ")
    channel_volume_top_rear_left = VolumeControl("CVTRL", status_command="CV?", set_command="CVTRL ")
    channel_volume_top_rear_right = VolumeControl("CVTRR", status_command="CV?", set_command="CVTRR ")
    channel_volume_rear_height_left = VolumeControl("CVRHL", status_command="CV?", set_command="CVRHL ")
    channel_volume_rear_height_right = VolumeControl("CVRHR", status_command="CV?", set_command="CVRHR ")
    channel_volume_front_dolby_left = VolumeControl("CVFDL", status_command="CV?", set_command="CVFDL ")
    channel_volume_front_dolby_right = VolumeControl("CVFDR", status_command="CV?", set_command="CVFDR ")
    channel_volume_surround_dolby_left = VolumeControl("CVSDL", status_command="CV?", set_command="CVSDL ")
    channel_volume_surround_dolby_right = VolumeControl("CVSDR", status_command="CV?", set_command="CVSDR ")
    channel_volume_back_dolby_left = VolumeControl("CVBDL", status_command="CV?", set_command="CVBDL ")
    channel_volume_back_dolby_right = VolumeControl("CVBDR", status_command="CV?", set_command="CVBDR ")
    channel_volume_surround_height_left = VolumeControl("CVSHL", status_command="CV?", set_command="CVSHL ")
    channel_volume_surround_height_right = VolumeControl("CVSHR", status_command="CV?", set_command="CVSHR ")
    channel_volume_top_surround = VolumeControl("CVTS", status_command="CV?", set_command="CVTS ")

    def channel_volume_factory_reset(self) -> None:
        self.connection.write("CVZRL")

    mute = EnumControl("MU", enum_type=Power)
    input_source = EnumControl("SI", enum_type=InputSource)

    # Supported input: 0-5
    smart_select = NumericControl("MSSMART", status_command="MSSMART ?", digits=1)

    def smart_select_memory(self, nr: int) -> None:
        """
        Supported input: 0-5
        """
        self.connection.write(f"MSSMART{nr} MEMORY")

    def smart_select_cancel(self) -> None:
        self.smart_select = 0

    audio_input_signal = EnumControl("SD", enum_type=AudioInputSignal)
    video_select = EnumControl("SV", enum_type=InputSource)
    auto_standby = EnumControl("STBY", enum_type=AutoStandby)
    eco_mode = EnumControl("ECO", enum_type=EcoMode)

    # Supported input: ### or OFF
    sleep_timer = Control("SLP")


def test() -> None:
    r = Receiver("172.16.10.106")

    for name in dir(r):
        if not name.startswith("_"):
            try:
                attr = getattr(r, name)
                if not callable(attr):
                    print(f"{name}: {attr}")
            except StatusError:
                print(f"{name} not supported")

    r.master_volume = "+"
    print(r.master_volume)
    r.master_volume = "-"
    print(r.master_volume)

if __name__ == "__main__":
    test()
