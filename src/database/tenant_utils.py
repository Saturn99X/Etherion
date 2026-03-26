"""
Utility functions for tenant-aware database operations.
"""

from typing import Optional, TypeVar, List
from sqlmodel import Session, select, SQLModel
from sqlalchemy.orm import Query
from sqlalchemy.sql.elements import BinaryExpression
from src.database.models import Tenant, User


T = TypeVar('T', bound=SQLModel)


def get_tenant_from_subdomain(subdomain: str, session: Session) -> Optional[Tenant]:
    """
    Retrieve a tenant by subdomain.
    
    Args:
        subdomain: The subdomain to look up
        session: Database session
        
    Returns:
        Tenant: The tenant if found, None otherwise
    """
    statement = select(Tenant).where(Tenant.subdomain == subdomain)
    return session.exec(statement).first()


def add_tenant_filter(query: Query, tenant_id: int, model_class: T) -> Query:
    """
    Add tenant_id filter to a query.
    
    Args:
        query: The SQLAlchemy query to modify
        tenant_id: The tenant ID to filter by
        model_class: The model class being queried
        
    Returns:
        The modified query with tenant_id filter
    """
    # Check if the model has a tenant_id attribute
    if hasattr(model_class, 'tenant_id'):
        return query.where(model_class.tenant_id == tenant_id)
    return query


def get_tenant_aware_records(session: Session, tenant_id: int, model_class: T) -> List[T]:
    """
    Get all records of a specific model class for a given tenant.
    
    Args:
        session: Database session
        tenant_id: The tenant ID to filter by
        model_class: The model class to query
        
    Returns:
        List of records belonging to the specified tenant
    """
    statement = select(model_class).where(model_class.tenant_id == tenant_id)
    return session.exec(statement).all()


def get_tenant_aware_record_by_id(session: Session, tenant_id: int, model_class: T, record_id: int) -> Optional[T]:
    """
    Get a specific record by ID, ensuring it belongs to the specified tenant.
    
    Args:
        session: Database session
        tenant_id: The tenant ID to filter by
        model_class: The model class to query
        record_id: The ID of the record to retrieve
        
    Returns:
        The record if found and belongs to the tenant, None otherwise
    """
    statement = select(model_class).where(
        model_class.id == record_id,
        model_class.tenant_id == tenant_id
    )
    return session.exec(statement).first()


def create_tenant_aware_record(session: Session, tenant_id: int, model_instance: T) -> T:
    """
    Create a new record with tenant association.
    
    Args:
        session: Database session
        tenant_id: The tenant ID to associate with the record
        model_instance: The model instance to create
        
    Returns:
        The created model instance
    """
    # Set the tenant_id on the model instance
    if hasattr(model_instance, 'tenant_id'):
        model_instance.tenant_id = tenant_id
    
    session.add(model_instance)
    session.commit()
    session.refresh(model_instance)
    return model_instance