#!/usr/bin/env python3
"""
Script to run load tests for Noisy Neighbor scenarios.

This script provides a command-line interface for running various load test
scenarios to evaluate system performance and tenant isolation.
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.testing.load_testing import (
    run_noisy_neighbor_tests,
    run_single_scenario,
    LoadTestScenario,
    TenantBehavior,
    TenantProfile,
    NoisyNeighborTestSuite
)


async def run_all_tests(base_url: str, output_file: str = None):
    """Run all noisy neighbor tests."""
    print("🚀 Starting Noisy Neighbor Load Tests")
    print(f"Base URL: {base_url}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("-" * 50)
    
    try:
        # Run all tests
        results = await run_noisy_neighbor_tests(base_url)
        
        # Generate report
        test_suite = NoisyNeighborTestSuite(base_url)
        report = test_suite.generate_report(results)
        
        # Print report
        print(report)
        
        # Save results if output file specified
        if output_file:
            # Save JSON results
            json_file = output_file.replace('.txt', '.json')
            with open(json_file, 'w') as f:
                # Convert results to serializable format
                json_results = {}
                for test_name, result in results.items():
                    json_results[test_name] = {
                        "scenario": result.scenario.value,
                        "success": result.success,
                        "duration_seconds": result.duration_seconds,
                        "total_tenants": result.total_tenants,
                        "total_requests": result.total_requests,
                        "metrics": {
                            "total_requests": result.metrics.total_requests,
                            "average_response_time": result.metrics.average_response_time,
                            "p95_response_time": result.metrics.p95_response_time,
                            "p99_response_time": result.metrics.p99_response_time,
                            "requests_per_second": result.metrics.requests_per_second,
                            "resource_contention_score": result.metrics.resource_contention_score,
                            "tenant_isolation_score": result.metrics.tenant_isolation_score
                        },
                        "system_metrics": result.system_metrics,
                        "recommendations": result.recommendations,
                        "violations": result.violations,
                        "error_message": result.error_message
                    }
                
                json.dump(json_results, f, indent=2)
            
            # Save text report
            with open(output_file, 'w') as f:
                f.write(report)
            
            print(f"\n📊 Results saved to:")
            print(f"  - JSON: {json_file}")
            print(f"  - Report: {output_file}")
        
        # Summary
        successful_tests = sum(1 for r in results.values() if r.success)
        total_tests = len(results)
        
        print(f"\n✅ Test Summary:")
        print(f"  - Successful: {successful_tests}/{total_tests}")
        print(f"  - Failed: {total_tests - successful_tests}/{total_tests}")
        
        if successful_tests == total_tests:
            print("🎉 All tests passed!")
            return 0
        else:
            print("⚠️  Some tests failed!")
            return 1
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


async def run_single_test(scenario: str, duration: int, base_url: str):
    """Run a single test scenario."""
    print(f"🚀 Running {scenario} test for {duration} seconds")
    print(f"Base URL: {base_url}")
    print("-" * 50)
    
    try:
        # Create test profiles based on scenario
        if scenario == "normal":
            profiles = [
                TenantProfile("tenant-1", TenantBehavior.NORMAL, 2.0),
                TenantProfile("tenant-2", TenantBehavior.NORMAL, 2.0),
                TenantProfile("tenant-3", TenantBehavior.NORMAL, 2.0)
            ]
            test_scenario = LoadTestScenario.NORMAL_LOAD
            
        elif scenario == "noisy_neighbor":
            profiles = [
                TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-3", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-noisy", TenantBehavior.AGGRESSIVE, 10.0,
                             resource_intensity=3.0, cpu_time_ms=200, memory_usage_mb=100)
            ]
            test_scenario = LoadTestScenario.NOISY_NEIGHBOR
            
        elif scenario == "bursty":
            profiles = [
                TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-2", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-bursty", TenantBehavior.BURSTY, 5.0,
                             resource_intensity=2.0)
            ]
            test_scenario = LoadTestScenario.BURST_LOAD
            
        elif scenario == "cache_thrashing":
            profiles = [
                TenantProfile("tenant-1", TenantBehavior.NORMAL, 1.0),
                TenantProfile("tenant-cache-1", TenantBehavior.AGGRESSIVE, 20.0,
                             cache_usage=0.9, resource_intensity=1.5),
                TenantProfile("tenant-cache-2", TenantBehavior.AGGRESSIVE, 20.0,
                             cache_usage=0.9, resource_intensity=1.5)
            ]
            test_scenario = LoadTestScenario.CACHE_THRASHING
            
        else:
            print(f"❌ Unknown scenario: {scenario}")
            print("Available scenarios: normal, noisy_neighbor, bursty, cache_thrashing")
            return 1
        
        # Run the test
        result = await run_single_scenario(
            test_scenario,
            profiles,
            duration_seconds=float(duration),
            base_url=base_url
        )
        
        # Print results
        print(f"\n📊 Test Results:")
        print(f"  - Scenario: {result.scenario.value}")
        print(f"  - Duration: {result.duration_seconds:.1f} seconds")
        print(f"  - Tenants: {result.total_tenants}")
        print(f"  - Total Requests: {result.total_requests}")
        print(f"  - Requests/Second: {result.metrics.requests_per_second:.2f}")
        print(f"  - Average Response Time: {result.metrics.average_response_time:.3f}s")
        print(f"  - P95 Response Time: {result.metrics.p95_response_time:.3f}s")
        print(f"  - P99 Response Time: {result.metrics.p99_response_time:.3f}s")
        print(f"  - Resource Contention Score: {result.metrics.resource_contention_score:.2f}")
        print(f"  - Tenant Isolation Score: {result.metrics.tenant_isolation_score:.2f}")
        
        if result.system_metrics:
            print(f"  - Average CPU: {result.system_metrics.get('avg_cpu_percent', 0):.1f}%")
            print(f"  - Max CPU: {result.system_metrics.get('max_cpu_percent', 0):.1f}%")
            print(f"  - Average Memory: {result.system_metrics.get('avg_memory_percent', 0):.1f}%")
            print(f"  - Max Memory: {result.system_metrics.get('max_memory_percent', 0):.1f}%")
        
        if result.violations:
            print(f"\n⚠️  Violations ({len(result.violations)}):")
            for violation in result.violations:
                print(f"  - {violation['type']} ({violation['severity']}): {violation['message']}")
        
        if result.recommendations:
            print(f"\n💡 Recommendations ({len(result.recommendations)}):")
            for rec in result.recommendations:
                print(f"  - {rec}")
        
        if result.success:
            print("\n✅ Test completed successfully!")
            return 0
        else:
            print(f"\n❌ Test failed: {result.error_message}")
            return 1
            
    except Exception as e:
        print(f"❌ Error running test: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run load tests for Noisy Neighbor scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python scripts/run_load_tests.py --all --url http://localhost:8000
  
  # Run a single test
  python scripts/run_load_tests.py --scenario noisy_neighbor --duration 60 --url http://localhost:8000
  
  # Run all tests and save results
  python scripts/run_load_tests.py --all --url http://localhost:8000 --output results.txt
        """
    )
    
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Run all noisy neighbor tests"
    )
    
    parser.add_argument(
        "--scenario",
        choices=["normal", "noisy_neighbor", "bursty", "cache_thrashing"],
        help="Run a single test scenario"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration of the test in seconds (default: 60)"
    )
    
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL for the application (default: http://localhost:8000)"
    )
    
    parser.add_argument(
        "--output",
        help="Output file for results (optional)"
    )
    
    args = parser.parse_args()
    
    if not args.all and not args.scenario:
        parser.error("Must specify either --all or --scenario")
    
    if args.all and args.scenario:
        parser.error("Cannot specify both --all and --scenario")
    
    # Run the appropriate test
    if args.all:
        return asyncio.run(run_all_tests(args.url, args.output))
    else:
        return asyncio.run(run_single_test(args.scenario, args.duration, args.url))


if __name__ == "__main__":
    sys.exit(main())
