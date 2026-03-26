import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from google.cloud import storage
from infrastructure.data_ingestion.preprocessors.tabular_preprocessor import process_tabular_file
from infrastructure.data_ingestion.preprocessors.text_preprocessor import process_text_file
from infrastructure.data_ingestion.indexer import index_documents

class TestDataIngestionPipeline:
    """Test suite for the intelligent data ingestion pipeline"""
    
    @pytest.fixture
    def mock_storage_client(self):
        """Mock GCS storage client"""
        with patch('infrastructure.data_ingestion.preprocessors.tabular_preprocessor.storage.Client') as mock:
            yield mock
    
    @pytest.fixture
    def mock_bucket(self):
        """Mock GCS bucket"""
        bucket = Mock(spec=storage.Bucket)
        bucket.blob.return_value = Mock()
        return bucket
    
    @pytest.fixture
    def sample_csv_data(self):
        """Sample CSV data for testing"""
        return """name,email,department
John,john@example.com,Engineering
Jane,jane@example.com,Marketing
Bob,bob@example.com,Sales"""
    
    @pytest.fixture
    def sample_xlsx_data(self):
        """Sample XLSX data (mocked as bytes)"""
        # In real implementation, this would be actual Excel file bytes
        return b"mock_excel_data"
    
    def test_process_tabular_file_csv(self, mock_storage_client, mock_bucket, sample_csv_data):
        """Test processing CSV file"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download
        mock_blob = Mock()
        mock_blob.download_as_bytes.return_value = sample_csv_data.encode()
        mock_bucket.blob.return_value = mock_blob
        
        # Process file
        result = process_tabular_file("test-bucket", "tenant1/project1/data.csv", "tenant1")
        
        # Verify results
        assert len(result) == 3  # 3 rows, each becomes a document
        assert result[0]['metadata']['tenant_id'] == 'tenant1'
        assert result[0]['metadata']['doc_type'] == 'tabular_group'
        assert 'name: ' in result[0]['content']
        assert 'email: ' in result[0]['content']
        assert 'department: ' in result[0]['content']
    
    def test_process_tabular_file_xlsx(self, mock_storage_client, mock_bucket, sample_xlsx_data):
        """Test processing XLSX file"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download
        mock_blob = Mock()
        mock_blob.download_as_bytes.return_value = sample_xlsx_data
        mock_bucket.blob.return_value = mock_blob
        
        # Process file
        result = process_tabular_file("test-bucket", "tenant1/project1/data.xlsx", "tenant1")
        
        # Verify results (mocked data, so expect 1 document)
        assert len(result) == 1
        assert result[0]['metadata']['tenant_id'] == 'tenant1'
        assert result[0]['metadata']['doc_type'] == 'tabular_group'
    
    def test_process_tabular_file_no_key_column(self, mock_storage_client, mock_bucket):
        """Test processing CSV with no suitable key column"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download with data that has no high-unique-ratio column
        mock_blob = Mock()
        mock_blob.download_as_bytes.return_value = "name,department\nJohn,Engineering\nJane,Engineering".encode()
        mock_bucket.blob.return_value = mock_blob
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="No suitable key column found"):
            process_tabular_file("test-bucket", "tenant1/project1/data.csv", "tenant1")
    
    def test_process_text_file(self, mock_storage_client, mock_bucket):
        """Test processing text file"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download
        mock_blob = Mock()
        test_text = "This is a test document. It contains multiple sentences. " * 20  # Long text
        mock_blob.download_as_text.return_value = test_text
        mock_bucket.blob.return_value = mock_blob
        
        # Process file
        result = process_text_file("test-bucket", "tenant1/project1/document.txt", "tenant1")
        
        # Verify results
        assert len(result) > 1  # Should be split into multiple chunks
        assert result[0]['metadata']['tenant_id'] == 'tenant1'
        assert result[0]['metadata']['doc_type'] == 'text_chunk'
        assert result[0]['metadata']['chunk_index'] == 0
        assert len(result[0]['content']) <= 1500  # Chunk size limit
    
    def test_process_text_file_too_small(self, mock_storage_client, mock_bucket):
        """Test processing text file that's too small"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download with very small text
        mock_blob = Mock()
        mock_blob.download_as_text.return_value = "small"
        mock_bucket.blob.return_value = mock_blob
        
        # Process file
        result = process_text_file("test-bucket", "tenant1/project1/small.txt", "tenant1")
        
        # Should return empty list
        assert result == []
    
    def test_process_text_file_too_large(self, mock_storage_client, mock_bucket):
        """Test processing text file that's too large (should be truncated)"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob download with very large text
        large_text = "x" * (15 * 1024 * 1024)  # 15MB
        mock_blob = Mock()
        mock_blob.download_as_text.return_value = large_text
        mock_bucket.blob.return_value = mock_blob
        
        # Process file
        result = process_text_file("test-bucket", "tenant1/project1/large.txt", "tenant1")
        
        # Should process truncated content
        assert len(result) > 0
        assert result[0]['metadata']['tenant_id'] == 'tenant1'
    
    def test_index_documents(self, mock_storage_client, mock_bucket):
        """Test indexing documents to JSONL"""
        # Setup mocks
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        
        # Mock blob upload
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob
        
        # Sample documents
        documents = [
            {
                'content': 'Test document 1',
                'metadata': {'tenant_id': 'tenant1', 'source_file': 'test.csv', 'doc_type': 'tabular_group'}
            },
            {
                'content': 'Test document 2',
                'metadata': {'tenant_id': 'tenant1', 'source_file': 'test.csv', 'doc_type': 'tabular_group'}
            }
        ]
        
        # Index documents
        result = index_documents(documents, 'tenant1', 'test-ingestion-bucket')
        
        # Verify results
        assert result.startswith('processed_test_')
        assert result.endswith('.jsonl')
        mock_blob.upload_from_string.assert_called_once()
        
        # Verify uploaded content is valid JSONL
        call_args = mock_blob.upload_from_string.call_args[0][0]
        lines = call_args.strip().split('\n')
        assert len(lines) == 2
        
        # Parse JSON lines
        import json
        doc1 = json.loads(lines[0])
        doc2 = json.loads(lines[1])
        
        assert doc1['content'] == 'Test document 1'
        assert doc1['metadata']['tenant_id'] == 'tenant1'
        assert doc2['content'] == 'Test document 2'
        assert doc2['metadata']['tenant_id'] == 'tenant1'
    
    def test_find_key_column(self):
        """Test key column detection logic"""
        import pandas as pd
        from infrastructure.data_ingestion.preprocessors.tabular_preprocessor import _find_key_column
        
        # Test with high unique ratio column
        df1 = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],  # 100% unique
            'name': ['a', 'b', 'c', 'd', 'e'],  # 100% unique
            'category': ['x', 'x', 'y', 'y', 'z']  # 60% unique
        })
        
        key_column = _find_key_column(df1)
        assert key_column in ['id', 'name']  # Either could be chosen
        
        # Test with no high unique ratio column
        df2 = pd.DataFrame({
            'category': ['x', 'x', 'y', 'y', 'z'],  # 60% unique
            'status': ['a', 'a', 'b', 'b', 'c']  # 60% unique
        })
        
        key_column = _find_key_column(df2)
        assert key_column is None
