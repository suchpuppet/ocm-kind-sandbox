"""
OCM Sandbox CLI - Local development tools for Open Cluster Management.

A command-line tool for bootstrapping and managing OCM environments in Kind clusters.
"""

import typer
from rich.console import Console
from ocm_sandbox import __version__, __description__
from ocm_sandbox.commands.wrap import wrap_command
from ocm_sandbox.commands.scaffold import scaffold_command
from ocm_sandbox.commands.load_images import load_images_command

console = Console()

# Create main Typer app
app = typer.Typer(
    name="ocm-sandbox",
    help=__description__,
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        console.print(f"ocm-sandbox version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
):
    """
    OCM Sandbox - Local development tools for Open Cluster Management.

    \b
    A CLI tool for:
    - Converting Helm charts to ManifestWorkReplicaSets
    - Generating OCM ClusterSet scaffolding
    - Loading Docker images into Kind clusters

    \b
    Common workflow:
        1. Bootstrap OCM environment:
           make bootstrap-kind-ocm

        2. Generate scaffolding:
           ocm-sandbox scaffold -N myapp -p myapp-placement

        3. Wrap Helm chart:
           helm template myapp ./chart > rendered.yaml
           ocm-sandbox wrap -i rendered.yaml -n myapp -N myapp -p myapp-placement

        4. Load custom images:
           ocm-sandbox load-images my-app:latest --cluster ocm-hub

    \b
    For more information:
        https://open-cluster-management.io/
    """
    pass


# Register commands
app.command(name="wrap", help="Convert Helm templates to ManifestWorkReplicaSet")(wrap_command)
app.command(name="scaffold", help="Generate OCM ClusterSet scaffolding")(scaffold_command)
app.command(name="load-images", help="Load Docker images into Kind clusters")(load_images_command)


if __name__ == "__main__":
    app()
