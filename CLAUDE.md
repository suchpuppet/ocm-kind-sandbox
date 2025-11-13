# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OCM KIND Sandbox** is a local development environment for Open Cluster Management (OCM). It provides a Makefile-driven workflow to bootstrap multi-cluster OCM setups using Kind (Kubernetes in Docker) and includes Python utilities for working with OCM resources.

**Purpose**: Enable developers to quickly spin up local OCM hub and spoke clusters for testing multi-cluster applications, ManifestWorkReplicaSets, Placements, and other OCM features without needing access to remote clusters.

## Development Environment

**Python Version**: 3.11+ (specified in `.python-version` and `pyproject.toml`)

**Dependency Management**: Poetry (see `pyproject.toml`)

**Required Tools**:
- `docker` or `podman` (container runtime)
- `kind` (Kubernetes in Docker)
- `kubectl` (Kubernetes CLI)
- `clusteradm` (OCM CLI tool)
- **macOS ONLY**: `docker-mac-net-connect` - **CRITICAL** for spoke-to-hub communication
  - Install: `brew install chipmk/tap/docker-mac-net-connect`
  - Start: `sudo brew services start chipmk/tap/docker-mac-net-connect`
  - Without this, spoke clusters CANNOT reach the hub on macOS

**Optional Tools**:
- `poetry` (Python dependency management - required for CLI development)
- `pipx` (for global CLI installation)
- `sonar-scanner` (for code quality)

## Quick Start for New Developers

```bash
# FIRST: Verify prerequisites (especially docker-mac-net-connect on macOS)
./scripts/check-prerequisites.sh

# OPTIONAL: Install OCM Sandbox CLI
make install              # Install with Poetry (use 'poetry run ocm-sandbox')
# OR
make install-global       # Install globally with pipx (use 'ocm-sandbox' directly)
# OR
poetry shell              # Activate venv (use 'ocm-sandbox' directly in this shell)

# Bootstrap complete OCM environment (hub + 2 spokes)
make bootstrap-kind-ocm

# Verify clusters are ready
kubectl get managedclusters --context kind-ocm-hub

# Clean up when done
make kind-delete-ocm
```

## Common Commands

### OCM Bootstrap & Management

```bash
make bootstrap-kind-ocm    # Full bootstrap: hub + 2 spoke clusters with OCM
make kind-create-hub       # Create hub cluster only
make kind-create-spoke     # Create spoke cluster only
make ocm-init-hub          # Initialize OCM on hub cluster
make ocm-enable-mwrs       # Enable ManifestWorkReplicaSet feature
make ocm-join-spoke        # Join spoke to hub
make kind-delete-ocm       # Delete all clusters
make load-images-to-kind   # Load Docker image into Kind (requires IMG=image:tag)
make load-images-from-config # Load images from images.yaml config file
```

### OCM Sandbox CLI

```bash
# Three ways to use the CLI:
poetry run ocm-sandbox --help        # Option 1: With poetry run prefix
poetry shell && ocm-sandbox --help   # Option 2: Activate shell first
make install-global && ocm-sandbox   # Option 3: Global install with pipx

# CLI Commands
ocm-sandbox wrap --help              # Convert Helm charts to MWRS
ocm-sandbox scaffold --help          # Generate OCM scaffolding
ocm-sandbox load-images --help       # Load images to Kind clusters

# Example: Wrap Helm chart
helm template myapp ./chart > rendered.yaml
ocm-sandbox wrap -i rendered.yaml -n myapp -N default -p default-placement

# Example: Generate scaffolding
ocm-sandbox scaffold -n default -N myapp -c default -p myapp-placement

# Example: Load images
ocm-sandbox load-images nginx:alpine redis:7
ocm-sandbox load-images --config images.yaml
```

### Testing and Quality

```bash
make install              # Install dependencies with Poetry
make test                 # Run Python unit tests with pytest
make lint                 # Run linters (pylint, flake8)
make format               # Format code with black and isort
```

### SonarQube

