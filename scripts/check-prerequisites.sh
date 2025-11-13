#!/bin/bash
#
# Prerequisites checker for OCM KIND Sandbox
# Verifies all required tools are installed and configured correctly
#

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Tracking
ERRORS=0
WARNINGS=0
PLATFORM=$(uname -s)

echo "=========================================="
echo "OCM KIND Sandbox - Prerequisites Check"
echo "=========================================="
echo ""
echo "Platform: $PLATFORM"
echo ""

# Function to check if command exists
check_command() {
    local cmd=$1
    local name=$2
    local install_cmd=$3
    local required=$4

    if command -v "$cmd" >/dev/null 2>&1; then
        local version
        version=$($cmd version 2>&1 | head -1 || echo "unknown")
        echo -e "${GREEN}✓${NC} $name is installed"
        echo "  Version: $version"
    else
        if [ "$required" = "required" ]; then
            echo -e "${RED}✗${NC} $name is NOT installed (REQUIRED)"
            echo "  Install: $install_cmd"
            ERRORS=$((ERRORS + 1))
        else
            echo -e "${YELLOW}⚠${NC} $name is NOT installed (optional)"
            echo "  Install: $install_cmd"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
}

# Function to check Docker
check_docker() {
    if command -v docker >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Docker is installed"
        docker version --format '  Client: {{.Client.Version}} | Server: {{.Server.Version}}' 2>/dev/null || echo "  (Unable to get version)"

        # Check if Docker daemon is running
        if docker ps >/dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Docker daemon is running"
        else
            echo -e "${RED}✗${NC} Docker daemon is NOT running"
            echo "  Start Docker Desktop or Docker Engine"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${RED}✗${NC} Docker is NOT installed (REQUIRED)"
        echo "  Install: https://docs.docker.com/get-docker/"
        ERRORS=$((ERRORS + 1))
    fi
}

# Function to check docker-mac-net-connect (macOS only)
check_docker_mac_net_connect() {
    if [ "$PLATFORM" = "Darwin" ]; then
        echo ""
        echo "--- macOS-Specific Requirements ---"

        if command -v brew >/dev/null 2>&1; then
            if brew list docker-mac-net-connect >/dev/null 2>&1; then
                echo -e "${GREEN}✓${NC} docker-mac-net-connect is installed"

                # Check if service is running
                local status
                status=$(brew services list | grep docker-mac-net-connect | awk '{print $2}')
                if [ "$status" = "started" ]; then
                    echo -e "${GREEN}✓${NC} docker-mac-net-connect service is running"
                else
                    echo -e "${RED}✗${NC} docker-mac-net-connect service is NOT running"
                    echo "  Status: $status"
                    echo "  Start: sudo brew services start chipmk/tap/docker-mac-net-connect"
                    ERRORS=$((ERRORS + 1))
                fi
            else
                echo -e "${RED}✗${NC} docker-mac-net-connect is NOT installed (REQUIRED for macOS)"
                echo "  This is CRITICAL for spoke-to-hub communication!"
                echo "  Install: brew install chipmk/tap/docker-mac-net-connect"
                echo "  Start:   sudo brew services start chipmk/tap/docker-mac-net-connect"
                ERRORS=$((ERRORS + 1))
            fi
        else
            echo -e "${YELLOW}⚠${NC} Homebrew not found - cannot check docker-mac-net-connect"
            echo "  Install Homebrew: https://brew.sh"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
}

# Function to check Python and optional packages
check_python() {
    if command -v python3 >/dev/null 2>&1; then
        local py_version
        py_version=$(python3 --version 2>&1)
        echo -e "${GREEN}✓${NC} Python 3 is installed"
        echo "  $py_version"

        # Check for pyyaml
        if python3 -c "import yaml" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} pyyaml is installed (for images.yaml support)"
        else
            echo -e "${YELLOW}⚠${NC} pyyaml is NOT installed (optional)"
            echo "  Install: pip install pyyaml"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo -e "${YELLOW}⚠${NC} Python 3 is NOT installed (optional, needed for utility scripts)"
        echo "  Install: https://www.python.org/downloads/"
        WARNINGS=$((WARNINGS + 1))
    fi
}

# Main checks
echo "=== Core Requirements ==="
check_docker
echo ""
check_command "kind" "Kind" "brew install kind (macOS) or https://kind.sigs.k8s.io/docs/user/quick-start/" "required"
echo ""
check_command "kubectl" "kubectl" "brew install kubectl (macOS) or https://kubernetes.io/docs/tasks/tools/" "required"
echo ""
check_command "clusteradm" "clusteradm" "curl -L https://raw.githubusercontent.com/open-cluster-management-io/clusteradm/main/install.sh | bash" "required"

# macOS-specific
check_docker_mac_net_connect

echo ""
echo "=== Optional Tools ==="
check_python
echo ""
check_command "pylint" "pylint" "pip install pylint" "optional"
echo ""
check_command "flake8" "flake8" "pip install flake8" "optional"
echo ""
check_command "pytest" "pytest" "pip install pytest" "optional"
echo ""
check_command "sonar-scanner" "sonar-scanner" "https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/" "optional"

# Summary
echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "You're ready to run:"
    echo "  make bootstrap-kind-ocm"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ $WARNINGS warning(s)${NC}"
    echo ""
    echo "Core requirements are met, but some optional tools are missing."
    echo "You can proceed with:"
    echo "  make bootstrap-kind-ocm"
    exit 0
else
    echo -e "${RED}✗ $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo ""
    echo "Please install the required tools before proceeding."
    if [ "$PLATFORM" = "Darwin" ]; then
        echo ""
        echo "CRITICAL for macOS: Make sure docker-mac-net-connect is installed and running!"
    fi
    exit 1
fi
