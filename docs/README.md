# TKE 超级节点 EIP Pod 管理工具

通过腾讯云 Python SDK + Kubernetes Python 客户端，在 TKE 超级节点集群上创建、查看、删除绑定 EIP 的 Pod。

---

## 环境要求

- Python 3.8+
- 网络可达 TKE 集群 API Server（内网或外网）
- 腾讯云账号，具备 TKE 和 VPC 操作权限

---

## 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 内容：
```
tencentcloud-sdk-python>=3.0.0
kubernetes>=26.1.0
```

---

## 配置凭证

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"
```

**外网访问（集群 API Server 不在同一内网时）：**

从 [TKE 控制台](https://console.cloud.tencent.com/tke2) → 集群 `cls-5mchtmid` → 基本信息 → 开启外网访问 → 下载 kubeconfig，然后：

```bash
export KUBECONFIG=/path/to/cls-5mchtmid-config.yaml
```

设置了 `KUBECONFIG` 时，程序优先使用该文件，忽略内置 kubeconfig。

---

## 使用方法

### 创建 Pod

```bash
python3 create_pod.py --name <pod-name> [--arch intel|amd]
```

**参数：**

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--name` | 是 | — | Pod 名称，集群内唯一 |
| `--arch` | 否 | `intel` | CPU 架构：`intel` 或 `amd` |

**示例：**
```bash
# 创建 Intel Pod
python3 create_pod.py --name my-pod-001 --arch intel

# 创建 AMD Pod
python3 create_pod.py --name my-pod-002 --arch amd
```

**输出示例：**
```
[OK] Pod created: my-pod-001
     Namespace  : eip-pods
     Status     : Pending
     CPU type   : intel
     EIP        : will be allocated by TKE (check with list_pods.py)
```

Pod 创建后处于 Pending 状态，约 30~60 秒后变为 Running，EIP 自动分配并绑定。

---

### 查看 Pod 列表

```bash
python3 list_pods.py
```

**输出示例：**
```
NAME                           STATUS       POD IP           NODE                                     CREATED                EIP
------------------------------------------------------------------------------------------------------------------------------------------
my-pod-001                     Running      172.21.80.44     eklet-subnet-heh2tv3n-pfa64p8i           2026-04-27 12:12:40    eip-aqg3ogyx
my-pod-002                     Running      172.21.80.95     eklet-subnet-heh2tv3n-pfa64p8i           2026-04-27 12:14:02    eip-ks177bsx
```

**列说明：**

| 列 | 说明 |
|----|------|
| NAME | Pod 名称 |
| STATUS | Pending / Running / Succeeded / Failed |
| POD IP | Pod 内网 IP |
| NODE | 超级节点名称 |
| CREATED | 创建时间（UTC+8） |
| EIP | 绑定的 EIP ID，Pending 时显示 `-` |

---

### 删除 Pod 并释放 EIP

```bash
python3 delete_pod.py --name <pod-name> --eip-id <eip-id>
```

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--name` | 是 | 要删除的 Pod 名称 |
| `--eip-id` | 是 | 要释放的 EIP ID（从 `list_pods.py` 输出中获取） |

**示例：**
```bash
python3 delete_pod.py --name my-pod-001 --eip-id eip-aqg3ogyx
```

**输出示例：**
```
[OK] Pod 'my-pod-001' deleted from namespace 'eip-pods'.
[INFO] EIP still unbinding, retrying in 5s... (0s elapsed)
[OK] EIP 'eip-aqg3ogyx' released. RequestId: 44f33efe-6aa3-451b-a1e0-04ecb904efc3
```

脚本自动处理 EIP 解绑延迟，最多等待 60 秒后释放。

---

## 完整操作流程

```bash
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"

# 1. 创建两个 Pod
python3 create_pod.py --name pod-intel-01 --arch intel
python3 create_pod.py --name pod-amd-01   --arch amd

# 2. 等待 30~60 秒后查看（确认 Running 和 EIP 已分配）
python3 list_pods.py

# 3. 记录 EIP ID，删除 Pod 并释放 EIP
python3 delete_pod.py --name pod-intel-01 --eip-id eip-xxxxxxxx
python3 delete_pod.py --name pod-amd-01   --eip-id eip-yyyyyyyy

# 4. 确认已清空
python3 list_pods.py
```

---

## 集群信息

| 属性 | 值 |
|------|-----|
| 集群 ID | `cls-5mchtmid` |
| 地域 | 北京（`ap-beijing`） |
| 命名空间 | `eip-pods` |
| Pod 规格 | 4 vCPU / 8 GiB |
| EIP 带宽 | 100 Mbps |
| EIP 计费 | 按流量后付费 |
| EIP 线路 | BGP |

---

## 常见问题

**Q: Pod 长时间处于 Pending，EIP 列显示 `-`？**

检查集群是否有可用的超级节点子网，以及账号 EIP 配额是否充足。

**Q: 删除时提示 `AddressStatusNotPermit`？**

脚本会自动重试，通常 5~10 秒后 EIP 解绑完成。如果超过 60 秒仍失败，请在腾讯云控制台手动释放。

**Q: 连接 API Server 超时？**

默认使用内网地址 `https://10.0.88.29`。如果本机不在同一 VPC，需要在 TKE 控制台开启外网访问并设置 `KUBECONFIG` 环境变量。

**Q: 如何查看已分配但未绑定的 EIP？**

到 [腾讯云控制台 → VPC → 弹性公网 IP](https://console.cloud.tencent.com/vpc/eip) 查看状态为"未绑定"的 EIP，然后用 `delete_pod.py --eip-id` 单独释放。

---

## 文档索引

| 文档 | 说明 |
|------|------|
| `docs/design.md` | 系统设计与架构文档 |
| `docs/sdk-usage.md` | SDK 调用详细说明 |
| `docs/README.md` | 本文档（快速上手） |
