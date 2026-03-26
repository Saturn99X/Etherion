"""
Atomic credit management system with transaction safety.
"""

import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from contextlib import contextmanager
from src.database.db import session_scope
from src.database.models import Tenant, ExecutionCost
from src.utils.tenant_context import get_tenant_context

logger = logging.getLogger(__name__)


class CreditInsufficientError(Exception):
    """Raised when insufficient credits for an operation."""
    pass


class CreditUpdateError(Exception):
    """Raised when credit update fails."""
    pass


class CreditTransaction:
    """Represents a credit transaction with rollback capability."""
    
    def __init__(self, tenant_id: int, amount: Decimal, operation: str, 
                 description: str = "", metadata: Optional[Dict[str, Any]] = None):
        self.tenant_id = tenant_id
        self.amount = amount
        self.operation = operation
        self.description = description
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()
        self.committed = False
        self.rolled_back = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to dictionary."""
        return {
            'tenant_id': self.tenant_id,
            'amount': float(self.amount),
            'operation': self.operation,
            'description': self.description,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
            'committed': self.committed,
            'rolled_back': self.rolled_back
        }


class CreditManager:
    """Atomic credit management system."""
    
    def __init__(self):
        self._active_transactions: Dict[str, CreditTransaction] = {}
    
    @contextmanager
    def atomic_credit_transaction(self, tenant_id: int, amount: Decimal, 
                                 operation: str, description: str = "",
                                 metadata: Optional[Dict[str, Any]] = None):
        """
        Context manager for atomic credit transactions.
        
        Args:
            tenant_id: Tenant ID
            amount: Credit amount (positive for credit, negative for debit)
            operation: Operation type (e.g., 'job_execution', 'api_call')
            description: Human-readable description
            metadata: Additional metadata
            
        Yields:
            CreditTransaction: The transaction object
            
        Raises:
            CreditInsufficientError: If insufficient credits
            CreditUpdateError: If update fails
        """
        transaction_id = f"{tenant_id}_{operation}_{datetime.utcnow().timestamp()}"
        transaction = CreditTransaction(tenant_id, amount, operation, description, metadata)
        
        try:
            # Store transaction (decision will be enforced atomically in DB)
            self._active_transactions[transaction_id] = transaction
            
            # Perform the credit update
            self._update_credits_atomic(tenant_id, amount, operation, description, metadata)
            
            # Mark as committed
            transaction.committed = True
            
            yield transaction
            
        except Exception as e:
            # Rollback only if update was committed and amount applied
            if transaction.committed and not transaction.rolled_back:
                self._rollback_credit_update(tenant_id, amount, operation)
                transaction.rolled_back = True
            raise e
        finally:
            # Clean up
            if transaction_id in self._active_transactions:
                del self._active_transactions[transaction_id]
    
    def _update_credits_atomic(self, tenant_id: int, amount: Decimal, 
                              operation: str, description: str,
                              metadata: Optional[Dict[str, Any]] = None):
        """Atomically update tenant credits."""
        try:
            with session_scope() as session:
                # Enforce non-negative balance atomically within the UPDATE
                result = session.execute(
                    text(
                        """
                        UPDATE tenant
                        SET credit_balance = credit_balance + :amount,
                            last_updated_at = :timestamp
                        WHERE id = :tenant_id
                          AND (credit_balance + :amount) >= 0
                        RETURNING credit_balance
                        """
                    ),
                    {
                        'amount': float(amount),
                        'tenant_id': tenant_id,
                        'timestamp': datetime.utcnow()
                    }
                )
                row = result.first()
                if not row:
                    # Determine current balance to improve error message (best effort)
                    bal = session.execute(
                        text("SELECT credit_balance FROM tenant WHERE id = :tenant_id"),
                        {'tenant_id': tenant_id}
                    ).scalar()
                    if bal is None:
                        raise CreditUpdateError(f"Tenant {tenant_id} not found")
                    raise CreditInsufficientError(
                        f"Insufficient credits. Attempted change: {amount}, Current balance: {bal}"
                    )
                new_balance = row[0]
                
                # Record the transaction in execution cost table
                execution_cost = ExecutionCost(
                    tenant_id=tenant_id,
                    operation_type=operation,
                    cost_amount=abs(float(amount)),
                    description=description,
                    metadata=metadata or {}
                )
                session.add(execution_cost)
                session.commit()
                
                logger.info(f"Updated credits for tenant {tenant_id}: {amount} (new balance: {new_balance})")
                
        except Exception as e:
            logger.error(f"Failed to update credits for tenant {tenant_id}: {e}")
            raise CreditUpdateError(f"Credit update failed: {str(e)}")
    
    def _rollback_credit_update(self, tenant_id: int, amount: Decimal, operation: str):
        """Rollback a credit update."""
        try:
            with session_scope() as session:
                # Reverse the credit update
                session.execute(
                    text("""
                        UPDATE tenant 
                        SET credit_balance = credit_balance - :amount,
                            last_updated_at = :timestamp
                        WHERE id = :tenant_id
                    """),
                    {
                        'amount': float(amount),
                        'tenant_id': tenant_id,
                        'timestamp': datetime.utcnow()
                    }
                )
                session.commit()
                
                logger.info(f"Rolled back credits for tenant {tenant_id}: {-amount}")
                
        except Exception as e:
            logger.error(f"Failed to rollback credits for tenant {tenant_id}: {e}")
    
    def get_credit_balance(self, tenant_id: int) -> Decimal:
        """Get current credit balance for a tenant."""
        try:
            with session_scope() as session:
                tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
                if not tenant:
                    raise CreditUpdateError(f"Tenant {tenant_id} not found")
                
                return Decimal(str(tenant.credit_balance))
                
        except Exception as e:
            logger.error(f"Failed to get credit balance for tenant {tenant_id}: {e}")
            return Decimal('0')
    
    def reserve_credits(self, tenant_id: int, amount: Decimal, 
                       operation: str, description: str = "",
                       metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Reserve credits for a future operation.
        
        Args:
            tenant_id: Tenant ID
            amount: Amount to reserve
            operation: Operation type
            description: Description
            metadata: Additional metadata
            
        Returns:
            str: Transaction ID for later commit/rollback
            
        Raises:
            CreditInsufficientError: If insufficient credits
        """
        transaction_id = f"reserve_{tenant_id}_{operation}_{datetime.utcnow().timestamp()}"
        
        # Create reservation transaction
        transaction = CreditTransaction(tenant_id, -amount, f"reserve_{operation}", 
                                      f"Reservation: {description}", metadata)
        self._active_transactions[transaction_id] = transaction
        
        # Reserve credits atomically (debit); will raise CreditInsufficientError if not enough
        self._update_credits_atomic(tenant_id, -amount, f"reserve_{operation}", 
                                   f"Reservation: {description}", metadata)
        
        return transaction_id
    
    def commit_reservation(self, transaction_id: str, final_amount: Optional[Decimal] = None):
        """
        Commit a credit reservation.
        
        Args:
            transaction_id: Transaction ID from reserve_credits
            final_amount: Final amount (if different from reserved amount)
        """
        if transaction_id not in self._active_transactions:
            raise CreditUpdateError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        
        if final_amount is not None and final_amount != abs(transaction.amount):
            # Adjust the reservation
            difference = final_amount - abs(transaction.amount)
            if difference != 0:
                self._update_credits_atomic(
                    transaction.tenant_id, 
                    difference, 
                    f"adjust_{transaction.operation}",
                    f"Adjustment for {transaction.description}"
                )
        
        # Mark as committed and clean up
        transaction.committed = True
        del self._active_transactions[transaction_id]
        
        logger.info(f"Committed credit reservation {transaction_id}")
    
    def rollback_reservation(self, transaction_id: str):
        """
        Rollback a credit reservation.
        
        Args:
            transaction_id: Transaction ID from reserve_credits
        """
        if transaction_id not in self._active_transactions:
            raise CreditUpdateError(f"Transaction {transaction_id} not found")
        
        transaction = self._active_transactions[transaction_id]
        
        # Refund the reserved credits
        self._update_credits_atomic(
            transaction.tenant_id, 
            abs(transaction.amount), 
            f"refund_{transaction.operation}",
            f"Refund for {transaction.description}"
        )
        
        # Mark as rolled back and clean up
        transaction.rolled_back = True
        del self._active_transactions[transaction_id]
        
        logger.info(f"Rolled back credit reservation {transaction_id}")
    
    def get_credit_history(self, tenant_id: int, limit: int = 100, 
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Get credit transaction history for a tenant.
        
        Args:
            tenant_id: Tenant ID
            limit: Maximum number of records
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            List of transaction records
        """
        try:
            with session_scope() as session:
                query = session.query(ExecutionCost).filter(
                    ExecutionCost.tenant_id == tenant_id
                ).order_by(ExecutionCost.created_at.desc())
                
                if start_date:
                    query = query.filter(ExecutionCost.created_at >= start_date)
                if end_date:
                    query = query.filter(ExecutionCost.created_at <= end_date)
                
                costs = query.limit(limit).all()
                
                return [
                    {
                        'id': cost.id,
                        'operation_type': cost.operation_type,
                        'cost_amount': cost.cost_amount,
                        'description': cost.description,
                        'metadata': cost.metadata,
                        'created_at': cost.created_at.isoformat()
                    }
                    for cost in costs
                ]
                
        except Exception as e:
            logger.error(f"Failed to get credit history for tenant {tenant_id}: {e}")
            return []
    
    def get_credit_summary(self, tenant_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get credit usage summary for a tenant.
        
        Args:
            tenant_id: Tenant ID
            days: Number of days to look back
            
        Returns:
            Dict with credit summary
        """
        try:
            with session_scope() as session:
                start_date = datetime.utcnow() - timedelta(days=days)
                
                # Get total costs
                total_costs = session.execute(
                    text("""
                        SELECT 
                            SUM(cost_amount) as total_cost,
                            COUNT(*) as transaction_count,
                            operation_type
                        FROM executioncost 
                        WHERE tenant_id = :tenant_id 
                        AND created_at >= :start_date
                        GROUP BY operation_type
                    """),
                    {'tenant_id': tenant_id, 'start_date': start_date}
                ).fetchall()
                
                # Get current balance
                current_balance = self.get_credit_balance(tenant_id)
                
                # Calculate daily averages
                daily_avg = sum(row.total_cost for row in total_costs) / days if days > 0 else 0
                
                return {
                    'tenant_id': tenant_id,
                    'current_balance': float(current_balance),
                    'period_days': days,
                    'total_cost': sum(row.total_cost for row in total_costs),
                    'transaction_count': sum(row.transaction_count for row in total_costs),
                    'daily_average': daily_avg,
                    'costs_by_operation': [
                        {
                            'operation_type': row.operation_type,
                            'total_cost': row.total_cost,
                            'transaction_count': row.transaction_count
                        }
                        for row in total_costs
                    ]
                }
                
        except Exception as e:
            logger.error(f"Failed to get credit summary for tenant {tenant_id}: {e}")
            return {
                'tenant_id': tenant_id,
                'current_balance': 0.0,
                'period_days': days,
                'total_cost': 0.0,
                'transaction_count': 0,
                'daily_average': 0.0,
                'costs_by_operation': []
            }
    
    def cleanup_expired_reservations(self, max_age_hours: int = 24):
        """
        Clean up expired credit reservations.
        
        Args:
            max_age_hours: Maximum age of reservations in hours
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        expired_transactions = []
        
        for transaction_id, transaction in self._active_transactions.items():
            if transaction.timestamp < cutoff_time and not transaction.committed:
                expired_transactions.append(transaction_id)
        
        for transaction_id in expired_transactions:
            try:
                self.rollback_reservation(transaction_id)
                logger.info(f"Cleaned up expired reservation {transaction_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup reservation {transaction_id}: {e}")


# Global credit manager instance
_credit_manager: Optional[CreditManager] = None


def get_credit_manager() -> CreditManager:
    """Get the global credit manager instance."""
    global _credit_manager
    if _credit_manager is None:
        _credit_manager = CreditManager()
    return _credit_manager


def charge_credits(amount: Decimal, operation: str, description: str = "",
                   metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Convenience function to charge credits for the current tenant.
    
    Args:
        amount: Amount to charge
        operation: Operation type
        description: Description
        metadata: Additional metadata
        
    Raises:
        CreditInsufficientError: If insufficient credits
        CreditUpdateError: If update fails
    """
    tenant_id = get_tenant_context()
    if tenant_id is None:
        raise CreditUpdateError("No tenant context available")
    
    credit_manager = get_credit_manager()
    
    with credit_manager.atomic_credit_transaction(
        tenant_id=tenant_id,
        amount=-amount,  # Negative for debit
        operation=operation,
        description=description,
        metadata=metadata
    ):
        pass  # Transaction is handled by the context manager


def add_credits(amount: Decimal, operation: str, description: str = "",
                metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Convenience function to add credits for the current tenant.
    
    Args:
        amount: Amount to add
        operation: Operation type
        description: Description
        metadata: Additional metadata
        
    Raises:
        CreditUpdateError: If update fails
    """
    tenant_id = get_tenant_context()
    if tenant_id is None:
        raise CreditUpdateError("No tenant context available")
    
    credit_manager = get_credit_manager()
    
    with credit_manager.atomic_credit_transaction(
        tenant_id=tenant_id,
        amount=amount,  # Positive for credit
        operation=operation,
        description=description,
        metadata=metadata
    ):
        pass  # Transaction is handled by the context manager
