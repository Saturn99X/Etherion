"""
Test model relationships and constraints.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import tempfile
import os


class TestModelRelationships:
    """Test model relationships and constraints."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        engine = create_engine(f'sqlite:///{path}')
        yield engine, path
        os.unlink(path)
    
    def test_tenant_user_relationship(self, temp_db):
        """Test tenant-user relationship."""
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
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            # Create users for the tenant
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user2', 'user2@test.com', 'User 2', 'google', 1, datetime('now'))
            """))
            
            session.commit()
            
            # Test the relationship
            result = session.execute(text("""
                SELECT t.name, COUNT(u.id) as user_count
                FROM tenant t
                LEFT JOIN user u ON t.id = u.tenant_id
                WHERE t.tenant_id = 'tenant1'
                GROUP BY t.id, t.name
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'Tenant 1'
            assert result[1] == 2
            
        finally:
            session.close()
    
    def test_user_project_relationship(self, temp_db):
        """Test user-project relationship."""
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
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            # Create a user
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            # Create projects for the user
            session.execute(text("""
                INSERT INTO project (name, description, user_id, tenant_id, created_at)
                VALUES ('Project 1', 'Description 1', 1, 1, datetime('now'))
            """))
            
            session.execute(text("""
                INSERT INTO project (name, description, user_id, tenant_id, created_at)
                VALUES ('Project 2', 'Description 2', 1, 1, datetime('now'))
            """))
            
            session.commit()
            
            # Test the relationship
            result = session.execute(text("""
                SELECT u.email, COUNT(p.id) as project_count
                FROM user u
                LEFT JOIN project p ON u.id = p.user_id
                WHERE u.user_id = 'user1'
                GROUP BY u.id, u.email
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'user1@test.com'
            assert result[1] == 2
            
        finally:
            session.close()
    
    def test_project_conversation_relationship(self, temp_db):
        """Test project-conversation relationship."""
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
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            # Create a user
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            # Create a project
            session.execute(text("""
                INSERT INTO project (name, description, user_id, tenant_id, created_at)
                VALUES ('Project 1', 'Description 1', 1, 1, datetime('now'))
            """))
            
            # Create conversations for the project
            session.execute(text("""
                INSERT INTO conversation (title, project_id, tenant_id, created_at)
                VALUES ('Conversation 1', 1, 1, datetime('now'))
            """))
            
            session.execute(text("""
                INSERT INTO conversation (title, project_id, tenant_id, created_at)
                VALUES ('Conversation 2', 1, 1, datetime('now'))
            """))
            
            session.commit()
            
            # Test the relationship
            result = session.execute(text("""
                SELECT p.name, COUNT(c.id) as conversation_count
                FROM project p
                LEFT JOIN conversation c ON p.id = c.project_id
                WHERE p.name = 'Project 1'
                GROUP BY p.id, p.name
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'Project 1'
            assert result[1] == 2
            
        finally:
            session.close()
    
    def test_conversation_message_relationship(self, temp_db):
        """Test conversation-message relationship."""
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
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            # Create a user
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            # Create a project
            session.execute(text("""
                INSERT INTO project (name, description, user_id, tenant_id, created_at)
                VALUES ('Project 1', 'Description 1', 1, 1, datetime('now'))
            """))
            
            # Create a conversation
            session.execute(text("""
                INSERT INTO conversation (title, project_id, tenant_id, created_at)
                VALUES ('Conversation 1', 1, 1, datetime('now'))
            """))
            
            # Create messages for the conversation
            session.execute(text("""
                INSERT INTO message (role, content, conversation_id, tenant_id, created_at)
                VALUES ('user', 'Hello', 1, 1, datetime('now'))
            """))
            
            session.execute(text("""
                INSERT INTO message (role, content, conversation_id, tenant_id, created_at)
                VALUES ('assistant', 'Hi there!', 1, 1, datetime('now'))
            """))
            
            session.commit()
            
            # Test the relationship
            result = session.execute(text("""
                SELECT c.title, COUNT(m.id) as message_count
                FROM conversation c
                LEFT JOIN message m ON c.id = m.conversation_id
                WHERE c.title = 'Conversation 1'
                GROUP BY c.id, c.title
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'Conversation 1'
            assert result[1] == 2
            
        finally:
            session.close()
    
    def test_job_execution_trace_relationship(self, temp_db):
        """Test job-execution trace relationship."""
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
            # Create a tenant
            session.execute(text("""
                INSERT INTO tenant (tenant_id, subdomain, name, admin_email, created_at)
                VALUES ('tenant1', 'tenant1', 'Tenant 1', 'admin1@test.com', datetime('now'))
            """))
            
            # Create a user
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            # Create a job
            session.execute(text("""
                INSERT INTO job (job_id, tenant_id, user_id, status, job_type, created_at, last_updated_at)
                VALUES ('test_job_1', 1, 1, 'QUEUED', 'test', datetime('now'), datetime('now'))
            """))
            
            # Create execution trace steps for the job
            session.execute(text("""
                INSERT INTO executiontracestep (job_id, tenant_id, step_number, timestamp, step_type, thought)
                VALUES ('test_job_1', 1, 1, datetime('now'), 'THOUGHT', 'Starting execution')
            """))
            
            session.execute(text("""
                INSERT INTO executiontracestep (job_id, tenant_id, step_number, timestamp, step_type, action_tool)
                VALUES ('test_job_1', 1, 2, datetime('now'), 'ACTION', 'test_tool')
            """))
            
            session.commit()
            
            # Test the relationship
            result = session.execute(text("""
                SELECT j.job_id, COUNT(ets.id) as step_count
                FROM job j
                LEFT JOIN executiontracestep ets ON j.job_id = ets.job_id
                WHERE j.job_id = 'test_job_1'
                GROUP BY j.id, j.job_id
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'test_job_1'
            assert result[1] == 2
            
        finally:
            session.close()
