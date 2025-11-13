# OCM KIND Sandbox - Makefile for local Open Cluster Management development
# This Makefile helps bootstrap OCM hub and spoke clusters in Kind for local development

SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

# OCM Configuration
CLUSTERADM_INIT_FLAGS ?= --feature-gates=ManagedClusterAutoApproval=true,ManifestWorkReplicaSet=true

# Kind Cluster Names
HUB_CLUSTER ?= ocm-hub
SPOKE_CLUSTER ?= ocm-spoke1
SPOKE2_CLUSTER ?= ocm-spoke2

# Kind Context Names
HUB_CTX ?= kind-$(HUB_CLUSTER)
SPOKE_CTX ?= kind-$(SPOKE_CLUSTER)
SPOKE2_CTX ?= kind-$(SPOKE2_CLUSTER)

# Image Configuration (for loading images into Kind if needed)
IMG ?= your-image:latest
CLUSTER ?= $(HUB_CLUSTER)

.PHONY: help
help:
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development Setup

.PHONY: install
install: ## Install OCM Sandbox CLI (use 'poetry shell' or 'poetry run' to access)
	@echo "Installing OCM Sandbox CLI with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Install from: https://python-poetry.org/docs/#installation"; exit 1; }
	@poetry install
	@echo ""
	@echo "✅ Installation complete!"
	@echo ""
	@echo "Usage options:"
	@echo "  1. Use with poetry run:  poetry run ocm-sandbox --help"
	@echo "  2. Activate venv:        poetry shell"
	@echo "                           ocm-sandbox --help"
	@echo "  3. Global install:       make install-global"

.PHONY: install-dev
install-dev: ## Install development dependencies
	@echo "Installing development dependencies with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Install from: https://python-poetry.org/docs/#installation"; exit 1; }
	@poetry install --with dev

.PHONY: install-global
install-global: ## Install OCM Sandbox CLI globally with pipx (no poetry run needed)
	@echo "Installing OCM Sandbox CLI globally with pipx..."
	@command -v pipx >/dev/null 2>&1 || { echo "❌ pipx not found. Install with: python3 -m pip install --user pipx"; exit 1; }
	@pipx install --force .
	@echo ""
	@echo "✅ Global installation complete!"
	@echo "   Use directly: ocm-sandbox --help"

.PHONY: shell
shell: ## Activate Poetry virtual environment shell
	@poetry shell

##@ Testing

.PHONY: test
test: ## Run Python tests with Poetry
	@echo "Running Python tests with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Install from: https://python-poetry.org/docs/#installation"; exit 1; }
	@poetry run pytest tests/ -v

.PHONY: lint
lint: ## Run Python linting with pylint and flake8
	@echo "Running Python linters with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Install from: https://python-poetry.org/docs/#installation"; exit 1; }
	@poetry run pylint ocm_sandbox/ || echo "pylint check completed with issues"
	@poetry run flake8 ocm_sandbox/ --max-line-length=120 --extend-ignore=E203,W503

.PHONY: format
format: ## Format Python code with black and isort
	@echo "Formatting Python code with Poetry..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry not found. Install from: https://python-poetry.org/docs/#installation"; exit 1; }
	@poetry run black ocm_sandbox/ tests/
	@poetry run isort ocm_sandbox/ tests/

##@ Kind + OCM (clusteradm)

.PHONY: kind-delete-ocm
kind-delete-ocm: ## Delete Kind OCM clusters (hub+spoke+spoke2)
	- kind delete cluster --name $(HUB_CLUSTER) || true
	- kind delete cluster --name $(SPOKE_CLUSTER) || true
	- kind delete cluster --name $(SPOKE2_CLUSTER) || true

.PHONY: kind-ensure-shared-network
kind-ensure-shared-network: ## Ensure spoke control-plane is connected to the shared 'kind' docker network
	- docker network create kind >/dev/null 2>&1 || true
	- docker network connect kind $(SPOKE_CLUSTER)-control-plane >/dev/null 2>&1 || true

