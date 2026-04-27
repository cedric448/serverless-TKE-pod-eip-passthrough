# TKE Supernode EIP Pod Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three Python scripts (create/delete/list) to manage TKE Supernode Pods with auto-allocated EIPs, using the Tencent Cloud Python SDK and Kubernetes Python client.

**Architecture:** A shared `config.py` provides credentials, cluster constants, and authenticated API clients. Three standalone scripts each perform one operation. EIP is auto-allocated by TKE via Pod annotations at creation time and released via VPC SDK at deletion time.

**Tech Stack:** Python 3.11, `tencentcloud-sdk-python`, `kubernetes` Python client, TKE cluster `cls-g8kurryp` (ap-beijing)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `requirements.txt` | Create | Pin SDK dependencies |
| `config.py` | Create | Credentials, constants, kubeconfig writer, API client factories |
| `create_pod.py` | Create | Create Pod with EIP annotation |
| `delete_pod.py` | Create | Delete Pod + release EIP by ID |
| `list_pods.py` | Create | List all pods in eip-pods namespace |
| `docs/superpowers/specs/2026-04-27-tke-supernode-eip-pod-design.md` | Already exists | Design spec |

---

## Task 1: Install Dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Write requirements.txt**

```
tencentcloud-sdk-python>=3.0.0
kubernetes>=26.1.0
```

- [ ] **Step 2: Install dependencies**

Run:
```bash
pip3 install tencentcloud-sdk-python kubernetes
```

Expected output includes:
```
Successfully installed tencentcloud-sdk-python-...
Successfully installed kubernetes-...
```

- [ ] **Step 3: Verify imports work**

Run:
```bash
python3 -c "from tencentcloud.vpc.v20170312 import vpc_client; from kubernetes import client; print('OK')"
```

Expected: `OK`

---

## Task 2: Create config.py

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write config.py**

