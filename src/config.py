"""
Shared configuration for TKE Supernode EIP Pod management scripts.

Required environment variables:
  TENCENTCLOUD_SECRET_ID    Tencent Cloud API Secret ID
  TENCENTCLOUD_SECRET_KEY   Tencent Cloud API Secret Key

Kubernetes authentication (choose one approach):

  Approach 1 — KUBECONFIG file (recommended):
    export KUBECONFIG=/path/to/kubeconfig.yaml

  Approach 2 — Individual TLS env vars:
    export K8S_SERVER=https://<api-server-ip>
    export K8S_CA_DATA=<base64-encoded-ca-cert>
    export K8S_CERT_DATA=<base64-encoded-client-cert>
    export K8S_KEY_DATA=<base64-encoded-client-private-key>

  Download your kubeconfig from TKE Console:
    https://console.cloud.tencent.com/tke2 → Cluster → Basic Info → Kubeconfig

Provides:
  get_k8s_client()  -> kubernetes.client.CoreV1Api
  get_vpc_client()  -> tencentcloud VpcClient (ap-beijing)
"""
import os
import tempfile

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.vpc.v20170312 import vpc_client
from kubernetes import client as k8s_client, config as k8s_config

# ── Cluster constants ──────────────────────────────────────────────────────────
REGION = "ap-beijing"
CLUSTER_ID = "cls-5mchtmid"
NAMESPACE = "eip-pods"


def get_credentials():
    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    if not secret_id or not secret_key:
        raise EnvironmentError(
            "Missing credentials: set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY"
        )
    return credential.Credential(secret_id, secret_key)


def get_k8s_client():
    """
    Return a configured CoreV1Api.

    Priority:
      1. KUBECONFIG env var — path to a kubeconfig file (recommended)
      2. K8S_SERVER + K8S_CA_DATA + K8S_CERT_DATA + K8S_KEY_DATA env vars
    """
    kubeconfig_path = os.environ.get("KUBECONFIG")

    if not kubeconfig_path:
        # Build kubeconfig from individual TLS env vars
        server = os.environ.get("K8S_SERVER")
        ca_data = os.environ.get("K8S_CA_DATA")
        cert_data = os.environ.get("K8S_CERT_DATA")
        key_data = os.environ.get("K8S_KEY_DATA")

        missing = [name for name, val in [
            ("K8S_SERVER", server), ("K8S_CA_DATA", ca_data),
            ("K8S_CERT_DATA", cert_data), ("K8S_KEY_DATA", key_data),
        ] if not val]

        if missing:
            raise EnvironmentError(
                f"Missing Kubernetes config. Set KUBECONFIG or all of: "
                f"{', '.join(missing)}\n"
                "See README.md for setup instructions."
            )

        kubeconfig_yaml = f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {ca_data}
    server: {server}
  name: {CLUSTER_ID}
contexts:
- context:
    cluster: {CLUSTER_ID}
    user: tke-user
  name: {CLUSTER_ID}-context
current-context: {CLUSTER_ID}-context
kind: Config
preferences: {{}}
users:
- name: tke-user
  user:
    client-certificate-data: {cert_data}
    client-key-data: {key_data}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(kubeconfig_yaml)
            kubeconfig_path = f.name

    k8s_config.load_kube_config(config_file=kubeconfig_path)
    return k8s_client.CoreV1Api()


def get_vpc_client():
    """Return a VPC SDK client for ap-beijing."""
    cred = get_credentials()
    http_profile = HttpProfile()
    http_profile.endpoint = "vpc.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return vpc_client.VpcClient(cred, REGION, client_profile)
