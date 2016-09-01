"""Validate state machine
"""

import os
import sys
import mock
import unittest
from contextlib import contextmanager

sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from hbm import Heartbeat, Status


@contextmanager
def stdout_redirector(stream):
    old_stdout = sys.stdout
    sys.stdout = stream
    try:
        yield
    finally:
        sys.stdout = old_stdout


class TestState(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(TestState, self).__init__(*args, **kwargs)
        self.device = Heartbeat('192.0.2.1')

    @mock.patch('hbm.Heartbeat.on_up')
    def test_startup_to_up(self, mock_on_up):
        """Transition from startup to up
        """
        device = self.device
        device.good_count = 1
        mystatus = Status()
        mystatus.runAll([device])
        self.assertEqual(device.state, 'starting up')

        device.good_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'starting up')

        device.good_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')

        mock_on_up.assert_called()

    @mock.patch('hbm.Heartbeat.on_up')
    @mock.patch('hbm.Heartbeat.on_fail')
    def test_up_to_fail(self, mock_on_fail, mock_on_up):
        """Transition from up to fail
        """
        device = self.device
        device.good_count = 3
        mystatus = Status()
        mystatus.runAll([device])
        device.max_fail_count = 3
        device.fail_count = 1
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        device.fail_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        device.fail_count = 3
        self.assertRaises(SystemExit, mystatus.runAll, [device])
        self.assertEqual(device.state, 'failed')
        mock_on_fail.assert_called()

    @unittest.skip('Not Applicable when FSM configured to exit on fail')
    @mock.patch('hbm.Heartbeat.on_fail')
    @mock.patch('hbm.Heartbeat.on_up')
    def test_fail_to_up(self, mock_on_fail, mock_on_up):
        """Transition from fail to up
        """
        device = self.device
        device.good_count = 3
        mystatus = Status()
        mystatus.runAll([device])
        device.max_fail_count = 3
        device.fail_count = 3
        mystatus.runAll([device])
        device.good_count = 1
        mystatus.runAll([device])
        self.assertEqual(device.state, 'failed')
        device.good_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'failed')
        device.good_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        mock_on_up.assert_called()

    @mock.patch('hbm.Heartbeat.on_up')
    def test_up_to_warn(self, mock_on_up):
        """Transition from up to warn
        """
        device = self.device
        device.good_count = 3
        mystatus = Status()
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        device.max_warn_count = 3
        device.warn_count = 1
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        device.warn_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        device.warn_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')

    @mock.patch('hbm.Heartbeat.on_fail')
    @mock.patch('hbm.Heartbeat.on_up')
    def test_warn_to_fail(self, mock_on_fail, mock_on_up):
        """Transition from warn to fail
        """
        device = self.device
        device.good_count = 3
        mystatus = Status()
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')

        device.max_warn_count = 3
        device.warn_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')

        device.max_fail_count = 3
        device.fail_count = 1
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')
        device.fail_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')
        device.fail_count = 3
        self.assertRaises(SystemExit, mystatus.runAll, [device])
        self.assertEqual(device.state, 'failed')
        mock_on_fail.assert_called()
        self.assertRaises(SystemExit)

    @mock.patch('hbm.Heartbeat.on_up')
    def test_warn_to_up(self, mock_on_up):
        """Transition from warn to up
        """
        device = self.device
        device.good_count = 3
        mystatus = Status()
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')

        device.max_warn_count = 3
        device.warn_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')

        device.good_count = 1
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')
        device.good_count = 2
        mystatus.runAll([device])
        self.assertEqual(device.state, 'warn')
        device.good_count = 3
        mystatus.runAll([device])
        self.assertEqual(device.state, 'up')
        mock_on_up.assert_called()

if __name__ == '__main__':
    unittest.main(module=__name__, buffer=True, exit=False)
