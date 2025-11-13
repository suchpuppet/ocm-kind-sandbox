"""
Unit tests for scaffold command (generate-clusterset-scaffolding logic).
"""
import pytest

from ocm_sandbox.commands.scaffold import generate_scaffolding_manifests


class TestGenerateYaml:
    """Test YAML generation for ClusterSet scaffolding."""

    def test_generate_basic_scaffolding(self):
        """Test generating basic scaffolding with default values."""
        docs = generate_scaffolding_manifests(
            name='default',
            namespace='test-namespace',
            clusterset='default',
            placement='test-placement'
        )

        # Should generate 3 documents: ManagedClusterSetBinding, Placement, ManifestWorkReplicaSet
        assert len(docs) == 3

        # Check ManagedClusterSetBinding
        binding = docs[0]
        assert binding['apiVersion'] == 'cluster.open-cluster-management.io/v1beta2'
        assert binding['kind'] == 'ManagedClusterSetBinding'
        assert binding['metadata']['name'] == 'default'
        assert binding['metadata']['namespace'] == 'test-namespace'
        assert binding['spec']['clusterSet'] == 'default'

        # Check Placement
        placement_doc = docs[1]
        assert placement_doc['apiVersion'] == 'cluster.open-cluster-management.io/v1beta1'
        assert placement_doc['kind'] == 'Placement'
        assert placement_doc['metadata']['name'] == 'test-placement'
        assert placement_doc['metadata']['namespace'] == 'test-namespace'
        assert placement_doc['spec']['clusterSets'] == ['default']

        # Check ManifestWorkReplicaSet
        mwrs = docs[2]
        assert mwrs['apiVersion'] == 'work.open-cluster-management.io/v1alpha1'
        assert mwrs['kind'] == 'ManifestWorkReplicaSet'
        assert mwrs['metadata']['name'] == 'test-namespace-namespace-mwrs'
        assert mwrs['metadata']['namespace'] == 'test-namespace'
        assert mwrs['spec']['placementRefs'][0]['name'] == 'test-placement'

        # Check namespace manifest
        namespace_manifest = mwrs['spec']['manifestWorkTemplate']['workload']['manifests'][0]
        assert namespace_manifest['apiVersion'] == 'v1'
        assert namespace_manifest['kind'] == 'Namespace'
        assert namespace_manifest['metadata']['name'] == 'test-namespace'

    def test_generate_custom_values(self):
        """Test generating scaffolding with custom values."""
        docs = generate_scaffolding_manifests(
            name='custom-binding',
            namespace='custom-namespace',
            clusterset='custom-set',
            placement='custom-placement'
        )

        assert len(docs) == 3

        # Verify custom values are used
        binding = docs[0]
        assert binding['metadata']['name'] == 'custom-binding'
        assert binding['metadata']['namespace'] == 'custom-namespace'
        assert binding['spec']['clusterSet'] == 'custom-set'

        placement_doc = docs[1]
        assert placement_doc['metadata']['name'] == 'custom-placement'
        assert placement_doc['spec']['clusterSets'] == ['custom-set']

        mwrs = docs[2]
        assert mwrs['metadata']['namespace'] == 'custom-namespace'
        assert mwrs['spec']['placementRefs'][0]['name'] == 'custom-placement'

    def test_manifest_structure(self):
        """Test that manifests have correct structure."""
        docs = generate_scaffolding_manifests(
            name='test',
            namespace='test',
            clusterset='test',
            placement='test'
        )

        # All documents should be dictionaries
        assert all(isinstance(doc, dict) for doc in docs)

        # All should have apiVersion and kind
        for doc in docs:
            assert 'apiVersion' in doc
            assert 'kind' in doc
            assert 'metadata' in doc


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
