#!/usr/bin/env python
# Copyright (c) 2016, Arista Networks, Inc. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# Neither the name of Arista Networks nor the names of its contributors may be
# used to endorse or promote products derived from this software without
# specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL ARISTA NETWORKS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
"""Upon notification of a BFD failure on the specified peer, shutdown the
appropriate interface to prevent automatic fall-back and send appropriate
notices.

Sample Syslog messages:
ti254...15:20:05#sh log last 20 min
Feb 11 15:20:00 ti254 Rib: %BGP-BFD-STATE-CHANGE: peer 192.0.3.1 (AS 10000) Up to Down  # noqa
Feb 11 15:20:00 ti254 Rib: %BGP-3-NOTIFICATION: sent to neighbor 192.0.3.1 (AS 10000) 6/6 (Cease/other configuration change) 0 bytes  # noqa
Feb 11 15:20:00 ti254 Rib: %BGP-5-ADJCHANGE: peer 192.0.3.1 (AS 10000) old state Established event Stop new state Idle  # noqa
Feb 11 15:20:00 ti254 Bfd: %BFD-5-STATE_CHANGE: peer 192.0.3.1 changed state from Up to Down  # noqa

Start this daemon with the following EOS config:

    bash# ssh admin@myAristaSwitch
    switch> enable
    switch# configure
    switch(config)# daemon bgpMonitor
    switch(config-daemon-bgpMonitor)# exec /mnt/flash/bfd_int_sync.py
    switch(config-daemon-bgpMonitor)# option interface value Ethernet52
    switch(config-daemon-bgpMonitor)# no shutdown

Monitor daemon status with:

    switch# show daemon
    Agent: bgpMonitor (running)
    No configuration options stored.

    Status:
    Data           Value
    -------------- ---------------------------
"""

import argparse
import ConfigParser
from jsonrpclib import Server
import os
import time
from pprint import pprint, pformat
import smtplib
import sys
import syslog
from ctypes import cdll, byref, create_string_buffer

DEBUG = False   # pylint: disable=C0103
CONFIG = {}   # pylint: disable=C0103
SNMP = {}   # pylint: disable=C0103
EMAIL = {}   # pylint: disable=C0103


def setProcName(newname):
    """Configure the process name so this may easily be identified in ps

    Args:
        newname (str): The desired processname
    """
    libc = cdll.LoadLibrary('libc.so.6')
    buff = create_string_buffer(len(newname) + 1)
    buff.value = newname
    libc.prctl(15, byref(buff), 0, 0, 0)


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
                        default='/persist/sys/hbm.ini',
                        help='Configuration file to load' +
                        ' (Default: /persist/sys/hbm.ini)')

    parser.add_argument('--debug',
                        action='store_true',
                        default=False,
                        help='Send debug information to the console')

    parser.add_argument('--interface',
                        type=str,
                        action='store',
                        default=None,
                        help='EOS interface name to monitor')

    parser.add_argument('--logfile',
                        type=str,
                        action='store',
                        default='/var/log/eos',
                        help='The path to the log to watch')

    args = parser.parse_args()

    global DEBUG
    if args.debug:
        DEBUG = True

    if DEBUG:
        print "CLI Args: {0}\n".format(pformat(args))

    return args


def log(msg, level='INFO', error=False, subject=''):
    """Logging facility setup.

    args:
        msg (str): The message to log.
        level (str): The priority level for the message. (Default: INFO)
                    See :mod:`syslog` for more options.
                    EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG
        error (bool): Flag if this is an error condition.
        subject (str): Optional text appended to the default email subject
                       from the config file.
    """

    if DEBUG:
        print "{0} ({1}) {2}".format(os.path.basename(sys.argv[0]), level, msg)

    if error:
        level = "ERR"
        print "ERROR: {0} ({1}) {2}".format(os.path.basename(sys.argv[0]),
                                            level, msg)

    priority = ''.join(["syslog.LOG_", level])
    syslog.syslog(eval(priority), msg)

    if EMAIL.get('enabled'):
        if subject is not '':
            subject = ': ' + subject

        message = """From: {}
To: {}
Subject: {}

{}
""".format(EMAIL['from'],
           ', '.join(EMAIL['to']),
           EMAIL['subject'] + subject, msg)

        if DEBUG:
            pprint(EMAIL)
        try:
            smtp_obj = smtplib.SMTP(EMAIL['mailserver'],
                                    EMAIL['mailserverport'])
            if EMAIL['starttls']:
                smtp_obj.starttls()
            if EMAIL['login']:
                smtp_obj.login(EMAIL['username'], EMAIL['password'])
            smtp_obj.sendmail(EMAIL['from'], EMAIL['to'], message)
            smtp_obj.quit()
            if DEBUG:
                print "Successfully sent email"
        except smtplib.SMTPException:
            print "Error: unable to send email"
        except:
            print "Error: SMTP error connecting to mailserver"


