# src/etherion_ai/middleware/request_logger.py
"""
Request logging middleware for audit trail.
"""

import time
import logging
from fastapi import Request, Response

from src.etherion_ai.utils.logging_utils import (
    generate_request_id, 
    log_request, 
    log_response
)

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def request_logger_middleware(request: Request, call_next) -> Response:
    """Function-based middleware to log requests and responses."""
    # Prefer client-provided request id if present
    try:
        incoming_req_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
    except Exception:
        incoming_req_id = None
    request_id = incoming_req_id or generate_request_id()
    request.state.request_id = request_id

    start_time = time.time()
    log_request(request, request_id)

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        # Propagate traceparent if provided by client or upstream
        try:
            tp = request.headers.get("traceparent")
            if tp:
                response.headers["traceparent"] = tp
        except Exception:
            pass
        log_response(request, response, request_id, start_time)
        return response
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            f"Request Error [ID: {request_id}]: {str(e)} "
            f"(Processing time: {processing_time:.4f}s)"
        )
        raise