```python
import os
import base64
import tempfile
from tencentcloud.common import credential
from tencentcloud.vpc.v20170312 import vpc_client, models as vpc_models
from kubernetes import client as k8s_client, config as k8s_config

# ── Cluster constants ──────────────────────────────────────────────────────────
REGION = "ap-beijing"
CLUSTER_ID = "cls-g8kurryp"
NAMESPACE = "eip-pods"
K8S_SERVER = "https://172.21.128.44"

# Base64-encoded kubeconfig fields (from kubeconfig in p.md)
CA_DATA = (
    "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURDakNDQWZLZ0F3SUJBZ0lCQURBTkJna3Fo"
    "a2lHOXcwQkFRc0ZBREFWTVJNd0VRWURWUVFERXdwcmRXSmwKY201bGRHVnpNQ0FYRFRJMk1ETXl"
    "PREUxTkRjeE9Wb1lEekl3TlRZd016SXdNVFUwTnpFNVdqQVZNUk13RVFZRApWUVFERXdwcmRXSmwK"
    "Y201bGRHVnpNSUlCSWpBTkJna3Foa2lHOXcwQkFRRUZBQU9DQVFnQU1JSUJDaUtDQVFFQQpzMjFY"
    "USs3SmlpTzU4Y3hmcjhMakJQcDNpbEs5bS9wL0NKSEhFcmxybVhEMUFnYnBLa2ZjSGxidVRYZDBI"
    "eEp1CmRlQ0x6dEcvajdlczZGRHFLdHdXOFZQWHg1SWg0VzV2dERPVHVac3RLSkY2R3RzbDBhOXIx"
    "Skg0ZkNXZDBDbEQKUG1jM2ZGL290T2hGZndnT3FXSmNwKzB4WVhmVndWb1RHaTdmZEltTEJOWkho"
    "SnZSdTRWU3RXTXd5S1FONEE0YwozL0pQN2VnRGIwaFZNVlgzaC8vd2M0SWJQd1ZZdXBoQWM2b2Zj"
    "R3BZMml6TTlCejkzRWt0aFpHdnRWVFVlUmxBCmkyQzhqR1grcGw0Yzg4NjZLVDFCQTkrbExFajhC"
    "bHJ0TEtjQnpxUUFyYjdjUDJhUFBTUEVHeUdKVGF1eUJzZnAKKzhCdVQrR291ZDdPNWhoZFRXUkZh"
    "d0lEQVFBQm8yTXdZVEFPQmdOVkhROEJBZjhFQkFNQ0FwUXdEd1lEVlIwVApBUUgvQkFVd0F3RUIv"
    "ekFkQmdOVkhRNEVGZ1FVTG5ZTUhKbG9xR1pKb3daN0d1OHR0ZGNqTUw4d0h3WURWUTBKC0JCZ3dG"
    "b0FVTG5ZTUhKbG9xR1pKb3daN0d1OHR0ZGNqTUw4d0RRWUpLb1pJaHZjTkFRRUxCUUFEZ2dFQkFF"
    "K0MKNmFQTW5RbnZYWWVxU1E1d3ZMcnlqbkYyQTlPUnpTaUJRb1FrMDl1WGVnUDJkS1NiVTg3bEdM"
    "L2NVTFVCVE16TwoyeVBDMVVIOElhSWlFQUc2KzdoTUowTkhYYStaQWN5SFJzVjNDdStGOS9jMkMw"
    "d2xSOTFqRDJOaHo1OVBHNGJ1CjFZYWlROGxPWGRyYkVyQlNRTUZPcnBrYjA3UEdLTHN5YVlGZEFV"
    "SlVDQ2F2QzREckxLN21oNjhjbVBjekRwZjkKM1p0YURENDN0aEFDK1AxaWoxanpwK1VmaER5Mmhq"
    "OUlLUE1BNWFwSWVVVWUvRWxLQ1poRVRTQzd1dVJzN2hsTwo"
    "aW9GdlVpZ2hReGlNVmVhRVd1eWFEdzlydWVuNzBUbHgvcDdjTDY2QjlRcDZ5aGM5SVppQkhKUW1s"
    "M0ZnUjR1YwpqRHBQbi9BUll2TXhZVjZ4TzJNPQotLS0tLUVORCBDRVJUSUZJQ0FURS0tLS0tCg=="
)

CERT_DATA = (
    "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSURMekNDQWhlZ0F3SUJBZ0lJWGhNeTBLOG5P"
    "Nmt3RFFZSktvWklodmNOQVFFTEJRQXdGVEVUTUJFR0ExVUUKQXhNS2EzVmlaWEp1WlhSbGN6QWFG"
    "dzB5TmpBek1qZ3hOVFV3TURoYUdBOHlNRFUyTURNeU9ERTFOVEF3T0ZvdwpOakVTTUJBR0ExVUVD"
    "aE1KZEd0bE9uVnpaWEp6TVNBd0hnWURWUVFERXhjeE1EQXdNREE0T0RFNU1qSXRNVGMzCk5EY3hN"
    "ekF3T0RDQ0FTSXdEUVlKS29aSWh2Y05BUUVCQlFBRGdnRVBBRENDQVFvQ2dnRUJBTVpBN3pJR3p4"
    "WDIKWnBraitGZk5kQVpuMk5Ca3pxR3BTN0VTOGhqbXVacmYyMDVpUDZDWVlqT00rdDQ0ZGM0UVRM"
    "Zk5PWXRsTlplOApxenhmdjE0N2s0eXo4aUx3ZmxKWjJTWWRRSjNidTBuNncvWnlNQSs4SEdvSXFz"
    "eHhxM0MxcjJXR2NiOVZUVGtkClVzdlJYaUFuZzY2V3d1RWpwQmVJZWZRUTI5S1psVWtkMFlldDZW"
    "RVhZdHJrd1IvNG5jbzdHNWw1UmlLOTZ4RTkKcjUvV2c5Vm93SzJUYkZjbGtjNHhCQ3pyWURBK0Fp"
    "b2hYTGVQbHN5S0s2aUNwQzgrcURRNGhXNmR3THdKL0cxagoyMTlyanJQQkZ5TEVNSXlJeXJCbWZx"
    "YldXWkd3OXpjNGRxd2x2ZnVhTHlIcWUrRk9pWW5BWGU3Uk1ZRGcxNjAwCk5SUzduSWI3c3EwQ0F3"
    "RUFBYU5nTUY0d0RnWURWUjBQQVFIL0JBUURBZ0tFTUIwR0ExVWRKUVFXTUJRR0NDc0cKQVFVRkJ3"
    "TUNCZ2dyQmdFRkJRY0RBVEFNQmdOVkhSTUJBZjhFQWpBQU1COEdBMVVkSXdRWU1CYUFGQzUyREJ5"
    "WgphS2htU2FNR2V4cnZMYlhYSXpDL01BMEdDU3FHU0liM0RRRUJDd1VBQTRJQkFRQVlVM05Ua0pp"
    "VGdxU1JHSC9qCnA5OEFoSUwyNngxZTkyR1hOQi90bFNuY2pHVENneDlCQnB1ZXU5OEdtT1lCaXlG"
    "RDB1by9jczV6OERMNmxzZmoKT2dsbFZnMVNHRnF6UE43YlNaa1ROVDR0b1JKOWVnekhuWXdnbHkr"
    "ZzU1a3pidHd4eGppODZnTkJraXBkeFhFVQpVSjU1WFNpR25OUjA0OVp5czYzSlU0TU43TzhkUXJJ"
    "b0JDcWU5RWpQYzhaYUlwRThDM2QvelM0bjVFS1VPN3djClFhR21PcC9tY2Z5N0hOTG1EaEw0Rk51"
    "c1Y3NU1VbUphVlZJTnYvTndpVHZOalRzSENKa3hIUjJzcmRScWtDU0EKckJmdWZrbi9VNWMySTkw"
    "elpVSTFnUmJHSVk1MitWVVhTdEduV3FheU51T20rb3dVdWk2elk2akJMVjIvaFdkWQp5RmVHCi0t"
    "LS0tRU5EIENFUlRJRklDQVRFLS0tLS0K"
)

KEY_DATA = (
    "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBeGtEdk1nYlBG"
    "ZlptbVNQNFY4MTBCbWZZMEdUT29hbExzUkx5R09hNW10L2JUbUkvCm9KaGlNNHo2M2poMXpoQk10"
    "ODA1aTJVMWw3eXJQRisvWGp1VGpMUHlJdkIrVWxuWkpoMUFuZHU3U2ZyRDluSXcKRDd3Y2FnaXF6"
    "SEdyY0xXdlpZWnh2MVZOT1IxU3k5RmVJQ2VEcnBiQzRTT2tGNGg1OUJEYjBwbVZTUjNSaDYzcApV"
    "UmRpMnVUQkgvaWR5anNibVhsR0lyM3JFVDJ2bjlhRDFXakFyWk5zVnlXUnpqRUVMT3RnTUQ0Q0tp"
    "RmN0NCtXCnpJb3JxSUtrTHo2b05EaUZicDNBdkFuOGJXUGJYMnVPczhFWElzUXdqSWpLc0daK3B0"
    "WlprYkQzTnpoMnJDVzkKKzVvdkllcDc0VTZKaWNCZDd0RXhnT0RYclRRMUZMdWNodnV5clFJREFR"
    "QUJBb0lCQUQrV1BDSHpoU0FxTTZZUwpuMmlxQVBpOC9oRjVBNzFlSzJUVUNzcHAxa1lTWHFpNVlt"
    "Y0QrUnRIc0g3dDVQcit4MXg4ZW1SM1JjVXhRa3JPCit2WWliYVRIWW5aS1pIbk5UNVNsOVQrc1ps"
    "bklFR3BQSFpNdVpuNnI0UHhKeVE0UmR2dzlMdWFMV1lWa0hsWTUKQk5PVFdPejZkZTc0RzMxZ3pK"
    "eTNlNG9Fc0prT1luMWdUQUZSVEZ5TXN6OEg0RTlUV09yZlFSNmpSQmJqNnRuZwo4Mm4wdmhHbDMr"
    "ZUFId3d5ZDdmWmNockh5OG1UMURHeHhQb2ZTQVJTMDZqTUpQSlJtOWVwczA1NzRZM0d0SEJmClBR"
    "bCtIS3ZkZ3dEbmRTZWphc2d0NXk0cVExVU81NHdramltSDRZcC9uSTJTMXRncGpzVElLdDdnWEZs"
    "Z1dVeDkKcThSL3VaRUNnWUVBMHVKSEgxQ29OWGdnaVZHNWgxeXFhS3VHZG1pODdBZ1ZEeDdUVlhJ"
    "QUxZUTJPN1RJRVE5bQpObUJlY0FHcDAwTVNtV3BSa0RsTXlYZ0RPaFcxRUpuSWhZYk1mU1dpMlRm"
    "UWxQLy8zYzZhUDZQSTFnVHYrOVVJCld4VFNQczlxYW51eEtLYlpnVEk1eTFtTXVaZzJ1MXpIZ0pI"
    "VDBDVmZzTEJLOUVUQWtacm5UQ2NDZ1lFQThLcnIKMEhZUS9XRG5BTnVhN0tQS0xpY1c5VnhSdTd1"
    "LzZvZWFoa3ZzKzdtRGp4T3RYWVVrcjE5UThoUS8wMHo1cGNMMgp1T3lJTzdXQlVJZFlPTjdOamtr"
    "VllYOGdjMnh0QVprQm5zT1kyOEpIdEdGZnZMSndrcGtTU2QydlVZMHNQNFBjCkJINnJ0eHNlcnhQ"
    "QnhNa21MdUp2TzVEYmV2UEs5K0FGUlEva1N3c0NnWUIxT2lJTkwxb0NOeC9uRmM0TGlDQ1cKaE5y"
    "L1VhUExsWWFYWEN4Z2NEblhFNHJPVCtWelRsc2tXUmZHTGJhSTROMGkrUzRUL1RaSlBIU1d3bUJm"
    "dFF6NQo1UUFoaFYxc1lKR0xjbTk2anBIQ1ZMcWM5aXV0a3pQTTVkc2wzVWtybmt6UjYwWTNnb01N"
    "SG1DUy95RlZyL0thCjd2V08zR2ZBSVkvWkQ2cjRoZUtUdXdLQmdRQ0U0VXBzZ2hQbFlwQ0pON2Qx"
    "ZXdYUnI0R01YWm0vTnUzQzkzWkoKT2ppeHovOGtpMi9JV0JBbVNGRndKK0FKc2RHUlJYRm1MeXNW"
    "RktVK3FrdjZzb0g2VXIzY1pBMnR6U3J1bStWNgpISE1VdTFOTjlBbWhMVURjb0dtcG9SNEF3QnF6"
    "UXdIQzlaR24rdkJaS0dadldjU2NWR2VvRXRZc0w5bGNQVE9MCnF6ZVlld0tCZ1FDSkVSZWVqeGtK"
    "azd0UCtnS0VBUjlIM1VRdVpqdFY4dEtwRjlJcnZzWUwrblRxZzhrR042SkIKNDRBWkVxSUV0RG1q"
    "Y3Z0K0tMYmNLY3VwRWhSeTA0aUJnVVdvMC8rejZrQ0FYZG1WWm1sYncxT3lZRmQ1TGswYwo0M3BC"
    "V0Y0VlZ1dWxhbGlBaFNMeU4reWRhSm9nMGhKZ3V6TUd5bXpmcUwvR2R5MUlqYmkrN1E9PQotLS0t"
    "LUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQo="
)


def get_credentials():
    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    if not secret_id or not secret_key:
        raise EnvironmentError(
            "Missing credentials: set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY"
        )
    return credential.Credential(secret_id, secret_key)


def get_k8s_client():
    """Write kubeconfig to a temp file and return a CoreV1Api client."""
    kubeconfig_yaml = f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {CA_DATA}
    server: {K8S_SERVER}
  name: {CLUSTER_ID}
contexts:
- context:
    cluster: {CLUSTER_ID}
    user: "100000881922"
  name: {CLUSTER_ID}-context
current-context: {CLUSTER_ID}-context
kind: Config
preferences: {{}}
users:
- name: "100000881922"
  user:
    client-certificate-data: {CERT_DATA}
    client-key-data: {KEY_DATA}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(kubeconfig_yaml)
        kubeconfig_path = f.name

    k8s_config.load_kube_config(config_file=kubeconfig_path)
    return k8s_client.CoreV1Api()


def get_vpc_client():
    """Return a VPC SDK client for ap-beijing."""
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    cred = get_credentials()
    http_profile = HttpProfile()
    http_profile.endpoint = "vpc.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return vpc_client.VpcClient(cred, REGION, client_profile)
```

