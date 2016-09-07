#!/usr/bin/env python
# pylint: disable=W0612, broad-except, invalid-name
#
# Copyright (c) 2016, Arista Networks, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#  - Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#  - Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#  - Neither the name of Arista Networks nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Heartbeat Monitor - Intelligent Bypass
#
#    Version 1.0-post 2015-09
#    Written by:
#       Andrei Dvornic, Arista Networks
#       EOS+ Consulting Services
#
#    Revision history:
#       1.0 - initial release
#       1.0+ - Multi-chassis support

"""
   DESCRIPTION
      The Heartbeat Monitor script enables users to monitor connectivity
      between two ports and apply/remove some configuration whenever the
      connectivity is lost/recovered. Connectivity is monitored through
      heartbeats which are regularly send out of an egress port and
      expected on another ingress port on the switch.

   INSTALLATION
      In order to install Heartbeat Monitor, copy 'hbm' to /mnt/flash.

      Heartbeat Monitor can then be started using:
         (bash:root)# /mnt/flash/hbm [<options>] <source_intf> <dest_intf> &
      and you can use 'nohup' utility in order to make this persistent
      over ssh:
         (bash:root)# nohup /mnt/flash/hbm [<options>]
                      <source_intf> <dest_intf> &

      See:
         (bash:root)# /mnt/flash/hbm --help
      for details about the command-line options.

      In order to run Heartbeat Monitor as a daemon (persistent after
      reboot), add the following to the startup-config:

      daemon hbm
         command /mnt/flash/hbm [<options>] <source_intf> <dest_intf>

      Heartbeat Monitor process name is 'hbm', so standard Linux tools can be
      used to stop and restart it with different options:
      e.g.
         (bash:root)# pkill hbm
         (bash:root)# /mnt/flash/hbm [<new-options>]
                      <source_intf> <dest_intf> &

      Note that in order to make sure the Heartbeat Monitor does not
      restart on reboot / starts with a different config on reboot,
      the startup-config has to be changed accordingly.

      In order to uninstall Heartbeat Monitor, use:
         (bash:root)# rm /mnt/flash/hbm
         (bash:root)# pkill hbm                    // if running

   PREREQUISITES
      eAPI must be enabled in order to allow the Heartbeat Monitor to
      update the configuration of the switch.

      STP must be disabled.

      MAC learning must be disabled on all interfaces involved in the
      setup.

      A layer-3 interface must be enabled allowing the heartbeat packets to
      reach the control-plane to effectively detect them.

   CONFIGURATION/DEBUGGING
      In order to start the Heartbeat Monitor, the following arguments must
      be specified:
       - source interface: name of the kernel interface corresponding to the
                           physical port on which the heartbeats are sent
       - destination interface: name of the kernel interface corresponding to
                                the L3 interface on which the heartbeats are
                                expected

      e.g.
         (bash:root)# /mnt/flash/hbm et2 vlan200

      By default, a heartbeat is transmitted every 10ms. In order to
      send heartbeats more/less often, please use the -i/--interval
      command line option:

      e.g.
         // send hearbeat every 300ms
         (bash:root)# /mnt/flash/hbm -i 300 ... <source_intf> <dest_intf>

      Connectivity failure is detected by checking whether a heartbeat
      is being received for a certain period, called timeout. By
      default, the timeout is 25ms, but that can be changed by using
      the -t/--timeout command line option:

      e.g.
         // expect hearbeat every second
         (bash:root)# /mnt/flash/hbm -t 1000 ... <source_intf> <dest_intf>

      In order to enable debugging output to stdout, use the -v/--verbose
      command line option.

      e.g.
         (bash:root)# /mnt/flash/hbm -v ... <source_intf> <dest_intf>

      Note that the output can be quite verbose so it is recommended
      that this option is used with caution, and only for debugging
      purposes.

      The switch is configured via eAPI - the authentication
      credentials for that must be configured at the top of the script
      in the highlighted section. This section should also be used in
      order to specify the source/destination MAC address to-be-used
      for the heartbeats. The destination MAC must correspond to the
      destination interface where the heartbeats are expected.

      The configuration which needs to be applied to the switch on
      heartbeats failure/recovery is also configurable at the top of
      the script.

   COMPATIBILITY
      Version 1.0 has been developed and tested against
      EOS-4.13.0. Please reach out to support@aristanetworks.com if
      you want to run this against a different EOS release.

   EXTRA
      The script also synchronizes the state of two interfaces,
      defined via the INTERFACE_1 and INTERFCE_2 constants in the
      configuration section.  If either of the two interfaces goes
      down, the other one is turned off automatically. Similarly,
      whenever the first interface recovers, the other interface is
      turned back on.
"""

