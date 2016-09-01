%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:    intelligent-bypass-l3
Version: Replaced_by_make
Release: 1%{?dist}
Summary: Bypasses a failed device when layer-3 heartbeats fail.
Source:  %{name}-%{version}-%{release}.tar.gz
Group:   Applications/Internet
License: BSD-3-Clause
URL:     http://www.arista.com

%global flash /mnt/flash
%global _sysconfdir /persist/sys

BuildArch: noarch
Requires:  python2
Requires:  Eos-release

%description
Intelligent bypass (Layer-3) consists of a pair of processes to monitor the
status of a 3rd-party security device.  Two methods are used.  When traffic is
diverted through the device via BGP, a BFD monitoring script will ensure that,
if BFD detects a failure, the local link and the corresponding link on a peer
switch will be shutdown.  This ensures that traffic may continue and not
auto-revert (BFD fall-back) until an operations team can confirm the device is
properly returned to service.  The second portion of intelligent bypass sends a
layer-3 heartbeat probe through the security device to the BGP peer address on
the other side.  If the round-trip time (RTT) of that traffic increases beyond
an alert threshold, syslog and email alerts will be generated.   In the event
that the RTT increases past the failure threshold for 3 consecutive tries, then
the local and peer ports will be shutdown and notifications sent.

A pester feature will repeat the failure status messages (syslog + email) until
the process is stopped.

Configuraion: /persist/sys/bfd_int_sync.ini
Service management: /mnt/flash/hbm_service --help
USAGE:
    hbm_service <start|status|stop|start_hbm|stop_hbm|start_bfdsync|stop_bfdsync>

Setup aliases for Operation staff:

Arista(config)#
alias hbm_status    bash /mnt/flash/hbm_service status
alias ips_mon       bash /mnt/flash/hbm_service
alias start_all     bash /mnt/flash/hbm_service start
alias start_bfdsync bash /mnt/flash/hbm_service start_bfdsync
alias start_hbm     bash /mnt/flash/hbm_service start_hbm
alias stop_all      bash /mnt/flash/hbm_service stop
alias stop_bfdsync  bash /mnt/flash/hbm_service stop_bfdsync
alias stop_hbm      bash /mnt/flash/hbm_service stop_hbm

Configure the service to start on-boot.  This method enables network staff to
easily see if this service is configured on this device:

Arista(config)#event-handler hbm
Arista(config-event-handler-hbm)#action bash /mnt/flash/hbm_service start
Arista(config-event-handler-hbm)#delay 300
Arista(config-event-handler-hbm)#trigger on-boot
Arista(config-event-handler-hbm)

%prep
%setup -q -n %{name}-%{version}

%install
%{__install} -m 0644 -D bfd_int_sync.ini %{buildroot}%{_sysconfdir}/bfd_int_sync.ini
%{__install} -m 0755 -D bfd_int_sync.py %{buildroot}%{_bindir}/bfd_int_sync.py
%{__install} -m 0755 -D hbm.py %{buildroot}%{_bindir}/hbm.py
%{__install} -m 0755 -D hbm_service %{buildroot}/%{_bindir}/hbm_service

%clean
rm -rf %{buildroot}

%post
# 1 - Perform tasks related to initial install
# 2 - Perform tasks related to upgrade (existing to new one)
if [ $1 -eq 1 ]; then
    #if [ -d "%{sysdbprofile_root}" ]; then
    #    %{__cp} %{igmpsrv_root}/SysdbProfiles/IgmpSnoopingSrv %{sysdbprofile_root}/IgmpSnoopingSrv
    #fi
fi
exit 0

# When the Cli package is available, install the daemon config command
%triggerin -- intelligent-bypass-l3
FastCli -p 15 -c "configure
daemon %{name}
exec /usr/bin/uwsgi --ini=/etc/uwsgi/igmpsnoopingsrv_wsgi.ini
heartbeat 60
no shutdown
end"
exit 0

%triggerun -- intelligent-bypass-l3
# $1 stores the number of versions of this RPM that will be installed after
#   this uninstall completes.
# $2 stores the number of versions of the target RPM that will be installed
#   after this uninstall completes.
if [ $1 -eq 0 -a $2 -gt 0 ] ; then
    FastCli -p 15 -c "configure
    daemon %{name}
    shutdown
    no daemon %{name}
    end"
    service nginx restart
fi
exit 0

%preun
# 0 - Perform tasks related to uninstallation
# 1 - Perform tasks related to upgrade
if [ $1 -eq 0 ]; then
    #if [ -f "%{sysdbprofile_root}/IgmpSnoopingSrv" ]; then
    #    %{__rm} %{sysdbprofile_root}/IgmpSnoopingSrv
    #fi
fi
exit 0


%files
%defattr(-,root,eosadmin,-)
%config(noreplace) %attr(644,root,root) %{_sysconfdir}/bfd_int_sync.ini
%{_bindir}/bfd_int_sync.py
%{_bindir}/hbm.py
%{_bindir}/hbm_service
%exclude %{_bindir}/*.py[co]

%changelog
* Mon Aug 29 2016 Jere Julian<jere@arista.com> - %{version}-1
- Initial release RPM packaging.
