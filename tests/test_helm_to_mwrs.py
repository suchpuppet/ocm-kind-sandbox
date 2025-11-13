"""
Unit tests for wrap command (helm_to_mwrs logic).
"""
import tempfile
import yaml
import pytest

from ocm_sandbox.commands.wrap import (
    build_feedback_for_manifest,
    extract_crd_resources,
    create_rbac_manifests,
    split_manifest_workload,
    kind_to_resource_plural,
    split_apiversion,
)


class TestSplitApiversion:
    """Test API version parsing."""

    def test_with_group(self):
        """Test parsing apiVersion with group."""
        group, version = split_apiversion("apps/v1")
        assert group == "apps"
        assert version == "v1"

    def test_without_group(self):
        """Test parsing apiVersion without group (core)."""
        group, version = split_apiversion("v1")
        assert group == ""
        assert version == "v1"


class TestKindToResourcePlural:
    """Test kind to plural resource name conversion."""

    def test_deployment(self):
        """Test Deployment → deployments."""
        assert kind_to_resource_plural("Deployment") == "deployments"

    def test_service(self):
        """Test Service → services."""
        assert kind_to_resource_plural("Service") == "services"

    def test_configmap(self):
        """Test ConfigMap → configmaps."""
        assert kind_to_resource_plural("ConfigMap") == "configmaps"

    def test_ingress(self):
        """Test Ingress → ingresses."""
        assert kind_to_resource_plural("Ingress") == "ingresses"

    def test_custom_resource(self):
        """Test custom resource (generic pluralization)."""
        assert kind_to_resource_plural("MyCustomResource") == "mycustomresources"


class TestBuildFeedbackForManifest:
    """Test feedback rule generation for manifests."""

    def test_deployment_feedback(self):
        """Test feedback rules for Deployment."""
        manifest = {
            'apiVersion': 'apps/v1',
            'kind': 'Deployment',
            'metadata': {'name': 'test-app', 'namespace': 'default'}
        }
        feedback = build_feedback_for_manifest(manifest)

        assert feedback is not None
        assert feedback['resourceIdentifier']['group'] == 'apps'
        assert feedback['resourceIdentifier']['resource'] == 'deployments'
        assert feedback['resourceIdentifier']['name'] == 'test-app'
        assert feedback['resourceIdentifier']['namespace'] == 'default'

        # Should have WellKnownStatus
        rule_types = [rule['type'] for rule in feedback['feedbackRules']]
        assert 'WellKnownStatus' in rule_types

        # Should also have JSONPaths for SpecReplicas and DeletionTimestamp
        json_paths_rule = next(r for r in feedback['feedbackRules'] if r['type'] == 'JSONPaths')
        path_names = [jp['name'] for jp in json_paths_rule['jsonPaths']]
        assert 'SpecReplicas' in path_names
        assert 'DeletionTimestamp' in path_names

    def test_statefulset_feedback(self):
        """Test feedback rules for StatefulSet."""
        manifest = {
            'apiVersion': 'apps/v1',
            'kind': 'StatefulSet',
            'metadata': {'name': 'test-sts', 'namespace': 'default'}
        }
        feedback = build_feedback_for_manifest(manifest)

        assert feedback is not None
        rule_types = [rule['type'] for rule in feedback['feedbackRules']]
        assert 'WellKnownStatus' in rule_types

    def test_service_feedback(self):
        """Test feedback rules for Service (no built-in feedback)."""
        manifest = {
            'apiVersion': 'v1',
            'kind': 'Service',
            'metadata': {'name': 'test-svc', 'namespace': 'default'}
        }
        feedback = build_feedback_for_manifest(manifest)

        # Service is not in builtins, should get custom JSONPaths
        assert feedback is not None
        rule_types = [rule['type'] for rule in feedback['feedbackRules']]
        assert 'WellKnownStatus' not in rule_types
        assert 'JSONPaths' in rule_types

    def test_crd_feedback(self):
        """Test feedback rules for custom resources."""
        manifest = {
            'apiVersion': 'example.com/v1',
            'kind': 'CustomResource',
            'metadata': {'name': 'test-cr', 'namespace': 'default'}
        }
        feedback = build_feedback_for_manifest(manifest)

        assert feedback is not None
        assert feedback['resourceIdentifier']['group'] == 'example.com'
        assert feedback['resourceIdentifier']['resource'] == 'customresources'

        # Should have JSONPaths for observedGeneration and deletionTimestamp
        json_paths_rule = feedback['feedbackRules'][0]
        assert json_paths_rule['type'] == 'JSONPaths'
        path_names = [jp['name'] for jp in json_paths_rule['jsonPaths']]
        assert 'ObservedGeneration' in path_names
        assert 'DeletionTimestamp' in path_names

    def test_invalid_manifest(self):
        """Test with invalid manifest."""
        # Missing kind
        manifest = {
            'apiVersion': 'v1',
            'metadata': {'name': 'test'}
        }
        feedback = build_feedback_for_manifest(manifest)
        assert feedback is None

        # Missing name
        manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {}
        }
        feedback = build_feedback_for_manifest(manifest)
        assert feedback is None

        # Not a dict
        feedback = build_feedback_for_manifest("not a dict")
        assert feedback is None


