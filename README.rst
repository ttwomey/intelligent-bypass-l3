============================
Intelligent-Bypass (Layer-3)
============================

Solution Overview
-----------------
Place the SSL/SourceFire parallel to the existing links between the Juniper SRX and Arista 7500, then use BGP to direct the desired traffic through the Sourcefire with a higher preference than the main links.  In the event of a failure, BGP will provide a bypass route for the traffic.  Then 2 mechanisms can be deployed to monitor the health of the Sourcefire links: BGP BFD and a health probe.  Two utilities will be used on the Arista 7500s.  The first, will monitor route changes for the specific BGP peer available through the Sourcefire.  When BFD removes that route, it will disable the local interface and peer-7500's interfaces to the Sourcefire to prevent fall-back and send appropriate notifications.  The second tool will send pings from the 7500, through the SourceFire link to the BGP peer address on the SRX, monitoring the round trip time (RTT).  When the RTT increases above a configurable warning threshold, syslog, and optional email, alerts will be generated. When the RTT increases above a configurable failure threshold, the local and peer interfaces to the Sourcefire will be disabled and appropriate notifications sent.

Components
----------

Route Monitor
~~~~~~~~~~~~~
On startup, the route monitor watches the routing table for a peer to come up on the configured interface.   Once up, it watches for a BFD state change on that route.  When a BFD state change is found, the local and peer failure_config will be applied to the local and peer 7500 switches.

Heartbeat Monitor
~~~~~~~~~~~~~~~~~
On startup, the heartbeat monitor will check the configured interface to be monitored, get the configured ip address, then use the peer ip address (assuming a /30 link) as the destination for pings.  Pings will be sent, the average RTT will be checked, then the script will pause for a configured number of seconds before restarting the loop. Three consecutive successfull ping attempts are required to transition to the Up state.  If the RTT is above a warning threshold, alerts will be sent via syslog and, optionally email.  If the failure threshold is surpassed 3 times in a row, the failure_config will be applied on both the local and peer switch..

Installation
------------
Install the extension package::
  Arista#copy http://<host>/intelligent-bypass.swix extensions:
  Arista#extension intelligent-bypass.swix
  Arista#sh extensions 
  Name                                       Version/Release           Status extension
  ------------------------------------------ ------------------------- ------ ----
  EosSdk-1.7.0-4.15.2F.i686.rpm              1.7.0/2692966.gaevanseoss A, I      1

  A: available | NA: not available | I: installed | NI: not installed | F: forced

  Arista#copy installed-extensions boot-extensions

Configuration
-------------
The default configuration file is in /mnt/flash/bfd_int_sync.ini (flash:bfd_int_sync.ini) This may be overridden with a command-line option: '--config </path/to/bfd_int_sync.ini>'.   This single file applies to both monitoring scripts.

