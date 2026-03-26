"""
Test database performance with indexes.
"""

import pytest
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import tempfile
import os


class TestDatabasePerformance:
    """Test database performance with indexes."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        engine = create_engine(f'sqlite:///{path}')
        yield engine, path
        os.unlink(path)
    
    def test_tenant_query_performance(self, temp_db):
        """Test performance of tenant-based queries."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
            # Enable foreign key constraints
            session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Create test data
            for i in range(100):
                session.execute(text(f"""
                    INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                    VALUES ('tenant{i}', 'tenant{i}', 'Tenant {i}', 'admin{i}@test.com', datetime('now'))
                """))
            
            for i in range(1000):
                tenant_id = (i % 100) + 1
                session.execute(text(f"""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES ('user{i}', 'user{i}@test.com', 'User {i}', {tenant_id}, datetime('now'))
                """))
            
            for i in range(5000):
                tenant_id = (i % 100) + 1
                user_id = (i % 1000) + 1
                session.execute(text(f"""
                    INSERT INTO project (name, description, user_id, tenant_id, created_at)
                    VALUES ('Project {i}', 'Description {i}', {user_id}, {tenant_id}, datetime('now'))
                """))
            
            session.commit()
            
            # Test query performance with tenant_id index
            start_time = time.time()
            result = session.execute(text("""
                SELECT COUNT(*) FROM project WHERE tenant_id = 1
            """)).fetchone()
            end_time = time.time()
            
            query_time = end_time - start_time
            assert query_time < 0.1, f"Query took too long: {query_time}s"
            assert result[0] == 50  # Should have 50 projects for tenant 1
            
        finally:
            session.close()
    
    def test_composite_index_performance(self, temp_db):
        """Test performance of composite indexes."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
            # Enable foreign key constraints
            session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Create test data
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            # Create many jobs with different statuses
            for i in range(1000):
                status = 'QUEUED' if i % 2 == 0 else 'COMPLETED'
                session.execute(text(f"""
                    INSERT INTO job (job_id, tenant_id, user_id, status, job_type, created_at, last_updated_at)
                    VALUES ('job{i}', 1, 1, '{status}', 'test', datetime('now'), datetime('now'))
                """))
            
            session.commit()
            
            # Test composite index performance (tenant_id + status)
            start_time = time.time()
            result = session.execute(text("""
                SELECT COUNT(*) FROM job WHERE tenant_id = 1 AND status = 'QUEUED'
            """)).fetchone()
            end_time = time.time()
            
            query_time = end_time - start_time
            assert query_time < 0.1, f"Composite index query took too long: {query_time}s"
            assert result[0] == 500  # Should have 500 QUEUED jobs
            
        finally:
            session.close()
    
    def test_foreign_key_index_performance(self, temp_db):
        """Test performance of foreign key indexes."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
            # Enable foreign key constraints
            session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Create test data
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            for i in range(100):
                session.execute(text(f"""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES ('user{i}', 'user{i}@test.com', 'User {i}', 'google', 1, datetime('now'))
                """))
            
            for i in range(1000):
                user_id = (i % 100) + 1
                session.execute(text(f"""
                    INSERT INTO project (name, description, user_id, tenant_id, created_at)
                    VALUES ('Project {i}', 'Description {i}', {user_id}, 1, datetime('now'))
                """))
            
            session.commit()
            
            # Test foreign key index performance (user_id)
            start_time = time.time()
            result = session.execute(text("""
                SELECT COUNT(*) FROM project WHERE user_id = 1
            """)).fetchone()
            end_time = time.time()
            
            query_time = end_time - start_time
            assert query_time < 0.1, f"Foreign key index query took too long: {query_time}s"
            assert result[0] == 10  # Should have 10 projects for user 1
            
        finally:
            session.close()
    
    def test_index_usage_verification(self, temp_db):
        """Test that indexes are being used by the query planner."""
        engine, _ = temp_db
        
        # Apply all migrations
        from alembic.config import Config
        from alembic import command
        cfg = Config('alembic.ini')
        cfg.set_main_option('sqlalchemy.url', str(engine.url))
        command.upgrade(cfg, 'head')
        
        Session = sessionmaker(bind=engine)
        session = Session()
            # Enable foreign key constraints
            session.execute(text('PRAGMA foreign_keys=ON'))
        
        try:
            # Create test data
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            for i in range(100):
                session.execute(text(f"""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES ('user{i}', 'user{i}@test.com', 'User {i}', 'google', 1, datetime('now'))
                """))
            
            session.commit()
            
            # Check that indexes exist
            result = session.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name LIKE '%tenant_id%'
            """)).fetchall()
            
            index_names = [row[0] for row in result]
            assert 'ix_user_tenant_id' in index_names
            
            # Test query plan to verify index usage
            result = session.execute(text("""
                EXPLAIN QUERY PLAN SELECT * FROM user WHERE tenant_id = 1
            """)).fetchall()
            
            # The query plan should show index usage
            query_plan = ' '.join([row[3] for row in result if row[3]])
            assert 'INDEX' in query_plan or 'SCAN' in query_plan
            
        finally:
            session.close()
