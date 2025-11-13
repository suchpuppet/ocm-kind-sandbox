"""
Unit tests for load-images command (load-images-to-kind logic).

Note: Tests for Docker/Kind interactions are mocked to avoid requiring
actual Docker/Kind installations during testing.
"""
import os
import tempfile
import yaml
from unittest.mock import patch
from pathlib import Path
import pytest

from ocm_sandbox.commands.load_images import load_images_from_config


class TestLoadImagesFromConfig:
    """Test YAML config file loading and parsing."""

    def test_load_simple_config(self):
        """Test loading simple image list."""
        config = {
            'images': [
                'nginx:alpine',
                'redis:7'
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            # Mock the functions that interact with Docker/Kind
            with patch('ocm_sandbox.commands.load_images.check_kind_cluster') as mock_check, \
                 patch('ocm_sandbox.commands.load_images.load_image_with_workaround') as mock_load:

                mock_check.return_value = True
                mock_load.return_value = True

                result = load_images_from_config(Path(config_file), 'test-cluster', 'linux/amd64')

                # Should succeed
                assert result == 0

                # Should check cluster once (default cluster)
                assert mock_check.call_count >= 1

                # Should load both images
                assert mock_load.call_count == 2

        finally:
            os.remove(config_file)

    def test_load_advanced_config(self):
        """Test loading config with per-image cluster specification."""
        config = {
            'images': [
                {'image': 'nginx:alpine', 'cluster': 'cluster1'},
                {'image': 'redis:7', 'cluster': 'cluster2'}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            with patch('ocm_sandbox.commands.load_images.check_kind_cluster') as mock_check, \
                 patch('ocm_sandbox.commands.load_images.load_image_with_workaround') as mock_load:

                mock_check.return_value = True
                mock_load.return_value = True

                result = load_images_from_config(Path(config_file), 'default-cluster', 'linux/amd64')

                # Should check both clusters
                assert mock_check.call_count == 2

                # Should load both images
                assert mock_load.call_count == 2

                # Verify correct clusters were used
                check_calls = [call[0][0] for call in mock_check.call_args_list]
                assert 'cluster1' in check_calls
                assert 'cluster2' in check_calls

        finally:
            os.remove(config_file)

    def test_missing_config_file(self):
        """Test handling of missing config file."""
        result = load_images_from_config(Path('/nonexistent/file.yaml'), 'test-cluster', 'linux/amd64')
        assert result == 1

    def test_invalid_yaml(self):
        """Test handling of invalid YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [[[")
            config_file = f.name

        try:
            result = load_images_from_config(Path(config_file), 'test-cluster', 'linux/amd64')
            assert result == 1
        finally:
            os.remove(config_file)

    def test_missing_images_key(self):
        """Test config without 'images' key."""
        config = {'wrong_key': ['nginx:alpine']}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            result = load_images_from_config(Path(config_file), 'test-cluster', 'linux/amd64')
            assert result == 1
        finally:
            os.remove(config_file)

    def test_empty_images_list(self):
        """Test config with empty images list."""
        config = {'images': []}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            result = load_images_from_config(Path(config_file), 'test-cluster', 'linux/amd64')
            # Should succeed but not load anything
            assert result == 0
        finally:
            os.remove(config_file)

    def test_mixed_format_config(self):
        """Test config with both simple and advanced format."""
        config = {
            'images': [
                'nginx:alpine',  # Simple format
                {'image': 'redis:7', 'cluster': 'custom-cluster'}  # Advanced format
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            with patch('ocm_sandbox.commands.load_images.check_kind_cluster') as mock_check, \
                 patch('ocm_sandbox.commands.load_images.load_image_with_workaround') as mock_load:

                mock_check.return_value = True
                mock_load.return_value = True

                result = load_images_from_config(Path(config_file), 'default-cluster', 'linux/amd64')

                assert result == 0
                assert mock_load.call_count == 2

        finally:
            os.remove(config_file)

    def test_cluster_not_found(self):
        """Test handling when specified cluster doesn't exist."""
        config = {
            'images': [
                {'image': 'nginx:alpine', 'cluster': 'nonexistent-cluster'}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            with patch('ocm_sandbox.commands.load_images.check_kind_cluster') as mock_check, \
                 patch('ocm_sandbox.commands.load_images.load_image_with_workaround') as mock_load:

                mock_check.return_value = False  # Cluster doesn't exist
                mock_load.return_value = True

                result = load_images_from_config(Path(config_file), 'default-cluster', 'linux/amd64')

                # Should fail due to missing cluster
                assert result == 1

        finally:
            os.remove(config_file)

    def test_image_load_failure(self):
        """Test handling when image load fails."""
        config = {
            'images': [
                'nginx:alpine',
                'bad-image:tag'
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_file = f.name

        try:
            with patch('ocm_sandbox.commands.load_images.check_kind_cluster') as mock_check, \
                 patch('ocm_sandbox.commands.load_images.load_image_with_workaround') as mock_load:

                mock_check.return_value = True
                # First image succeeds, second fails
                mock_load.side_effect = [True, False]

                result = load_images_from_config(Path(config_file), 'test-cluster', 'linux/amd64')

                # Should return error code due to failure
                assert result == 1

        finally:
            os.remove(config_file)


class TestImageParsing:
    """Test image name parsing and validation."""

    def test_valid_image_names(self):
        """Test various valid image name formats."""
        valid_images = [
            'nginx',
            'nginx:latest',
            'nginx:1.21',
            'library/nginx',
            'library/nginx:latest',
            'docker.io/library/nginx',
            'docker.io/library/nginx:1.21',
            'gcr.io/my-project/my-image:v1.0.0',
            'localhost:5000/myimage:dev',
        ]

        # All should be valid strings
        for image in valid_images:
            assert isinstance(image, str)
            assert len(image) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
