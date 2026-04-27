# TKE 超级节点 EIP Pod 管理 — SDK 调用文档

本文档说明项目中每个腾讯云 SDK / Kubernetes API 调用的目的、入参和返回值。

---

## 一、Kubernetes Python Client

### 安装

```bash
pip install kubernetes>=26.1.0
```

### 初始化客户端

```python
from kubernetes import client as k8s_client, config as k8s_config

# 从 kubeconfig 文件初始化
k8s_config.load_kube_config(config_file="/path/to/kubeconfig.yaml")
api = k8s_client.CoreV1Api()
```

---

### 1.1 创建命名空间

**调用：** `CoreV1Api.create_namespace()`

**场景：** `create_pod.py` 在首次运行时，若 `eip-pods` 命名空间不存在则自动创建。

```python
from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException

def ensure_namespace(api: k8s_client.CoreV1Api, namespace: str):
    try:
        api.read_namespace(namespace)          # 检查是否已存在
    except ApiException as e:
        if e.status == 404:
            ns = k8s_client.V1Namespace(
                metadata=k8s_client.V1ObjectMeta(name=namespace)
            )
            api.create_namespace(ns)           # 不存在则创建
```

---

### 1.2 创建 Pod

**调用：** `CoreV1Api.create_namespaced_pod(namespace, body)`

**场景：** `create_pod.py` 创建超级节点 Pod，通过 annotation 触发 EIP 自动分配。

```python
import json
from kubernetes import client as k8s_client

def build_pod_manifest(name: str, arch: str) -> k8s_client.V1Pod:
    # EIP 参数通过 annotation 传递给 TKE 调度器
    eip_attrs = json.dumps({
        "InternetMaxBandwidthOut": 100,            # 带宽 100 Mbps
        "InternetChargeType": "TRAFFIC_POSTPAID_BY_HOUR",  # 按流量计费
        "AddressType": "EIP",                      # 标准 EIP
        "InternetServiceProvider": "BGP",          # BGP 线路
    })

    return k8s_client.V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace="eip-pods",
            annotations={
                # EIP 规格配置
                "eks.tke.cloud.tencent.com/eip-attributes": eip_attrs,
                # Never: Pod 删除时 EIP 不自动释放，需手动调用 VPC API 释放
                "eks.tke.cloud.tencent.com/eip-claim-delete-policy": "Never",
                # CPU 厂商：intel 或 amd
                "eks.tke.cloud.tencent.com/cpu-type": arch,
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

# 创建 Pod
pod = api.create_namespaced_pod(namespace="eip-pods", body=manifest)
print(pod.metadata.name)   # Pod 名称
print(pod.status.phase)    # 初始为 None 或 "Pending"
```

**关键 annotation 说明：**

| Annotation | 值 | 说明 |
|---|---|---|
| `eks.tke.cloud.tencent.com/eip-attributes` | JSON 字符串 | EIP 规格，TKE 调度时自动申请 |
| `eks.tke.cloud.tencent.com/eip-claim-delete-policy` | `Never` / `Release` | `Never`=Pod 删后保留 EIP；`Release`=自动释放 |
| `eks.tke.cloud.tencent.com/cpu-type` | `intel` / `amd` | 指定 CPU 厂商 |

**错误处理：**

```python
from kubernetes.client.rest import ApiException

try:
    pod = api.create_namespaced_pod(namespace="eip-pods", body=manifest)
except ApiException as e:
    if e.status == 409:
        print("Pod 已存在")
    else:
        print(f"创建失败: {e.status} {e.reason}")
```

---

### 1.3 列出 Pod

**调用：** `CoreV1Api.list_namespaced_pod(namespace)`

**场景：** `list_pods.py` 列出 `eip-pods` 下所有 Pod 及其绑定的 EIP。

```python
pods = api.list_namespaced_pod(namespace="eip-pods")

for pod in pods.items:
    name    = pod.metadata.name
    phase   = pod.status.phase          # Pending / Running / Succeeded / Failed
    pod_ip  = pod.status.pod_ip         # Pod 分配的内网 IP
    node    = pod.spec.node_name        # 超级节点名称
    created = pod.metadata.creation_timestamp

    annotations = pod.metadata.annotations or {}
    # TKE 绑定 EIP 后写入此 annotation
    eip_id = annotations.get("tke.cloud.tencent.com/eip-id", "未分配")

    print(f"{name} | {phase} | {pod_ip} | {eip_id}")
```

**EIP ID annotation：**
- key: `tke.cloud.tencent.com/eip-id`
- 值示例: `eip-aqg3ogyx`
- 时机: Pod 从 Pending 变为 Running 后写入

---

### 1.4 删除 Pod

**调用：** `CoreV1Api.delete_namespaced_pod(name, namespace)`

**场景：** `delete_pod.py` 删除指定 Pod。

