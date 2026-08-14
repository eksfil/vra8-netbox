"""
Copyright (c) 2020 VMware, Inc.
Modified for NetBox by Ryan Hinson (@rnhinson)
This product is licensed to you under the Apache License, Version 2.0 (the "License").
You may not use this product except in compliance with the License.
This product may include a number of subcomponents with separate copyright notices
and license terms. Your use of these subcomponents is subject to the terms and
conditions of the subcomponent's license, as noted in the LICENSE file.
"""
import requests
from vra_ipam_utils.ipam import IPAM
import logging
from requests.packages import urllib3
import ipaddress


def handler(context, inputs):
    ipam = IPAM(context, inputs)
    IPAM.do_get_ip_ranges = do_get_ip_ranges
    return ipam.get_ip_ranges()


def do_get_ip_ranges(self, auth_credentials, cert):
    try:
        ignore_ssl = str(self.inputs["endpoint"]["endpointProperties"]["ignore_ssl"])
        if ignore_ssl == "true":
            urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)
            verify = False
        else:
            verify = True
    except Exception as e:
        raise e

    netbox_object = self.inputs["endpoint"]["endpointProperties"]["netboxObject"]
    netbox_tag = self.inputs["endpoint"]["endpointProperties"]["netboxTag"]
    netbox_url = self.inputs["endpoint"]["endpointProperties"]["hostName"]
    netbox_site = self.inputs["endpoint"]["endpointProperties"]["netboxSite"]
    username = auth_credentials["privateKeyId"]
    token = auth_credentials["privateKey"]

    logging.info("Collecting ranges")

    headers = {"Authorization": f"Bearer {token}"}

    # IP Range objects in NetBox have no "site" field, so the site filter
    # only applies when querying prefixes. For ip-ranges, tag is the sole scope.
    if netbox_object == "prefixes":
        url = f"{str(netbox_url)}/api/ipam/{str(netbox_object)}/?site={str(netbox_site)}&tag={str(netbox_tag)}"
    else:
        url = f"{str(netbox_url)}/api/ipam/{str(netbox_object)}/?tag={str(netbox_tag)}"

    result_ranges = []

    # Follow pagination until every page has been collected
    while url:
        response = requests.get(url, verify=verify, headers=headers)
        response.raise_for_status()
        payload = response.json()
        r = payload["results"]

        if netbox_object == "prefixes":
            for prefix in r:
                subnet = ipaddress.ip_network(str(prefix["prefix"]))
                network_range = {
                    "id": str(prefix['id']),
                    "name": str(prefix['vlan']['name']),
                    "startIPAddress": str(subnet[4]),
                    "endIPAddress": str(subnet[-4]),
                    "ipVersion": "IPv4",
                    "subnetPrefixLength": str(subnet.prefixlen),
                    "gatewayAddress": str(subnet[1]),
                }
                try:
                    if "domain" in self.inputs["endpoint"]["endpointProperties"]:
                        network_range["domain"] = self.inputs["endpoint"]["endpointProperties"]["domain"]
                    else:
                        logging.info("Domain variable not set. Ignoring.")
                except Exception as e:
                    raise e
                result_ranges.append(network_range)
        else:
            for ip_range in r:
                subnet = (ipaddress.ip_interface(str(ip_range['start_address']))).network
                network_range = {
                    "id": str(ip_range['id']),
                    "name": str(ip_range['display']),
                    "startIPAddress": str(ip_range['start_address'].split('/')[0]),
                    "endIPAddress": str(ip_range['end_address'].split('/')[0]),
                    "ipVersion": str(ip_range['family']['label']),
                    "subnetPrefixLength": str(subnet.prefixlen),
                    "gatewayAddress": str(subnet[1]),
                }
                try:
                    if "domain" in self.inputs["endpoint"]["endpointProperties"]:
                        network_range["domain"] = self.inputs["endpoint"]["endpointProperties"]["domain"]
                    else:
                        logging.info("Domain variable not set. Ignoring.")
                except Exception as e:
                    raise e
                result_ranges.append(network_range)

        url = payload.get("next")

    result = {
        "ipRanges": result_ranges
    }
    return result
