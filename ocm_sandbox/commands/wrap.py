"""
Wrap Helm charts into OCM ManifestWorkReplicaSets.

Converts Helm chart templates into OCM ManifestWorkReplicaSet resources with:
- Automatic CRD detection and RBAC generation
- Smart status feedback configuration (WellKnownStatus for built-in resources)
- Automatic 256KB splitting for large manifests
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

# Constants
MAX_FILE_SIZE = 256 * 1024  # 256 KB size limit for MWRS


def split_apiversion(api_version: str) -> Tuple[str, str]:
    """Split API version into group and version."""
    if "/" in api_version:
        group, version = api_version.split("/", 1)
    else:
        group, version = "", api_version
    return group, version


def kind_to_resource_plural(kind: str) -> str:
    """Convert Kind to resource plural name."""
    k = (kind or "").lower()
    special = {
        "endpoints": "endpoints",
        "ingress": "ingresses",
        "networkpolicy": "networkpolicies",
        "configmap": "configmaps",
        "secret": "secrets",
        "serviceaccount": "serviceaccounts",
        "persistentvolumeclaim": "persistentvolumeclaims",
        "rolebinding": "rolebindings",
        "clusterrole": "clusterroles",
        "clusterrolebinding": "clusterrolebindings",
        "horizontalpodautoscaler": "horizontalpodautoscalers",
        "poddisruptionbudget": "poddisruptionbudgets",
        "statefulset": "statefulsets",
        "daemonset": "daemonsets",
        "deployment": "deployments",
        "job": "jobs",
        "cronjob": "cronjobs",
        "service": "services",
        "pod": "pods",
    }
    return special.get(k, f"{k}s")


def build_feedback_for_manifest(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build feedback configuration for a manifest."""
    if not isinstance(m, dict):
        return None
    api_version = m.get("apiVersion", "")
    kind = m.get("kind", "")
    meta = m.get("metadata", {}) or {}
    name = meta.get("name")
    namespace = meta.get("namespace")
    if not kind or not name:
        return None
    group, _ = split_apiversion(api_version)
    resource = kind_to_resource_plural(kind)

    k_low = kind.lower()
    builtins = {"deployment", "statefulset", "daemonset", "job", "pod", "ingress"}
    if k_low in builtins:
        rules = [{"type": "WellKnownStatus"}]
        # Only add JSONPaths for fields NOT covered by WellKnownStatus
        json_paths = []
        if k_low in ["deployment", "statefulset"]:
            json_paths = [
                {"name": "SpecReplicas", "path": ".spec.replicas"},
                {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
            ]
        elif k_low == "daemonset":
            json_paths = [
                {"name": "DesiredNumberScheduled", "path": ".status.desiredNumberScheduled"},
                {"name": "NumberAvailable", "path": ".status.numberAvailable"},
                {"name": "UpdatedNumberScheduled", "path": ".status.updatedNumberScheduled"},
                {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
            ]
        elif k_low == "job":
            json_paths = [
                {"name": "Succeeded", "path": ".status.succeeded"},
                {"name": "Failed", "path": ".status.failed"},
                {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
            ]
        elif k_low == "pod":
            json_paths = [
                {"name": "Phase", "path": ".status.phase"},
                {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
            ]
        elif k_low == "ingress":
            json_paths = [
                {"name": "LBIPs", "path": ".status.loadBalancer.ingress[*].ip"},
                {"name": "LBHosts", "path": ".status.loadBalancer.ingress[*].hostname"},
                {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
            ]
        if json_paths:
            rules.append({"type": "JSONPaths", "jsonPaths": json_paths})
        return {
            "resourceIdentifier": {
                "group": group,
                "resource": resource,
                "name": name,
                "namespace": namespace,
            },
            "feedbackRules": rules,
        }

    # For other kinds (CRDs/custom), use robust JSONPaths
    json_paths = [
        {"name": "ObservedGeneration", "path": ".status.observedGeneration"},
        {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
    ]
    return {
        "resourceIdentifier": {
            "group": group,
            "resource": resource,
            "name": name,
            "namespace": namespace,
        },
        "feedbackRules": [{"type": "JSONPaths", "jsonPaths": json_paths}],
    }


def extract_crd_resources(helm_templates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Extract CRD-related API groups and resources for RBAC generation."""
    rbac_rules = {}

    for manifest in helm_templates:
        if isinstance(manifest, dict) and manifest.get("kind") == "CustomResourceDefinition":
            api_group = manifest["spec"]["group"]
            resources = [manifest["spec"]["names"]["plural"]]
            verbs = ["get", "list", "watch", "create", "update", "patch", "delete"]

            if api_group not in rbac_rules:
                rbac_rules[api_group] = {"resources": set(), "verbs": set()}

            rbac_rules[api_group]["resources"].update(resources)
            rbac_rules[api_group]["verbs"].update(verbs)

    return rbac_rules


def create_rbac_manifests(rbac_rules: Dict[str, Dict[str, Any]], role_name: str) -> List[Dict[str, Any]]:
    """Create ClusterRole and ClusterRoleBinding for Klusterlet service account."""
    if not rbac_rules:
        return []

    cluster_role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": role_name},
        "rules": [],
    }

    for api_group, data in rbac_rules.items():
        cluster_role["rules"].append(
            {"apiGroups": [api_group], "resources": list(data["resources"]), "verbs": list(data["verbs"])}
        )

    cluster_role_binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": f"{role_name}-binding"},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": role_name},
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": "klusterlet-work-sa",
                "namespace": "open-cluster-management-agent",
            }
        ],
    }

    return [cluster_role, cluster_role_binding]


def split_manifest_workload(
    workload: List[Dict[str, Any]], max_size: int = MAX_FILE_SIZE
) -> List[List[Dict[str, Any]]]:
    """Split workloads into multiple MWRS files if necessary."""
    split_workloads = []
    current_workload = []
    current_size = 0

    for manifest in workload:
        manifest_yaml = yaml.dump(manifest, default_flow_style=False)
        manifest_size = len(manifest_yaml.encode("utf-8"))

        if current_size + manifest_size > max_size:
            split_workloads.append(current_workload)
            current_workload = []
            current_size = 0

        current_workload.append(manifest)
        current_size += manifest_size

    if current_workload:
        split_workloads.append(current_workload)

    return split_workloads


def generate_mwrs_files(
    helm_templates: List[Dict[str, Any]],
    name: str,
    namespace: str,
    placement: str,
    output_prefix: str,
) -> List[str]:
    """Generate MWRS files with dynamic splitting and RBAC handling."""
    rbac_rules = extract_crd_resources(helm_templates)
    rbac_manifests = create_rbac_manifests(rbac_rules, role_name=f"{name}-rbac-role")

    # Include RBAC manifests in the first workload set
    if rbac_manifests:
        helm_templates.extend(rbac_manifests)

    split_workloads = split_manifest_workload(helm_templates)
    output_files = []

    for index, workload in enumerate(split_workloads):
        # Build feedback for the manifests in this split
        manifest_configs = []
        for m in workload:
            cfg = build_feedback_for_manifest(m)
            if cfg:
                manifest_configs.append(cfg)
        filename = f"{output_prefix}_part_{index+1}.yaml"
        mwrs_content = {
            "apiVersion": "work.open-cluster-management.io/v1alpha1",
            "kind": "ManifestWorkReplicaSet",
            "metadata": {
                "name": f"{name}-{index+1}",
                "namespace": namespace,
            },
            "spec": {
                "cascadeDeletionPolicy": "Background",
                "placementRefs": [{"name": placement}],
                "manifestWorkTemplate": {"manifestConfigs": manifest_configs, "workload": {"manifests": workload}},
            },
        }
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump(mwrs_content, f, default_flow_style=False)
        output_files.append(filename)

    return output_files


def wrap_command(
    input_file: Path = typer.Option(..., "--input", "-i", help="Input rendered Helm YAML file"),
    name: str = typer.Option(..., "--name", "-n", help="Name of the MWRS"),
    namespace: str = typer.Option(..., "--namespace", "-N", help="Namespace for the MWRS"),
    placement: str = typer.Option(..., "--placement", "-p", help="Placement name for MWRS"),
    output: str = typer.Option("mwrs", "--output", "-o", help="Output file prefix"),
) -> None:
    """
    Convert Helm templates to ManifestWorkReplicaSet with RBAC and automatic splitting.

    This command takes rendered Helm templates and converts them into OCM
    ManifestWorkReplicaSet resources. It automatically:

    \b
    - Detects CRDs and generates appropriate RBAC
    - Configures status feedback (WellKnownStatus for built-ins)
    - Splits large manifests into multiple files (256KB limit)

    \b
    Example:
        # Render Helm chart and wrap it
        helm template my-app ./my-chart > rendered.yaml
        ocm-sandbox wrap -i rendered.yaml -n my-app -N default -p my-placement
    """
    if not input_file.exists():
        console.print(f"[red]Error: Input file not found: {input_file}[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Reading Helm templates from:[/blue] {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        helm_templates = [doc for doc in yaml.safe_load_all(f) if doc is not None]

    console.print(f"[blue]Found {len(helm_templates)} manifests[/blue]")

    output_files = generate_mwrs_files(helm_templates, name, namespace, placement, output)

    # Display results in a nice table
    table = Table(title="Generated MWRS Files")
    table.add_column("File", style="cyan")
    table.add_column("Command", style="green")

    for file in output_files:
        table.add_row(file, f"kubectl apply -f {file} --context kind-ocm-hub")

    console.print(table)
    console.print(f"\n[green]Success! Generated {len(output_files)} MWRS file(s)[/green]")
