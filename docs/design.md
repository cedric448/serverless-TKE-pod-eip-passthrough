# TKE 超级节点 EIP Pod 管理系统 — 设计与架构文档

## 1. 项目概述

本项目提供三个独立的 Python 脚本，通过腾讯云 SDK 和 Kubernetes Python 客户端，在腾讯云 TKE 超级节点集群上管理 Pod 生命周期。每个 Pod 创建时自动绑定一个独立的 EIP（弹性公网 IP），删除时同步回收 EIP。全程不依赖 kubectl，仅使用 SDK/API 调用。

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        本地执行环境                               │
│                                                                  │
│  create_pod.py ──┐                                               │
│  list_pods.py  ──┼── config.py ─┬─ Kubernetes Python Client ──► │
│  delete_pod.py ──┘              └─ TencentCloud VPC SDK ──────► │
└──────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌─────────────────────┐    ┌────────────────────────────────────┐
│  TKE 集群 API Server │    │  腾讯云 VPC API                    │
│  cls-5mchtmid        │    │  vpc.tencentcloudapi.com           │
│  (ap-beijing)        │    │  ap-beijing                        │
└─────────────────────┘    └────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TKE 超级节点                                  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Namespace: eip-pods                                       │  │
│  │                                                           │  │
│  │  Pod: my-pod-001   Pod: my-pod-002   Pod: my-pod-N        │  │
│  │  CPU: 4c / 8Gi     CPU: 4c / 8Gi    ...                  │  │
│  │  EIP: eip-xxxxx    EIP: eip-yyyyy                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 组件设计

### 3.1 文件结构

```
shengwang/
├── config.py          # 共享模块：凭证、集群常量、API 客户端工厂
├── create_pod.py      # 创建 Pod（含 EIP 自动分配注解）
├── list_pods.py       # 列出 eip-pods 命名空间下所有 Pod
├── delete_pod.py      # 删除 Pod + 释放 EIP
├── requirements.txt   # Python 依赖
└── docs/
    ├── design.md      # 本文档（设计 & 架构）
    ├── sdk-usage.md   # SDK 调用文档
    └── README.md      # 快速上手
```

### 3.2 config.py — 共享配置模块

**职责：**
- 从环境变量加载 AK/SK 凭证
- 内置 kubeconfig（CA、证书、私钥的 base64 编码）
- 提供 `get_k8s_client()` 返回 Kubernetes `CoreV1Api`
- 提供 `get_vpc_client()` 返回腾讯云 VPC SDK 客户端

**关键常量：**

| 常量 | 值 | 说明 |
|------|-----|------|
| `REGION` | `ap-beijing` | 集群所在地域 |
| `CLUSTER_ID` | `cls-5mchtmid` | TKE 集群 ID |
| `NAMESPACE` | `eip-pods` | Pod 所在命名空间 |
| `K8S_SERVER` | `https://10.0.88.29` | API Server 地址（内网） |

**凭证优先级：**
1. 环境变量 `KUBECONFIG` 指向的 kubeconfig 文件（外网访问时使用）
2. 内置 kubeconfig（内网直连时使用）

### 3.3 create_pod.py — 创建 Pod

**流程：**
```
输入参数 (--name, --arch)
    │
    ▼
get_k8s_client()
    │
    ▼
ensure_namespace()  ── 不存在则创建 eip-pods namespace
    │
    ▼
build_pod_manifest()  ── 构造 Pod YAML（含 EIP 注解）
    │
    ▼
CoreV1Api.create_namespaced_pod()
    │
    ▼
输出 Pod 名称 / 状态 / CPU 类型
```

**EIP 分配机制：**

TKE 超级节点通过 Pod annotation 实现 EIP 自动分配，无需预先调用 VPC API 申请。调度器读取以下注解后，在 Pod 绑定节点时自动申请并绑定 EIP：

