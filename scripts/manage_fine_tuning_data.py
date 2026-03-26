#!/usr/bin/env python3
"""
Management script for fine-tuning data operations.

This script provides command-line tools for managing the fine-tuning data
collection system, including manual archival, data collection campaigns,
and ML team data access.
"""

import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from src.services.fine_tuning_manager import FineTuningDataManager
from src.tasks.fine_tuning_archival import (
    collect_fine_tuning_data,
    cleanup_old_fine_tuning_data,
    generate_fine_tuning_report
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def collect_data(days_back: int = 30) -> Dict[str, Any]:
    """Collect fine-tuning data from recent jobs."""
    logger.info(f"Starting fine-tuning data collection for last {days_back} days")

    try:
        manager = FineTuningDataManager()
        result = await manager.collect_fine_tuning_data(days_back=days_back)

        logger.info("Data collection completed successfully"        logger.info(f"Task ID: {result.get('task_id', 'N/A')}")
        logger.info(f"Status: {result.get('status', 'unknown')}")

        return result

    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        return {'success': False, 'error': str(e)}

async def get_statistics() -> Dict[str, Any]:
    """Get comprehensive statistics about fine-tuning data."""
    logger.info("Generating fine-tuning statistics")

    try:
        manager = FineTuningDataManager()
        statistics = await manager.get_fine_tuning_statistics()

        logger.info("Statistics generated successfully")
        logger.info(f"Total archived jobs: {statistics.get('database_stats', {}).get('total_jobs_with_traces', 0)}")
        logger.info(f"Success rate: {statistics.get('database_stats', {}).get('success_rate_percent', 0)".1f"}%")

        return statistics

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        return {'success': False, 'error': str(e)}

async def get_ml_dataset(
    date_range: Optional[tuple] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """Get ML training dataset."""
    logger.info("Retrieving ML training dataset")

    try:
        manager = FineTuningDataManager()
        dataset = await manager.get_ml_training_dataset(
            date_range=date_range,
            limit=limit
        )

        logger.info("Dataset retrieved successfully")
        logger.info(f"Total traces: {dataset.get('total_traces', 0)}")

        return dataset

    except Exception as e:
        logger.error(f"Failed to get ML dataset: {e}")
        return {'success': False, 'error': str(e)}

async def validate_privacy() -> Dict[str, Any]:
    """Validate privacy compliance of archived data."""
    logger.info("Validating privacy compliance")

    try:
        manager = FineTuningDataManager()
        compliance_report = await manager.validate_privacy_compliance()

        logger.info("Privacy validation completed")
        logger.info(f"Compliance score: {compliance_report.get('compliance_score', 0)".1f"}%")
        logger.info(f"Is compliant: {compliance_report.get('is_compliant', False)}")

        if not compliance_report.get('is_compliant', False):
            logger.warning("Privacy compliance issues found!")
            for issue in compliance_report.get('compliance_issues', []):
                logger.warning(f"  Issue: {issue}")

        return compliance_report

    except Exception as e:
        logger.error(f"Privacy validation failed: {e}")
        return {'success': False, 'error': str(e)}

async def get_dashboard_data() -> Dict[str, Any]:
    """Get comprehensive dashboard data for ML team."""
    logger.info("Generating ML team dashboard data")

    try:
        manager = FineTuningDataManager()
        dashboard_data = await manager.get_ml_team_dashboard_data()

        logger.info("Dashboard data generated successfully")
        overview = dashboard_data.get('overview', {})
        logger.info(f"Total traces: {overview.get('total_traces', 0)}")
        logger.info(f"Total size: {overview.get('total_size_mb', 0)".1f"} MB")
        logger.info(f"Compliance score: {overview.get('compliance_score', 0)".1f"}%")

        recommendations = dashboard_data.get('recommendations', [])
        if recommendations:
            logger.info(f"Recommendations: {len(recommendations)} items")
            for rec in recommendations:
                logger.info(f"  - {rec.get('type', 'unknown')}: {rec.get('message', 'N/A')}")

        return dashboard_data

    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        return {'success': False, 'error': str(e)}

async def schedule_collection_campaign(
    days_back: int = 30,
    cleanup_old: bool = True,
    generate_report: bool = True
) -> Dict[str, Any]:
    """Schedule a comprehensive data collection campaign."""
    logger.info("Scheduling data collection campaign")

    try:
        manager = FineTuningDataManager()

        campaign_config = {
            'days_back': days_back,
            'cleanup_old_data': cleanup_old,
            'generate_report': generate_report
        }

        result = await manager.schedule_data_collection_campaign(campaign_config)

        logger.info("Campaign scheduled successfully")
        logger.info(f"Campaign ID: {result.get('campaign_id', 'N/A')}")
        logger.info(f"Tasks scheduled: {len([t for t in result.get('tasks_scheduled', {}).values() if t])}")

        return result

    except Exception as e:
        logger.error(f"Failed to schedule collection campaign: {e}")
        return {'success': False, 'error': str(e)}

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage fine-tuning data collection and ML team access"
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Collect data command
    collect_parser = subparsers.add_parser('collect', help='Collect fine-tuning data')
    collect_parser.add_argument('--days-back', type=int, default=30,
                               help='Number of days to look back (default: 30)')

    # Statistics command
    stats_parser = subparsers.add_parser('stats', help='Get fine-tuning statistics')

    # ML dataset command
    dataset_parser = subparsers.add_parser('dataset', help='Get ML training dataset')
    dataset_parser.add_argument('--start-date', type=str,
                               help='Start date in YYYY-MM-DD format')
    dataset_parser.add_argument('--end-date', type=str,
                               help='End date in YYYY-MM-DD format')
    dataset_parser.add_argument('--limit', type=int,
                               help='Maximum number of traces to return')

    # Privacy validation command
    privacy_parser = subparsers.add_parser('privacy', help='Validate privacy compliance')

    # Dashboard command
    dashboard_parser = subparsers.add_parser('dashboard', help='Get ML team dashboard data')

    # Campaign command
    campaign_parser = subparsers.add_parser('campaign', help='Schedule collection campaign')
    campaign_parser.add_argument('--days-back', type=int, default=30,
                                help='Number of days to look back (default: 30)')
    campaign_parser.add_argument('--no-cleanup', action='store_true',
                                help='Skip cleanup of old data')
    campaign_parser.add_argument('--no-report', action='store_true',
                                help='Skip report generation')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run the appropriate async function
    async def run_command():
        if args.command == 'collect':
            result = await collect_data(args.days_back)
        elif args.command == 'stats':
            result = await get_statistics()
        elif args.command == 'dataset':
            date_range = None
            if args.start_date and args.end_date:
                date_range = (args.start_date, args.end_date)
            result = await get_ml_dataset(date_range=date_range, limit=args.limit)
        elif args.command == 'privacy':
            result = await validate_privacy()
        elif args.command == 'dashboard':
            result = await get_dashboard_data()
        elif args.command == 'campaign':
            result = await schedule_collection_campaign(
                days_back=args.days_back,
                cleanup_old=not args.no_cleanup,
                generate_report=not args.no_report
            )
        else:
            print(f"Unknown command: {args.command}")
            return

        # Pretty print the result
        import json
        print(json.dumps(result, indent=2, default=str))

    # Run the async function
    try:
        asyncio.run(run_command())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
