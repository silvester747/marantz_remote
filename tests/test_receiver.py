#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test the receiver interface
"""

import pytest

from enum import Enum
from typing import List, Pattern
from unittest.mock import MagicMock

from marantz_remote.receiver import (Control, EnumControl, NumericControl, ReceiverConnection,
                                     StatusError, VolumeControl)


class MockTelnet(object):
    def __init__(self, host=None):
        self.written = []
        self.expectations = {}
        self.responses = []

    def close(self):
        pass

    def write(self, buffer: bytes):
        self.written.append(buffer)
        if buffer in self.expectations:
            self.responses.extend(self.expectations[buffer])

    def expect(self, patterns: List[Pattern], timeout: int = None):
        while self.responses:
            response = self.responses.pop(0)
            for i, p in enumerate(patterns):
                m = p.match(response)
                if m:
                    return i, m, response
        return -1, None, b""


class MockReceiverConnection(ReceiverConnection):
    def __init__(self):
        self.connection = MockTelnet()
        self.timeout = 1

    def has_written(self, message: str) -> bool:
        return message.encode('ascii') in self.connection.written

    def set_response(self, command: str, response: str) -> None:
        self.set_responses(command, [response])

    def set_responses(self, command: str, responses: List[str]) -> None:
        byte_responses = [f"{r}\r".encode("ascii") for r in responses]
        self.connection.expectations[command.encode("ascii")] = byte_responses


def test_control__name_only():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW")

    parent = TestParent()
    parent.connection.set_response("PW?", "PWOFF")

    assert parent.control == "OFF"

    parent.control = "ON"
    assert parent.connection.has_written("PWON")


def test_control__override_status_command():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW", status_command="PW ?")

    parent = TestParent()
    parent.connection.set_response("PW ?", "PWOFF")

    assert parent.control == "OFF"

    parent.control = "ON"
    assert parent.connection.has_written("PWON")


def test_control__override_set_command():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW", set_command="PWA")

    parent = TestParent()
    parent.connection.set_response("PW?", "PWOFF")

    assert parent.control == "OFF"

    parent.control = "ON"
    assert parent.connection.has_written("PWAON")


def test_control__override_response_prefix():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW", response_prefix="PWA")

    parent = TestParent()
    parent.connection.set_response("PW?", "PWAOFF")

    assert parent.control == "OFF"

    parent.control = "ON"
    assert parent.connection.has_written("PWON")


def test_control__incorrect_response():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW")

    parent = TestParent()
    parent.connection.set_response("PW?", "RWAUTO")

    with pytest.raises(StatusError):
        assert parent.control == "OFF"


def test_control__ignore_other_responses():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = Control("PW")

    parent = TestParent()
    parent.connection.set_responses("PW?", ["CV20", "MV30", "MUOFF", "PWOFF"])

    assert parent.control == "OFF"


def test_numericcontrol():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = NumericControl("MV")

    parent = TestParent()
    parent.connection.set_response("MV?", "MV50")
    assert parent.control == 50

    parent.connection.set_response("MV?", "MV70")
    assert parent.control == 70

    parent.control = 4
    assert parent.connection.has_written("MV04")

    parent.control = 38
    assert parent.connection.has_written("MV38")


def test_numericcontrol__invalid_response():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = NumericControl("MV")

    parent = TestParent()
    parent.connection.set_responses("MV?", ["MVO", "MVTRUE", "MVFALSE", "MV", "MVB30"])
    with pytest.raises(StatusError):
        assert parent.control == 1


def test_numericcontrol__invalid_input():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = NumericControl("MV")

    parent = TestParent()
    with pytest.raises(ValueError):
        parent.control = -1
    with pytest.raises(ValueError):
        parent.control = 100


def test_numericcontrol__more_digits():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = NumericControl("MV", digits=4)

    parent = TestParent()
    parent.connection.set_response("MV?", "MV0050")
    assert parent.control == 50

    parent.connection.set_response("MV?", "MV0700")
    assert parent.control == 700

    parent.control = 4
    assert parent.connection.has_written("MV0004")

    parent.control = 38
    assert parent.connection.has_written("MV0038")

    parent.control = 210
    assert parent.connection.has_written("MV0210")

    parent.control = 3233
    assert parent.connection.has_written("MV3233")


def test_volumecontrol():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = VolumeControl("MV")

    parent = TestParent()

    parent.control = "+"
    assert parent.connection.has_written("MVUP")

    parent.control = "-"
    assert parent.connection.has_written("MVDOWN")


def test_enumcontrol():
    class TestEnum(Enum):
        Auto = "AUTO"
        HDMI = "HDMI"
        Digital = "DIGITAL"


    class TestParent(object):
        connection = MockReceiverConnection()
        control = EnumControl("SD", enum_type=TestEnum)

    parent = TestParent()
    parent.connection.set_response("SD?", "SDAUTO")
    assert parent.control == TestEnum.Auto

    parent.connection.set_response("SD?", "SDHDMI")
    assert parent.control == TestEnum.HDMI

    parent.connection.set_response("SD?", "SDDIGITAL")
    assert parent.control == TestEnum.Digital

    parent.connection.set_response("SD?", "SDNO")
    with pytest.raises(StatusError):
        assert parent.control == TestEnum.Auto

    parent.control = TestEnum.Auto
    assert parent.connection.has_written("SDAUTO")
