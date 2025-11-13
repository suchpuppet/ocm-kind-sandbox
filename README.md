# OCM KIND Sandbox

A streamlined local development environment for [Open Cluster Management (OCM)](https://open-cluster-management.io/) using [Kind](https://kind.sigs.k8s.io/) (Kubernetes in Docker). This repository provides a Makefile-driven workflow and Python utilities to quickly bootstrap a multi-cluster OCM setup on your local machine.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Makefile Targets](#makefile-targets)
- [Python Utilities](#python-utilities)
- [macOS Networking](#macos-networking)
- [Troubleshooting](#troubleshooting)
- [Code Quality with SonarQube](#code-quality-with-sonarqube)
- [LLM Assisted Development](#llm-assisted-development)

## Overview

This repository helps you:
- **Bootstrap OCM clusters locally**: Create hub and spoke Kind clusters with OCM pre-configured
- **Test multi-cluster scenarios**: Experiment with ManifestWorkReplicaSets (MWRS), Placements, and ClusterSets
- **Convert Helm charts to MWRS**: Use Python utilities to transform Helm templates into OCM resources
- **Develop OCM applications**: Test OCM integrations without needing access to remote clusters

**What is OCM?**
Open Cluster Management is a Kubernetes-native project that enables multi-cluster orchestration. It uses a hub-spoke architecture where:
- **Hub cluster**: Central management plane that coordinates workload distribution
- **Spoke clusters**: Managed clusters that run workloads and report status back to the hub

## Prerequisites

### Required Tools

**All Platforms:**
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (macOS/Windows) or Docker Engine (Linux)
- **[Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)** - Kubernetes in Docker
- **[kubectl](https://kubernetes.io/docs/tasks/tools/)** - Kubernetes CLI
- **[clusteradm](https://open-cluster-management.io/getting-started/installation/start-the-control-plane/)** - OCM CLI tool

**macOS ONLY:**
- **[docker-mac-net-connect](https://github.com/chipmk/docker-mac-net-connect)** - **REQUIRED** for spoke-to-hub communication
  - Without this, spoke clusters cannot reach the hub cluster
  - Enables container-to-container networking on Docker Desktop for Mac

### Installation Commands

```bash
# macOS (using Homebrew)
brew install kind kubectl

# CRITICAL for macOS: Install docker-mac-net-connect
brew install chipmk/tap/docker-mac-net-connect

# Start docker-mac-net-connect service
sudo brew services start chipmk/tap/docker-mac-net-connect

# Install clusteradm
curl -L https://raw.githubusercontent.com/open-cluster-management-io/clusteradm/main/install.sh | bash

# Verify installations
kind version
kubectl version --client
clusteradm version

# Verify docker-mac-net-connect is running
brew services list | grep docker-mac-net-connect
# Should show: started
```

```bash
# Linux (example for Ubuntu/Debian)
# Install Docker Engine first, then:
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Install clusteradm
curl -L https://raw.githubusercontent.com/open-cluster-management-io/clusteradm/main/install.sh | bash
```

### Optional Tools

- **Python 3.11+** - For using the OCM Sandbox CLI
- **[Poetry](https://python-poetry.org/)** - Python dependency management (recommended for development)
- **[sonar-scanner](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/)** - For code quality analysis

## Quick Start

### 0. Install OCM Sandbox CLI (Optional)

If you want to use the OCM Sandbox CLI tools for wrapping Helm charts and loading images:

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install OCM Sandbox CLI
make install
```

**Three ways to use the CLI:**

**Option 1: Use with `poetry run` prefix** (no activation needed)
```bash
poetry run ocm-sandbox --version
poetry run ocm-sandbox wrap --help
```

**Option 2: Activate Poetry shell** (no prefix needed while shell is active)
```bash
poetry shell          # Activates virtual environment
ocm-sandbox --version # Now works directly!
exit                  # Exit the shell when done
```

**Option 3: Global install with pipx** (always available, no prefix)
```bash
# Install pipx if needed
python3 -m pip install --user pipx

# Install globally
make install-global

# Now available everywhere
ocm-sandbox --version
```

**Note**: The CLI is optional. You can bootstrap OCM clusters without it using `make bootstrap-kind-ocm`.

### 1. Verify Prerequisites

Before starting, verify all required tools are installed:

```bash
./scripts/check-prerequisites.sh
```

This script will check for:
- ✓ Docker and Docker daemon
- ✓ Kind, kubectl, clusteradm
- ✓ **macOS: docker-mac-net-connect** (critical!)
- ⚠ Optional: Python, Poetry, pyyaml

**If any errors are reported, install the missing tools before proceeding.**

### 2. Bootstrap Complete OCM Environment

This single command creates hub + 2 spoke clusters with OCM fully configured:

```bash
make bootstrap-kind-ocm
```

This will:
1. Create 3 Kind clusters: `ocm-hub`, `ocm-spoke1`, `ocm-spoke2`
2. Initialize OCM on the hub cluster with ManifestWorkReplicaSet feature enabled
3. Join both spoke clusters to the hub
4. Configure macOS-compatible networking between clusters
5. Accept spoke registrations and approve certificates

**Wait time**: ~5-10 minutes depending on your system

### 3. Verify the Setup

```bash
# Check that spokes are registered and available
kubectl get managedclusters --context kind-ocm-hub

# Expected output:
# NAME         HUB ACCEPTED   MANAGED CLUSTER URLS   JOINED   AVAILABLE   AGE
# ocm-spoke1   true           https://...            True     True        2m
# ocm-spoke2   true           https://...            True     True        2m
```

### 4. Create a Test MWRS (Optional - requires CLI)

Use the OCM Sandbox CLI to generate OCM scaffolding:

```bash
# Generate scaffolding
poetry run ocm-sandbox scaffold \
  -n default \
  -N test-namespace \
  -c default \
  -p test-placement \
  -o test-scaffolding.yaml

kubectl apply -f test-scaffolding.yaml --context kind-ocm-hub
```

### 5. Clean Up

```bash
make kind-delete-ocm
```

## Architecture

### Cluster Layout

```
┌─────────────────────────────────────────────────────────┐
│                      Local Machine                       │
│                                                           │
│  ┌──────────────┐         ┌──────────────┐              │
│  │  ocm-spoke1  │         │  ocm-spoke2  │              │
│  │  (Kind)      │         │  (Kind)      │              │
│  │              │         │              │              │
│  │ ┌──────────┐ │         │ ┌──────────┐ │              │
│  │ │ Work     │ │         │ │ Work     │ │              │
│  │ │ Agent    │ │         │ │ Agent    │ │              │
│  │ └────┬─────┘ │         │ └────┬─────┘ │              │
│  └──────┼───────┘         └──────┼───────┘              │
│         │                        │                       │
│         │   Registration &       │                       │
│         │   Heartbeat            │                       │
│         │                        │                       │
│         └────────┬───────────────┘                       │
│                  │                                       │
│         ┌────────▼────────┐                              │
│         │    ocm-hub      │                              │
│         │    (Kind)       │                              │
│         │                 │                              │
│         │ ┌─────────────┐ │                              │
│         │ │ Registration│ │                              │
│         │ │ Controller  │ │                              │
│         │ └─────────────┘ │                              │
│         │                 │                              │
│         │ ┌─────────────┐ │                              │
│         │ │ Work        │ │                              │
│         │ │ Controller  │ │                              │
│         │ └─────────────┘ │                              │
│         │                 │                              │
│         │ ┌─────────────┐ │                              │
│         │ │ Placement   │ │                              │
│         │ │ Controller  │ │                              │
│         │ └─────────────┘ │                              │
│         └─────────────────┘                              │
└─────────────────────────────────────────────────────────┘
```

### OCM Resource Flow

```
Hub Cluster                                  Spoke Clusters
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────┐
│ ManifestWorkReplica │
│       Set           │
└──────────┬──────────┘
           │
           │ references
           │
┌──────────▼──────────┐
│    Placement        │
│  (selects spokes)   │
└──────────┬──────────┘
           │
           │ creates
           │
    ┌──────▼──────┐    ┌──────────┐
    │ManifestWork │───▶│ ocm-spoke1│
    │   (spoke1)  │    └──────┬────┘
    └─────────────┘           │
                              │ applies
    ┌─────────────┐           │
    │ManifestWork │    ┌──────▼──────────┐
    │   (spoke2)  │───▶│  Resources      │
    └─────────────┘    │ (Deployments,   │
                       │  Services, etc) │
                       └─────────────────┘
                              │
                              │ feedback
                              │
                       ┌──────▼────────┐
                       │ Status updates│
                       │  back to hub  │
                       └───────────────┘
```

## Makefile Targets

### OCM Bootstrap & Management

| Target | Description |
|--------|-------------|
| `make bootstrap-kind-ocm` | Complete OCM setup (hub + 2 spokes) |
| `make kind-create-hub` | Create hub cluster only |
| `make kind-create-spoke` | Create spoke cluster only |
| `make ocm-init-hub` | Initialize OCM on hub |
| `make ocm-enable-mwrs` | Enable ManifestWorkReplicaSet feature |
| `make ocm-join-spoke` | Join spoke to hub |
| `make kind-delete-ocm` | Delete all clusters |

### Testing & Quality

| Target | Description |
|--------|-------------|
| `make test` | Run Python unit tests (if they exist) |
| `make lint` | Run Python linters (pylint and flake8) |

### SonarQube

| Target | Description |
|--------|-------------|
| `make sonar-start` | Start SonarQube server (http://localhost:9001) |
| `make sonar-scan` | Run code quality scan |
| `make sonar-status` | Check SonarQube status |
| `make sonar-stop` | Stop SonarQube server |
| `make sonar-clean` | Remove SonarQube data volumes |

### Utility

| Target | Description |
|--------|-------------|
| `make help` | Display all available targets |
| `make load-images-to-kind` | Load Docker image into Kind cluster (requires IMG=image:tag) |
| `make load-images-from-config` | Load images from images.yaml configuration file |

## OCM Sandbox CLI

The OCM Sandbox CLI provides three main commands for working with OCM in local Kind clusters.

### Installation

```bash
# Install with make
make install

# Choose how to use it:
# Option 1: poetry run prefix
poetry run ocm-sandbox --version

# Option 2: Activate Poetry shell (recommended for development)
poetry shell
ocm-sandbox --version  # No prefix needed!

# Option 3: Global install (recommended for regular use)
make install-global
ocm-sandbox --version  # Available everywhere!
```

### Commands

#### 1. `ocm-sandbox wrap` - Wrap Helm Charts as MWRS

Converts Helm chart templates into OCM ManifestWorkReplicaSet resources with intelligent features:

**Features**:
- Automatic CRD detection and RBAC generation
- Smart status feedback configuration (WellKnownStatus for built-in resources)
- Automatic 256KB splitting for large manifests

**Usage**:
```bash
# Render Helm chart to YAML
helm template my-app ./my-chart > rendered.yaml

# Convert to MWRS
poetry run ocm-sandbox wrap \
  --input rendered.yaml \
  --name my-app-mwrs \
  --namespace default \
  --placement my-placement \
  --output mwrs

# Apply to hub
kubectl apply -f mwrs_part_1.yaml --context kind-ocm-hub
```

**Example**:
```bash
# Convert nginx Helm chart to MWRS
helm template nginx oci://registry-1.docker.io/bitnamicharts/nginx > nginx.yaml
poetry run ocm-sandbox wrap -i nginx.yaml -n nginx-demo -N default -p default -o nginx-mwrs
kubectl apply -f nginx-mwrs_part_1.yaml --context kind-ocm-hub
```

#### 2. `ocm-sandbox scaffold` - Generate ClusterSet Scaffolding

Generates OCM scaffolding resources: ManagedClusterSetBinding, Placement, and namespace MWRS.

**Usage**:
```bash
poetry run ocm-sandbox scaffold \
  --name default \
  --namespace my-namespace \
  --clusterset default \
  --placement my-placement \
  --output scaffolding.yaml

kubectl apply -f scaffolding.yaml --context kind-ocm-hub
```

**Short form**:
```bash
poetry run ocm-sandbox scaffold -n default -N my-namespace -c default -p my-placement -o scaffolding.yaml
```

#### 3. `ocm-sandbox load-images` - Load Images to Kind

Loads Docker images into Kind clusters with workarounds for multi-arch images. Supports both command-line arguments and YAML configuration files.

**Features**:
- Multiple fallback methods for loading images (direct, archive, platform-specific, buildx)
- YAML configuration file support for batch loading
- Per-image cluster targeting
- Rich terminal output with progress indicators

**Basic Usage**:
```bash
# Load a specific image to default cluster (ocm-hub)
poetry run ocm-sandbox load-images nginx:alpine

# Load to specific cluster
poetry run ocm-sandbox load-images --cluster ocm-spoke1 my-app:latest

# Load multiple images
poetry run ocm-sandbox load-images nginx:alpine redis:7 busybox:latest

# Using Makefile (single image)
make load-images-to-kind IMG=my-app:latest CLUSTER=ocm-hub
```

**YAML Configuration File**:

Create an `images.yaml` file to manage your images:

```yaml
images:
  # Simple format: loads to default cluster
  - nginx:alpine
  - redis:7-alpine

  # Advanced format: specify target cluster
  - image: my-app:latest
    cluster: ocm-hub

  - image: spoke-app:v1.0
    cluster: ocm-spoke1
```

Then load all images:
```bash
# Copy from example
cp images.yaml.example images.yaml

# Edit images.yaml with your images
# ...

# Load all images from config
poetry run ocm-sandbox load-images --config images.yaml

# Or using Makefile
make load-images-from-config
```

### Getting Help

Each command has detailed help:

```bash
poetry run ocm-sandbox --help
poetry run ocm-sandbox wrap --help
poetry run ocm-sandbox scaffold --help
poetry run ocm-sandbox load-images --help
```

## macOS Networking

On macOS (and Windows), Docker runs inside a virtual machine, which means Kind clusters can't communicate via the standard Kubernetes API server addresses. This repository includes automated workarounds.

### The Problem

When spoke clusters try to register with the hub:
- Spoke uses hub's external API URL (e.g., `https://127.0.0.1:xxxxx`)
- This URL doesn't work from inside the spoke's Docker container
- Registration fails with connection timeout errors

### The Solution

The `ocm-patch-spoke-bootstrap` target automatically:

1. **Creates a shared Docker network** (`kind`)
   ```bash
   docker network create kind
   docker network connect kind ocm-spoke1-control-plane
   ```

2. **Gets the hub's internal Docker IP**
   ```bash
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ocm-hub-control-plane
   # Returns: 172.18.0.2 (example)
   ```

3. **Patches spoke kubeconfigs** to use the internal IP
   - Changes `server: https://127.0.0.1:xxxxx` → `server: https://172.18.0.2:6443`
   - Adds `tls-server-name: kubernetes` to bypass certificate validation

4. **Restarts spoke agents** to pick up the new configuration

### Manual Verification

If registration fails, check:

```bash
# Verify hub IP is reachable from spoke
kubectl --context kind-ocm-spoke1 run test-pod --rm -it --image=nicolaka/netshoot -- /bin/bash
# Inside pod:
curl -k https://172.18.0.2:6443/healthz

# Check spoke agent logs
kubectl logs -n open-cluster-management-agent \
  deployment/klusterlet-registration-agent \
  --context kind-ocm-spoke1
```

## Troubleshooting

### macOS: docker-mac-net-connect Not Running

**Symptom**: Spoke clusters fail to join hub, timeout errors, or stuck in `Pending` state on macOS

**Cause**: `docker-mac-net-connect` service is not running or not installed

**Solution**:
```bash
# Check if docker-mac-net-connect is installed
brew list | grep docker-mac-net-connect

# If not installed:
brew install chipmk/tap/docker-mac-net-connect

# Check service status
brew services list | grep docker-mac-net-connect

# If not started or shows error:
sudo brew services restart chipmk/tap/docker-mac-net-connect

# Verify it's running (should show "started")
brew services list | grep docker-mac-net-connect

# Test container-to-container connectivity
# Get hub IP
HUB_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ocm-hub-control-plane)
echo "Hub IP: $HUB_IP"

# From your Mac, try to reach the hub
ping -c 2 $HUB_IP

# If ping works, docker-mac-net-connect is functioning
```

**Note**: After starting docker-mac-net-connect, you may need to delete and recreate your Kind clusters:
```bash
make kind-delete-ocm
make bootstrap-kind-ocm
```

### Clusters Won't Join

**Symptom**: Spoke clusters stuck in `Pending` state (after confirming docker-mac-net-connect is running)

**Solution**:
```bash
# Re-run the patching
make ocm-patch-spoke-bootstrap

# Manually approve CSRs
kubectl certificate approve $(kubectl get csr -o name) --context kind-ocm-hub

# Check logs
kubectl logs -n open-cluster-management-agent deployment/klusterlet-registration-agent --context kind-ocm-spoke1
```

### Hub Components Not Ready

**Symptom**: OCM hub controllers crash or not starting

**Solution**:
```bash
# Check hub component status
kubectl get pods -n open-cluster-management-hub --context kind-ocm-hub
kubectl get pods -n open-cluster-management --context kind-ocm-hub

# Restart components
kubectl rollout restart deployment -n open-cluster-management-hub --context kind-ocm-hub
```

### ManifestWorkReplicaSet Not Working

**Symptom**: MWRS created but no ManifestWork appears on spokes

**Solution**:
```bash
# Verify MWRS feature is enabled
kubectl get clustermanager cluster-manager -o yaml --context kind-ocm-hub | grep ManifestWorkReplicaSet

# Re-enable if needed
make ocm-enable-mwrs

# Check placement
kubectl get placement -A --context kind-ocm-hub
kubectl describe placement <name> -n <namespace> --context kind-ocm-hub
```

### Docker Network Issues

**Symptom**: Spoke can't reach hub even after patching

**Solution**:
```bash
# Verify shared network exists
docker network ls | grep kind

# Check spoke is connected
docker network inspect kind | grep ocm-spoke1

# Manually connect if needed
docker network connect kind ocm-spoke1-control-plane
```

## Code Quality with SonarQube

This repository includes SonarQube configuration for analyzing Python scripts and bash scripts.

### Setup

```bash
# Start SonarQube
make sonar-start

# Wait ~60 seconds, then visit http://localhost:9001
# Login: admin / admin (you'll be prompted to change password)
```

### Running Analysis

```bash
# Run scan
make sonar-scan

# View results at http://localhost:9001
```

### Configuration

- **sonar-project.properties**: SonarQube project configuration
- **docker-compose.sonar.yml**: SonarQube + PostgreSQL stack
- Scans: Python package in `ocm_sandbox/` and bash scripts in `scripts/`

## Testing

This repository includes comprehensive unit tests for the OCM Sandbox CLI and automated CI via GitHub Actions.

### Running Tests Locally

```bash
# Install dependencies with Poetry
poetry install

# Run all tests
make test

# Or use poetry directly
poetry run pytest tests/ -v

# Run with coverage
poetry run pytest tests/ --cov=ocm_sandbox --cov-report=term --cov-report=html

# View coverage report
open htmlcov/index.html

# Run linters
make lint

# Format code
make format
```

### Test Structure

```
tests/
├── test_cli.py                               # Tests for CLI commands (Typer)
├── test_helm_to_mwrs.py                      # Tests for wrap command logic
├── test_generate_clusterset_scaffolding.py   # Tests for scaffold command logic
└── test_load_images_to_kind.py               # Tests for load-images command logic
```

### What's Tested

- **CLI entry points** (test_cli.py):
  - Command-line argument parsing
  - Help text generation
  - Version output
  - Integration between CLI and underlying functions
  - Error handling for missing/invalid arguments

- **wrap command logic** (test_helm_to_mwrs.py):
  - API version parsing
  - Kind to plural resource conversion
  - Feedback rule generation for all resource types
  - CRD extraction and RBAC generation
  - Manifest workload splitting (256KB limit)

- **scaffold command logic** (test_generate_clusterset_scaffolding.py):
  - YAML generation for ManagedClusterSetBinding
  - Placement resource creation
  - ManifestWorkReplicaSet with namespace manifest

- **load-images command logic** (test_load_images_to_kind.py):
  - YAML config file parsing
  - Simple and advanced image format handling
  - Per-image cluster targeting
  - Error handling for missing files/invalid config

### Continuous Integration

GitHub Actions automatically runs on every push and pull request:

- ✅ **Tests**: Python 3.11 and 3.12 on Ubuntu and macOS
- ✅ **Linting**: pylint and flake8
- ✅ **Shellcheck**: Bash script validation
- ✅ **Prerequisites Check**: Verifies check-prerequisites.sh works
- ✅ **Code Coverage**: Uploaded to Codecov

See `.github/workflows/ci.yml` for details.

### Adding New Tests

When adding new functions to scripts, add corresponding tests:

```python
# tests/test_your_script.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from your_script import your_function

def test_your_function():
    result = your_function(input_data)
    assert result == expected_output
```

## LLM Assisted Development

### Context for AI/LLM Assistants

When working with this repository using AI coding assistants (Claude Code, GitHub Copilot, ChatGPT, etc.), provide this context:

```
This is the OCM KIND Sandbox repository - a local development environment for Open Cluster Management (OCM).

PURPOSE:
- Bootstrap multi-cluster OCM environments using Kind (Kubernetes in Docker)
- Provide utilities to convert Helm charts to OCM ManifestWorkReplicaSets
- Enable local testing of OCM features without remote clusters

KEY COMPONENTS:
1. Makefile: Main automation layer for bootstrapping hub and spoke Kind clusters with OCM
2. OCM Sandbox CLI (ocm_sandbox/ package):
   - ocm-sandbox wrap: Converts Helm templates to ManifestWorkReplicaSets with RBAC generation
   - ocm-sandbox scaffold: Creates OCM ClusterSet scaffolding
   - ocm-sandbox load-images: Multi-arch image loading utility with YAML config support
3. Poetry for dependency management (pyproject.toml)

ARCHITECTURE:
- Hub cluster (ocm-hub): Central OCM control plane
- Spoke clusters (ocm-spoke1, ocm-spoke2): Managed clusters
- OCM controllers run on hub, agents run on spokes
- Spokes register with hub and report status back

MACOS NETWORKING QUIRK:
On macOS, Kind clusters can't communicate via normal API server addresses due to Docker VM isolation.
The Makefile includes ocm-patch-spoke-bootstrap which:
1. Creates shared Docker network
2. Patches spoke kubeconfigs to use hub's internal Docker IP
3. Adds tls-server-name: kubernetes for cert validation

DEVELOPMENT WORKFLOW:
1. Install CLI: `make install` or `make install-global`
2. Run `make bootstrap-kind-ocm` to create complete environment
3. Use `ocm-sandbox wrap` to convert Helm charts to MWRS resources
4. Use `ocm-sandbox scaffold` to generate OCM scaffolding
5. Apply to hub cluster and verify propagation to spokes
6. Clean up with `make kind-delete-ocm`

KEY FILES:
- Makefile: All automation targets
- pyproject.toml: Poetry dependency management and CLI configuration
- ocm_sandbox/: Python CLI package
  - cli.py: Typer CLI entry point
  - commands/wrap.py: Helm to MWRS converter
  - commands/scaffold.py: Scaffolding generator
  - commands/load_images.py: Image loading utility
- tests/: Comprehensive unit tests for all CLI commands
- images.yaml.example: Example configuration for batch image loading
- scripts/check-prerequisites.sh: Prerequisite verification script
- sonar-project.properties: Code quality configuration
- CLAUDE.md: Additional Claude Code-specific context

TESTING:
- Python tests should go in tests/ directory
- Run with `make test` (uses pytest)
- Linting: `make lint` (pylint, flake8)
- Code quality: `make sonar-scan`

COMMON TASKS:
- Add new OCM scaffolding targets to Makefile
- Enhance helm_to_mwrs.py with new resource types
- Add unit tests for Python utilities
- Document new OCM patterns and examples
```

### Tips for LLM Interactions

**Good prompts**:
- "Add a Makefile target to verify all ManagedClusters are in Available state"
- "Create a unit test for the helm_to_mwrs.py RBAC generation function"
- "Add support for StatefulSet status feedback in helm_to_mwrs.py"
- "Document how to troubleshoot spoke registration failures in README"

**Context to provide**:
- Whether you're working on hub or spoke setup
- If adding new OCM resource types to scripts
- Any specific OCM features you're testing (Placement, MWRS, ClusterSets)
- macOS vs Linux environment (for networking behavior)

## Contributing

Contributions welcome! Areas for improvement:

- [ ] Add unit tests for Python utilities
- [ ] Add more OCM example patterns
- [ ] Support for additional Kubernetes resource types in helm_to_mwrs.py
- [ ] Windows networking support (similar to macOS)
- [ ] GitHub Actions CI/CD pipeline
- [ ] Helm chart for deploying custom apps to MWRS

## Resources

- [Open Cluster Management Documentation](https://open-cluster-management.io/)
- [Kind Documentation](https://kind.sigs.k8s.io/)
- [ManifestWorkReplicaSet API](https://open-cluster-management.io/concepts/manifestworkreplicaset/)
- [Placement API](https://open-cluster-management.io/concepts/placement/)

## License

This project is provided as-is for educational and development purposes.