.PHONY: kind-create-hub
kind-create-hub: ## Create Kind hub cluster
	kind create cluster --name $(HUB_CLUSTER)

.PHONY: kind-create-spoke
kind-create-spoke: ## Create Kind spoke cluster
	kind create cluster --name $(SPOKE_CLUSTER)

.PHONY: ocm-init-hub
ocm-init-hub: ## Initialize OCM hub on Kind hub cluster (requires clusteradm)
	@command -v clusteradm >/dev/null 2>&1 || { echo "clusteradm not found. Install from: https://open-cluster-management.io/getting-started/installation/start-the-control-plane/"; exit 1; }
	clusteradm init --wait $(CLUSTERADM_INIT_FLAGS) --context $(HUB_CTX)

.PHONY: ocm-enable-mwrs
ocm-enable-mwrs: ## Enable ManifestWorkReplicaSet feature gate on hub
	@echo "Enabling ManifestWorkReplicaSet feature gate on hub..."
	@kubectl patch clustermanager cluster-manager --type=merge -p '{"spec":{"workConfiguration":{"featureGates":[{"feature":"ManifestWorkReplicaSet","mode":"Enable"}]}}}' --context $(HUB_CTX) || true
	@echo "Waiting for hub components to reconcile..."
	@kubectl --context $(HUB_CTX) -n open-cluster-management-hub wait --for=condition=Available deploy --all --timeout=180s || true
	@kubectl --context $(HUB_CTX) -n open-cluster-management wait --for=condition=Available deploy --all --timeout=180s || true

.PHONY: ocm-join-spoke
ocm-join-spoke: ## Join spoke cluster to hub (token + hub apiserver)
	@command -v clusteradm >/dev/null 2>&1 || { echo "clusteradm not found"; exit 1; }
	@echo "Joining $(SPOKE_CTX) to hub $(HUB_CTX)..."
	@TOKEN=$$(clusteradm get token --context $(HUB_CTX) 2>/dev/null); \
	 HUB_API_RAW=$$(kubectl config view --raw -o jsonpath='{.clusters[?(@.name=="$(HUB_CTX)")].cluster.server}'); \
	 HUB_API=$$HUB_API_RAW; \
	 TMPK=$$(mktemp); kubectl --context $(HUB_CTX) -n kube-public get cm cluster-info -o jsonpath='{.data.kubeconfig}' > $$TMPK; \
	 CA_B64=$$(sed -n 's/^[[:space:]]*certificate-authority-data:[[:space:]]*//p' $$TMPK | head -1); \
	 echo $$CA_B64 | base64 -d > $$TMPK.ca; \
	 echo "Executing: clusteradm join --hub-token <redacted> --hub-apiserver $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER)"; \
	 (clusteradm join --hub-token $$TOKEN --hub-apiserver $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER) \
	  || clusteradm join --hub-token $$TOKEN --hub-server $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER)) || true; \
	 echo "Accepting spoke on hub..."; \
	 clusteradm accept --clusters $(SPOKE_CLUSTER) --context $(HUB_CTX) || true; \
	 echo "Verifying bootstrap secret on spoke..."; \
	 for i in $$(seq 1 30); do kubectl --context $(SPOKE_CTX) -n open-cluster-management-agent get secret bootstrap-hub-kubeconfig >/dev/null 2>&1 && break || { echo "Waiting for bootstrap-hub-kubeconfig..."; sleep 2; }; done; \
	 kubectl --context $(SPOKE_CTX) -n open-cluster-management-agent get secret bootstrap-hub-kubeconfig >/dev/null 2>&1 || { \
	   echo "Retrying clusteradm join (bootstrap secret not found)"; \
	   (clusteradm join --hub-token $$TOKEN --hub-apiserver $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER) \
	    || clusteradm join --hub-token $$TOKEN --hub-server $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER)) || true; \
	 }; \
	 echo "Sleeping briefly before patching to allow klusterlet to settle..."; sleep 30
	@( \
	  for i in $$(seq 1 40); do \
	    if kubectl --context $(SPOKE_CTX) -n open-cluster-management-agent get secret bootstrap-hub-kubeconfig >/dev/null 2>&1; then \
	      $(MAKE) ocm-patch-spoke-bootstrap; \
	      $(MAKE) ocm-accept-approve; \
	      exit 0; \
	    fi; \
	    sleep 3; \
	  done; \
	  echo "bootstrap-hub-kubeconfig did not appear within timeout; skipping background patch"; \
	) &

