# tests/test_deployment.py
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

class TestDeployment(unittest.TestCase):
    """Test deployment configuration and setup."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        dockerfile_path = os.path.join(os.path.dirname(__file__), '..', 'Dockerfile')
        self.assertTrue(os.path.exists(dockerfile_path), "Dockerfile should exist")

    def test_requirements_txt_exists(self):
        """Test that requirements.txt exists."""
        requirements_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
        self.assertTrue(os.path.exists(requirements_path), "requirements.txt should exist")

    def test_terraform_files_exist(self):
        """Test that Terraform files exist."""
        terraform_paths = [
            'terraform/modules/tenant/main.tf',
            'terraform/modules/tenant/variables.tf',
            'terraform/modules/tenant/outputs.tf',
            'terraform/modules/tenant/versions.tf',
            'terraform/modules/tenant/monitoring.tf',
            'terraform/modules/tenant/security.tf',
            'terraform/environments/dev/backend.tf',
            'terraform/environments/prod/backend.tf',
            'terraform/environments/dev/main.tf',
            'terraform/environments/prod/main.tf',
        ]
        
        for path in terraform_paths:
            full_path = os.path.join(os.path.dirname(__file__), '..', path)
            self.assertTrue(os.path.exists(full_path), f"Terraform file {path} should exist")

    def test_workflow_file_exists(self):
        """Test that GitHub Actions workflow file exists."""
        workflow_path = os.path.join(os.path.dirname(__file__), '..', '.github', 'workflows', 'main.yml')
        self.assertTrue(os.path.exists(workflow_path), "GitHub Actions workflow file should exist")

    @patch('src.etherion_ai.utils.logging_utils.CLOUD_LOGGING_AVAILABLE', False)
    def test_logging_setup_without_cloud_logging(self):
        """Test logging setup without Google Cloud Logging."""
        from src.etherion_ai.utils.logging_utils import setup_logging
        # This should not raise an exception
        setup_logging()

    def test_monitoring_initialization(self):
        """Test monitoring initialization."""
        from src.etherion_ai.utils.monitoring import initialize_monitoring
        # This should not raise an exception
        initialize_monitoring("test-project-id")

    def test_profiling_initialization(self):
        """Test profiling initialization."""
        from src.etherion_ai.utils.profiling import initialize_performance_profiler
        # This should not raise an exception
        initialize_performance_profiler("test-project-id")

if __name__ == '__main__':
    unittest.main()