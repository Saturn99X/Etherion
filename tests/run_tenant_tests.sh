#!/bin/bash

# Script to run all tenant-related tests
echo "========================================="
echo "Running All Tenant-Related Tests"
echo "========================================="

# Activate virtual environment
source venv/bin/activate

# Run tests
echo ""
echo "1. Running Basic Tenant Test..."
python test_tenant.py

echo ""
echo "2. Running Tenant Utilities Test..."
python test_tenant_utils.py

echo ""
echo "3. Running Tenant Creation Test..."
python test_tenant_creation.py

echo ""
echo "4. Running Tenant Functionality Demonstration..."
python demo_tenant_functionality.py

echo ""
echo "========================================="
echo "All Tenant Tests Completed!"
echo "========================================="