- [ ] **Step 2: Verify config.py loads without error**

Run:
```bash
cd /root/shengwang && TENCENTCLOUD_SECRET_ID=test TENCENTCLOUD_SECRET_KEY=test python3 -c "import config; print('config OK')"
```

Expected: `config OK`

---

## Task 3: Create create_pod.py

**Files:**
- Create: `create_pod.py`

- [ ] **Step 1: Write create_pod.py**

```python
#!/usr/bin/env python3
"""
Create a TKE Supernode Pod with auto-allocated EIP.

Usage:
    python create_pod.py --name <pod-name> [--arch intel|amd]
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
        "InternetServiceProvider": "BGP"
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
            }
        ),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="main",
                    image="nginx:latest",
                    resources=k8s_client.V1ResourceRequirements(
                        requests={"cpu": "4", "memory": "8Gi"},
                        limits={"cpu": "4", "memory": "8Gi"},
                    )
                )
            ],
            restart_policy="Never",
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Create TKE Supernode Pod with EIP")
    parser.add_argument("--name", required=True, help="Pod name")
    parser.add_argument("--arch", choices=["intel", "amd"], default="intel",
                        help="CPU architecture (default: intel)")
    args = parser.parse_args()

    try:
        api = config.get_k8s_client()
    except EnvironmentError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure namespace exists
    core = k8s_client.CoreV1Api()
    try:
        core.read_namespace(config.NAMESPACE)
    except ApiException as e:
        if e.status == 404:
            ns = k8s_client.V1Namespace(
                metadata=k8s_client.V1ObjectMeta(name=config.NAMESPACE)
            )
            core.create_namespace(ns)
            print(f"[INFO] Namespace '{config.NAMESPACE}' created.")
        else:
            print(f"[ERROR] Failed to check namespace: {e}", file=sys.stderr)
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
            print(f"[ERROR] Pod '{args.name}' already exists in namespace '{config.NAMESPACE}'.",
                  file=sys.stderr)
        else:
            print(f"[ERROR] Failed to create pod: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
cd /root/shengwang && python3 -m py_compile create_pod.py && echo "Syntax OK"
```