import argparse
import ConfigParser
import json
from jsonrpclib import Server
import jsonrpclib
import os
from pprint import pformat
import re
import smtplib
import socket
import subprocess
import sys
import syslog
import time
import traceback

from ctypes import cdll, byref, create_string_buffer

DEBUG = False          # pylint: disable=C0103
MAIL = None            # pylint: disable=C0103


def setProcName(newname):
    """Configure the process name so this may easily be identified in ps

    Args:
        newname (str): The desired processname
    """
    libc = cdll.LoadLibrary('libc.so.6')
    buff = create_string_buffer(len(newname) + 1)
    buff.value = newname
    libc.prctl(15, byref(buff), 0, 0, 0)


def log(msg, level='INFO', error=False, email=False, subject=''):
    """Log messages to syslog and, optionally, email

    Args:
        msg (str): The message to log.
        level (str): The priority level for the message. (Default: INFO)
                    See :mod:`syslog` for more options.
                    EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG
        error (bool): Flag if this is an error condition.
        email (bool): Send this as an email, also. (Default: False)
        subject (str): Email subject string

    """

    if DEBUG:
        print "{0} ({1}) {2}".format(os.path.basename(sys.argv[0]), level, msg)

    if error:
        level = "ERR"
        print "ERROR: {0} ({1}) {2}".format(os.path.basename(sys.argv[0]),
                                            level, msg)

    priority = ''.join(["syslog.LOG_", level])
    syslog.syslog(eval(priority), msg)

    if email:
        if MAIL and MAIL.config['enabled']:
            MAIL.send(msg, subject=subject)


class mail(object):
    """Handle sending email notifications
    """
    config = {}

    def __init__(self, config):
        """Store the options from the config"""
        self.config = config

    def send(self, msg, subject=''):
        """Wrap the message in an envelope and send it

        Args:
            msg (str): message body to send
            subject (str): Override the subject line in the config
        """

        if self.config['enabled']:

            if subject is not '':
                subject = ': ' + subject

            message = """From: {}
To: {}
Subject: {}

{}
""".format(self.config['from'],
                ','.join(self.config['to']),
                self.config['subject'] + subject, msg)

            try:
                smtp_obj = smtplib.SMTP(self.config['mailserver'],
                                        self.config['mailserverport'])
                if self.config['starttls']:
                    smtp_obj.starttls()
                if self.config['login']:
                    smtp_obj.login(self.config['username'],
                                   self.config['password'])
                smtp_obj.sendmail(self.config['from'],
                                  self.config['to'],
                                  message)
                smtp_obj.quit()
                if DEBUG:
                    print "Successfully sent email"
                log("Successfully sent email", level='DEBUG')
            except smtplib.SMTPException:
                if DEBUG:
                    print "Warning: unable to send email"
                log("Warning: unable to send email", level='WARNING')


