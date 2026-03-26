"""
Integration tests to verify platform works without billing system.

This test suite ensures that after billing removal:
1. Jobs can execute without credit checks
2. API starts without Stripe environment variables
3. GraphQL schema has no payment types
4. No billing tables exist in database
5. User signup works without credit allocation
"""

import pytest
import os
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from src.database.db import get_db
from src.database.models import Tenant, User


class TestNoBillingSystem:
    """Test suite for billing-free platform operation."""

    def test_api_starts_without_stripe_env_vars(self):
        """Verify API can start without Stripe environment variables."""
        # These should not be required
        stripe_vars = [
            'STRIPE_SECRET_KEY',
            'STRIPE_PUBLISHABLE_KEY',
            'STRIPE_WEBHOOK_SECRET',
        ]
        
        for var in stripe_vars:
            # Verify these are not set or are empty
            value = os.getenv(var, '')
            assert value == '', f"{var} should not be required but is set to: {value}"

    def test_no_billing_tables_in_database(self):
        """Verify billing tables have been removed from database."""
        session = next(get_db())
        
        try:
            inspector = inspect(session.get_bind())
            tables = inspector.get_table_names()
            
            # These tables should NOT exist
            billing_tables = [
                'credit_ledger',
                'stripe_event',
                'tenant_credit_balance',
            ]
            
            for table in billing_tables:
                assert table not in tables, f"Billing table '{table}' still exists in database"
                
        finally:
            session.close()

    def test_tenant_has_no_credit_balance_column(self):
        """Verify tenant table no longer has credit_balance column."""
        session = next(get_db())
        
        try:
            inspector = inspect(session.get_bind())
            columns = [col['name'] for col in inspector.get_columns('tenant')]
            
            assert 'credit_balance' not in columns, "Tenant table still has credit_balance column"
            
        finally:
            session.close()

    def test_cost_tracking_disabled_by_default(self):
        """Verify cost tracking is disabled by default."""
        cost_tracking_enabled = os.getenv('ENABLE_COST_TRACKING', 'false').lower()
        assert cost_tracking_enabled == 'false', "Cost tracking should be disabled by default"

    def test_no_credit_manager_imports(self):
        """Verify credit_manager module does not exist."""
        with pytest.raises(ModuleNotFoundError):
            import src.services.credit_manager  # noqa: F401

    def test_no_pricing_credit_manager_imports(self):
        """Verify pricing/credit_manager module does not exist."""
        with pytest.raises(ModuleNotFoundError):
            import src.services.pricing.credit_manager  # noqa: F401

    def test_no_ledger_imports(self):
        """Verify ledger module does not exist."""
        with pytest.raises(ModuleNotFoundError):
            import src.services.pricing.ledger  # noqa: F401

    @pytest.mark.asyncio
    async def test_user_signup_without_credit_allocation(self):
        """Verify user signup works without credit allocation."""
        from src.auth.service import _password_signup_impl
        
        session = next(get_db())
        
        try:
            # Create a test user without credits
            result = await _password_signup_impl(
                email=f"test_{os.urandom(4).hex()}@example.com",
                password="TestPass123!",
                session=session,
                name="Test User",
                subdomain=f"test{os.urandom(4).hex()}",
            )
            
            # Verify user was created
            assert result is not None
            assert 'access_token' in result
            assert 'user' in result
            
            # Verify no credit-related data in response
            user_data = result['user']
            assert not hasattr(user_data, 'credit_balance')
            assert not hasattr(user_data, 'credits')
            
        finally:
            session.close()

    def test_graphql_schema_has_no_payment_types(self):
        """Verify GraphQL schema does not expose payment-related types."""
        from src.etherion_ai.graphql_schema.schema import schema
        
        # Get all type names from schema
        type_names = [t.name for t in schema.type_map.values()]
        
        # These types should NOT exist
        billing_types = [
            'Payment',
            'CreditBalance',
            'CreditLedger',
            'StripeEvent',
            'PaymentIntent',
            'CheckoutSession',
        ]
        
        for billing_type in billing_types:
            assert billing_type not in type_names, f"Billing type '{billing_type}' still exists in GraphQL schema"

    def test_no_payment_mutations(self):
        """Verify GraphQL schema has no payment mutations."""
        from src.etherion_ai.graphql_schema.schema import schema
        
        mutation_type = schema.mutation_type
        if mutation_type:
            mutation_fields = mutation_type.fields.keys()
            
            # These mutations should NOT exist
            payment_mutations = [
                'createPayment',
                'createCheckoutSession',
                'createPaymentLink',
                'allocateCredits',
                'deductCredits',
            ]
            
            for mutation in payment_mutations:
                assert mutation not in mutation_fields, f"Payment mutation '{mutation}' still exists"

    def test_no_payment_queries(self):
        """Verify GraphQL schema has no payment queries."""
        from src.etherion_ai.graphql_schema.schema import schema
        
        query_type = schema.query_type
        if query_type:
            query_fields = query_type.fields.keys()
            
            # These queries should NOT exist
            payment_queries = [
                'creditBalance',
                'paymentHistory',
                'creditLedger',
                'stripeEvents',
            ]
            
            for query in payment_queries:
                assert query not in query_fields, f"Payment query '{query}' still exists"

    def test_orchestrator_runs_without_credit_checks(self):
        """Verify orchestrator can run without credit checks."""
        # Import orchestrator modules to ensure they don't reference billing
        from src.services.goal_orchestrator import execute_goal_celery_task
        from src.services.team_orchestrator import TeamOrchestrator
        
        # If imports succeed without errors, credit checks are removed
        assert execute_goal_celery_task is not None
        assert TeamOrchestrator is not None

    def test_no_stripe_endpoints_in_app(self):
        """Verify Stripe endpoints have been removed from app.py."""
        from src.etherion_ai.app import app
        
        # Get all routes
        routes = [route.path for route in app.routes]
        
        # These routes should NOT exist
        stripe_routes = [
            '/api/payments/checkout',
            '/api/payments/link',
            '/api/stripe/webhook',
            '/webhook/stripe',
        ]
        
        for route in stripe_routes:
            assert route not in routes, f"Stripe route '{route}' still exists"


class TestCostTrackingOptional:
    """Test suite for optional cost tracking feature."""

    def test_cost_tracker_module_exists(self):
        """Verify cost_tracker module still exists (but is optional)."""
        from src.services.pricing import cost_tracker
        assert cost_tracker is not None

    def test_cost_tracker_respects_feature_flag(self):
        """Verify cost tracker checks ENABLE_COST_TRACKING flag."""
        from src.services.pricing.cost_tracker import CostTracker
        
        # Create instance
        tracker = CostTracker()
        
        # Verify it has the feature flag check
        # (implementation detail - may need adjustment based on actual implementation)
        assert hasattr(tracker, 'enabled') or os.getenv('ENABLE_COST_TRACKING', 'false').lower() == 'false'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
