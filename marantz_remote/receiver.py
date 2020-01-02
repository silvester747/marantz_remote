# -*- coding: utf-8 -*-

"""Main module."""

import re
import sys

from enum import Enum
from telnetlib import Telnet
from typing import Any, List, Match, MutableMapping, Optional, Pattern, Tuple, Type

from twisted.conch.telnet import StatefulTelnetProtocol
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol


class NotConnectedError(Exception):
    def __str__(self) -> str:
        return "Not connected"


class ReceiverProtocol(StatefulTelnetProtocol):
    delimiter: bytes = b"\r"

    receiver: "ReceiverBase"

    def __init__(self, receiver: "ReceiverBase"):
        self.receiver = receiver

    def connectionLost(self, reason):
        print("Connection lost", file=sys.stderr)

    def lineReceived(self, line):
        self.receiver.parse(line.decode("ascii"))


class ReceiverBase(object):
    response_handlers: List[Tuple[Pattern, "Control"]]
    cached_values: MutableMapping[str, Any]
    protocol: Optional[ReceiverProtocol] = None
    connected: Optional[Deferred] = None
    pending_writes: List[str]
    deferred_writer: Optional[Deferred] = None
    timeout: int

    def __init__(self, host: str, timeout: int = 1):
        self.cached_values = {}
        self.pending_writes = []
        self.timeout = timeout

        self.connected = self.connect(host)
        self.connected.addCallback(self._connected)
        self.connected.addCallback(self._write_next)

    def connect(self, host: str) -> Deferred:
        endpoint = TCP4ClientEndpoint(reactor, host, 23)
        protocol = ReceiverProtocol(self)
        return connectProtocol(endpoint, protocol)

    def write(self, command: str) -> None:
        self.pending_writes.append(command)

        if self.deferred_writer is None:
            self._write_next(None)

    def _write_next(self, _):
        if self.protocol is None:
            return
        if not self.pending_writes:
            return

        command = self.pending_writes.pop(0)
        self.protocol.sendLine(command.encode("ascii"))

        if self.timeout > 0:
            self.deferred_writer = Deferred()
            self.deferred_writer.addTimeout(self.timeout, reactor)
            self.deferred_writer.addCallback(self._write_next)
            self.deferred_writer.addErrback(self._write_next)

    def _connected(self, protocol):
        self.protocol = protocol
        self.connected = None

    def parse(self, line):
        handled = False
        for pattern, control in self.response_handlers:
            match = pattern.match(line)
            if match:
                control.parse(self, match)
                handled = True
        if not handled:
            print(f"Unhandled response: {line}", file=sys.stderr)
        if self.deferred_writer:
            self.deferred_writer, d = None, self.deferred_writer
            d.callback(None)


class Control(object):
    name: str
    status_command: str
    response_prefix: str
    response_pattern: str
    set_command: str
    deferreds: List[Deferred]

    def __init__(self, name: str, status_command: Optional[str] = None,
                 response_prefix: Optional[str] = None, set_command: Optional[str] = None):
        self.name = name
        self.status_command = status_command or f"{name}?"
        self.response_prefix = response_prefix or name
        self.response_pattern = self._response_pattern(self.response_prefix)
        self.set_command = set_command or name
        self.deferreds = []

    def _response_pattern(self, response_prefix: str) -> str:
        return f"{response_prefix}(.*)"

    def __get__(self, instance: ReceiverBase, owner=None) -> Deferred:
        d = Deferred()
        value = instance.cached_values.get(self.name, None)
        if value:
            d.callback(value)
        else:
            instance.write(self.status_command)
            self.deferreds.append(d)
        return d

    def __set__(self, instance: ReceiverBase, value: Any) -> None:
        instance.write(f"{self.set_command}{value}")

    def __delete__(self, instance: ReceiverBase):
        pass

    def __set_name__(self, owner, name):
        if not hasattr(owner, "response_handlers"):
            owner.response_handlers = []
        owner.response_handlers.append((re.compile(self.response_pattern), self))
        self.name = name

    def parse(self, instance, match):
        self.store_value(instance, match.group(1))

    def store_value(self, instance, value):
        instance.cached_values[self.name] = value
        for d in self.deferreds:
            d.callback(value)
        self.deferreds.clear()

    def clear_value(self, instance):
        if self.name in instance.cached_values:
            del instance.cached_values[self.name]