```bash
make sonar-start          # Start SonarQube on http://localhost:9001
make sonar-scan           # Run code analysis
make sonar-status         # Check SonarQube status
make sonar-stop           # Stop SonarQube
make sonar-clean          # Remove SonarQube data volumes
```

## Architecture

### Cluster Layout

- **Hub cluster** (`kind-ocm-hub`): Central OCM control plane
  - Runs OCM controllers (registration, work, placement)
  - Context: `kind-ocm-hub`

- **Spoke clusters** (`kind-ocm-spoke1`, `kind-ocm-spoke2`): Managed clusters
  - Run OCM agents (registration-agent, work-agent)
  - Report status back to hub
  - Contexts: `kind-ocm-spoke1`, `kind-ocm-spoke2`

### OCM Resource Flow

1. **ManifestWorkReplicaSet** (MWRS) created on hub
2. **Placement** selects target spoke clusters
3. MWRS controller creates **ManifestWork** for each selected spoke
4. Work agents on spokes apply manifests to their clusters
5. Status feedback flows back to hub via ManifestWork status

## Code Structure

### OCM Sandbox CLI Package

```
ocm_sandbox/
├── __init__.py           # Package metadata (__version__, __description__)
├── cli.py                # Typer CLI entry point
├── commands/
│   ├── __init__.py
│   ├── wrap.py           # helm_to_mwrs logic (Helm → MWRS conversion)
│   ├── scaffold.py       # generate-clusterset-scaffolding logic
│   └── load_images.py    # load-images-to-kind logic
└── utils/                # Shared utilities (currently empty)
    └── __init__.py
```

### 1. `ocm-sandbox wrap` (ocm_sandbox/commands/wrap.py)

Converts Helm chart templates into OCM ManifestWorkReplicaSet resources.

**Key Features**:
- Automatically extracts CRDs and generates RBAC (ClusterRole/ClusterRoleBinding)
- Splits large workloads into multiple MWRS files (256 KB limit per MWRS)
- Adds intelligent feedback rules:
  - `WellKnownStatus` for common resources (Deployment, StatefulSet, DaemonSet, Job, Pod, Ingress)
  - Custom JSONPaths for CRDs: `observedGeneration`, `deletionTimestamp`

**Usage**:
```bash
helm template my-chart ./chart-dir > rendered.yaml
ocm-sandbox wrap \
  -i rendered.yaml \
  -n my-app-mwrs \
  -N default \
  -p my-placement \
  -o mwrs
# Generates: mwrs_part_1.yaml, mwrs_part_2.yaml, etc.
```

**Key Functions**:
- `build_feedback_for_manifest(m: dict)`: Creates feedback rules based on resource kind
- `extract_crd_resources(helm_templates)`: Extracts CRDs and generates RBAC rules
- `split_manifest_workload(workload, max_size=256KB)`: Splits manifests if too large
- `generate_mwrs_files(...)`: Main function that orchestrates MWRS generation
- `wrap_command(...)`: Typer CLI command entry point

### 2. `ocm-sandbox scaffold` (ocm_sandbox/commands/scaffold.py)

Generates OCM ClusterSet scaffolding: ManagedClusterSetBinding, Placement, and a namespace MWRS.

**Usage**:
```bash
ocm-sandbox scaffold \
  -n default \
  -N metallb-system \
  -c default \
  -p clusterset-placement \
  -o scaffolding.yaml
```

**Key Functions**:
- `generate_scaffolding_manifests(...)`: Returns list of manifests
- `scaffold_command(...)`: Typer CLI command entry point

### 3. `ocm-sandbox load-images` (ocm_sandbox/commands/load_images.py)

Multi-arch Docker image loader for Kind clusters. Supports command-line arguments and YAML configuration files for batch loading.

**Features**:
- Multiple fallback methods for loading images
- YAML configuration file support (requires `pyyaml`)
- Per-image cluster targeting
- Rich terminal output with progress indicators