```python
from kubernetes.client.rest import ApiException

try:
    api.delete_namespaced_pod(name="my-pod", namespace="eip-pods")
    print("Pod 删除成功")
except ApiException as e:
    if e.status == 404:
        print("Pod 不存在，可能已被删除")
    else:
        raise
```

---

## 二、腾讯云 VPC SDK

### 安装

```bash
pip install tencentcloud-sdk-python>=3.0.0
```

### 初始化客户端

```python
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.vpc.v20170312 import vpc_client

cred = credential.Credential("YOUR_SECRET_ID", "YOUR_SECRET_KEY")

http_profile = HttpProfile()
http_profile.endpoint = "vpc.tencentcloudapi.com"

client_profile = ClientProfile()
client_profile.httpProfile = http_profile

client = vpc_client.VpcClient(cred, "ap-beijing", client_profile)
```

---

### 2.1 释放 EIP

**调用：** `VpcClient.ReleaseAddresses(request)`

**场景：** `delete_pod.py` 在 Pod 删除后释放绑定的 EIP。

```python
from tencentcloud.vpc.v20170312 import models as vpc_models
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

req = vpc_models.ReleaseAddressesRequest()
req.AddressIds = ["eip-aqg3ogyx"]   # 支持批量，此处传单个

try:
    resp = client.ReleaseAddresses(req)
    print(f"释放成功，RequestId: {resp.RequestId}")
except TencentCloudSDKException as e:
    print(f"释放失败: {e.code} - {e.message}")
```

**常见错误码：**

| 错误码 | 说明 | 处理方式 |
|--------|------|---------|
| `AddressStatusNotPermit` | EIP 仍处于 BIND 状态 | 等待几秒后重试（Pod 刚删除时出现） |
| `InvalidAddressId.NotFound` | EIP ID 不存在 | 检查 EIP ID 是否正确 |
| `AuthFailure` | AK/SK 无效或无权限 | 检查凭证和 CAM 权限 |

**重试示例（处理 Pod 刚删除时 EIP 尚未解绑）：**

```python
import time

max_wait = 60   # 最多等待 60 秒
interval = 5    # 每 5 秒重试一次
elapsed = 0

while elapsed <= max_wait:
    try:
        req = vpc_models.ReleaseAddressesRequest()
        req.AddressIds = [eip_id]
        resp = client.ReleaseAddresses(req)
        print(f"EIP {eip_id} 释放成功")
        break
    except TencentCloudSDKException as e:
        if "AddressStatusNotPermit" in str(e) and elapsed < max_wait:
            print(f"EIP 尚未解绑，{interval}s 后重试...")
            time.sleep(interval)
            elapsed += interval
        else:
            raise
```

---

## 三、TKE 超级节点关键 Annotation 参考

### EIP 规格参数（`eip-attributes`）

```json
{
  "InternetMaxBandwidthOut": 100,
  "InternetChargeType": "TRAFFIC_POSTPAID_BY_HOUR",
  "AddressType": "EIP",
  "InternetServiceProvider": "BGP"
}
```

| 字段 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| `InternetMaxBandwidthOut` | int | 1~1000 | 出带宽上限（Mbps） |
| `InternetChargeType` | string | `TRAFFIC_POSTPAID_BY_HOUR`（按流量）/ `BANDWIDTH_POSTPAID_BY_HOUR`（按带宽） | 计费方式 |
| `AddressType` | string | `EIP`（标准）/ `AnycastEIP`（Anycast） | EIP 类型 |
| `InternetServiceProvider` | string | `BGP` / `CMCC` / `CUCC` / `CTCC` | 运营商线路 |

### EIP 删除策略（`eip-claim-delete-policy`）

| 值 | 行为 |
|----|------|
| `Never` | Pod 删除后 EIP 保留，需手动调用 `ReleaseAddresses` 释放 |
| `Release` | Pod 删除后 EIP 自动释放（慎用，EIP 不可恢复） |

### CPU 类型（`cpu-type`）

| 值 | 说明 |
|----|------|
| `intel` | Intel CPU |
| `amd` | AMD CPU |

---

## 四、完整调用链路示意

### 创建流程

```
create_pod.py
    │
    ├─ k8s CoreV1Api.read_namespace()          检查命名空间
    ├─ k8s CoreV1Api.create_namespace()        [首次] 创建命名空间
    └─ k8s CoreV1Api.create_namespaced_pod()   创建 Pod
                │
                └─ TKE 调度器读取 eip-attributes annotation
                        │
                        └─ TKE 自动调用 VPC AllocateAddresses + BindAddresses
                                │
                                └─ Pod annotation 写入 tke.cloud.tencent.com/eip-id
```

### 删除流程

```
delete_pod.py
    │
    ├─ k8s CoreV1Api.delete_namespaced_pod()   删除 Pod
    │           │
    │           └─ TKE 自动调用 VPC UnbindAddresses (EIP 解绑，不释放)
    │
    └─ vpc VpcClient.ReleaseAddresses()        释放 EIP（含重试）
```