Expected: `Syntax OK`

---

## Task 4: Create list_pods.py

**Files:**
- Create: `list_pods.py`

- [ ] **Step 1: Write list_pods.py**

```python
#!/usr/bin/env python3
"""
List all Pods in the eip-pods namespace.

Usage:
    python list_pods.py
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

    header = f"{'NAME':<30} {'STATUS':<12} {'POD IP':<16} {'NODE':<40} {'CREATED':<25} {'EIP'}"
    print(header)
    print("-" * len(header))

    for pod in pods.items:
        name = pod.metadata.name or "-"
        phase = pod.status.phase or "Unknown"
        pod_ip = pod.status.pod_ip or "-"
        node = pod.spec.node_name or "-"
        created = pod.metadata.creation_timestamp.strftime("%Y-%m-%d %H:%M:%S") if pod.metadata.creation_timestamp else "-"
        annotations = pod.metadata.annotations or {}
        eip = annotations.get("tke.cloud.tencent.com/eip-id", "-")
        print(f"{name:<30} {phase:<12} {pod_ip:<16} {node:<40} {created:<25} {eip}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
cd /root/shengwang && python3 -m py_compile list_pods.py && echo "Syntax OK"
```

Expected: `Syntax OK`

---

## Task 5: Create delete_pod.py

