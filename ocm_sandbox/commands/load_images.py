"""
Load Docker images into Kind clusters with multi-arch workarounds.

This module handles the common multi-arch image loading issues with Kind by trying
multiple methods to ensure images are properly loaded into Kind clusters.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

console = Console()


def run_command(cmd: List[str], check: bool = False, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(cmd, capture_output=capture_output, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e


def check_kind_cluster(cluster_name: str) -> bool:
    """Check if Kind cluster exists."""
    result = run_command(["kind", "get", "clusters"])
    if result.returncode != 0:
        console.print("[red]Error: Failed to list Kind clusters[/red]")
        return False

    clusters = result.stdout.strip().split("\n")
    if cluster_name in clusters:
        console.print(f"[green]✓[/green] Kind cluster '{cluster_name}' found")
        return True
    else:
        console.print(f"[red]Error: Kind cluster '{cluster_name}' not found![/red]")
        console.print("[yellow]Available clusters:[/yellow]")
        for cluster in clusters:
            console.print(f"  - {cluster}")
        console.print(f"\n[yellow]Create a cluster with:[/yellow] kind create cluster --name {cluster_name}")
        return False


def load_image_direct(image: str, cluster_name: str) -> bool:
    """Try direct kind load (Method 1)."""
    console.print(f"[blue]Method 1:[/blue] Direct load of {image}")
    result = run_command(["kind", "load", "docker-image", image, "--name", cluster_name])
    if result.returncode == 0:
        console.print(f"[green]✓[/green] Loaded {image} directly")
        return True
    return False


def load_image_archive(image: str, cluster_name: str) -> bool:
    """Try docker save/load with archive (Method 2)."""
    console.print("[blue]Method 2:[/blue] Creating platform-specific image archive")
    safe_name = image.replace("/", "_").replace(":", "_")
    temp_file = f"/tmp/kind-image-{safe_name}.tar"

    try:
        # Save image to tar
        result = run_command(["docker", "save", image, "-o", temp_file])
        if result.returncode != 0:
            return False

        # Load into kind
        result = run_command(["kind", "load", "image-archive", temp_file, "--name", cluster_name])
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Loaded {image} via archive method")
            return True
    finally:
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return False


def load_image_platform_pull(image: str, cluster_name: str, platform: str) -> bool:
    """Try pulling with specific platform and retry (Method 3)."""
    # Only works for registry images
    if "." not in image.split(":")[0] and "/" not in image.split(":")[0]:
        console.print("[dim]Method 3: Skipped (local image, no registry to pull from)[/dim]")
        return False

    console.print(f"[blue]Method 3:[/blue] Pulling with specific platform ({platform})")
    platform_image = f"{image}-kind-temp"

    try:
        # Pull with platform
        result = run_command(["docker", "pull", "--platform", platform, image])
        if result.returncode != 0:
            return False

        # Tag
        run_command(["docker", "tag", image, platform_image])

        # Load
        result = run_command(["kind", "load", "docker-image", platform_image, "--name", cluster_name])
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Loaded {image} via platform-specific pull")
            return True
    finally:
        # Clean up temp image
        run_command(["docker", "rmi", platform_image])

    return False


def load_image_buildx(image: str, cluster_name: str, platform: str) -> bool:
    """Try using buildx to create platform-specific image (Method 4)."""
    # Check if buildx is available
    result = run_command(["docker", "buildx", "version"])
    if result.returncode != 0:
        console.print("[dim]Method 4: Skipped (buildx not available)[/dim]")
        return False

    console.print("[blue]Method 4:[/blue] Creating platform-specific image with buildx")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
        f.write(f"FROM {image}\n")
        temp_dockerfile = f.name

    try:
        # Build with platform
        result = run_command(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                platform,
                "--load",
                "-t",
                f"{image}-kind",
                "-f",
                temp_dockerfile,
                ".",
            ]
        )
        if result.returncode != 0:
            return False

        # Load
        result = run_command(["kind", "load", "docker-image", f"{image}-kind", "--name", cluster_name])
        if result.returncode == 0:
            console.print(f"[green]✓[/green] Loaded {image} via buildx method")
            run_command(["docker", "rmi", f"{image}-kind"])
            return True

        run_command(["docker", "rmi", f"{image}-kind"])
    finally:
        if os.path.exists(temp_dockerfile):
            os.remove(temp_dockerfile)

    return False


def load_image_with_workaround(image: str, cluster_name: str, platform: str = "linux/amd64") -> bool:
    """Load image with multi-arch workarounds."""
    console.print(f"\n[bold]Loading image:[/bold] {image}")

    # Method 1: Direct load
    if load_image_direct(image, cluster_name):
        return True

    console.print("[yellow]Direct load failed, trying multi-arch workarounds...[/yellow]")

    # Method 2: Archive
    if load_image_archive(image, cluster_name):
        return True

    # Method 3: Platform pull
    if load_image_platform_pull(image, cluster_name, platform):
        return True

    # Method 4: Buildx
    if load_image_buildx(image, cluster_name, platform):
        return True

    console.print(f"[red]Error: All methods failed for {image}[/red]")
    console.print("\n[yellow]Suggestions:[/yellow]")
    console.print(f"  1. Rebuild the image for platform {platform}")
    console.print("  2. Use a multi-arch base image")
    console.print(f"  3. Check if the image is available from a registry with {platform} support")

    return False


def load_images_from_config(config_path: Path, cluster_name: str, platform: str) -> int:
    """Load images from YAML configuration file."""
    if not YAML_AVAILABLE:
        console.print("[red]Error: PyYAML is not installed. Install with: pip install pyyaml[/red]")
        return 1

    if not config_path.exists():
        console.print(f"[red]Error: Configuration file not found: {config_path}[/red]")
        return 1

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error: Failed to parse YAML configuration: {e}[/red]")
        return 1

    if not config or "images" not in config:
        console.print("[red]Error: Configuration file must contain an 'images' list[/red]")
        return 1

    images = config["images"]
    if not isinstance(images, list):
        console.print("[red]Error: 'images' must be a list[/red]")
        return 1

    loaded_count = 0
    failed_count = 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task(f"Processing {len(images)} images...", total=len(images))

        for item in images:
            if isinstance(item, str):
                # Simple format: just image name
                image = item
                target_cluster = cluster_name
            elif isinstance(item, dict):
                # Advanced format: {image: "name", cluster: "cluster-name"}
                image = item.get("image")
                target_cluster = item.get("cluster", cluster_name)
                if not image:
                    console.print(f"[yellow]Warning: Skipping invalid entry: {item}[/yellow]")
                    continue
            else:
                console.print(f"[yellow]Warning: Skipping invalid entry: {item}[/yellow]")
                continue

            progress.update(task, description=f"Processing: {image} -> {target_cluster}")

            # Check cluster exists
            if not check_kind_cluster(target_cluster):
                failed_count += 1
                progress.advance(task)
                continue

            # Load image
            if load_image_with_workaround(image, target_cluster, platform):
                loaded_count += 1
            else:
                failed_count += 1

            progress.advance(task)

    console.print(f"\n[green]Successfully loaded {loaded_count} images[/green]")
    if failed_count > 0:
        console.print(f"[yellow]Failed to load {failed_count} images[/yellow]")

    return 0 if failed_count == 0 else 1


def load_images_command(
    images: List[str] = typer.Argument(None, help="Docker images to load (e.g., nginx:latest, my-app:v1.0)"),
    cluster: str = typer.Option(
        os.environ.get("KIND_CLUSTER", "ocm-hub"), "--cluster", "-c", help="Kind cluster name"
    ),
    platform: str = typer.Option(
        os.environ.get("DOCKER_PLATFORM", "linux/amd64"), "--platform", "-p", help="Target platform"
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="YAML configuration file with images to load"),
) -> None:
    """
    Load Docker images into Kind clusters with multi-arch workarounds.

    This command handles multi-arch image loading issues by trying multiple
    methods to ensure images are properly loaded.

    \b
    Methods tried (in order):
    1. Direct kind load
    2. Docker save/load with archive
    3. Platform-specific pull
    4. Buildx with platform specification

    \b
    Examples:
        # Load specific images to default cluster
        ocm-sandbox load-images my-app:latest nginx:alpine

        # Load to specific cluster
        ocm-sandbox load-images --cluster ocm-spoke1 my-app:latest

        # Load from configuration file
        ocm-sandbox load-images --config images.yaml

        # Use different platform
        ocm-sandbox load-images --platform linux/arm64 my-app:latest
    """
    # Check prerequisites
    if subprocess.run(["which", "kind"], capture_output=True).returncode != 0:
        console.print("[red]Error: kind command not found! Please install Kind first.[/red]")
        console.print("[yellow]Install: https://kind.sigs.k8s.io/docs/user/quick-start/#installation[/yellow]")
        raise typer.Exit(1)

    if subprocess.run(["which", "docker"], capture_output=True).returncode != 0:
        console.print("[red]Error: docker command not found! Please install Docker first.[/red]")
        raise typer.Exit(1)

    # Verify cluster exists
    if not check_kind_cluster(cluster):
        raise typer.Exit(1)

    # Load from config file
    if config:
        result = load_images_from_config(config, cluster, platform)
        raise typer.Exit(result)

    # Load from command line arguments
    if not images:
        console.print("[red]Error: No images specified. Use --config or provide images as arguments.[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]Loading {len(images)} image(s) into Kind cluster: {cluster}[/blue]")
    console.print(f"[blue]Target platform: {platform}[/blue]")

    loaded_count = 0
    failed_count = 0

    for image in images:
        if load_image_with_workaround(image, cluster, platform):
            loaded_count += 1
        else:
            failed_count += 1

    console.print(f"\n[green]Image loading completed! Loaded {loaded_count}/{len(images)} images[/green]")

    if failed_count > 0:
        console.print(f"[yellow]Failed to load {failed_count} images[/yellow]")
        raise typer.Exit(1)
