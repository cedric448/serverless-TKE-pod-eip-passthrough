#!/usr/bin/env python3
"""
Create a TKE Supernode Pod with auto-allocated EIP.

Usage:
    python create_pod.py --name <pod-name> [--arch intel|amd]

The Pod will be created in the 'eip-pods' namespace with:
  - 4 vCPU, 8 GiB RAM
  - EIP auto-allocated by TKE (100 Mbps, pay-per-traffic, BGP)
  - CPU architecture: intel (default) or amd
"""
import argparse
import json
import sys

from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

import config


def build_pod_manifest(name: str, arch: str) -> k8s_client.V1Pod:
    cpu_type = "intel" if arch == "intel" else "amd"
    eip_attrs = json.dumps({
        "InternetMaxBandwidthOut": 100,
        "InternetChargeType": "TRAFFIC_POSTPAID_BY_HOUR",
        "AddressType": "EIP",
        "InternetServiceProvider": "BGP",
    })
    return k8s_client.V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace=config.NAMESPACE,
            annotations={
                "eks.tke.cloud.tencent.com/eip-attributes": eip_attrs,
                "eks.tke.cloud.tencent.com/eip-claim-delete-policy": "Never",
                "eks.tke.cloud.tencent.com/cpu-type": cpu_type,
            },
        ),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="main",
                    image="nginx:latest",
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "4", "memory": "8Gi"},
                        limits={"cpu": "4", "memory": "8Gi"},
                    ),
                )
            ],
            restart_policy="Never",
        ),
    )


def ensure_namespace(api: k8s_client.CoreV1Api) -> None:
    try:
        api.read_namespace(config.NAMESPACE)
    except ApiException as e:
        if e.status == 404:
            ns = k8s_client.V1Namespace(
                metadata=k8s_client.V1ObjectMeta(name=config.NAMESPACE)
            )
            api.create_namespace(ns)
            print(f"[INFO] Namespace '{config.NAMESPACE}' created.")
        else:
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Create a TKE Supernode Pod with EIP auto-allocation"
    )
    parser.add_argument("--name", required=True, help="Pod name")
    parser.add_argument(
        "--arch",
        choices=["intel", "amd"],
        default="intel",
        help="CPU architecture (default: intel)",
    )
    args = parser.parse_args()

    try:
        api = config.get_k8s_client()
    except EnvironmentError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    try:
        ensure_namespace(api)
    except ApiException as e:
        print(f"[ERROR] Failed to check/create namespace: {e}", file=sys.stderr)
        sys.exit(1)

    manifest = build_pod_manifest(args.name, args.arch)

    try:
        pod = api.create_namespaced_pod(namespace=config.NAMESPACE, body=manifest)
        print(f"[OK] Pod created: {pod.metadata.name}")
        print(f"     Namespace  : {pod.metadata.namespace}")
        print(f"     Status     : {pod.status.phase or 'Pending'}")
        print(f"     CPU type   : {args.arch}")
        print(f"     EIP        : will be allocated by TKE (check with list_pods.py)")
    except ApiException as e:
        if e.status == 409:
            print(
                f"[ERROR] Pod '{args.name}' already exists in namespace '{config.NAMESPACE}'.",
                file=sys.stderr,
            )
        else:
            print(f"[ERROR] Failed to create pod: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