**Files:**
- Create: `delete_pod.py`

- [ ] **Step 1: Write delete_pod.py**

```python
#!/usr/bin/env python3
"""
Delete a TKE Supernode Pod and release its EIP.

Usage:
    python delete_pod.py --name <pod-name> --eip-id <eip-xxxxxxxx>
"""
import argparse
import sys
from kubernetes.client.rest import ApiException
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.vpc.v20170312 import models as vpc_models
import config


def main():
    parser = argparse.ArgumentParser(description="Delete TKE Pod and release EIP")
    parser.add_argument("--name", required=True, help="Pod name to delete")
    parser.add_argument("--eip-id", required=True, help="EIP ID to release (e.g. eip-xxxxxxxx)")
    args = parser.parse_args()

    # Step 1: Delete Pod
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

    # Step 2: Release EIP
    try:
        vpc = config.get_vpc_client()
        req = vpc_models.ReleaseAddressesRequest()
        req.AddressIds = [args.eip_id]
        resp = vpc.ReleaseAddresses(req)
        print(f"[OK] EIP '{args.eip_id}' released. RequestId: {resp.RequestId}")
    except TencentCloudSDKException as e:
        print(f"[ERROR] Failed to release EIP '{args.eip_id}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
cd /root/shengwang && python3 -m py_compile delete_pod.py && echo "Syntax OK"
```

