from src.utils.data_models import FailureReport


class TeamExecutionError(Exception):
    def __init__(self, failure_report: FailureReport):
        super().__init__(failure_report.reason)
        self.failure_report = failure_report