::
  Arista#bash cat /mnt/flash/bfd_int_sync.ini

  ###############################################################################
  #
  [General]
  # Seconds to pause between probes
  interval = 5

  # Alert holddown timer.  Limit consecutive alerts to one every <n> seconds.
  alert_holddown = 10

  # Send alerts when Ping RTT is greater than
  alert_threshold = 13

  # Fail-over and alert when Ping RTT is greater than
  failure_threshold = 15

  # The interface to monitor
  interface1 = Ethernet2
  interface2 = Ethernet2

  # The IP address on the opposite side of the device being monitored:
  #  If not set, assume a /30 and use the opposite address from the
  #  local interface.
  #probe_dst_address1 = 192.0.3.1
  #probe_dst_address2 = 192.0.4.1

  [eapi]
  # Configure eAPI settings for the switch on which we're running
  hostname = localhost
  port = 80
  protocol= http
  username = hbmuser
  password = icanttellyou
  #url = https://arista:arista@localhost:443/command-api

  starting_config = enable,
              configure,
              interface Ethernet4,
              description HBM: Starting,
              no shutdown

  ok_config = enable,
              configure,
              interface Ethernet4,
              description HBM: OK

  fail_config = enable,
                configure,
                interface Ethernet4,
                description HBM: Fail

                #shutdown

  shutdown_config = enable,
                configure,
                interface Ethernet4,
                description HBM: Disabled

  [peer_eapi]
  # Configure eAPI settings for our peer switch so we can configure ports there
  hostname = 192.0.2.1
  port = 80
  protocol= http
  username = hbmuser
  password = icanttellyou
  #url = https://arista:arista@localhost:443/command-api

  starting_config = enable,
              configure,
              interface Ethernet4,
              description HBM: Starting,
              no shutdown

  ok_config = enable,
              configure,
              interface Ethernet4,
              description HBM: OK

  fail_config = enable,
                configure,
                interface Ethernet4,
                description HBM: Fail

              # shutdown

  shutdown_config = enable,
                configure,
                interface Ethernet4,
                description HBM: Disabled

  [email]
  # If enabled, below, configure the necessary settings to send email alerts
  enabled = yes
  from = Arista 7500-A <veos01@example.com>
  to = NOC <vagrant@example.com>
  subject = Arista BFD Monitor script
  mailserver = example.com
  mailserverport = 25
  starttls = no
  login = no
  username = 
  password = 

Automatic startup
-----------------
On-switch EOS config to ensure scripts start automatically on reload::

  Arista(config)#event-handler hbm
  Arista(config-event-handler-hbm)#action bash /mnt/flash/hbm.py
  Arista(config-event-handler-hbm)#delay 300
  Arista(config-event-handler-hbm)#trigger on-boot
  Arista(config-event-handler-hbm)#exit

  Arista(config)#event-handler bfd_sync
  Arista(config-event-handler-bfd_sync)#action bash /mnt/flash/bfd_int_sync.py
  Arista(config-event-handler-bfd_sync)#delay 300
  Arista(config-event-handler-bfd_sync)#trigger on-boot
  Arista(config-event-handler-bfd_sync)#end

Operation
---------
EOS config aliases may be created to simplify starting/stopping of the services::

  Arista(config)#
  alias hbm_status    bash /mnt/flash/hbm_service status
  alias ips_mon       bash /mnt/flash/hbm_service
  alias start_all     bash /mnt/flash/hbm_service start
  alias start_bfdsync bash /mnt/flash/hbm_service start_bfdsync
  alias start_hbm     bash /mnt/flash/hbm_service start_hbm
  alias stop_all      bash /mnt/flash/hbm_service stop
  alias stop_bfdsync  bash /mnt/flash/hbm_service stop_bfdsync
  alias stop_hbm      bash /mnt/flash/hbm_service stop_hbm


Verify monitor scripts are running
----------------------------------

::

  Arista#hbm_status
  7931 hbm
  8633 bfd_int_sync
  Arista#stop_all
  Arista#hbm_status
   Not running


Planned Maintenance
-------------------
Prior to scheduled maintenance which could be expected to affect any part of the monitored paths, hbm and bfd_int_sync should be stopped on both peer 7500 switches.   Once maintenance is completed, the monitoring services should be re-enabled::

  Arista#stop_all
  ... perform maintenance activities
  Arista#start_all

Testing
-------

::

  bash /mnt/flash/hbm_service
  USAGE:
      hbm_service <start|status|stop|start_hbm|stop_hbm|start_bfdsync|stop_bfdsync>

  bash /mnt/flash/hbm.py --debug
  usage: hbm.py [-h] [--config CONFIG] [--debug] [--logfile LOGFILE]


  bash /mnt/flash/hbm.py --config /mnt/flash/bfd_int_sync.ini --debug

  bash /mnt/flash/bfd_int_sync.py --help
  usage: bfd_int_sync.py [-h] [--config CONFIG] [--debug]
                         [--interface INTERFACE] [--logfile LOGFILE]

  bash /mnt/flash/bfd_int_sync.py --config /mnt/flash/bfd_int_sync.ini --debug
