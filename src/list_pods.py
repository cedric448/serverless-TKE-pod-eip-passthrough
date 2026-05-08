#!/usr/bin/env python3
"""
List all Pods in the eip-pods namespace.

Usage:
    python list_pods.py

Output columns:
    NAME | STATUS | POD IP | NODE | CREATED | EIP ID | EIP IP
"""
import sys

from kubernetes.client.rest import ApiException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.vpc.v20170312 import models as vpc_models

import config


def query_eip_addresses(eip_ids):
    """Query EIP public IPs by their IDs. Returns dict {eip_id: public_ip}."""
    if not eip_ids:
        return {}
    try:
        vpc = config.get_vpc_client()
        req = vpc_models.DescribeAddressesRequest()
        req.AddressIds = eip_ids
        resp = vpc.DescribeAddresses(req)
        return {
            addr.AddressId: addr.AddressIp
            for addr in (resp.AddressSet or [])
        }
    except TencentCloudSDKException:
        return {}


def main():
    try:
        api = config.get_k8s_client()
    except EnvironmentError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    try:
        pods = api.list_namespaced_pod(namespace=config.NAMESPACE)
    except ApiException as e:
        if e.status == 404:
            print(f"[INFO] Namespace '{config.NAMESPACE}' not found. No pods yet.")
            return
        print(f"[ERROR] Failed to list pods: {e}", file=sys.stderr)
        sys.exit(1)

    if not pods.items:
        print(f"[INFO] No pods found in namespace '{config.NAMESPACE}'.")
        return

    # Collect all EIP IDs to batch query
    pod_eip_map = {}
    for pod in pods.items:
        annotations = pod.metadata.annotations or {}
        eip_id = annotations.get("tke.cloud.tencent.com/eip-id", "")
        if eip_id:
            pod_eip_map[pod.metadata.name] = eip_id

    # Batch query EIP public IPs via VPC SDK
    eip_ip_map = query_eip_addresses(list(pod_eip_map.values()))

    col_name = 25
    col_status = 10
    col_podip = 16
    col_node = 36
    col_created = 20
    col_eipid = 16
    header = (
        f"{'NAME':<{col_name}} {'STATUS':<{col_status}} {'POD IP':<{col_podip}}"
        f" {'NODE':<{col_node}} {'CREATED':<{col_created}}"
        f" {'EIP ID':<{col_eipid}} EIP IP"
    )
    print(header)
    print("-" * len(header))

    for pod in pods.items:
        name = pod.metadata.name or "-"
        phase = (pod.status.phase or "Unknown")
        pod_ip = (pod.status.pod_ip or "-")
        node = (pod.spec.node_name or "-")
        created = (
            pod.metadata.creation_timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if pod.metadata.creation_timestamp
            else "-"
        )
        annotations = pod.metadata.annotations or {}
        eip_id = annotations.get("tke.cloud.tencent.com/eip-id", "-")
        eip_ip = eip_ip_map.get(eip_id, "-")
        print(
            f"{name:<{col_name}} {phase:<{col_status}} {pod_ip:<{col_podip}}"
            f" {node:<{col_node}} {created:<{col_created}}"
            f" {eip_id:<{col_eipid}} {eip_ip}"
        )


if __name__ == "__main__":
    main()