**Basic Usage**:
```bash
# Single image to default cluster (ocm-hub)
ocm-sandbox load-images nginx:alpine

# Multiple images
ocm-sandbox load-images nginx:alpine redis:7 my-app:latest

# Specific cluster
ocm-sandbox load-images --cluster ocm-spoke1 my-app:latest

# Via Makefile
make load-images-to-kind IMG=my-app:latest CLUSTER=ocm-hub
```

**YAML Configuration**:
```yaml
# images.yaml
images:
  - nginx:alpine
  - redis:7-alpine
  - image: my-app:latest
    cluster: ocm-hub
  - image: spoke-app:v1.0
    cluster: ocm-spoke1
```

```bash
# Load all images from config
ocm-sandbox load-images --config images.yaml
# Or via Makefile
make load-images-from-config
```

**Loading Methods** (tries in order):
1. Direct `kind load docker-image`
2. Docker save/load with archive
3. Platform-specific pull and load
4. Buildx-based platform conversion

**Key Functions**:
- `load_image_with_workaround(...)`: Main loading logic with fallbacks
- `load_images_from_config(...)`: Load from YAML config
- `load_images_command(...)`: Typer CLI command entry point

## macOS Networking (CRITICAL)

### The Problem

On macOS, Docker runs in a VM. Kind clusters (running in Docker containers) can't communicate with each other via normal Kubernetes API addresses:
- Hub API server is exposed on `https://127.0.0.1:xxxxx`
- Spoke containers can't reach `127.0.0.1` (it's the spoke's localhost, not the host)
- Spoke containers need to reach hub container's internal Docker IP
- **Without `docker-mac-net-connect`, container-to-container networking doesn't work on macOS**

### The Solution: docker-mac-net-connect

**`docker-mac-net-connect` is ABSOLUTELY REQUIRED on macOS** for spoke-to-hub communication.

What it does:
- Creates a VPN tunnel between macOS host and Docker containers
- Enables container-to-container networking within Docker Desktop's VM
- Allows Kind clusters (containers) to reach each other via their Docker network IPs

**Install and start**:
```bash
brew install chipmk/tap/docker-mac-net-connect
sudo brew services start chipmk/tap/docker-mac-net-connect
```

### How the Makefile Handles It

The `ocm-patch-spoke-bootstrap` target (automatically called by `bootstrap-kind-ocm`) does:

1. **Creates shared Docker network** named `kind`
   ```bash
   docker network create kind
   docker network connect kind ocm-spoke1-control-plane
   ```

2. **Gets hub's internal Docker IP**
   ```bash
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ocm-hub-control-plane
   # Returns something like: 172.18.0.2
   ```

3. **Patches spoke kubeconfigs** in `open-cluster-management-agent` namespace
   - Secrets: `bootstrap-hub-kubeconfig`, `hub-kubeconfig-secret`
   - Changes: `server: https://127.0.0.1:xxxxx` → `server: https://172.18.0.2:6443`
   - Adds: `tls-server-name: kubernetes` (bypasses cert validation)

4. **Restarts spoke agents**
   ```bash
   kubectl rollout restart deploy/klusterlet-registration-agent -n open-cluster-management-agent
   kubectl rollout restart deploy/klusterlet-work-agent -n open-cluster-management-agent
   ```

**Key Files**:
- Makefile: `ocm-patch-spoke-bootstrap` target (lines 206-344 in original)
- Makefile: `kind-ensure-shared-network` target

### Debugging Network Issues

```bash
# Verify spoke can reach hub
kubectl --context kind-ocm-spoke1 run test --rm -it --image=nicolaka/netshoot -- bash
# Inside pod:
HUB_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ocm-hub-control-plane)
curl -k https://$HUB_IP:6443/healthz

# Check spoke agent logs
kubectl logs -n open-cluster-management-agent deployment/klusterlet-registration-agent --context kind-ocm-spoke1
```

## Makefile Variables

Key environment variables that can be overridden:

