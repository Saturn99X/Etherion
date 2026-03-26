"""
Test data integrity and validation.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import tempfile
import os


class TestDataIntegrity:
    """Test data integrity and validation."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        engine = create_engine(f'sqlite:///{path}')
        yield engine, path
        os.unlink(path)
    
    def test_foreign_key_constraint_enforcement(self, temp_db):
        """Test that foreign key constraints are properly enforced."""
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
            
            session.commit()
            
            # Try to create a user with invalid tenant_id
            try:
                session.execute(text("""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES ('user1', 'user1@test.com', 'User 1', 'google', 999, datetime('now'))
                """))
                session.commit()
                assert False, "Foreign key constraint should have been enforced"
            except Exception as e:
                # Expected to fail
                assert "FOREIGN KEY constraint failed" in str(e) or "no such table" in str(e)
            
            # Try to create a project with invalid user_id
            try:
                session.execute(text("""
                    INSERT INTO project (name, description, user_id, tenant_id, created_at)
                    VALUES ('Project 1', 'Description 1', 999, 1, datetime('now'))
                """))
                session.commit()
                assert False, "Foreign key constraint should have been enforced"
            except Exception as e:
                # Expected to fail
                assert "FOREIGN KEY constraint failed" in str(e) or "no such table" in str(e)
                
        finally:
            session.close()
    
    def test_unique_constraint_enforcement(self, temp_db):
        """Test that unique constraints are properly enforced."""
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
            
            session.commit()
            
            # Try to create a user with duplicate user_id
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            try:
                session.execute(text("""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES ('user1', 'user2@test.com', 'User 2', 'google', 1, datetime('now'))
                """))
                session.commit()
                assert False, "Unique constraint should have been enforced"
            except Exception as e:
                # Expected to fail
                assert "UNIQUE constraint failed" in str(e) or "no such table" in str(e)
                
        finally:
            session.close()
    
    def test_not_null_constraint_enforcement(self, temp_db):
        """Test that NOT NULL constraints are properly enforced."""
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
            
            session.commit()
            
            # Try to create a user with NULL user_id
            try:
                session.execute(text("""
                    INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                    VALUES (NULL, 'user1@test.com', 'User 1', 1, datetime('now'))
                """))
                session.commit()
                assert False, "NOT NULL constraint should have been enforced"
            except Exception as e:
                # Expected to fail
                assert "NOT NULL constraint failed" in str(e) or "no such table" in str(e)
                
        finally:
            session.close()
    
    def test_cascade_delete_behavior(self, temp_db):
        """Test cascade delete behavior for related records."""
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
            
            session.commit()
            
            # Verify the project exists
            result = session.execute(text("""
                SELECT COUNT(*) FROM project WHERE name = 'Project 1'
            """)).fetchone()
            assert result[0] == 1
            
            # Delete the user (this should cascade to delete the project)
            session.execute(text("""
                DELETE FROM user WHERE user_id = 'user1'
            """))
            session.commit()
            
            # Verify the project was deleted
            result = session.execute(text("""
                SELECT COUNT(*) FROM project WHERE name = 'Project 1'
            """)).fetchone()
            assert result[0] == 0
            
        finally:
            session.close()
    
    def test_data_validation_at_model_level(self, temp_db):
        """Test data validation at the model level."""
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
            
            session.commit()
            
            # Test valid data insertion
            session.execute(text("""
                INSERT INTO user (user_id, email, name, provider, tenant_id, created_at)
                VALUES ('user1', 'user1@test.com', 'User 1', 'google', 1, datetime('now'))
            """))
            
            session.commit()
            
            # Verify the user was created
            result = session.execute(text("""
                SELECT user_id, email, name FROM user WHERE user_id = 'user1'
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'user1'
            assert result[1] == 'user1@test.com'
            assert result[2] == 'User 1'
            
        finally:
            session.close()
    
    def test_referential_integrity(self, temp_db):
        """Test referential integrity across related tables."""
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
            
            session.commit()
            
            # Test referential integrity by joining related tables
            result = session.execute(text("""
                SELECT t.name as tenant_name, u.email as user_email, p.name as project_name, c.title as conversation_title
                FROM tenant t
                JOIN user u ON t.id = u.tenant_id
                JOIN project p ON u.id = p.user_id AND t.id = p.tenant_id
                JOIN conversation c ON p.id = c.project_id AND t.id = c.tenant_id
                WHERE t.tenant_id = 'tenant1'
            """)).fetchone()
            
            assert result is not None
            assert result[0] == 'Tenant 1'
            assert result[1] == 'user1@test.com'
            assert result[2] == 'Project 1'
            assert result[3] == 'Conversation 1'
            
        finally:
            session.close()