class TestExtractCrdResources:
    """Test CRD extraction and RBAC generation."""

    def test_extract_single_crd(self):
        """Test extracting a single CRD."""
        manifests = [
            {
                'apiVersion': 'apiextensions.k8s.io/v1',
                'kind': 'CustomResourceDefinition',
                'spec': {
                    'group': 'example.com',
                    'names': {'plural': 'widgets'}
                }
            }
        ]

        rbac_rules = extract_crd_resources(manifests)

        assert 'example.com' in rbac_rules
        assert 'widgets' in rbac_rules['example.com']['resources']
        assert 'get' in rbac_rules['example.com']['verbs']
        assert 'create' in rbac_rules['example.com']['verbs']

    def test_extract_multiple_crds(self):
        """Test extracting multiple CRDs."""
        manifests = [
            {
                'apiVersion': 'apiextensions.k8s.io/v1',
                'kind': 'CustomResourceDefinition',
                'spec': {
                    'group': 'example.com',
                    'names': {'plural': 'widgets'}
                }
            },
            {
                'apiVersion': 'apiextensions.k8s.io/v1',
                'kind': 'CustomResourceDefinition',
                'spec': {
                    'group': 'example.com',
                    'names': {'plural': 'gadgets'}
                }
            },
            {
                'apiVersion': 'apiextensions.k8s.io/v1',
                'kind': 'CustomResourceDefinition',
                'spec': {
                    'group': 'other.io',
                    'names': {'plural': 'things'}
                }
            }
        ]

        rbac_rules = extract_crd_resources(manifests)

        assert len(rbac_rules) == 2
        assert 'widgets' in rbac_rules['example.com']['resources']
        assert 'gadgets' in rbac_rules['example.com']['resources']
        assert 'things' in rbac_rules['other.io']['resources']

    def test_no_crds(self):
        """Test with no CRDs."""
        manifests = [
            {'apiVersion': 'v1', 'kind': 'Service'},
            {'apiVersion': 'apps/v1', 'kind': 'Deployment'}
        ]

        rbac_rules = extract_crd_resources(manifests)
        assert rbac_rules == {}


class TestCreateRbacManifests:
    """Test RBAC manifest generation."""

    def test_create_rbac(self):
        """Test creating ClusterRole and ClusterRoleBinding."""
        rbac_rules = {
            'example.com': {
                'resources': {'widgets', 'gadgets'},
                'verbs': {'get', 'list', 'create'}
            }
        }

        manifests = create_rbac_manifests(rbac_rules, 'test-role')

        assert len(manifests) == 2

        # Check ClusterRole
        cluster_role = manifests[0]
        assert cluster_role['kind'] == 'ClusterRole'
        assert cluster_role['metadata']['name'] == 'test-role'
        assert len(cluster_role['rules']) == 1
        assert cluster_role['rules'][0]['apiGroups'] == ['example.com']
        assert set(cluster_role['rules'][0]['resources']) == {'widgets', 'gadgets'}

        # Check ClusterRoleBinding
        cluster_role_binding = manifests[1]
        assert cluster_role_binding['kind'] == 'ClusterRoleBinding'
        assert cluster_role_binding['metadata']['name'] == 'test-role-binding'
        assert cluster_role_binding['roleRef']['name'] == 'test-role'
        assert cluster_role_binding['subjects'][0]['name'] == 'klusterlet-work-sa'

    def test_empty_rbac_rules(self):
        """Test with empty RBAC rules."""
        manifests = create_rbac_manifests({}, 'test-role')
        assert manifests == []


class TestSplitManifestWorkload:
    """Test manifest workload splitting."""

    def test_no_split_needed(self):
        """Test when all manifests fit in one workload."""
        manifests = [
            {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cm1'}},
            {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cm2'}}
        ]

        result = split_manifest_workload(manifests, max_size=1024*1024)  # 1MB

        assert len(result) == 1
        assert len(result[0]) == 2

    def test_split_required(self):
        """Test splitting when workload exceeds max size."""
        # Create large manifests
        large_data = 'x' * (100 * 1024)  # 100KB string
        manifests = [
            {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': f'cm{i}'}, 'data': {'large': large_data}}
            for i in range(5)
        ]

        # Split at 200KB
        result = split_manifest_workload(manifests, max_size=200 * 1024)

        # Should split into multiple workloads
        assert len(result) > 1

        # Each workload should be smaller than max_size
        for workload in result:
            workload_yaml = '\n---\n'.join(yaml.dump(m) for m in workload)
            assert len(workload_yaml.encode('utf-8')) <= 200 * 1024


class TestGenerateMwrsFiles:
    """Integration test for generate_mwrs_files (writes files)."""

    def test_generate_files(self):
        """Test generating MWRS files."""
        # We'll skip this in unit tests since it writes files
        # This would be better as an integration test
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
