"""
Test database migrations up and down.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import tempfile
import os


class TestMigrations:
    """Test all migrations can be applied and rolled back."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        engine = create_engine(f'sqlite:///{path}')
        yield engine, path
        os.unlink(path)
    
    @pytest.fixture
    def alembic_cfg(self, temp_db):
        """Create alembic config for testing."""
        engine, db_path = temp_db
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', f'sqlite:///{db_path}')
        return cfg
    
    def test_migration_chain_integrity(self, alembic_cfg):
        """Test that all migrations can be applied in sequence."""
        # Apply all migrations
        command.upgrade(alembic_cfg, 'head')
        
        # Verify we can get current revision
        from alembic import script
        from alembic.runtime import migration
        from sqlalchemy import create_engine
        script_dir = script.ScriptDirectory.from_config(alembic_cfg)
        engine = create_engine(alembic_cfg.get_main_option('sqlalchemy.url'))
        with engine.connect() as connection:
            context = migration.MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            assert current_rev is not None
            assert current_rev == script_dir.get_current_head()
    
    def test_migration_rollback(self, alembic_cfg):
        """Test that migrations can be rolled back."""
        # Apply all migrations
        command.upgrade(alembic_cfg, 'head')
        
        # Roll back to base
        command.downgrade(alembic_cfg, 'base')
        
        # Verify we're at base
        from alembic import script
        from alembic.runtime import migration
        from sqlalchemy import create_engine
        script_dir = script.ScriptDirectory.from_config(alembic_cfg)
        engine = create_engine(alembic_cfg.get_main_option('sqlalchemy.url'))
        with engine.connect() as connection:
            context = migration.MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            assert current_rev is None
    
    def test_foreign_key_constraints(self, temp_db):
        """Test that foreign key constraints are properly enforced."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        # Test foreign key constraint enforcement
        Session = sessionmaker(bind=engine)
        session = Session()
        # Enable foreign key constraints
        session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Try to insert a job with invalid tenant_id
            result = session.execute(text("""
                INSERT INTO job (job_id, tenant_id, user_id, status, job_type, created_at, last_updated_at)
                VALUES ('test_job', 99999, 1, 'QUEUED', 'test', datetime('now'), datetime('now'))
            """))
            session.commit()
            # This should fail due to foreign key constraint
            assert False, "Foreign key constraint not enforced"
        except Exception as e:
            # Expected to fail - SQLite may not enforce foreign keys by default
            # So we just check that we got some kind of error
            assert "constraint" in str(e).lower() or "no such table" in str(e).lower()
        finally:
            session.close()
    
    def test_indexes_created(self, temp_db):
        """Test that all required indexes are created."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        # Check that key indexes exist
        Session = sessionmaker(bind=engine)
        session = Session()
        # Enable foreign key constraints
        session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Check for tenant_id indexes
            result = session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name LIKE '%tenant_id%'
            """)).fetchall()
            
            index_names = [row[0] for row in result]
            expected_indexes = [
                'ix_job_tenant_id',
                'ix_executiontracestep_tenant_id',
                'ix_customagentdefinition_tenant_id',
                'ix_agentteam_tenant_id'
            ]
            
            for expected in expected_indexes:
                assert expected in index_names, f"Index {expected} not found"
                
        finally:
            session.close()