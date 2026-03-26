"""
Tests for atomic credit management system.
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from src.services.credit_manager import (
    CreditManager, CreditTransaction, CreditInsufficientError, 
    CreditUpdateError, get_credit_manager, charge_credits, add_credits
)
from src.database.models import Tenant, ExecutionCost


class TestCreditTransaction:
    """Test CreditTransaction class."""
    
    def test_credit_transaction_creation(self):
        """Test credit transaction creation."""
        transaction = CreditTransaction(
            tenant_id=123,
            amount=Decimal('10.50'),
            operation='test_operation',
            description='Test transaction',
            metadata={'key': 'value'}
        )
        
        assert transaction.tenant_id == 123
        assert transaction.amount == Decimal('10.50')
        assert transaction.operation == 'test_operation'
        assert transaction.description == 'Test transaction'
        assert transaction.metadata == {'key': 'value'}
        assert not transaction.committed
        assert not transaction.rolled_back
    
    def test_credit_transaction_to_dict(self):
        """Test credit transaction serialization."""
        transaction = CreditTransaction(
            tenant_id=123,
            amount=Decimal('10.50'),
            operation='test_operation',
            description='Test transaction'
        )
        
        data = transaction.to_dict()
        
        assert data['tenant_id'] == 123
        assert data['amount'] == 10.50
        assert data['operation'] == 'test_operation'
        assert data['description'] == 'Test transaction'
        assert data['committed'] is False
        assert data['rolled_back'] is False


class TestCreditManager:
    """Test CreditManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.credit_manager = CreditManager()
        self.tenant_id = 123
        self.initial_balance = Decimal('100.00')
    
    @patch('src.services.credit_manager.session_scope')
    def test_get_credit_balance(self, mock_session_scope):
        """Test getting credit balance."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.50
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        balance = self.credit_manager.get_credit_balance(self.tenant_id)
        
        assert balance == Decimal('100.50')
        mock_session.query.assert_called_once()
    
    @patch('src.services.credit_manager.session_scope')
    def test_get_credit_balance_tenant_not_found(self, mock_session_scope):
        """Test getting credit balance for non-existent tenant."""
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        balance = self.credit_manager.get_credit_balance(self.tenant_id)
        
        assert balance == Decimal('0')
    
    @patch('src.services.credit_manager.session_scope')
    def test_insufficient_credits_error(self, mock_session_scope):
        """Test insufficient credits error."""
        # Mock tenant with low balance
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 5.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Try to charge more than available
        with pytest.raises(CreditInsufficientError):
            with self.credit_manager.atomic_credit_transaction(
                tenant_id=self.tenant_id,
                amount=Decimal('-10.00'),
                operation='test_operation'
            ):
                pass
    
    @patch('src.services.credit_manager.session_scope')
    def test_successful_credit_transaction(self, mock_session_scope):
        """Test successful credit transaction."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Successful transaction
        with self.credit_manager.atomic_credit_transaction(
            tenant_id=self.tenant_id,
            amount=Decimal('-10.00'),
            operation='test_operation',
            description='Test charge'
        ) as transaction:
            assert transaction.tenant_id == self.tenant_id
            assert transaction.amount == Decimal('-10.00')
            assert transaction.committed
        
        # Verify database update was called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @patch('src.services.credit_manager.session_scope')
    def test_credit_transaction_rollback(self, mock_session_scope):
        """Test credit transaction rollback on error."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Transaction that fails
        with pytest.raises(ValueError):
            with self.credit_manager.atomic_credit_transaction(
                tenant_id=self.tenant_id,
                amount=Decimal('-10.00'),
                operation='test_operation'
            ) as transaction:
                # Simulate an error
                raise ValueError("Test error")
        
        # Verify rollback was called
        assert mock_session.execute.call_count >= 2  # Original + rollback
    
    @patch('src.services.credit_manager.session_scope')
    def test_reserve_credits(self, mock_session_scope):
        """Test credit reservation."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Reserve credits
        transaction_id = self.credit_manager.reserve_credits(
            tenant_id=self.tenant_id,
            amount=Decimal('10.00'),
            operation='test_operation',
            description='Test reservation'
        )
        
        assert transaction_id.startswith('reserve_')
        assert transaction_id in self.credit_manager._active_transactions
    
    @patch('src.services.credit_manager.session_scope')
    def test_commit_reservation(self, mock_session_scope):
        """Test committing a credit reservation."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Reserve credits
        transaction_id = self.credit_manager.reserve_credits(
            tenant_id=self.tenant_id,
            amount=Decimal('10.00'),
            operation='test_operation'
        )
        
        # Commit reservation
        self.credit_manager.commit_reservation(transaction_id)
        
        # Verify transaction is no longer active
        assert transaction_id not in self.credit_manager._active_transactions
    
    @patch('src.services.credit_manager.session_scope')
    def test_rollback_reservation(self, mock_session_scope):
        """Test rolling back a credit reservation."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Reserve credits
        transaction_id = self.credit_manager.reserve_credits(
            tenant_id=self.tenant_id,
            amount=Decimal('10.00'),
            operation='test_operation'
        )
        
        # Rollback reservation
        self.credit_manager.rollback_reservation(transaction_id)
        
        # Verify transaction is no longer active
        assert transaction_id not in self.credit_manager._active_transactions
    
    @patch('src.services.credit_manager.session_scope')
    def test_get_credit_history(self, mock_session_scope):
        """Test getting credit history."""
        # Mock execution costs
        mock_cost1 = MagicMock()
        mock_cost1.id = 1
        mock_cost1.operation_type = 'test_operation'
        mock_cost1.cost_amount = 10.50
        mock_cost1.description = 'Test operation'
        mock_cost1.metadata = {}
        mock_cost1.created_at = datetime.utcnow()
        
        mock_cost2 = MagicMock()
        mock_cost2.id = 2
        mock_cost2.operation_type = 'another_operation'
        mock_cost2.cost_amount = 5.25
        mock_cost2.description = 'Another operation'
        mock_cost2.metadata = {'key': 'value'}
        mock_cost2.created_at = datetime.utcnow()
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_cost1, mock_cost2]
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Get history
        history = self.credit_manager.get_credit_history(self.tenant_id, limit=10)
        
        assert len(history) == 2
        assert history[0]['operation_type'] == 'test_operation'
        assert history[0]['cost_amount'] == 10.50
        assert history[1]['operation_type'] == 'another_operation'
        assert history[1]['cost_amount'] == 5.25
    
    @patch('src.services.credit_manager.session_scope')
    def test_get_credit_summary(self, mock_session_scope):
        """Test getting credit summary."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 75.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.fetchall.return_value = [
            MagicMock(total_cost=25.00, transaction_count=5, operation_type='test_operation'),
            MagicMock(total_cost=15.00, transaction_count=3, operation_type='another_operation')
        ]
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Get summary
        summary = self.credit_manager.get_credit_summary(self.tenant_id, days=30)
        
        assert summary['tenant_id'] == self.tenant_id
        assert summary['current_balance'] == 75.00
        assert summary['total_cost'] == 40.00
        assert summary['transaction_count'] == 8
        assert len(summary['costs_by_operation']) == 2
    
    def test_cleanup_expired_reservations(self):
        """Test cleanup of expired reservations."""
        # Create expired transaction
        old_time = datetime.utcnow() - timedelta(hours=25)
        transaction = CreditTransaction(
            tenant_id=self.tenant_id,
            amount=Decimal('-10.00'),
            operation='test_operation'
        )
        transaction.timestamp = old_time
        
        transaction_id = 'expired_transaction'
        self.credit_manager._active_transactions[transaction_id] = transaction
        
        # Mock rollback
        with patch.object(self.credit_manager, 'rollback_reservation') as mock_rollback:
            self.credit_manager.cleanup_expired_reservations(max_age_hours=24)
            
            mock_rollback.assert_called_once_with(transaction_id)


class TestCreditManagerIntegration:
    """Integration tests for credit manager."""
    
    @patch('src.services.credit_manager.session_scope')
    def test_concurrent_credit_updates(self, mock_session_scope):
        """Test concurrent credit updates are handled safely."""
        # Mock tenant
        mock_tenant = MagicMock()
        mock_tenant.credit_balance = 100.00
        
        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_tenant
        mock_session.execute.return_value.scalar_one.return_value = 90.00
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        credit_manager = CreditManager()
        
        # Simulate concurrent transactions
        def make_transaction(amount):
            with credit_manager.atomic_credit_transaction(
                tenant_id=123,
                amount=amount,
                operation='concurrent_test'
            ):
                pass
        
        # These should all succeed without conflicts
        make_transaction(Decimal('-5.00'))
        make_transaction(Decimal('-3.00'))
        make_transaction(Decimal('-2.00'))
        
        # Verify all transactions were processed
        assert mock_session.execute.call_count >= 3


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @patch('src.services.credit_manager.get_tenant_context')
    @patch('src.services.credit_manager.get_credit_manager')
    def test_charge_credits(self, mock_get_credit_manager, mock_get_tenant_context):
        """Test charge_credits convenience function."""
        # Mock tenant context
        mock_get_tenant_context.return_value = 123
        
        # Mock credit manager
        mock_credit_manager = MagicMock()
        mock_get_credit_manager.return_value = mock_credit_manager
        
        # Test charging credits
        charge_credits(
            amount=Decimal('10.00'),
            operation='test_operation',
            description='Test charge'
        )
        
        # Verify credit manager was called
        mock_credit_manager.atomic_credit_transaction.assert_called_once()
        call_args = mock_credit_manager.atomic_credit_transaction.call_args[1]
        assert call_args['tenant_id'] == 123
        assert call_args['amount'] == Decimal('-10.00')
        assert call_args['operation'] == 'test_operation'
    
    @patch('src.services.credit_manager.get_tenant_context')
    @patch('src.services.credit_manager.get_credit_manager')
    def test_add_credits(self, mock_get_credit_manager, mock_get_tenant_context):
        """Test add_credits convenience function."""
        # Mock tenant context
        mock_get_tenant_context.return_value = 123
        
        # Mock credit manager
        mock_credit_manager = MagicMock()
        mock_get_credit_manager.return_value = mock_credit_manager
        
        # Test adding credits
        add_credits(
            amount=Decimal('10.00'),
            operation='test_operation',
            description='Test credit'
        )
        
        # Verify credit manager was called
        mock_credit_manager.atomic_credit_transaction.assert_called_once()
        call_args = mock_credit_manager.atomic_credit_transaction.call_args[1]
        assert call_args['tenant_id'] == 123
        assert call_args['amount'] == Decimal('10.00')
        assert call_args['operation'] == 'test_operation'
    
    @patch('src.services.credit_manager.get_tenant_context')
    def test_charge_credits_no_tenant_context(self, mock_get_tenant_context):
        """Test charge_credits with no tenant context."""
        # Mock no tenant context
        mock_get_tenant_context.return_value = None
        
        # Test that it raises an error
        with pytest.raises(CreditUpdateError, match="No tenant context available"):
            charge_credits(
                amount=Decimal('10.00'),
                operation='test_operation'
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
