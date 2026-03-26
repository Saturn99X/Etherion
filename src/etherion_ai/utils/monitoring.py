# src/etherion_ai/utils/monitoring.py
import logging
from typing import Any, Dict, Optional
from google.cloud import error_reporting, monitoring_v3
from google.cloud.monitoring_v3 import MetricServiceClient
from google.api_core.exceptions import GoogleAPIError


class MonitoringClient:
    """Client for Google Cloud Monitoring and Error Reporting."""

    def __init__(self, project_id: str):
        """Initialize the monitoring client."""
        self.project_id = project_id
        self.error_client = error_reporting.Client(project=project_id)
        self.metric_client = MetricServiceClient()
        self.logger = logging.getLogger(__name__)

    def report_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Report an error to Google Cloud Error Reporting."""
        try:
            self.error_client.report(error, context=context)
            self.logger.info(f"Error reported to Google Cloud Error Reporting: {str(error)}")
        except GoogleAPIError as e:
            self.logger.error(f"Failed to report error to Google Cloud Error Reporting: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error while reporting to Google Cloud Error Reporting: {str(e)}")

    def create_metric(self, metric_type: str, metric_kind: str, value_type: str) -> None:
        """Create a custom metric in Google Cloud Monitoring."""
        try:
            project_name = f"projects/{self.project_id}"
            
            descriptor = monitoring_v3.MetricDescriptor()
            descriptor.type = f"custom.googleapis.com/{metric_type}"
            descriptor.metric_kind = getattr(monitoring_v3.MetricDescriptor.MetricKind, metric_kind)
            descriptor.value_type = getattr(monitoring_v3.MetricDescriptor.ValueType, value_type)
            descriptor.description = f"Custom metric for {metric_type}"

            self.metric_client.create_metric_descriptor(
                name=project_name,
                metric_descriptor=descriptor
            )
            
            self.logger.info(f"Custom metric created: {metric_type}")
        except GoogleAPIError as e:
            self.logger.error(f"Failed to create custom metric: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error while creating custom metric: {str(e)}")

    def write_time_series(self, metric_type: str, points: list, resource_labels: Dict[str, str]) -> None:
        """Write time series data to a custom metric."""
        try:
            project_name = f"projects/{self.project_id}"
            
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"custom.googleapis.com/{metric_type}"
            series.resource.type = "generic_node"
            series.resource.labels = resource_labels
            
            for point in points:
                series.points.append(point)

            self.metric_client.create_time_series(
                name=project_name,
                time_series=[series]
            )
            
            self.logger.info(f"Time series data written for metric: {metric_type}")
        except GoogleAPIError as e:
            self.logger.error(f"Failed to write time series data: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error while writing time series data: {str(e)}")


# Global monitoring client instance
monitoring_client: Optional[MonitoringClient] = None


def initialize_monitoring(project_id: str) -> None:
    """Initialize the global monitoring client."""
    global monitoring_client
    monitoring_client = MonitoringClient(project_id)


def get_monitoring_client() -> Optional[MonitoringClient]:
    """Get the global monitoring client."""
    return monitoring_client


def report_application_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
    """Report an application error to Google Cloud Error Reporting."""
    client = get_monitoring_client()
    if client:
        client.report_error(error, context)
    else:
        logging.warning("Monitoring client not initialized. Error not reported to Google Cloud Error Reporting.")


def record_custom_metric(metric_type: str, points: list, resource_labels: Dict[str, str]) -> None:
    """Record data for a custom metric in Google Cloud Monitoring."""
    client = get_monitoring_client()
    if client:
        client.write_time_series(metric_type, points, resource_labels)
    else:
        logging.warning("Monitoring client not initialized. Metric data not recorded.")