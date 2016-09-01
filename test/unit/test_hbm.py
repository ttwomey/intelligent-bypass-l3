import sys
import os
import unittest
import mock
# from pprint import pprint
from StringIO import StringIO
# import syslog
from contextlib import contextmanager

sys.path.append(os.path.join(os.path.dirname(__file__), '../lib'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from hbm import log, conf_string_to_list, run_cmds, intfStatus, check_path

EMAIL = {}


@contextmanager
def stdout_redirector(stream):
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
                            u'vlanInformation': {u'interfaceForwardingModel': u'bridged',
                                                 u'interfaceMode': u'bridged',
                                                 u'vlanId': 1}
                            }
                           }

    @mock.patch('syslog.syslog')
    def test_log(self, mock_syslog):
        """Verify basics of the log() function
        """

        message = "Test message"
        log(message)

    @mock.patch('syslog.syslog')
    def test_log_debug(self, mock_syslog):
        """Verify the log() function set to DEBUG
        """
        message = "Test message"
        log(message, level='DEBUG')
        mock_syslog.assert_called_with(7, message)
        args, kwargs = mock_syslog.call_args
        self.assertTrue(message in args)

    @mock.patch('syslog.syslog')
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
    @mock.patch('syslog.syslog')
    @mock.patch('smtplib.SMTP')
    @mock.patch('hbm.email')
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