.PHONY: bootstrap-kind-ocm
bootstrap-kind-ocm: ## Create 2 Kind clusters (hub+spoke1+spoke2), initialize OCM, join spokes
	@echo "=== OCM KIND Sandbox Bootstrap ==="
	@echo "This will create 3 Kind clusters and configure OCM between them"
	@echo ""
	@echo "=== Creating Kind clusters (hub: $(HUB_CLUSTER), spokes: $(SPOKE_CLUSTER), $(SPOKE2_CLUSTER)) ==="
	kind get clusters | grep -qx '$(HUB_CLUSTER)' || kind create cluster --name $(HUB_CLUSTER)
	kind get clusters | grep -qx '$(SPOKE_CLUSTER)' || kind create cluster --name $(SPOKE_CLUSTER)
	@echo "=== Initializing OCM hub on $(HUB_CTX) ==="
	command -v clusteradm >/dev/null 2>&1 || { echo "clusteradm not found"; exit 1; }
	clusteradm init --wait $(CLUSTERADM_INIT_FLAGS) --context $(HUB_CTX) || true
	$(MAKE) ocm-enable-mwrs
	@echo "=== Ensuring shared docker network connectivity (macOS compatibility) ==="
	$(MAKE) kind-ensure-shared-network
	@echo "=== Joining spoke $(SPOKE_CTX) to hub ==="
	TOKEN=$$(clusteradm get token --context $(HUB_CTX) 2>/dev/null); \
	 HUB_API_RAW=$$(kubectl config view --raw -o jsonpath='{.clusters[?(@.name=="$(HUB_CTX)")].cluster.server}'); \
	 HUB_API=$$HUB_API_RAW; \
	 TMPK=$$(mktemp); kubectl --context $(HUB_CTX) -n kube-public get cm cluster-info -o jsonpath='{.data.kubeconfig}' > $$TMPK; \
	 CA_B64=$$(sed -n 's/^[[:space:]]*certificate-authority-data:[[:space:]]*//p' $$TMPK | head -1); \
	 echo $$CA_B64 | base64 -d > $$TMPK.ca; \
	 echo "Executing: clusteradm join --hub-token <redacted> --hub-apiserver $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER)"; \
	 (clusteradm join --hub-token $$TOKEN --hub-apiserver $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER) \
	  || clusteradm join --hub-token $$TOKEN --hub-server $$HUB_API --ca-file $$TMPK.ca --context $(SPOKE_CTX) --cluster-name $(SPOKE_CLUSTER)) || true; \
	 clusteradm accept --clusters $(SPOKE_CLUSTER) --context $(HUB_CTX) || true
	@sleep 20
	$(MAKE) ocm-patch-spoke-bootstrap
	$(MAKE) ocm-accept-approve
	@( \
	  for i in $$(seq 1 40); do \
	    if kubectl --context $(SPOKE_CTX) -n open-cluster-management-agent get secret bootstrap-hub-kubeconfig >/dev/null 2>&1; then \
	      $(MAKE) ocm-patch-spoke-bootstrap; \
	      $(MAKE) ocm-accept-approve; \
	      exit 0; \
	    fi; \
	    sleep 3; \
	  done; \
	  echo "bootstrap-hub-kubeconfig did not appear within timeout; skipping background patch"; \
	) &
	@echo "=== Creating and joining second spoke ($(SPOKE2_CLUSTER)) ==="
	kind get clusters | grep -qx '$(SPOKE2_CLUSTER)' || kind create cluster --name $(SPOKE2_CLUSTER)
	$(MAKE) kind-ensure-shared-network SPOKE_CLUSTER=$(SPOKE2_CLUSTER)
	$(MAKE) ocm-join-spoke SPOKE_CLUSTER=$(SPOKE2_CLUSTER)
	@echo "=== Allowing extra time for spoke2 to settle ==="
	@sleep 30
	@echo "=== Switching kubectl context to hub ($(HUB_CTX)) ==="
	kubectl config use-context $(HUB_CTX)
	@echo ""
	@echo "=== Bootstrap complete! ==="
	@echo "Hub Context:    $(HUB_CTX)"
	@echo "Spoke Contexts: $(SPOKE_CTX), $(SPOKE2_CTX)"
	@echo ""
	@echo "Verify clusters are ready:"
	@echo "  kubectl get managedclusters --context $(HUB_CTX)"
	@echo ""
	@echo "To clean up:"
	@echo "  make kind-delete-ocm"

