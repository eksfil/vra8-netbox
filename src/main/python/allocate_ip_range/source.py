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
import os
import ipaddress
from requests.packages import urllib3


def handler(context, inputs):

    ipam = IPAM(context, inputs)
    IPAM.do_allocate_ip = do_allocate_ip

    return ipam.allocate_ip()


def do_allocate_ip(self, auth_credentials, cert):
    username = auth_credentials["privateKeyId"]  # not needed for NetBox, but required for vRA IPAM plugin
    token = auth_credentials["privateKey"]

    allocation_result = []
    try:
        resource = self.inputs["resourceInfo"]
        for allocation in self.inputs["ipAllocations"]:
            allocation_result.append(
                allocate(
                    resource,
                    auth_credentials,
                    allocation,
                    self.context,
                    self.inputs["endpoint"],
                )
            )
    except Exception as e:
        try:
            rollback(allocation_result, auth_credentials, self.inputs["endpoint"])
        except Exception as rollback_e:
            logging.error(
                f"Error during rollback of allocation result {str(allocation_result)}"
            )
            logging.error(rollback_e)
        raise e

    assert len(allocation_result) > 0
    return {"ipAllocations": allocation_result}


def allocate(resource, auth_credentials, allocation, context, endpoint):

    last_error = None
    for range_id in allocation["ipRangeIds"]:

        logging.info(f"Allocating from range {range_id}")
        try:
            logging.warning(str(range_id))
            return allocate_in_range(
                range_id, auth_credentials, resource, allocation, context, endpoint
            )
        except Exception as e:
            last_error = e
            logging.error(f"Failed to allocate from range {range_id}: {str(e)}")

    logging.error("No more ranges. Raising last error")
    raise last_error


def allocate_in_range(range_id, auth_credentials, resource, allocation, context, endpoint):

    try:
        ignore_ssl = str(endpoint["endpointProperties"]["ignore_ssl"])
        if ignore_ssl == "true":
            urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)
            verify = False
        else:
            verify = True
    except Exception as e:
        raise e

    token = auth_credentials["privateKey"]
    netbox_url = endpoint["endpointProperties"]["hostName"]
    netbox_object = endpoint["endpointProperties"]["netboxObject"]
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    ips = []

    if netbox_object == "ip-ranges":
        response = requests.get(
            f"{netbox_url}/api/ipam/ip-ranges/{str(range_id)}/",
            headers=headers,
            verify=verify,
        )
        r = response.json()
    else:
        response = requests.get(
            f"{netbox_url}/api/ipam/prefixes/{str(range_id)}/",
            headers=headers,
            verify=verify,
        )
        r = response.json()

    if str(r["id"]) != str(range_id):  # ensure we have the correct prefix
        p_error =
