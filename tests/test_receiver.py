#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test the receiver interface
"""

import pytest
import pytest_twisted

from enum import Enum
from typing import List, Pattern
from twisted.internet import reactor
from twisted.internet.defer import Deferred, TimeoutError
from twisted.internet.testing import StringTransportWithDisconnection
from unittest.mock import MagicMock

from marantz_remote.receiver import (Control, EnumControl, NumericControl, ReceiverBase,
                                     ReceiverProtocol, VolumeControl)


class MockedConnectionReceiver(ReceiverBase):
    test_connects_directly: bool = True

    def __init__(self, host: str, timeout: int = 1):
        super().__init__(host, timeout)
        if self.test_connects_directly:
            self.finish_connect()

    def connect(self, host: str) -> Deferred:
        self.transport = StringTransportWithDisconnection()
        return Deferred()

    def finish_connect(self):
        protocol = ReceiverProtocol(self)
        protocol.makeConnection(self.transport)
        self.connected.callback(protocol)

    def write_response(self, msg):
        self.protocol.lineReceived(msg)

    def sent(self):
        data = self.transport.value()
        self.transport.clear()
        return data


def test_receiverbase_connect_then_write():
    class TestParent(MockedConnectionReceiver):
        test_connects_directly = False

    parent = TestParent("fakehost")
    parent.finish_connect()
    parent.write("Test")
    assert parent.sent() == b"Test\r"


def test_receiverbase_write_before_connect():
    class TestParent(MockedConnectionReceiver):
        test_connects_directly = False

    parent = TestParent("fakehost")
    parent.write("Test")
    assert parent.sent() == b""

    parent.finish_connect()
    assert parent.sent() == b"Test\r"


def test_receiverbase_multiple_writes_wait_for_each_response():
    class TestParent(MockedConnectionReceiver):
        test_connects_directly = False
        control = Control("PW")

    parent = TestParent("fakehost")
    parent.finish_connect()
    parent.write("Test")
    parent.write("Test2")
    parent.write("Test3")
    assert parent.sent() == b"Test\r"

    parent.write_response(b"Response")
    assert parent.sent() == b"Test2\r"

    parent.write_response(b"Response2")
    assert parent.sent() == b"Test3\r"


@pytest_twisted.inlineCallbacks
def test_receiverbase_multiple_writes_with_no_response():
    class TestParent(MockedConnectionReceiver):
        test_connects_directly = False
        control = Control("PW")

    parent = TestParent("fakehost", 0.1)
    parent.finish_connect()
    parent.write("Test")
    parent.write("Test2")
    parent.write("Test3")
    assert parent.sent() == b"Test\r"

    def check():
        assert parent.sent() == b"Test2\rTest3\r"
    yield reactor.callLater(1.0, check)


def test_receiverbase_multiple_writes_with_no_timeout():
    class TestParent(MockedConnectionReceiver):
        test_connects_directly = False
        control = Control("PW")

    parent = TestParent("fakehost", 0)
    parent.finish_connect()
    parent.write("Test")
    parent.write("Test2")
    parent.write("Test3")
    assert parent.sent() == b"Test\rTest2\rTest3\r"


@pytest_twisted.inlineCallbacks
def test_control__name_only():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW?\r"

    parent.write_response(b"PWOFF")
    d.addTimeout(1, reactor)
    value = yield d
    assert value == "OFF"

    parent.control = "ON"
    assert parent.sent() == b"PWON\r"


@pytest_twisted.inlineCallbacks
def test_control__override_status_command():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW", status_command="PW ?")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW ?\r"

    parent.write_response(b"PWOFF")
    d.addTimeout(1, reactor)
    value = yield d
    assert value == "OFF"

    parent.control = "ON"
    assert parent.sent() == b"PWON\r"


@pytest_twisted.inlineCallbacks
def test_control__override_set_command():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW", set_command="PWA")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW?\r"

    parent.write_response(b"PWOFF")
    d.addTimeout(1, reactor)
    value = yield d
    assert value == "OFF"

    parent.control = "ON"
    assert parent.sent() == b"PWAON\r"


@pytest_twisted.inlineCallbacks
def test_control__override_response_prefix():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW", response_prefix="PWA")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW?\r"

    parent.write_response(b"PWAOFF")
    d.addTimeout(1, reactor)
    value = yield d
    assert value == "OFF"

    parent.control = "ON"
    assert parent.sent() == b"PWON\r"


@pytest_twisted.inlineCallbacks
def test_control__incorrect_response():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW?\r"

    parent.write_response(b"RWAUTO")
    d.addTimeout(1, reactor)

    with pytest.raises(TimeoutError):
        yield d


@pytest_twisted.inlineCallbacks
def test_control__ignore_other_responses():
    class TestParent(MockedConnectionReceiver):
        control = Control("PW")

    parent = TestParent("fakehost")
    d = parent.control
    assert parent.sent() == b"PW?\r"

    parent.write_response(b"CV20")
    parent.write_response(b"MV30")
    parent.write_response(b"MUON")
    parent.write_response(b"PWOFF")

    d.addTimeout(1, reactor)
    value = yield d
    assert value == "OFF"


@pytest_twisted.inlineCallbacks
def test_numericcontrol():
    class TestParent(MockedConnectionReceiver):
        control = NumericControl("MV")

    parent = TestParent("fakehost")

    d = parent.control
    assert parent.sent() == b"MV?\r"

    parent.write_response(b"MV50")
    d.addTimeout(1, reactor)
    value = yield d
    assert value == 50

    parent.write_response(b"MV70")
    d = parent.control
    assert not parent.sent()

    d.addTimeout(1, reactor)
    value = yield d
    assert value == 70

    parent.control = 4
    assert parent.sent() == b"MV04\r"
    parent.write_response(b"MV04")

    parent.control = 38
    assert parent.sent() == b"MV38\r"


@pytest_twisted.inlineCallbacks
def test_numericcontrol__invalid_response():
    class TestParent(MockedConnectionReceiver):
        control = NumericControl("MV")

    parent = TestParent("fakehost")

    d = parent.control
    assert parent.sent() == b"MV?\r"

    parent.write_response(b"MVO")
    parent.write_response(b"MVTRUE")
    parent.write_response(b"MVFALSE")
    parent.write_response(b"MV")
    parent.write_response(b"MVB30")
    d.addTimeout(1, reactor)
    with pytest.raises(TimeoutError):
        yield d


def test_numericcontrol__invalid_input():
    class TestParent(MockedConnectionReceiver):
        control = NumericControl("MV")

    parent = TestParent("fakehost")
    with pytest.raises(ValueError):
        parent.control = -1
    with pytest.raises(ValueError):
        parent.control = 100


@pytest_twisted.inlineCallbacks
def test_numericcontrol__more_digits():
    class TestParent(MockedConnectionReceiver):
        control = NumericControl("MV", digits=4)

    parent = TestParent("fakehost")

    parent.write_response(b"MV0050")
    value = yield parent.control.addTimeout(1, reactor)
    assert value == 50

    parent.write_response(b"MV0700")
    value = yield parent.control.addTimeout(1, reactor)
    assert value == 700

    parent.control = 4
    assert parent.sent() == b"MV0004\r"
    parent.write_response(b"MV0004")

    parent.control = 38
    assert parent.sent() == b"MV0038\r"
    parent.write_response(b"MV0038")

    parent.control = 210
    assert parent.sent() == b"MV0210\r"
    parent.write_response(b"MV0210")

    parent.control = 3233
    assert parent.sent() == b"MV3233\r"
    parent.write_response(b"MV3233")


def test_volumecontrol():
    class TestParent(MockedConnectionReceiver):
        control = VolumeControl("MV")

    parent = TestParent("fakehost")

    parent.control = "+"
    assert parent.sent() == b"MVUP\r"
    parent.write_response(b"MV31")

    parent.control = "-"
    assert parent.sent() == b"MVDOWN\r"
    parent.write_response(b"MV30")


@pytest_twisted.inlineCallbacks
def test_enumcontrol():
    class TestEnum(Enum):
        Auto = "AUTO"
        HDMI = "HDMI"
        Digital = "DIGITAL"


    class TestParent(MockedConnectionReceiver):
        control = EnumControl("SD", enum_type=TestEnum)

    parent = TestParent("fakehost")

    parent.write_response(b"SDAUTO")
    value = yield parent.control.addTimeout(1, reactor)
    assert value == TestEnum.Auto

    parent.write_response(b"SDHDMI")
    value = yield parent.control.addTimeout(1, reactor)
    assert value == TestEnum.HDMI

    parent.write_response(b"SDDIGITAL")
    value = yield parent.control.addTimeout(1, reactor)
    assert value == TestEnum.Digital

    parent.write_response(b"SDNO")
    with pytest.raises(TimeoutError):
        yield parent.control.addTimeout(1, reactor)
    assert parent.sent() == b"SD?\r"
    parent.write_response(b"SDNO")

    parent.control = TestEnum.Auto
    assert parent.sent() == b"SDAUTO\r"
