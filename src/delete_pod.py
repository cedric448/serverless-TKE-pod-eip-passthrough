#!/usr/bin/env python3
"""
Delete a TKE Supernode Pod and release its EIP.

Usage:
    python delete_pod.py --name <pod-name> --eip-id <eip-xxxxxxxx>

Steps:
  1. Delete the Pod from namespace 'eip-pods'
  2. Release the EIP via Tencent Cloud VPC SDK
"""
import argparse
import sys

from kubernetes.client.rest import ApiException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.vpc.v20170312 import models as vpc_models

import config


def main():
    parser = argparse.ArgumentParser(
        description="Delete a TKE Supernode Pod and release its EIP"
    )
    parser.add_argument("--name", required=True, help="Pod name to delete")
    parser.add_argument(
        "--eip-id", required=True, help="EIP ID to release (e.g. eip-xxxxxxxx)"
    )
    args = parser.parse_args()

    # ── Step 1: Delete Pod ────────────────────────────────────────────────────
    try:
        api = config.get_k8s_client()
    except EnvironmentError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    try:
        api.delete_namespaced_pod(name=args.name, namespace=config.NAMESPACE)
        print(f"[OK] Pod '{args.name}' deleted from namespace '{config.NAMESPACE}'.")
    except ApiException as e:
        if e.status == 404:
            print(f"[WARN] Pod '{args.name}' not found — may already be deleted.")
        else:
            print(f"[ERROR] Failed to delete pod: {e}", file=sys.stderr)
            sys.exit(1)

    # ── Step 2: Release EIP ───────────────────────────────────────────────────
    # EIP may still be in BIND state briefly after pod deletion; retry for up to 60s
    import time
    vpc = config.get_vpc_client()
    max_wait = 60
    interval = 5
    elapsed = 0
    while elapsed <= max_wait:
        try:
            req = vpc_models.ReleaseAddressesRequest()
            req.AddressIds = [args.eip_id]
            resp = vpc.ReleaseAddresses(req)
            print(f"[OK] EIP '{args.eip_id}' released. RequestId: {resp.RequestId}")
            break
        except TencentCloudSDKException as e:
            err_str = str(e)
            if "AddressStatusNotPermit" in err_str and elapsed < max_wait:
                print(f"[INFO] EIP still unbinding, retrying in {interval}s... ({elapsed}s elapsed)")
                time.sleep(interval)
                elapsed += interval
            else:
                print(f"[ERROR] Failed to release EIP '{args.eip_id}': {e}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
