#!/usr/bin/env python
#
# Red Hat Satellite Dynamic Inventory for Ansible
# Copyright 2016 by Fotis Gimian (MIT License)
#
# Set your inventory to point to this script and ensure the script is
# executable.  You'll need an INI file with Satellite details of the following
# style (whereby you may specify one or more Satellite servers):
#
# [satellite]
# base_url = <base-url>
# username = <username>
# password = <password>
#
# You may set the SATELLITE_SETTINGS environment variable to the location of
# this ini file or it will assume satellite.ini by default.
#
# You may target a specific Satellite instance by overriding the
# SATELLITE_INSTANCE environment variable with the name of the instance you're
# interested in.
#
# This script should also function with Foreman, although it hasn't been
# explicitly tested against Foreman.
#
import argparse
from datetime import datetime
import ConfigParser
import json
import os

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# The location of the cached inventory
CACHE_DIR = os.path.join(os.path.expanduser('~'), '.inventory_cache')

# The duration to cache for (in seconds)
CACHE_TIME = 24 * 60 * 60  # 24 hours

# The number of items to retrieve per page from the Satellite API
PER_PAGE = 500


def process_hostgroup_name(hostgroup_name, instance):
    if hostgroup_name is None:
        return None

    if instance is not None:
        hostgroup_name = instance + '/' + hostgroup_name

    return hostgroup_name.replace(' ', '_')


def main():
    # Setup CLI arguments and force the script only to be used with --list
    parser = argparse.ArgumentParser(
        description='Provides Ansible inventory from Red Hat Satellite'
    )
    parser.add_argument('--list', dest='list', action='store_true',
                        required=True,
                        help='list all hosts, hostgroups and their metadata')
    parser.parse_args()

    # Determine the Satellite settings to use
    satellite_settings = os.environ.get('SATELLITE_SETTINGS', 'satellite.ini')
    satellite_instance = os.environ.get('SATELLITE_INSTANCE')

    # Determine the cache filename
    cache_satellite_settings = os.path.basename(satellite_settings)
    if satellite_settings.endswith('.ini'):
        cache_satellite_settings = cache_satellite_settings[:-4]

    if satellite_instance is None:
        cache_satellite_instance = 'all'
    else:
        cache_satellite_instance = satellite_instance.replace(' ', '_').lower()

    cache_path = os.path.join(
        CACHE_DIR,
        cache_satellite_settings + '.' + cache_satellite_instance + '.cache'
    )

    # Read the cached version if possible
    if os.path.isfile(cache_path):
        current_time = datetime.now()
        modified_time = datetime.fromtimestamp(os.path.getmtime(cache_path))

        # If the cache file is still current, we use it instead of reaching
        # for the Satellite API
        if (current_time - modified_time).seconds < CACHE_TIME:
            try:
                with open(cache_path) as cache_fp:
                    inventory = json.load(cache_fp)
                    print json.dumps(inventory, indent=4)
                exit(0)
            except ValueError:
                pass

    # Read Satellite settings
    instances = []
    config = ConfigParser.SafeConfigParser()
    try:
        config.read(satellite_settings)
        if satellite_instance:
            satellite_instances = [satellite_instance]
        else:
            satellite_instances = config.sections()

        for satellite_instance in satellite_instances:
            base_url = config.get(satellite_instance, 'base_url')
            username = config.get(satellite_instance, 'username')
            password = config.get(satellite_instance, 'password')
            instances.append(
                (satellite_instance, base_url, username, password)
            )
    except ConfigParser.Error:
        print (
            'error: unable to find or read all required files from '
            'settings file {satellite_settings}'.format(
                satellite_settings=satellite_settings
            )
        )
        exit(1)

    # Disable urllib3 SSL warnings
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    content_type = 'application/json'

    # Initialise our inventory dict
    inventory = {
        '_meta': {
            'hostvars': {}
        }
    }

    for instance, base_url, username, password in instances:
        # Setup our API with the provided URL and credentials
        session = requests.Session()
        session.auth = (username, password)
        session.verify = False

        try:
            # Obtain hostgroups from Satellite
            page = 1
            while True:
                rv = session.get(
                    base_url + '/api/v2/hostgroups',
                    params={
                        'page': page,
                        'per_page': PER_PAGE
                    },
                    headers={
                        'Accept': content_type,
                        'Content-type': content_type
                    }
                )
                rv.raise_for_status()
                hostgroups = rv.json()['results']
                if not hostgroups:
                    break
                page += 1

                for hostgroup in hostgroups:
                    hostgroup_name = process_hostgroup_name(
                        hostgroup['title'],
                        instance if len(instances) > 1 else None
                    )
                    hostgroup.pop('title')

                    if hostgroup_name not in inventory:
                        inventory[hostgroup_name] = {
                            'hosts': [],
                            'vars': {}
                        }

                    inventory[hostgroup_name]['vars'] = hostgroup

            # Obtain hosts from Satellite
            page = 1
            while True:
                rv = session.get(
                    base_url + '/api/v2/hosts',
                    params={
                        'page': page,
                        'per_page': PER_PAGE
                    },
                    headers={
                        'Accept': content_type,
                        'Content-type': content_type
                    }
                )
                rv.raise_for_status()
                hosts = rv.json()['results']
                if not hosts:
                    break
                page += 1

                for host in hosts:
                    hostgroup_name = process_hostgroup_name(
                        host['hostgroup_name'],
                        instance if len(instances) > 1 else None
                    )
                    hostname = host['name']

                    host.pop('hostgroup_name')
                    host.pop('name')

                    if hostgroup_name not in inventory:
                        inventory[hostgroup_name] = {
                            'hosts': [],
                            'vars': {}
                        }

                    inventory[hostgroup_name]['hosts'].append(hostname)
                    inventory['_meta']['hostvars'][hostname] = host

        except (requests.RequestException, IndexError, ValueError):
            print 'error: unable to obtain host details from Satellite'
            exit(1)
        except KeyboardInterrupt:
            exit(2)

    # Save the result to our cache
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    with open(cache_path, 'w') as cache_fp:
        json.dump(inventory, cache_fp)

    print json.dumps(inventory, indent=4)


if __name__ == '__main__':
    main()
