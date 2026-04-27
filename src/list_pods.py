#!/usr/bin/env python3
"""
List all Pods in the eip-pods namespace.

Usage:
    python list_pods.py

Output columns:
    NAME | STATUS | POD IP | NODE | CREATED | EIP ID
"""
import sys

from kubernetes.client.rest import ApiException

import config


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

    col_name = 30
    col_status = 12
    col_ip = 16
    col_node = 40
    col_created = 22
    header = (
        f"{'NAME':<{col_name}} {'STATUS':<{col_status}} {'POD IP':<{col_ip}}"
        f" {'NODE':<{col_node}} {'CREATED':<{col_created}} EIP"
    )
    print(header)
    print("-" * (len(header) + 10))

    for pod in pods.items:
        name = pod.metadata.name or "-"
        phase = (pod.status.phase or "Unknown")
        pod_ip = (pod.status.pod_ip or "-")
        node = (pod.spec.node_name or "-")
        created = (
            pod.metadata.creation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if pod.metadata.creation_timestamp
            else "-"
        )
        annotations = pod.metadata.annotations or {}
        # TKE writes the allocated EIP ID into this annotation after binding
        eip = annotations.get("tke.cloud.tencent.com/eip-id", "-")
        print(
            f"{name:<{col_name}} {phase:<{col_status}} {pod_ip:<{col_ip}}"
            f" {node:<{col_node}} {created:<{col_created}} {eip}"
        )


if __name__ == "__main__":
    main()