def parse_config(filename):
    """ Read the config file (Default: /persist/sys/rphm.conf)

    Read in settings from the config file.  The default:
        /persist/sys/rphm.conf, is set in parse_cli().

    Args:
        filename (str): The path to the config file.

    Returns:
        dict: A dictionary of configuration and switch definitions.

    """

    if not filename:
        filename = "/persist/sys/hbm.conf"

    defaults = {
        'hostname': 'localhost',
        'protocol': 'https',
        'port': '443',
        'username': 'arista',
        'password': 'arista',
        'url': '%(protocol)s://%(username)s:%(password)s@%(hostname)s:%(port)s'
               '/command-api',
    }
    os.path.isfile(filename)
    if not os.access(filename, os.R_OK):
        log("Unable to read config file {0}".format(filename))
        raise IOError("Unable to read config file {0}".format(filename))

    config = ConfigParser.SafeConfigParser(defaults)
    config.read(filename)

    global EMAIL
    try:
        config.options('email')
    except ConfigParser.NoSectionError, err:
        log("Required [email] section missing from config file {0}: ({1})".
            format(filename, err))
        raise IOError(
            "Required [email] section missing from config file {0}: ({1})".
            format(filename, err))
    EMAIL['enabled'] = config.getboolean('email', 'enabled')
    EMAIL['starttls'] = config.getboolean('email', 'starttls')
    EMAIL['login'] = config.getboolean('email', 'login')
    EMAIL['mailserver'] = config.get('email', 'mailserver')
    EMAIL['mailserverport'] = config.getint('email', 'mailserverport')
    EMAIL['from'] = config.get('email', 'from')
    EMAIL['subject'] = config.get('email', 'subject')
    recipients = config.get('email', 'to')
    EMAIL['to'] = []
    for line in recipients.split('\n'):
        for recipient in line.split(","):
            recipient = recipient.strip('\t')
            EMAIL['to'].append(recipient)
    if DEBUG:
        print "EMAIL: {0}\n".format(pformat(EMAIL))

    global CONFIG
    CONFIG['hostname'] = config.get('eapi', 'hostname')
    CONFIG['protocol'] = config.get('eapi', 'protocol')
    CONFIG['port'] = config.get('eapi', 'port')
    CONFIG['username'] = config.get('eapi', 'username')
    CONFIG['password'] = config.get('eapi', 'password')
    CONFIG['url'] = config.get('eapi', 'url')
    CONFIG['starting_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'starting_config'))
    CONFIG['ok_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'ok_config'))
    CONFIG['fail_config'] = \
        conf_string_to_list(config.get('eapi',
                                       'fail_config'))

    CONFIG['alert_holddown'] = config.getint('General', 'alert_holddown')
    CONFIG['interface1'] = config.get('General', 'interface1')
    CONFIG['interface2'] = config.get('General', 'interface2')

    if 'peer_eapi' in config.sections():
        CONFIG['peer_hostname'] = config.get('peer_eapi', 'hostname')
        CONFIG['peer_protocol'] = config.get('peer_eapi', 'protocol')
        CONFIG['peer_port'] = config.get('peer_eapi', 'port')
        CONFIG['peer_username'] = config.get('peer_eapi', 'username')
        CONFIG['peer_password'] = config.get('peer_eapi', 'password')
        CONFIG['peer_url'] = config.get('peer_eapi', 'url')
        CONFIG['peer_starting_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'starting_config'))
        CONFIG['peer_ok_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'ok_config'))
        CONFIG['peer_fail_config'] = \
            conf_string_to_list(config.get('peer_eapi',
                                           'fail_config'))

    if DEBUG:
        print "CONFIG: {0}\n".format(pformat(CONFIG))


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


def get_peer(interface, routes):
    """Lookup the BGP peer associated with a given interface

    Args:
        interface (str): Interface name to find
        routes (list): an eAPI structure containing the installed ip routes

    Returns:
        str: the IP address of the peer on the desired interface
    """

    peer = None
    for route in routes[0]['vrfs']['default']['routes']:
        for via in routes[0]['vrfs']['default']['routes'][route]['vias']:
            if interface in via.values():
                thispeer = via.get('nexthopAddr')
                if thispeer is not None:
                    peer = thispeer
    return peer


def main():
    """Ensure the selected interface is up and that there is a BGP peer
       connected via that interface.  Once the interface and peer are up
       monitor syslog for any BGP BFD peer changes.  Upon a change in the
       peer, shutdown the selected interface to prevent automatic recovery
    """

    setProcName('bfd_int_sync')

    args = parse_cmd_line()
    parse_config(args.config)
    switch = Server(CONFIG['url'])
    peer_switch = Server(CONFIG['peer_url'])
    interfaces = []
    interfaces.append(CONFIG['interface1'])
    interfaces.append(CONFIG['interface2'])
    log("Checking interfaces {} and {}".format(CONFIG['interface1'],
                                               CONFIG['interface2']),
        subject='BFD starting')

    switch.runCmds(1, CONFIG['starting_config'])
    if CONFIG['peer_url']:
        peer_switch.runCmds(1, CONFIG['peer_starting_config'])

    link_up = False
    while link_up is not True:
        for interface in interfaces:
            response = switch.runCmds(1, ['show interfaces {} '
                                          'status'.format(interface)])
            interface_stat = response[0]['interfaceStatuses'][interface]
            if interface_stat['linkStatus'] != 'connected':
                log("Interface is shutdown.  Please 'no shutdown' interface {}"
                    " to continue.".format(interface), level='WARNING')
            else:
                if interface_stat['lineProtocolStatus'] == 'up':
                    link_up = True
                    log("Interface {} is up".format(interface), level='DEBUG')
                else:
                    log("Interface Protocol is not up.  Please check interface"
                        " {} to continue.".format(interface), level='WARNING')
            if link_up is not True:
                log("Waiting for interface {} to come up...".format(interface),
                    level='WARNING')
                time.sleep(5)

    peer1 = None
    peer2 = None
    while peer1 is None or peer2 is None:
        routes = switch.runCmds(1, ['show ip route'])
        peer1 = get_peer(interfaces[0], routes)
        peer2 = get_peer(interfaces[1], routes)
        if peer1 is None or peer2 is None:
            log("Waiting for routes to come up on interfaces {} and {}.".
                format(interfaces[0], interfaces[1]), level='WARNING')
            time.sleep(5)

    switch.runCmds(1, CONFIG['ok_config'])
    if CONFIG['peer_url']:
        peer_switch.runCmds(1, CONFIG['peer_ok_config'])

    log("Watching interface " + interfaces[0] + " (peer: " + peer1 + ") and "
        "interface " + interfaces[1] + " (peer: " + peer2 + ")",
        subject="BFD Running")

    current = open(args.logfile, 'r')
    curr_inode = os.fstat(current.fileno()).st_ino
    current.seek(0, 2)  # Go to the end of the file

    running = True
    while running is True:
        line = None
        while True:
            line = current.readline()
            if line == "":
                continue
            # Look for lines like:
            # Rib: %BGP-BFD-STATE-CHANGE: peer 192.0.3.1 (AS 10000) Up to Down
            if 'BGP-BFD-STATE-CHANGE' not in line:
                continue
            if peer1 in line:
                running = False
                peer = peer1
                interface = interfaces[0]
            if peer2 in line:
                running = False
                peer = peer2
                interface = interfaces[1]
            if running is False:
                log(line, level='DEBUG')
                log("BFD State Change for peer {}, "
                    "(interface {})".format(peer, interface),
                    level='DEBUG')
                switch.runCmds(1, CONFIG['fail_config'])
                if CONFIG['peer_url']:
                    peer_switch.runCmds(1, CONFIG['peer_fail_config'])
                log("...WARNING: BFD triggered an automated shutdown of "
                    "interface {}".format(interface), level='WARNING',
                    subject="BFD Failed")

                if CONFIG['alert_holddown'] > 0:
                    # Send alerts on a regular interval until manually stopped.
                    log("BFD triggered automatic shutdown of {}.".
                        format(interface),
                        subject="BFD Failed")
                    time.sleep(CONFIG['alert_holddown'])
                break

        try:
            if os.stat(args.logfile).st_ino != curr_inode:
                newfile = open(args.logfile, 'r')
                current.close()
                current = newfile
                # Don't seek here or we could miss logs written between the
                #   last run and us opening the new file.
                curr_inode = os.fstat(current.fileno()).st_ino
                continue
        except IOError:
            pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Manually shutdown",
            subject="Manually shutdown")
        pass