```json
eks.tke.cloud.tencent.com/eip-attributes:
{
  "InternetMaxBandwidthOut": 100,
  "InternetChargeType": "TRAFFIC_POSTPAID_BY_HOUR",
  "AddressType": "EIP",
  "InternetServiceProvider": "BGP"
}
eks.tke.cloud.tencent.com/eip-claim-delete-policy: "Never"
eks.tke.cloud.tencent.com/cpu-type: "intel" | "amd"
```

`eip-claim-delete-policy: Never` 表示 Pod 删除后 EIP **不自动释放**，需手动调用 VPC API 释放（避免意外丢失 IP）。

**Pod 规格：**

```yaml
resources:
  requests:
    cpu: "4"
    memory: "8Gi"
  limits:
    cpu: "4"
    memory: "8Gi"
```

### 3.4 list_pods.py — 查看 Pod

**流程：**
```
get_k8s_client()
    │
    ▼
CoreV1Api.list_namespaced_pod(namespace="eip-pods")
    │
    ▼
格式化输出表格：NAME | STATUS | POD IP | NODE | CREATED | EIP
```

**EIP ID 读取位置：**
TKE 在 EIP 绑定完成后，将 EIP ID 写入 Pod annotation：
```
tke.cloud.tencent.com/eip-id: eip-xxxxxxxx
```
`list_pods.py` 直接从该 annotation 读取并展示。

### 3.5 delete_pod.py — 删除 Pod + 释放 EIP

**流程：**
```
输入参数 (--name, --eip-id)
    │
    ▼
get_k8s_client()
    │
    ▼
CoreV1Api.delete_namespaced_pod()
    │
    ▼
get_vpc_client()
    │
    ▼
ReleaseAddresses() ── 重试最多 60s（EIP 解绑有延迟）
    │
    ▼
输出释放结果
```

**重试逻辑：**
Pod 删除后，EIP 的状态从 `BIND` 变为 `UNBIND` 需要几秒。直接调用 `ReleaseAddresses` 会返回 `AddressStatusNotPermit` 错误。`delete_pod.py` 以 5 秒间隔自动重试，最多等待 60 秒。

---

## 4. EIP 生命周期

```
create_pod.py 执行
    │
    ▼
Pod Pending ── TKE 调度器读取 EIP 注解
    │
    ▼
TKE 自动调用 VPC API 申请 EIP
    │
    ▼
EIP 状态: ALLOCATING → BIND
    │
    ▼
Pod Running（EIP ID 写入 Pod annotation）
    │
    ▼
delete_pod.py 执行
    │
    ├── Pod 删除
    │
    ▼
EIP 状态: BIND → UNBIND（需 5~10 秒）
    │
    ▼
delete_pod.py 调用 ReleaseAddresses（含重试）
    │
    ▼
EIP 释放完成
```

---

## 5. 集群信息

| 属性 | 值 |
|------|-----|
| 集群 ID | `cls-5mchtmid` |
| 地域 | 北京（`ap-beijing`） |
| 集群类型 | TKE 超级节点（Serverless） |
| API Server（内网） | `https://10.0.88.29` |
| 命名空间 | `eip-pods` |
| Pod 规格 | 4 vCPU / 8 GiB |
| EIP 带宽 | 100 Mbps |
| EIP 计费 | 按流量后付费（`TRAFFIC_POSTPAID_BY_HOUR`） |
| EIP ISP | BGP |

---

## 6. 依赖

| 包 | 版本要求 | 用途 |
|----|---------|------|
| `tencentcloud-sdk-python` | ≥ 3.0.0 | 腾讯云 VPC API（EIP 释放） |
| `kubernetes` | ≥ 26.1.0 | K8s API（Pod 创建/删除/列表） |
| Python | 3.8+ | 运行时 |

---

## 7. 安全说明

- AK/SK 通过环境变量注入，不写入代码
- kubeconfig TLS 证书内置于 `config.py`，仅用于内网访问
- 外网访问时建议通过 `KUBECONFIG` 环境变量指定从 TKE 控制台下载的最新 kubeconfig
- `eip-claim-delete-policy: Never` 防止 EIP 因 Pod 意外删除而自动释放，保护 IP 资源
