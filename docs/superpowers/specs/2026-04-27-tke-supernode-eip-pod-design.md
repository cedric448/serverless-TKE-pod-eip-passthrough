# TKE Supernode EIP Pod Management — Design Spec

## Overview

This project provides three standalone Python scripts to manage Pods on a Tencent Cloud TKE Supernode cluster. Each Pod is bound to a dedicated EIP (Elastic IP) with 100Mbps bandwidth, pay-per-traffic, BGP ISP. All operations use the Tencent Cloud Python SDK and the Kubernetes Python client — kubectl is only used for manual verification.

---

## Target Environment

| Property | Value |
|---|---|
| Cluster ID | `cls-g8kurryp` |
| Region | `ap-beijing` |
| Namespace | `eip-pods` |
| Pod Spec | 4 vCPU, 8 GiB RAM (Intel or AMD) |
| EIP Bandwidth | 100 Mbps, `TRAFFIC_POSTPAID_BY_HOUR`, BGP |
| Credentials | `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` env vars |

---

## Architecture

```
shengwang/
├── config.py          # Shared constants, credential loader, kubeconfig writer
├── create_pod.py      # Allocate EIP (via annotation) + create Pod
├── delete_pod.py      # Delete Pod + release EIP by ID
├── list_pods.py       # List all pods in eip-pods namespace with status
├── requirements.txt   # tencentcloud-sdk-python, kubernetes
└── docs/
    └── superpowers/
        ├── specs/2026-04-27-tke-supernode-eip-pod-design.md
        └── plans/2026-04-27-tke-supernode-eip-pod-plan.md
```

---

## Component Design

### config.py

Responsibilities:
- Load `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` from environment
- Define cluster constants: `REGION`, `CLUSTER_ID`, `NAMESPACE`, `SERVER`, `CA_DATA`, `CERT_DATA`, `KEY_DATA`
- Write kubeconfig to a temp file and return a configured `kubernetes.client.CoreV1Api` instance
- Expose `get_k8s_client()` and `get_tke_client()` (TKE SDK client), `get_vpc_client()` (VPC SDK client)

### create_pod.py

CLI: `python create_pod.py --name <pod-name> [--cpu 4] [--memory 8] [--arch intel|amd]`

Steps:
1. Build Pod manifest with:
   - `resources.requests/limits`: `cpu: "4"`, `memory: "8Gi"`
   - `nodeSelector`: `beta.kubernetes.io/arch: amd64` (Intel) or `beta.kubernetes.io/arch: amd64` with AMD annotation
   - Annotations for EIP auto-allocation:
     ```
     eks.tke.cloud.tencent.com/eip-attributes: '{"InternetMaxBandwidthOut":100,"InternetChargeType":"TRAFFIC_POSTPAID_BY_HOUR","AddressType":"EIP","InternetServiceProvider":"BGP"}'
     eks.tke.cloud.tencent.com/eip-claim-delete-policy: "Never"
     ```
2. Call `CoreV1Api.create_namespaced_pod(namespace="eip-pods", body=manifest)`
3. Print Pod name and status

**EIP allocation method:** TKE Supernode supports automatic EIP allocation via Pod annotations — no separate VPC `AllocateAddresses` call is needed. TKE allocates and binds the EIP during Pod scheduling.

### delete_pod.py

CLI: `python delete_pod.py --name <pod-name> --eip-id <eip-xxxxxxxx>`

Steps:
1. Call `CoreV1Api.delete_namespaced_pod(name, namespace="eip-pods")`
2. Call VPC SDK `ReleaseAddresses(AddressIds=[eip_id])` in `ap-beijing`
3. Print confirmation

### list_pods.py

CLI: `python list_pods.py`

Steps:
1. Call `CoreV1Api.list_namespaced_pod(namespace="eip-pods")`
2. Print table: Pod Name | Status | Node | IP | Creation Time
3. For each Pod, also print EIP annotation value if present

---

## EIP Binding Mechanism

Per [TKE docs](https://cloud.tencent.com/document/product/457/64886), Supernode Pods support EIP via annotations:

```yaml
annotations:
  eks.tke.cloud.tencent.com/eip-attributes: |
    {"InternetMaxBandwidthOut":100,"InternetChargeType":"TRAFFIC_POSTPAID_BY_HOUR","AddressType":"EIP","InternetServiceProvider":"BGP"}
  eks.tke.cloud.tencent.com/eip-claim-delete-policy: "Never"
```

- `TRAFFIC_POSTPAID_BY_HOUR` = pay-per-traffic billing
- `InternetMaxBandwidthOut: 100` = 100 Mbps
- `AddressType: EIP` = standard EIP (not AnyCast)
- `InternetServiceProvider: BGP` = BGP ISP
- `eip-claim-delete-policy: Never` = EIP is NOT auto-released when Pod is deleted (must be released manually via VPC SDK)

---

## CPU/Architecture Spec

For 4c8g on TKE Supernode:

```yaml
resources:
  requests:
    cpu: "4"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

Intel vs AMD is selected via `eks.tke.cloud.tencent.com/cpu-type` annotation:
- Intel: `"intel"`
- AMD: `"amd"`

---

## Error Handling

- Missing env vars: print clear error and exit with code 1
- Pod already exists: catch `ApiException(409)` and print message
- Pod not found on delete: catch `ApiException(404)` and print message
- EIP release failure: print SDK error response and exit with code 1

---

## Dependencies

```
tencentcloud-sdk-python>=3.0.0
kubernetes>=26.1.0
```

---

## Verification (kubectl-based, manual only)

```bash
# After create_pod.py
kubectl get pod -n eip-pods <pod-name> -o wide

# After list_pods.py output, verify EIP annotation
kubectl get pod -n eip-pods <pod-name> -o jsonpath='{.metadata.annotations}'

# After delete_pod.py
kubectl get pod -n eip-pods  # should show pod gone
```