.PHONY: ocm-patch-spoke-bootstrap
ocm-patch-spoke-bootstrap: ## Patch spoke bootstrap/hub kubeconfigs to use hub container IP:6443 (macOS Kind-to-Kind networking)
	@echo "Patching spoke kubeconfigs to reach hub via hub container IP (macOS compatibility)..."
	@NS=open-cluster-management-agent; \
	 HUB_IP=$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $(HUB_CLUSTER)-control-plane 2>/dev/null); \
	 if [ -z "$$HUB_IP" ]; then echo "Could not determine hub control-plane IP; skipping patch"; exit 0; fi; \
	 HUB_URL=https://$$HUB_IP:6443; \
	 kubectl --context $(SPOKE_CTX) -n $$NS get secret bootstrap-hub-kubeconfig >/dev/null 2>&1 || { echo "bootstrap-hub-kubeconfig not ready; skipping"; exit 0; }; \
	 for S in bootstrap-hub-kubeconfig hub-kubeconfig-secret; do \
	   DATA=$$(kubectl --context $(SPOKE_CTX) -n $$NS get secret $$S -o jsonpath='{.data.kubeconfig}' 2>/dev/null || echo ""); \
	   if [ -z "$$DATA" ]; then echo "No $$S yet; skipping $$S"; continue; fi; \
	   TMP=$$(mktemp); (echo $$DATA | base64 -d 2>/dev/null || echo $$DATA | base64 -D) > $$TMP; \
	   sed -i '' -e "s#server: .*#server: $$HUB_URL#g" $$TMP || sed -i -e "s#server: .*#server: $$HUB_URL#g" $$TMP; \
	   if grep -q 'tls-server-name:' $$TMP; then \
	     sed -i '' -e "s#tls-server-name:.*#tls-server-name: kubernetes#g" $$TMP || sed -i -e "s#tls-server-name:.*#tls-server-name: kubernetes#g" $$TMP; \
	   else \
	     awk 'BEGIN{added=0} /server:\s/ && !added {print; print "    tls-server-name: kubernetes"; added=1; next} {print}' $$TMP > $$TMP.new && mv $$TMP.new $$TMP; \
	   fi; \
	   kubectl create secret generic $$S --from-file=kubeconfig=$$TMP -n $$NS --dry-run=client -o yaml | kubectl --context $(SPOKE_CTX) apply -f -; \
	   rm -f $$TMP; \
	   echo "Applied $$S with server $$HUB_URL"; \
	 done; \
	 kubectl --context $(SPOKE_CTX) -n $$NS rollout restart deploy/klusterlet-registration-agent || true; \
	 kubectl --context $(SPOKE_CTX) -n $$NS rollout restart deploy/klusterlet-work-agent || true

