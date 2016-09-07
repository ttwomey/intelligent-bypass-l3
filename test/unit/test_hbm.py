import sys
import os
import unittest
from mock import patch
import jsonrpclib
# from pprint import pprint
from StringIO import StringIO
# import syslog
from contextlib import contextmanager

sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from hbm import log, conf_string_to_list, run_cmds, intfStatus  # noqa

EMAIL = {}


@contextmanager
def stdout_redirector(stream):
    """Redirect STDOUT so we can capture log messages
    """
    old_stdout = sys.stdout
    sys.stdout = stream
    try:
        yield
    finally:
        sys.stdout = old_stdout


class TestHbm(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(TestHbm, self).__init__(*args, **kwargs)
        self.longMessage = True
        self.interfaces = {u'Ethernet1':
                           {u'autoNegotiateActive': False,
                            u'autoNegotigateActive': False,
                            u'bandwidth': 10000000000,
                            u'description': u'',
                            u'duplex': u'duplexFull',
                            u'interfaceType': u'Not Present',
                            u'linkStatus': u'notconnect',
                            u'vlanInformation': {u'interfaceForwardingModel': u'bridged',  # noqa
                                                 u'interfaceMode': u'bridged',
                                                 u'vlanId': 1}
                            }
                           }
        self.eapi_obj = jsonrpclib.Server(
            "http://admin:admin@localhost:80/command-api")

    def test_string_to_list(self):
        """Verify conversion of a srting from the INI file gets converted to a
        python list
        """
        line = 'enable,\nconfigure,\ninterface Ethernet52,\ndescription OK'
        expected = ['enable',
                    'configure',
                    'interface Ethernet52',
                    'description OK']
        self.assertEqual(conf_string_to_list(line), expected)

    def test_intfStatus(self):
        """Verify basics of the intfStatus() function
        """
        response = [{
            u'interfaces': {
                u'Ethernet1': {
                    u'lastStatusChangeTimestamp': 1468967397.91,
                    u'name': u'Ethernet1',
                    u'duplex': u'duplexFull',
                    u'autoNegotiate': u'success',
                    u'burnedInAddress': u'00:1c:73:0c:e1:b7',
                    u'mtu': 3978,
                    u'hardware': u'ethernet',
                    u'interfaceStatus': u'connected',
                    u'bandwidth': 1000000000,
                    u'forwardingModel': u'bridged',
                    u'lineProtocolStatus': u'up',
                    u'interfaceCounters': {
                        u'outBroadcastPkts': 504,
                        u'outUcastPkts': 550,
                        u'totalOutErrors': 0,
                        u'inMulticastPkts': 161575,
                        u'counterRefreshTime': 1473182586.74,
                        u'inBroadcastPkts': 8374438788,
                        u'outputErrorsDetail': {
                            u'collisions': 0,
                            u'lateCollisions': 0,
                            u'txPause': 0,
                            u'deferredTransmissions': 0
                        },
                        u'outOctets': 326526111,
                        u'outDiscards': 0,
                        u'inOctets': 536002463282,
                        u'inUcastPkts': 217,
                        u'inputErrorsDetail': {
                            u'runtFrames': 0,
                            u'fcsErrors': 0,
                            u'alignmentErrors': 0,
                            u'rxPause': 0,
                            u'symbolErrors': 0,
                            u'giantFrames': 0
                        },
                        u'linkStatusChanges': 9,
                        u'outMulticastPkts': 2596479,
                        u'totalInErrors': 0,
                        u'inDiscards': 0
                    },
                    u'interfaceStatistics': {
                        u'inBitsRate': 62.1194641099,
                        u'updateInterval': 300.0,
                        u'outBitsRate': 562.28074618,
                        u'outPktsRate': 0.565920614711,
                        u'inPktsRate': 0.0323538875573
                    },
                    u'interfaceAddress': [],
                    u'physicalAddress': u'00:1c:73:0c:e1:b7',
                    u'description': u''
                }}}]

        eapi_obj = jsonrpclib.Server("http://me:me@localhost:80/command-api")
        with patch('jsonrpclib.Server._request') as mock:
            mock.return_value = response
            output = intfStatus(eapi_obj, 'Ethernet1')
            self.assertEquals(output, 'up')

    def test_run_cmds(self):
        """Verify basics of the run_cmds() function
        """

        response = [{
            "modelName": "vEOS",
            "internalVersion": "4.15.3F-2812776.4153F",
            "systemMacAddress": "08:00:27:c9:c8:c5",
            "serialNumber": "",
            "memTotal": 1897596,
            "bootupTimestamp": 1472239579.45,
            "memFree": 120348,
            "version": "4.15.3F",
            "architecture": "i386",
            "internalBuildId": "34549125-b84f-41f0-b8bb-ce9d509814de",
            "hardwareRevision": ""
        }]

        eapi_obj = jsonrpclib.Server("http://me:me@localhost:80/command-api")
        with patch('jsonrpclib.Server._request') as mock:
            mock.return_value = response

            output = run_cmds(eapi_obj, ['show version'])
            self.assertEquals(None, output)

    @patch('syslog.syslog')
    def test_log(self, mock_syslog):
        """Verify basics of the log() function
        """

        message = "Test message"
        log(message)

    @patch('syslog.syslog')
    def test_log_debug(self, mock_syslog):
        """Verify the log() function set to DEBUG
        """
        message = "Test message"
        log(message, level='DEBUG')
        mock_syslog.assert_called_with(7, message)
        args, kwargs = mock_syslog.call_args
        self.assertTrue(message in args)

    @patch('syslog.syslog')
    def test_log_error(self, mock_syslog):
        """Verify the log() function with error=True
        """
        message = "Test message"
        out = StringIO()
        with stdout_redirector(out):
            log(message, error=True)
        output = out.getvalue().strip()
        assert output.startswith('ERROR:')
        mock_syslog.assert_called_with(3, message)
        args, kwargs = mock_syslog.call_args
        self.assertTrue(message in args)

    global EMAIL
    EMAIL = {'enabled': True,
             'from': 'jere@arsita.com',
             'to': ['eosplus-dev@arista.com'],
             'subject': 'this is a test',
             'mailserver': 'localhost'}

    @unittest.skip('disabled')
    @patch('syslog.syslog')
    @patch('smtplib.SMTP')
    @patch('hbm.email')
    def test_email_basic(self, mock_email, mock_smtp, mock_syslog):
        """Verify the log() function with email=True
        """
        message = "Test message"
        out = StringIO()
        with stdout_redirector(out):
            log(message, email=True)
        output = out.getvalue().strip()
        print "DEBUG: {0}".format(output)
        mock_syslog.assert_called_with(6, message)
        args, kwargs = mock_syslog.call_args
        self.assertTrue(message in args)
        mock_email.assert_called_with('my email')

if __name__ == '__main__':
    unittest.main(module=__name__, buffer=True, exit=False)
