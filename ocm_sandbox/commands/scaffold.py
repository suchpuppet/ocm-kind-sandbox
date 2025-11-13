"""
Generate OCM ClusterSet scaffolding resources.

Creates the necessary OCM resources to get started:
- ManagedClusterSetBinding
- Placement
- ManifestWorkReplicaSet with namespace manifest
"""

from pathlib import Path
from typing import List, Dict, Any
import yaml
import typer
from rich.console import Console

console = Console()


def generate_scaffolding_manifests(
    name: str, namespace: str, clusterset: str, placement: str
) -> List[Dict[str, Any]]:
    """Generate scaffolding manifests."""
    manifests = [
        {
            "apiVersion": "cluster.open-cluster-management.io/v1beta2",
            "kind": "ManagedClusterSetBinding",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"clusterSet": clusterset},
        },
        {
            "apiVersion": "cluster.open-cluster-management.io/v1beta1",
            "kind": "Placement",
            "metadata": {"name": placement, "namespace": namespace},
            "spec": {"clusterSets": [clusterset]},
        },
        {
            "apiVersion": "work.open-cluster-management.io/v1alpha1",
            "kind": "ManifestWorkReplicaSet",
            "metadata": {"name": f"{namespace}-namespace-mwrs", "namespace": namespace},
            "spec": {
                "placementRefs": [{"name": placement}],
                "manifestWorkTemplate": {
                    "workload": {"manifests": [{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}]}
                },
            },
        },
    ]
    return manifests


def scaffold_command(
    name: str = typer.Option("default", "--name", "-n", help="Name of the ManagedClusterSetBinding"),
    namespace: str = typer.Option("default", "--namespace", "-N", help="Namespace for the resources"),
    clusterset: str = typer.Option("default", "--clusterset", "-c", help="ClusterSet name"),
    placement: str = typer.Option("clusterset-placement", "--placement", "-p", help="Placement name"),
    output: Path = typer.Option("scaffolding.yaml", "--output", "-o", help="Output file name"),
) -> None:
    """
    Generate ClusterSet scaffolding YAML with namespace ManifestWorkReplicaSet.

    This command creates the basic OCM scaffolding resources needed to deploy
    workloads to managed clusters:

    \b
    1. ManagedClusterSetBinding - Binds a ClusterSet to a namespace
    2. Placement - Selects clusters from the ClusterSet
    3. ManifestWorkReplicaSet - Creates namespace on selected clusters

    \b
    Example:
        # Generate scaffolding for 'production' namespace
        ocm-sandbox scaffold -n prod-binding -N production -c production -p prod-placement

    \b
    After generation, apply to hub:
        kubectl apply -f scaffolding.yaml --context kind-ocm-hub
    """
    console.print("[blue]Generating OCM scaffolding resources...[/blue]")
    console.print(f"  Name: {name}")
    console.print(f"  Namespace: {namespace}")
    console.print(f"  ClusterSet: {clusterset}")
    console.print(f"  Placement: {placement}")

    manifests = generate_scaffolding_manifests(name, namespace, clusterset, placement)

    with open(output, "w") as f:
        for manifest in manifests:
            yaml.dump(manifest, f, default_flow_style=False)
            f.write("---\n")

    console.print(f"\n[green]Success! Generated {output}[/green]")
    console.print(f"\n[yellow]Next steps:[/yellow]")
    console.print(f"  kubectl apply -f {output} --context kind-ocm-hub")
    console.print(f"  kubectl get managedclusters --context kind-ocm-hub")
