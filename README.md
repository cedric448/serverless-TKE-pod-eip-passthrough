# serverless-TKE-pod-eip-passthrough

通过腾讯云 Python SDK + Kubernetes Python 客户端，在 TKE 超级节点（Serverless）集群上管理 Pod 生命周期。每个 Pod 创建时自动绑定独立 EIP，删除时同步回收 EIP。全程无需 kubectl，仅使用 SDK/API 调用。

## 功能

- **创建 Pod**：在超级节点上创建 4c8g Pod，自动分配并绑定 EIP（100Mbps，按流量，BGP）
- **查看 Pod**：列出命名空间下所有 Pod 的状态、IP 和绑定的 EIP ID
- **删除 Pod**：删除 Pod 并释放对应 EIP（含自动重试机制）
- 支持 Intel / AMD CPU 选择

## 目录结构

```
.
├── src/
│   ├── config.py          # 共享配置：凭证加载、API 客户端工厂
│   ├── create_pod.py      # 创建 Pod（含 EIP 自动分配注解）
│   ├── list_pods.py       # 查看 eip-pods 命名空间下所有 Pod
│   └── delete_pod.py      # 删除 Pod + 释放 EIP
├── docs/
│   ├── design.md          # 系统设计与架构文档
│   ├── sdk-usage.md       # SDK 调用详细说明
│   └── README.md          # 操作手册（中文）
├── .env.example           # 环境变量示例
├── requirements.txt       # Python 依赖
└── README.md              # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置凭证

```bash
cp .env.example .env
# 编辑 .env，填入你的凭证
```

或直接导出环境变量：

```bash
# 腾讯云 AK/SK
export TENCENTCLOUD_SECRET_ID="your-secret-id"
export TENCENTCLOUD_SECRET_KEY="your-secret-key"

# Kubernetes 认证（推荐方式：kubeconfig 文件）
# 从 TKE 控制台下载 kubeconfig: 集群 → 基本信息 → APIServer信息 → 开启外网访问 → 下载
export KUBECONFIG=/path/to/kubeconfig.yaml
```

> **内网访问备选方式**：设置 `K8S_SERVER` / `K8S_CA_DATA` / `K8S_CERT_DATA` / `K8S_KEY_DATA` 四个环境变量（参见 `.env.example`）。

### 3. 使用脚本

切换到 `src/` 目录后运行：

```bash
cd src/

# 创建 Pod（Intel，默认）
python3 create_pod.py --name my-pod-001 --arch intel

# 创建 Pod（AMD）
python3 create_pod.py --name my-pod-002 --arch amd

# 查看所有 Pod
python3 list_pods.py

# 删除 Pod 并释放 EIP（EIP ID 从 list_pods.py 输出中获取）
python3 delete_pod.py --name my-pod-001 --eip-id eip-xxxxxxxx
```

## 示例输出

**创建 Pod：**
```
[OK] Pod created: my-pod-001
     Namespace  : eip-pods
     Status     : Pending
     CPU type   : intel
     EIP        : will be allocated by TKE (check with list_pods.py)
```

**查看 Pod（Running 后）：**
```
NAME                           STATUS       POD IP           NODE                                     CREATED                EIP
------------------------------------------------------------------------------------------------------------------------------------------
my-pod-001                     Running      172.21.80.44     eklet-subnet-heh2tv3n-pfa64p8i           2026-04-27 12:12:40    eip-aqg3ogyx
```

**删除 Pod：**
```
[OK] Pod 'my-pod-001' deleted from namespace 'eip-pods'.
[INFO] EIP still unbinding, retrying in 5s... (0s elapsed)
[OK] EIP 'eip-aqg3ogyx' released. RequestId: 44f33efe-...
```

## 集群信息

| 属性 | 值 |
|------|-----|
| 集群类型 | TKE 超级节点（Serverless） |
| 地域 | 北京（`ap-beijing`） |
| 命名空间 | `eip-pods` |
| Pod 规格 | 4 vCPU / 8 GiB |
| EIP 带宽 | 100 Mbps |
| EIP 计费 | 按流量后付费 |
| EIP 线路 | BGP |

## 技术依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `tencentcloud-sdk-python` | ≥ 3.0.0 | 腾讯云 VPC API（EIP 释放） |
| `kubernetes` | ≥ 26.1.0 | Kubernetes API（Pod 增删查） |

## EIP 绑定原理

TKE 超级节点通过 Pod annotation 实现 EIP 自动分配，无需预先申请：

```json
eks.tke.cloud.tencent.com/eip-attributes: {
  "InternetMaxBandwidthOut": 100,
  "InternetChargeType": "TRAFFIC_POSTPAID_BY_HOUR",
  "AddressType": "EIP",
  "InternetServiceProvider": "BGP"
}
eks.tke.cloud.tencent.com/eip-claim-delete-policy: "Never"
```

`eip-claim-delete-policy: Never` 表示 Pod 删除时 EIP **不自动释放**，需调用 `delete_pod.py` 手动释放，防止意外丢失 IP。

## 文档

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 详细操作手册（含常见问题） |
| [docs/design.md](docs/design.md) | 系统设计与架构文档 |
| [docs/sdk-usage.md](docs/sdk-usage.md) | SDK 调用详细说明（含代码示例） |

## 参考资料

- [TKE 超级节点 Pod 直通 EIP 官方文档](https://cloud.tencent.com/document/product/457/64886)
- [腾讯云 Python SDK](https://github.com/TencentCloud/tencentcloud-sdk-python)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