Expected: `Syntax OK`

---

## Task 6: End-to-End Test

- [ ] **Step 1: Set credentials**

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"
```

- [ ] **Step 2: Create a Pod (Intel)**

```bash
cd /root/shengwang
python3 create_pod.py --name test-pod-001 --arch intel
```

Expected output:
```
[OK] Pod created: test-pod-001
     Namespace  : eip-pods
     Status     : Pending
     CPU type   : intel
     EIP        : will be allocated by TKE (check with list_pods.py)
```

- [ ] **Step 3: List Pods**

```bash
python3 list_pods.py
```

Expected: table with `test-pod-001` listed (status may be `Pending` initially)

- [ ] **Step 4: Wait for Pod to be Running, note EIP ID**

Run list again after ~30 seconds:
```bash
python3 list_pods.py
```

Note the EIP ID from the output (column `EIP`). If EIP column shows `-`, check annotations via kubectl:
```bash
kubectl get pod -n eip-pods test-pod-001 -o jsonpath='{.metadata.annotations}' 2>/dev/null || echo "kubectl not available"
```

Alternatively, check TKE console for the EIP bound to the pod.

- [ ] **Step 5: Delete Pod and release EIP**

Replace `eip-xxxxxxxx` with the actual EIP ID:
```bash
python3 delete_pod.py --name test-pod-001 --eip-id eip-xxxxxxxx
```

Expected:
```
[OK] Pod 'test-pod-001' deleted from namespace 'eip-pods'.
[OK] EIP 'eip-xxxxxxxx' released. RequestId: ...
```

- [ ] **Step 6: Confirm deletion**

```bash
python3 list_pods.py
```

Expected: `[INFO] No pods found in namespace 'eip-pods'.`
