#!/usr/bin/env python3
#
# Copyright (C) 2018-2020 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import jinja2
import ipaddress

from copy import deepcopy

from vyos.config import Config
from vyos import ConfigError

config_file = r'/etc/ntp.conf'

# Please be careful if you edit the template.
config_tmpl = """
### Autogenerated by ntp.py ###

#
# Non-configurable defaults
#
driftfile /var/lib/ntp/ntp.drift
# By default, only allow ntpd to query time sources, ignore any incoming requests
restrict default noquery nopeer notrap nomodify
# Local users have unrestricted access, allowing reconfiguration via ntpdc
restrict 127.0.0.1
restrict -6 ::1

#
# Configurable section
#

{% if servers -%}
{% for s in servers -%}
# Server configuration for: {{ s.name }}
server {{ s.name }} iburst {{ s.options | join(" ") }}
{% endfor -%}
{% endif %}

{% if allowed_networks -%}
{% for n in allowed_networks -%}
# Client configuration for network: {{ n.network }}
restrict {{ n.address }} mask {{ n.netmask }} nomodify notrap nopeer

{% endfor -%}
{% endif %}

{% if listen_address -%}
# NTP should listen on configured addresses only
interface ignore wildcard
{% for a in listen_address -%}
interface listen {{ a }}
{% endfor -%}
{% endif %}

"""

default_config_data = {
    'servers': [],
    'allowed_networks': [],
    'listen_address': []
}

def get_config():
    ntp = deepcopy(default_config_data)
    conf = Config()
    if not conf.exists('system ntp'):
        return None
    else:
        conf.set_level('system ntp')

    if conf.exists('allow-clients address'):
        networks = conf.return_values('allow-clients address')
        for n in networks:
            addr = ipaddress.ip_network(n)
            net = {
                "network" : n,
                "address" : addr.network_address,
                "netmask" : addr.netmask
            }

            ntp['allowed_networks'].append(net)

    if conf.exists('listen-address'):
        ntp['listen_address'] = conf.return_values('listen-address')

    if conf.exists('server'):
        for node in conf.list_nodes('server'):
            options = []
            server = {
                "name": node,
                "options": []
            }
            if conf.exists('server {0} noselect'.format(node)):
                options.append('noselect')
            if conf.exists('server {0} preempt'.format(node)):
                options.append('preempt')
            if conf.exists('server {0} prefer'.format(node)):
                options.append('prefer')

            server['options'] = options
            ntp['servers'].append(server)

    return ntp

def verify(ntp):
    # bail out early - looks like removal from running config
    if ntp is None:
        return None

    # Configuring allowed clients without a server makes no sense
    if len(ntp['allowed_networks']) and not len(ntp['servers']):
        raise ConfigError('NTP server not configured')

    for n in ntp['allowed_networks']:
        try:
            addr = ipaddress.ip_network( n['network'] )
            break
        except ValueError:
            raise ConfigError("{0} does not appear to be a valid IPv4 or IPv6 network, check host bits!".format(n['network']))

    return None

def generate(ntp):
    # bail out early - looks like removal from running config
    if ntp is None:
        return None

    tmpl = jinja2.Template(config_tmpl)
    config_text = tmpl.render(ntp)
    with open(config_file, 'w') as f:
        f.write(config_text)

    return None

def apply(ntp):
    if ntp is not None:
        os.system('sudo systemctl restart ntp.service')
    else:
        # NTP support is removed in the commit
        os.system('sudo systemctl stop ntp.service')
        os.unlink(config_file)

    return None

if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        sys.exit(1)