- `IMG`: Container image to load into Kind (default: `your-image:latest`)
- `CLUSTERADM_INIT_FLAGS`: OCM feature gates (default: enables `ManagedClusterAutoApproval` and `ManifestWorkReplicaSet`)
- `HUB_CLUSTER`: Hub cluster name (default: `ocm-hub`)
- `SPOKE_CLUSTER`: Spoke cluster name (default: `ocm-spoke1`)
- `SPOKE2_CLUSTER`: Second spoke name (default: `ocm-spoke2`)

**Example**:
```bash
# Use custom cluster names
HUB_CLUSTER=my-hub SPOKE_CLUSTER=my-spoke make bootstrap-kind-ocm

# Load specific image
IMG=my-controller:dev make load-images-to-kind
```

## Testing Strategy

### Unit Tests (Python)

All CLI commands have comprehensive unit tests in `tests/` directory managed with Poetry.

**Test structure**:
```bash
tests/
├── test_cli.py                               # Tests for CLI entry points (Typer)
├── test_helm_to_mwrs.py                      # Tests for wrap command logic
├── test_generate_clusterset_scaffolding.py   # Tests for scaffold command logic
└── test_load_images_to_kind.py               # Tests for load-images command logic
```

**Running tests**:
```bash
# Install dependencies with Poetry
poetry install

# Run all tests
make test
# or directly: poetry run pytest tests/ -v

# Run with coverage
poetry run pytest tests/ --cov=ocm_sandbox --cov-report=term --cov-report=html

# Run linters
make lint
# or: poetry run pylint ocm_sandbox/ && poetry run flake8 ocm_sandbox/

# Format code
make format
# or: poetry run black ocm_sandbox/ tests/ && poetry run isort ocm_sandbox/ tests/
```

**Test coverage includes**:
- **CLI entry points**: Argument parsing, help text, version, error handling
- **wrap command**: API version parsing, feedback generation (WellKnownStatus, JSONPaths), CRD extraction, RBAC generation, manifest splitting
- **scaffold command**: YAML generation for ManagedClusterSetBinding, Placement, and MWRS
- **load-images command**: YAML config parsing, multi-cluster targeting, error handling
- Edge cases and error conditions

**GitHub Actions CI**:
- Tests run on every push/PR
- Multi-platform (Ubuntu, macOS)
- Multi-version (Python 3.11, 3.12)
- Poetry-based dependency management with caching
- Includes linting (pylint, flake8) and code formatting checks (black, isort)
- Shellcheck for bash scripts
- CLI installation verification
- Code coverage uploaded to Codecov

### Integration Tests (End-to-End)

Test OCM setup by running Makefile targets:

```bash
# Test bootstrap
make bootstrap-kind-ocm
kubectl get managedclusters --context kind-ocm-hub

# Test CLI commands
ocm-sandbox scaffold -n default -N test -c default -p test -o test.yaml
kubectl apply -f test.yaml --context kind-ocm-hub
kubectl get manifestworkreplicaset -n test --context kind-ocm-hub

# Cleanup
make kind-delete-ocm
```

## Troubleshooting Guide

### Spoke Registration Fails

**Symptom**: `kubectl get managedclusters` shows spoke stuck in `Pending`

**Solution**:
```bash
# Re-apply networking patch
make ocm-patch-spoke-bootstrap SPOKE_CLUSTER=ocm-spoke1

# Manually approve CSRs
kubectl get csr --context kind-ocm-hub
kubectl certificate approve <csr-name> --context kind-ocm-hub

# Check logs
kubectl logs -n open-cluster-management-agent deployment/klusterlet-registration-agent --context kind-ocm-spoke1
```

### MWRS Not Creating ManifestWork

**Symptom**: MWRS created but no ManifestWork appears

**Solution**:
```bash
# Check placement is selecting clusters
kubectl describe placement <placement-name> -n <namespace> --context kind-ocm-hub

# Verify MWRS references correct placement
kubectl get manifestworkreplicaset <name> -n <namespace> -o yaml --context kind-ocm-hub

# Check MWRS controller logs
kubectl logs -n open-cluster-management-hub deployment/klusterlet-work-controller --context kind-ocm-hub
```

### Hub Components Not Starting

