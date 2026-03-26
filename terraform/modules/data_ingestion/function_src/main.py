# Wrapper module to expose Cloud Function entry points for Gen 2 Python runtime
# This ensures entry points are importable from the default module name "main".

from cloud_function import (
    pull_tenant_data,
    process_uploaded_file,
    manual_process,
)