class EnumControl(Control):
    enum_type: Type[Enum]

    def __init__(self, *args, enum_type: Type[Enum], **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_type = enum_type

    def __set__(self, instance: ReceiverBase, value: Enum) -> None:
        super().__set__(instance, value.value)

    def parse(self, instance, match):
        try:
            self.store_value(instance, self.enum_type(match.group(1)))
        except ValueError:
            self.clear_value(instance)
            print(f"Invalid value: {match.group(1)}", file=sys.stderr)


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

    def _response_pattern(self, response_prefix: str) -> str:
        return f"{response_prefix}(\\s*\\d+)"

    def parse(self, instance, match):
        try:
            self.store_value(instance, int(match.group(1)))
        except:
            print(f"Invalid value: {match.group(1)}", file=sys.stderr)
            self.clear_value(instance)


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

    # Only for Video Select
    On = "ON"
    Off = "OFF"


class AudioInputSignal(Enum):
    Auto = "AUTO"
    HDMI = "HDMI"
    Digital = "DIGITAL"
    Analog = "ANALOG"
    Ch7_1 = "7.1IN"

    # Return value only
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
    StandBy = "STANDBY"


class SurroundMode(Enum):
    # Settable values
    Movie = "MOVIE"
    Music = "MUSIC"
    Game = "GAME"
    Direct = "DIRECT"
    PureDirect = "PURE DIRECT"
    Stereo = "STEREO"
    Auto = "AUTO"
    DolbyDigital = "DOLBY DIGITAL"
    DtsSurround = "DTS SURROUND"
    Auro3D = "AURO3D"
    Auro2DSurround = "AURO2DSURR"
    MultiChannelStereo = "MCH STEREO"
    Virtual = "VIRTUAL"

    # Rotate between options
    Left = "LEFT"
    Right = "RIGHT"

    # Return only
    # TODO: Split combined modes
    DolbySurround = "DOLBY SURROUND"
    DolbyAtmos = "DOLBY ATMOS"
    DolbyDigitalDS = "DOLBY D+DS"
    DolbyDigitalNeuralX = "DOLBY D+NEURAL:X"
    DolbyDigitalPlus = "DOLBY D+"
    DolbyDigitalPlusDS = "DOLBY D+ +DS"
    DolbyDigitalPlusNeuralX = "DOLBY D+ +NEURAL:X"
    DolbyHD = "DOLBY HD"
    DolbyHDDS = "DOLBY HD+DS"
    DolbyHDNeuralX = "DOLBY HD+NEURAL:X"
    NeuralX = "NEURAL:X"
    DtsEsDscrt6_1 = "DTS ES DSCRT6.1"
    DtsEsMtrx6_1 = "DTS ES MTRX6.1"
    DtsDS = "DTS+DS"
    DtsNeuralX = "DTS+NEURAL:X"
    DtsEsMtrxNeuralX = "DTS ES MTRX+NEURAL:X"
    DtsEsDscrtNeuralX = "DTS ES DSCRT+NEURAL:X"
    Dts96_24 = "DTS96/24"
    Dts96EsMtrx = "DTS96 ES MTRX"
    DtsHD = "DTS HD"
    DtsHDMstr = "DTS HD MSTR"
    DtsHDDS = "MSDTS HD+DS"
    DtsHDNeuralX = "DTS HD+NEURAL:X"
    DtsX = "DTS:X"
    DtsXMstr = "DTS:X MSTR"
    DtsExpress = "DTS EXPRESS"
    DtsES8ChDscrt = "DTS ES 8CH DSCRT"
    MultiChIn = "MULTI CH IN"
    MultiChInDS = "M CH IN+DS"
    MultiChInNeuralX = "M CH IN+NEURAL:X"
    MultiChIn7_1 = "MULTI CH IN 7.1"


class Aspect(Enum):
    Normal = "NRM"
    Full = "FUL"


class HdmiMonitor(Enum):
    Auto = "AUTO"
    Out1 = "1"
    Out2 = "2"


class HdmiResolution(Enum):
    Resolution480p576p = "48P"
    Resolution1080i = "10I"
    Resolution720p = "72P"
    Resolution1080p = "10P"
    Resolution1080p24Hz = "10P24"
    Resolution4K = "4K"
    Resolution4K60_50 = "4KF"
    Auto = "AUTO"


class HdmiAudioDecode(Enum):
    Amp = "AMP"
    TV = "TV"


class VideoProcess(Enum):
    Auto = "AUTO"
    Game = "GAME"
    Movie = "MOVI"

class Receiver(ReceiverBase):
    #
    # Main Zone - Power
    #
    power = EnumControl("PW", enum_type=Power)
    main_zone_power = EnumControl("ZM", enum_type=Power)

    #
    # Main Zone - Volume setting
    #
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
        self.write("CVZRL")

    mute = EnumControl("MU", enum_type=Power)

    #
    # Main Zone - Input setting
    #
    input_source = EnumControl("SI", enum_type=InputSource)

    # Supported input: 0-5
    smart_select = NumericControl("MSSMART", status_command="MSSMART ?", digits=1)

    def smart_select_memory(self, nr: int) -> None:
        """
        Supported input: 0-5
        """
        self.write(f"MSSMART{nr} MEMORY")

    def smart_select_cancel(self) -> None:
        self.smart_select = 0

    audio_input_signal = EnumControl("SD", enum_type=AudioInputSignal)
    video_select = EnumControl("SV", enum_type=InputSource)

    #
    # Main Zone - Auto Standby
    #
    auto_standby = EnumControl("STBY", enum_type=AutoStandby)

    #
    # Main Zone - ECO
    #
    eco_mode = EnumControl("ECO", enum_type=EcoMode)

    #
    # Main Zone - Sleep
    # Supported input: ### or OFF
    sleep_timer = Control("SLP")

    #
    # Main Zone - Surround
    #
    surround_mode = EnumControl("MS", enum_type=SurroundMode)

    #
    # Main Zone - Aspect
    #
    aspect = EnumControl("VSASP", enum_type=Aspect)

    #
    # Main Zone - HDMI Setting
    #
    hdmi_monitor = EnumControl("VSMONI", enum_type=HdmiMonitor)
    hdmi_output = EnumControl("VSSC", enum_type=HdmiResolution)
    hdmi_resolution = EnumControl("VSSCH", enum_type=HdmiResolution)
    hdmi_audio_decode = EnumControl("VSAUDIO ", enum_type=HdmiAudioDecode)

    #
    # Main Zone - Video Process
    #
    video_process = EnumControl("VSVPM", status_command="VSVPM ?", enum_type=VideoProcess)


def test() -> None:
    r = Receiver("172.16.10.106")

    def print_value(value, name):
        print(f"{name}: {value}")

    def print_error(value, name):
        print(f"{name} not available")

    def run_test(protocol):
        for name in dir(r):
            if not name.startswith("_"):
                attr = getattr(r, name)
                if isinstance(attr, Deferred):
                    attr.addTimeout(1, reactor).addCallback(print_value, name).addErrback(print_error, name)

        r.master_volume = "+"
        print(r.master_volume)
        r.master_volume = "-"
        print(r.master_volume)

    r.connected.addCallback(run_test)

    reactor.run()

if __name__ == "__main__":
    test()