**Symptom**: OCM controllers crashing or not ready

**Solution**:
```bash
# Check pod status
kubectl get pods -n open-cluster-management-hub --context kind-ocm-hub
kubectl get pods -n open-cluster-management --context kind-ocm-hub

# Check events
kubectl get events -n open-cluster-management-hub --context kind-ocm-hub --sort-by='.lastTimestamp'

# Restart components
kubectl rollout restart deployment -n open-cluster-management-hub --context kind-ocm-hub
```

## Code Patterns

### Adding New Resource Types to helm_to_mwrs.py

When adding support for a new Kubernetes resource type:

1. Update `build_feedback_for_manifest()` function
2. Add resource type to `builtins` set if it has well-known status
3. Define JSONPaths for resource-specific fields
4. Update `kind_to_resource_plural()` if plural is non-standard

**Example** (adding CronJob):
```python
builtins = {"deployment", "statefulset", "daemonset", "job", "pod", "ingress", "cronjob"}

if k_low == "cronjob":
    json_paths = [
        {"name": "LastScheduleTime", "path": ".status.lastScheduleTime"},
        {"name": "Active", "path": ".status.active"},
        {"name": "DeletionTimestamp", "path": ".metadata.deletionTimestamp"},
    ]
```

### Adding Makefile Targets

Follow existing patterns:

```makefile
.PHONY: my-target
my-target: ## Description shown in help
	@echo "Doing something..."
	# Commands here
```

**Best practices**:
- Use `.PHONY` for all non-file targets
- Add `##` comment for help text
- Use `@echo` for user-facing messages
- Use `@` prefix to hide command echo for clean output

## File Reference

### Configuration Files

- **Makefile**: Main automation (OCM bootstrap, testing, SonarQube)
- **sonar-project.properties**: SonarQube configuration (Python + Bash)
- **docker-compose.sonar.yml**: SonarQube + PostgreSQL stack
- **.python-version**: Python version (3.11.11)

### Scripts

- **scripts/check-prerequisites.sh**: Prerequisites verification script (Bash) - checks all required tools
- **scripts/helm_to_mwrs.py**: Helm to MWRS converter (Python)
- **scripts/generate-clusterset-scaffolding.py**: OCM scaffolding generator (Python)
- **scripts/load-images-to-kind.py**: Multi-arch image loader with YAML config support (Python)
- **images.yaml.example**: Example configuration for batch image loading

### Documentation

- **README.md**: User-facing documentation with quick start
- **CLAUDE.md**: This file - developer/AI assistant context

## Development Workflow

### Typical Development Session

1. **Start fresh environment**
   ```bash
   make bootstrap-kind-ocm
   ```

2. **Make changes** to Python scripts or Makefile

3. **Test changes**
   ```bash
   # Test Python script
   ./scripts/helm_to_mwrs.py -i test.yaml -n test -N default -p default -o test-mwrs

   # Apply to hub
   kubectl apply -f test-mwrs_part_1.yaml --context kind-ocm-hub

   # Verify on spoke
   kubectl get all -n default --context kind-ocm-spoke1
   ```

4. **Run quality checks**
   ```bash
   make lint
   make test
   ```

5. **Clean up**
   ```bash
   make kind-delete-ocm
   ```

### Adding New Features

**For Makefile targets**:
1. Add target with `.PHONY` and `##` help text
2. Test manually
3. Update README.md with new target

**For Python scripts**:
1. Add/modify functions in scripts/
2. Add unit tests in tests/
3. Run `make lint-python`
4. Update README.md with usage examples

**For OCM patterns**:
1. Create example YAML in documentation
2. Test with `make bootstrap-kind-ocm`
3. Document in README.md

## Resources

- [OCM Documentation](https://open-cluster-management.io/)
- [Kind Documentation](https://kind.sigs.k8s.io/)
- [ManifestWorkReplicaSet API](https://open-cluster-management.io/concepts/manifestworkreplicaset/)
- [OCM GitHub](https://github.com/open-cluster-management-io)
