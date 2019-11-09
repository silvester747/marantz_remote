#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test the receiver interface
"""

import pytest

from typing import List, Pattern
from unittest.mock import MagicMock

from marantz_remote.receiver import BooleanControl, Control, ReceiverConnection, StatusError


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


def test_booleancontrol():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = BooleanControl("PW")

    parent = TestParent()
    parent.connection.set_response("PW?", "PWOFF")
    assert parent.control == False

    parent.connection.set_response("PW?", "PWON")
    assert parent.control == True

    parent.control = True
    assert parent.connection.has_written("PWON")

    parent.control = False
    assert parent.connection.has_written("PWOFF")


def test_booleancontrol__invalidresponse():
    class TestParent(object):
        connection = MockReceiverConnection()
        control = BooleanControl("PW")

    parent = TestParent()
    parent.connection.set_responses("PW?", ["PWO", "PWTRUE", "PWFALSE", "PW0", "PW1"])
    with pytest.raises(StatusError):
        assert parent.control == False

