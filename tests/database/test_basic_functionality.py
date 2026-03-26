"""
Basic database functionality tests to demonstrate the database foundation is working.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import tempfile
import os


class TestBasicDatabaseFunctionality:
    """Test basic database functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        engine = create_engine(f'sqlite:///{path}')
        yield engine, path
        os.unlink(path)
    
    def test_migration_chain_works(self, temp_db):
        """Test that the migration chain can be applied successfully."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        
        # This should not raise any exceptions
        command.upgrade(cfg, 'head')
        
        # Verify we can query the database
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Check that tables exist
            result = session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('tenant', 'user', 'project', 'job')
            """)).fetchall()
            
            table_names = [row[0] for row in result]
            expected_tables = ['tenant', 'user', 'project', 'job']
            
            for expected in expected_tables:
                assert expected in table_names, f"Table {expected} not found"
                
        finally:
            session.close()
    
    def test_tenant_isolation_structure(self, temp_db):
        """Test that tenant isolation structure is in place."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Check that tenant_id columns exist in key tables
            result = session.execute(text("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name IN ('user', 'project', 'job')
            """)).fetchall()
            
            # Verify tenant_id columns exist
            for row in result:
                sql = row[0]
                assert 'tenant_id' in sql, f"tenant_id column not found in table schema: {sql}"
                
        finally:
            session.close()
    
    def test_foreign_key_structure(self, temp_db):
        """Test that foreign key structure is in place."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Check that indexes exist for foreign keys
            result = session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name LIKE '%tenant_id%'
            """)).fetchall()
            
            index_names = [row[0] for row in result]
            # Should have at least some tenant_id indexes
            assert len(index_names) > 0, "No tenant_id indexes found"
            
        finally:
            session.close()
    
    def test_can_create_basic_data(self, temp_db):
        """Test that we can create basic data with proper structure."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('test_tenant', 'test', 'Test Tenant', 'admin@test.com', datetime('now'))
            """))
            
            # Create a user with provider field
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('test_user', 'user@test.com', 'Test User', 'google', 1, datetime('now'))
            """))
            
            session.commit()
            
            # Verify data was created
            result = session.execute(text("""
                SELECT COUNT(*) FROM tenant WHERE tenant_id = 'test_tenant'
            """)).fetchone()
            assert result[0] == 1
            
            result = session.execute(text("""
                SELECT COUNT(*) FROM user WHERE user_id = 'test_user'
            """)).fetchone()
            assert result[0] == 1
            
        finally:
            session.close()