.PHONY: ocm-accept-approve
ocm-accept-approve: ## Accept the spoke on hub and approve any Pending CSRs
	@echo "Accepting $(SPOKE_CLUSTER) on hub and approving pending CSRs..."
	@clusteradm accept --clusters $(SPOKE_CLUSTER) --context $(HUB_CTX) || true
	@for i in $$(seq 1 30); do \
		PENDING=$$(kubectl get csr --context $(HUB_CTX) --no-headers 2>/dev/null | awk '/Pending/ {print $$1}'); \
		if [ -n "$$PENDING" ]; then echo "Approving: $$PENDING"; echo "$$PENDING" | xargs -r kubectl certificate approve --context $(HUB_CTX) || true; fi; \
		JOINED=$$(kubectl get managedcluster $(SPOKE_CLUSTER) -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterJoined")].status}' --context $(HUB_CTX) 2>/dev/null || echo ""); \
		AVAIL=$$(kubectl get managedcluster $(SPOKE_CLUSTER) -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status}' --context $(HUB_CTX) 2>/dev/null || echo ""); \
		[ "$$JOINED" = "True" ] && [ "$$AVAIL" = "True" ] && break; \
		sleep 2; \
	 done; \
	 kubectl get managedclusters --context $(HUB_CTX) || true

.PHONY: load-images-to-kind
load-images-to-kind: ## Load Docker images into Kind cluster (use IMG=image:tag CLUSTER=cluster-name)
	@if [ -z "$(IMG)" ]; then \
		echo "❌ No image specified. Usage: make load-images-to-kind IMG=my-image:tag"; \
		echo "Or use: make load-images-from-config"; \
		exit 1; \
	fi
	@echo "Loading image $(IMG) into Kind cluster..."
	@poetry run ocm-sandbox load-images --cluster $(CLUSTER) $(IMG)

.PHONY: load-images-from-config
load-images-from-config: ## Load images from images.yaml config file
	@if [ ! -f "images.yaml" ]; then \
		echo "❌ images.yaml not found. Copy from example:"; \
		echo "   cp images.yaml.example images.yaml"; \
		exit 1; \
	fi
	@poetry run ocm-sandbox load-images --config images.yaml

##@ SonarQube

.PHONY: sonar-start
sonar-start: ## Start local SonarQube server with Docker Compose
	@echo "Starting local SonarQube server on http://localhost:9001 ..."
	@docker compose -f docker-compose.sonar.yml up -d
	@echo "Wait ~60s for SonarQube to initialize. Default creds: admin/admin"
	@echo "Change password on first login at: http://localhost:9001"

.PHONY: sonar-status
sonar-status: ## Check SonarQube server status
	@docker compose -f docker-compose.sonar.yml ps
	@echo "\nPort 9001 usage:" && (lsof -i :9001 || echo "Port 9001 is free")
	@echo "\nRecent logs:" && docker compose -f docker-compose.sonar.yml logs --tail=10 sonarqube 2>/dev/null || true

.PHONY: sonar-stop
sonar-stop: ## Stop local SonarQube server
	@docker compose -f docker-compose.sonar.yml down

.PHONY: sonar-scan
sonar-scan: ## Run SonarQube scan against local SonarQube server
	@echo "Running SonarQube analysis..."
	@echo "Checking if SonarQube is running..."
	@curl -s http://localhost:9001/api/system/status | grep -q "UP" || { echo "❌ SonarQube not running. Start with: make sonar-start"; exit 1; }
	@command -v sonar-scanner >/dev/null 2>&1 || { echo "❌ sonar-scanner not found. Install from: https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/"; exit 1; }
	@echo "✅ SonarQube is running. Starting scan..."
	sonar-scanner -Dsonar.host.url=http://localhost:9001 -Dsonar.login=admin -Dsonar.password=admin

.PHONY: sonar-clean
sonar-clean: ## Remove SonarQube data volumes (clean slate)
	@echo "Removing SonarQube data volumes..."
	@docker compose -f docker-compose.sonar.yml down -v
	@echo "✅ SonarQube data volumes removed"