def parse_cmd_line():
    """Parse the command line options and return an args dict.

    Returns:
        dict: A dictionary of CLI arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            'Monitor the BGP peer across a specified interface.  Shutdown that'
            ' interface if the peer goes down due to BFD to force a manual'
            ' recovery.'))

    parser.add_argument('--config',
                        type=str,
                        default='/persist/sys/bfd_int_sync.ini',
                        help='Configuration file to load' +
                        ' (Default: /persist/sys/bfd_int_sync.ini)')

    parser.add_argument('--debug',
                        action='store_true',
                        default=False,
                        help='Send debug information to the console')

    parser.add_argument('--logfile',
                        type=str,
                        action='store',
                        default='/var/log/eos',
                        help='The path to the log to watch')

    args = parser.parse_args()

    global DEBUG  # pylint: disable=C0103
    if args.debug:
        DEBUG = True

    if DEBUG:
        print "CLI Args: {0}\n".format(pformat(args))

    return args


def parse_config(filename):
    """ Read settings from the config file

    Args:
        filename (str): The path to the config file.

    Returns:
        dict: A dictionary of configuration and switch definitions.
    """

    if not filename:
        filename = "/persist/sys/hbm.conf"
    os.path.isfile(filename)
    if not os.access(filename, os.R_OK):
        log('Unable to read config file {0}'.format(filename))
        raise IOError("Unable to read config file {0}".format(filename))

    defaults = {
        'hostname': 'localhost',
        'hostname2': '',
        'protocol': 'https',
        'port': '443',
        'username': 'arista',
        'password': 'arista',
        'url': '%(protocol)s://%(username)s:%(password)s@%(hostname)s:' +
               '%(port)s/command-api',
        'interval': '5',
        'timeout': '5',
        'alert_threshold': '4',
        'failure_threshold': '8'
    }

    config = ConfigParser.SafeConfigParser(defaults)
    config.read(filename)

    CONFIG = {}

    try:
        config.options('email')
    except ConfigParser.NoSectionError, err:
        log("Required [email] section missing from config file {0}: ({1})".
            format(filename, err))
        raise IOError(
            "Required [email] section missing from config file {0}: ({1})".
            format(filename, err))
    CONFIG['email'] = {}
    CONFIG['email']['enabled'] = config.getboolean('email', 'enabled')
    CONFIG['email']['starttls'] = config.getboolean('email', 'starttls')
    CONFIG['email']['login'] = config.getboolean('email', 'login')
    CONFIG['email']['mailserver'] = config.get('email', 'mailserver')
    CONFIG['email']['mailserverport'] = config.getint('email',
                                                      'mailserverport')
    CONFIG['email']['from'] = config.get('email', 'from')
    CONFIG['email']['subject'] = config.get('email', 'subject')
    CONFIG['email']['to'] = conf_string_to_list(config.get('email', 'to'))
    if DEBUG:
        print "EMAIL: {0}\n".format(pformat(CONFIG['email']))

    CONFIG['eapi'] = {}
    CONFIG['eapi']['hostname'] = config.get('eapi', 'hostname')
    CONFIG['eapi']['protocol'] = config.get('eapi', 'protocol')
    CONFIG['eapi']['port'] = config.get('eapi', 'port')
    CONFIG['eapi']['username'] = config.get('eapi', 'username')
    CONFIG['eapi']['password'] = config.get('eapi', 'password')
    CONFIG['eapi']['ok_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'ok_config'))
    CONFIG['eapi']['fail_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'fail_config'))
    CONFIG['eapi']['shutdown_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'shutdown_config'))
    CONFIG['eapi']['url'] = config.get('eapi', 'url')

    if 'peer_eapi' in config.sections():
        CONFIG['peer'] = {}
        CONFIG['peer']['hostname'] = config.get('peer_eapi', 'hostname')
        CONFIG['peer']['protocol'] = config.get('peer_eapi', 'protocol')
        CONFIG['peer']['port'] = config.get('peer_eapi', 'port')
        CONFIG['peer']['username'] = config.get('peer_eapi', 'username')
        CONFIG['peer']['password'] = config.get('peer_eapi', 'password')
        CONFIG['peer']['ok_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'ok_config'))
        CONFIG['peer']['fail_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'fail_config'))
        CONFIG['peer']['shutdown_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'shutdown_config'))
        CONFIG['peer']['url'] = config.get('peer_eapi', 'url')

    CONFIG['interval'] = config.getint('General', 'interval')
    CONFIG['alert_holddown'] = config.getint('General', 'alert_holddown')
    CONFIG['timeout'] = config.getint('General', 'timeout')
    CONFIG['alert_threshold'] = config.getfloat('General', 'alert_threshold')
    CONFIG['failure_threshold'] = config.getfloat('General',
                                                  'failure_threshold')
    CONFIG['interface1'] = config.get('General', 'interface1')
    CONFIG['interface2'] = config.get('General', 'interface2')
    if 'probe_dst_address1' in config.items('General'):
        CONFIG['probe_dst_address1'] = config.get('General',
                                                  'probe_dst_address1')
    if 'probe_dst_address2' in config.items('General'):
        CONFIG['probe_dst_address2'] = config.get('General',
                                                  'probe_dst_address2')

    if DEBUG:
        print "CONFIG: {0}\n".format(pformat(CONFIG))

    return CONFIG


def conf_string_to_list(list_as_string):
    """Given a 'list' as returned from ConfigParser, split it, trim it,
    then return a real list object.

    Example input:
        'enable,\nconfigure,\ninterface Ethernet52,\ndescription HBM: OK'
    """

    list_from_string = []
    for line in list_as_string.split('\n'):
        for item in line.split(","):
            item = item.strip('\t')
            if len(item):
                list_from_string.append(item)
    return list_from_string


def run_cmds(eapi, cmds):
    """Returns the output of eapi_client.runCmds()

    Args:
        eapi (obj): JSONrpc Switch object
        cmds (list): List of commands to execute on a switch

    Returns:
        list: JSONrpc response
    """

    if DEBUG:
        print "Executing commands: {}".format(pformat(cmds))

    try:
        eapi.runCmds(1, cmds)
    except jsonrpclib.jsonrpc.ProtocolError as err:
        log("Command Error: {}. Attempted commands: {}.".format(
            err[0][1], json.loads(jsonrpclib.history.request)['params'][1]),
            error=True)


def intfStatus(eapi, intf):
    """Returns interface status of the given intf

    Args:
        eapi (obj): JSONrpc Switch object
        intf (str): Interface name to be checked

    Returns:
        str: The eAPI lineProtocolStatus value
    """
    output = eapi.runCmds(1, ['show interfaces %s' % intf])[0]
    return output['interfaces'][intf]['lineProtocolStatus']


def check_path(dst_address):
    """Initiate pings, then return tuple of stats

    Args:
        dst_address (str): IP address of the remote interface to monitor

    Returns:
        tuple: Ping command results: (retcode, pmin, pavg, pmax, pmdev)
    """
    log('Sending ping...', level='DEBUG')

    cmd = ['ping',
           '-c', '1',
           # '-t', str(timeout),
           dst_address]

    retcode = 0
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        match = re.match(r"^.*=\s([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)\s.*$",
                         output, re.MULTILINE | re.DOTALL)
        (pmin, pavg, pmax, pmdev) = match.groups()

        (pmin, pavg, pmax, pmdev) = (float(pmin), float(pavg),
                                     float(pmax), float(pmdev))
    except subprocess.CalledProcessError as err:
        (pmin, pavg, pmax, pmdev) = (None, None, None, None)
        retcode = err.returncode

    return (retcode, pmin, pavg, pmax, pmdev)


def wait_for_eapi(eapi):
    """Continuously test whether eAPI is enabled on a switch before continuing

    Args:
        eapi (obj): JSONrpc Switch object
    """
    eapi_enabled = False
    while not eapi_enabled:
        try:
            eapi.runCmds(1, ['enable'])
            eapi_enabled = True
        except socket.error:
            log('Waiting for eAPI to be enabled...')
            time.sleep(1)


class State(object):
    """The methods of this class are a template for the required states of a
    device
    """
    def run(self):
        """Override this to define actions to run in this state
        """
        assert 0, "run not implemented"

    def next(self, heartbeat):
        """Override this to define the next state based on some analysis
        """
        assert 0, "next not implemented"


class StateMachine(object):
    """This sets the initial state and maintains state during execution
    """
    def __init__(self, initialState):
        self.currentState = initialState
        self.currentState.run()

    # Template method:
    def runAll(self, devices):
        """For each device, passed, run next() to get the next state, then
        run the run() method for that state
        """
        for device in devices:
            if DEBUG:
                print "Run State @ call: " + str(device.state)
            self.currentState = self.currentState.next(device)
            self.currentState.run()


class Startup(State):
    """Define the Startup state.  In this state eAPI is being verified
    and initial heartbeats are generated.
    """
    def run(self):
        if DEBUG:
            print "Starting up"

    def next(self, heartbeat):
        """Continue in the Startup state until the minimum good heartbeats
        pass
        """
        if heartbeat.good_count == heartbeat.min_good_count:
            heartbeat.state = "up"
            log("Device came up.  Setting state STARTUP --> UP",
                email=True,
                subject="Heartbeats up")
            heartbeat.on_up()
            return Status.up
        heartbeat.state = "starting up"
        return Status.startup


class Up(State):
    """Define the Up state.  Heartbeats are passing and we are monitoring
    then path.
    """
    def run(self):
        if DEBUG:
            print "Up"

    def next(self, heartbeat):
        """Too many consecutive heartbeat failures cause the state to go down.
        Too many consecutive heartbeats beyond the warning threshold cause the
        state to go to warn.
        """
        if heartbeat.fail_count == heartbeat.max_fail_count:
            heartbeat.state = "failed"
            heartbeat.good_count = 0
            log("Device reached max_fail_count.  Setting state --> DOWN",
                email=True,
                subject="Heartbeats down")
            heartbeat.on_fail()
            return Status.failed
        elif heartbeat.warn_count == heartbeat.max_warn_count:
            heartbeat.state = "warn"
            heartbeat.good_count = 0
            log("Device reached max_warn_count.  Setting state --> WARN",
                email=True,
                subject="Heartbeats down")
            heartbeat.on_warn()
            return Status.warn
        return Status.up


class Failed(State):
    """Define the Failed state
    """
    def run(self):
        """Exit on failure.  Enforces manual intervention to recover.
        """
        if DEBUG:
            print "Failed"
        exit()

    def next(self, heartbeat):
        """IF allowed to auto-recover, once there are sufficient consecutive
        successful heartbeats, transition to Up.
        """
        if heartbeat.good_count == heartbeat.min_good_count:
            heartbeat.state = "up"
            heartbeat.fail_count = 0
            heartbeat.warn_count = 0
            log("Device came up.  Setting state FAILED --> UP",
                email=True,
                subject="Heartbeats up")
            heartbeat.on_up()
            return Status.up
        return Status.failed


class Warn(State):
    """Define the Warn state.  Send alerts but keep running.
    """
    def run(self):
        if DEBUG:
            print "Warning"

    def next(self, heartbeat):
        """If heartbeats fail consecutively, transition to Down.  If heartbeat
        latency improves, go back to Up.
        """
        if heartbeat.fail_count == heartbeat.max_fail_count:
            heartbeat.state = "failed"
            heartbeat.good_count = 0
            log("Device reached max_fail_count.  Setting state --> DOWN",
                email=True,
                subject="Heartbeats down")
            heartbeat.on_fail()
            return Status.failed
        elif heartbeat.good_count == heartbeat.min_good_count:
            heartbeat.warn_count = 0
            heartbeat.state = "up"
            log("Device came up.  Setting state WARN --> UP",
                email=True,
                subject="Heartbeats up")
            heartbeat.on_up()
            return Status.up
        return Status.warn


class Status(StateMachine):
    """Define the valid states and initial state
    """
    def __init__(self):
        StateMachine.__init__(self, Status.startup)

Status.startup = Startup()
Status.up = Up()
Status.failed = Failed()
Status.warn = Warn()


class Heartbeat(object):
    """State machine to monitor devices
    """

    def __init__(self, probe_dst_address, interface='', timeout=1):
        """Set initial state

        Args:
            probe_dst_address (str): IP address to use as the ping destination
            interface (str): Linux interface name on which to send probes
            timeout (int): Ping timeout setting
        """

        self.probe_dst_address = probe_dst_address
        self.interface = interface
        self.timeout = timeout

        self.state = 'not started'
        self.status = None

        # Number of ms at which to consider heartbeat a warn or fail
        self.warn_threshold = 4
        self.fail_threshold = 8

        # eAPI config from the INI file
        self.eapi = {}
        self.peer = {}

        self.good_count = 0
        self.warn_count = 0
        self.fail_count = 0
        self.min_good_count = 3
        self.max_warn_count = 3
        self.max_fail_count = 3

        self.pause_seconds = 10

        self.alert_holddown = 0  # 0 = exit on failure

    def __str__(self):
        return self.state

    def do_health_check(self):
        """Generate a heartbeat. If successful, compare latency with
        configured thresholds. Increment status counters on the object.
        """
        (retcode, pmin, pavg, pmax, pmdev) = check_path(self.probe_dst_address)
        log('Received echo reply min/agv/max/mdev '
            '{}/{}/{}/{} ms'.format(pmin,
                                    pavg,
                                    pmax,
                                    pmdev),
            level='DEBUG')

        if retcode is not 0 or pavg > self.fail_threshold:
            self.fail_count += 1
            log("Device check failed {} times ({}, {}/{}).".
                format(self.fail_count, retcode, pavg, self.fail_threshold),
                level='WARNING')
        elif pavg > self.warn_threshold:
            self.warn_count += 1
            log("Device check degraded {} times.".format(self.warn_count),
                email=True, subject='Heartbeats degraded',
                level='WARNING')
        else:
            self.good_count += 1

    def on_up(self):
        """Perform actions on transition to up
        """
        run_cmds(self.eapi['switch'], self.eapi['ok_config'])
        if self.peer['ok_config']:
            run_cmds(self.peer['switch'], self.peer['ok_config'])

    def on_warn(self):
        """Perform actions on transition to warn
        """
        pass

    def on_fail(self):
        """Perform actions on transition to fail
        """
        log('Disabling the monitored path due to multiple failures',
            level='CRIT')
        run_cmds(self.eapi['switch'], self.eapi['fail_config'])
        if self.peer['fail_config']:
            run_cmds(self.peer['switch'], self.peer['fail_config'])

        while self.alert_holddown > 0:
            # Send alerts on a regular interval until manually stopped.
            log("Heartbeat monitor triggered automatic shutdown of {}"
                " and {}.".format(self.interface1, self.interface2),
                email=True,
                subject="Heartbeats triggered shutdown")
            time.sleep(self.alert_holddown)

    def on_shutdown(self):
        """Perform actions on transition to fail
        """
        log('Disabling the monitor process.',
            level='CRIT')
        run_cmds(self.eapi['switch'], self.eapi['shutdown_config'])
        if self.peer['shutdown_config']:
            run_cmds(self.peer['switch'], self.peer['shutdown_config'])


def get_peer_addr(CONFIG, interface):
    """Given a layer-3 interface and assuming a /30, determine the peer's
    IP address

    Args:
        CONFIG (dict): Parsed settings from the config file
        interface (str): Interface name to be analyzed

    Returns:
        str: The peer's IP address as a string
    """
    # better done with a module like netaddr or ipaddr but attempting to
    # avoid installing additional modules
    import subprocess

    output = CONFIG['eapi']['switch'].runCmds(1, ['show ip interface %s' %
                                                  interface])[0]
    mask_len = \
        output['interfaces'][interface]['interfaceAddress']['primaryIp']['maskLen']  # noqa
    if mask_len != 30:
        log("Interface {}/{} is not using a /30 network".format(interface,
                                                                mask_len))

    local_addr = \
        output['interfaces'][interface]['interfaceAddress']['primaryIp']['address']  # noqa

    output = subprocess.check_output(['ipcalc', '-bn', str(local_addr) + '/' +
                                      str(mask_len)])
    match_expr = r'^BROADCAST=(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*NETWORK=(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})'  # noqa
    regex = re.compile(match_expr, re.DOTALL)
    match_obj = regex.match(output)
    (bcast, network) = match_obj.groups()
    boct = int(bcast.split('.')[3])
    local_oct = int(local_addr.split('.')[3])
    if local_oct + 1 < boct:
        peer_oct = local_oct + 1
    else:
        peer_oct = local_oct - 1

    return '.'.join(['.'.join(local_addr.split('.')[0:3]), str(peer_oct)])


def main():
    """Main function"""

    # configure syslog
    syslog.openlog('heartbeatMonitor', 0, syslog.LOG_LOCAL4)

    args = parse_cmd_line()
    if not DEBUG:
        syslog.setlogmask(syslog.LOG_UPTO(syslog.LOG_INFO))

    CONFIG = parse_config(args.config)

    global MAIL
    MAIL = mail(CONFIG['email'])

    # Check cmd line options
    if CONFIG['timeout'] < CONFIG['interval']:
        log('Timeout must be higher than the heartbeat interval.', error=True)

    # configure eAPI
    CONFIG['eapi']['switch'] = Server(CONFIG['eapi']['url'])
    wait_for_eapi(CONFIG['eapi']['switch'])
    log('Local eAPI is enabled...', level='DEBUG')

    if CONFIG['peer']['url']:
        CONFIG['peer']['switch'] = Server(CONFIG['peer']['url'])
        wait_for_eapi(CONFIG['peer']['switch'])
        log('Peer eAPI is enabled...', level='DEBUG')

    log('Testing path on startup...', email=True,
        subject='Heartbeats starting')

    # Determine peer addresses if not pre-configured
    if not CONFIG.get('probe_dst_address1'):
        CONFIG['probe_dst_address1'] = get_peer_addr(CONFIG,
                                                     CONFIG['interface1'])
    if not CONFIG.get('probe_dst_address2'):
        CONFIG['probe_dst_address2'] = get_peer_addr(CONFIG,
                                                     CONFIG['interface2'])

    # setup to monitor both the A-side and B-side paths..
    devices = []
    devices.append(Heartbeat(CONFIG['probe_dst_address1'],
                             interface=CONFIG['interface1'],
                             timeout=CONFIG['timeout']))
    devices.append(Heartbeat(CONFIG['probe_dst_address2'],
                             interface=CONFIG['interface2'],
                             timeout=CONFIG['timeout']))
    for device in devices:
        device.eapi = CONFIG['eapi']
        device.peer = CONFIG['peer']
        device.warn_threshold = CONFIG['alert_threshold']
        device.fail_threshold = CONFIG['failure_threshold']
        device.alert_holddown = CONFIG['alert_holddown']
        device.interface1 = CONFIG['interface1']
        device.interface2 = CONFIG['interface2']
        device.status = Status()
    # Starting up the link

    while True:

        try:
            for device in devices:
                device.do_health_check()
                device.status.runAll([device])
            time.sleep(CONFIG['interval'])
        except KeyboardInterrupt:
            log('Exiting main loop by user interrupt (^C)',
                email=True, subject='Heartbeats manually cancelled')
            raise

    for device in devices:
        device.on_shutdown()

if __name__ == '__main__':
    setProcName('hbm')

    try:
        main()
    except KeyboardInterrupt:
        log('Exiting by user interrupt (^C)')
    except Exception, e:
        log('Heartbeat monitor failed: %s (%s)' %
            (e, traceback.format_exc()), error=True)
