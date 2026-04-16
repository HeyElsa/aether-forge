"""HTTP utilities with retry and backoff for Aether Forge.

Provides a retry-capable HTTP client using stdlib urllib with
exponential backoff and configurable retry policies.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetryPolicy:
    """Configuration for HTTP retry behavior."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)
    timeout_seconds: float = 30.0


_DEFAULT_POLICY = RetryPolicy()


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retry_policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    """Perform a GET request and parse JSON response with retry."""
    policy = retry_policy or _DEFAULT_POLICY
    return _request_with_retry(url, headers=headers or {}, method="GET", policy=policy)


def http_post_json(
    url: str,
    *,
    body: dict[str, Any] | bytes,
    headers: dict[str, str] | None = None,
    retry_policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    """Perform a POST request and parse JSON response with retry."""
    policy = retry_policy or _DEFAULT_POLICY
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf8")
    else:
        data = body
    all_headers = {"Content-Type": "application/json", **(headers or {})}
    return _request_with_retry(url, headers=all_headers, method="POST", data=data, policy=policy)


def _request_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    method: str,
    data: bytes | None = None,
    policy: RetryPolicy,
) -> dict[str, Any]:
    last_error: Exception | None = None
    delay = policy.base_delay_seconds

    for attempt in range(policy.max_retries + 1):
        try:
            req = urllib_request.Request(url, data=data, headers=headers, method=method)
            with urllib_request.urlopen(req, timeout=policy.timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf8"))

        except urllib_error.HTTPError as error:
            last_error = error
            if error.code in policy.retryable_status_codes and attempt < policy.max_retries:
                # Check for Retry-After header
                retry_after = error.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = min(float(retry_after), policy.max_delay_seconds)
                    except ValueError:
                        pass

                logger.warning(
                    "HTTP %d from %s (attempt %d/%d), retrying in %.1fs",
                    error.code, url, attempt + 1, policy.max_retries + 1, delay,
                )
                time.sleep(delay)
                delay = min(delay * policy.backoff_multiplier, policy.max_delay_seconds)
                continue

            # Non-retryable HTTP error
            try:
                body = error.read().decode("utf8")
                return json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise HttpError(
                    f"HTTP {error.code} from {url}",
                    status_code=error.code,
                    url=url,
                ) from error

        except urllib_error.URLError as error:
            last_error = error
            if attempt < policy.max_retries:
                logger.warning(
                    "Connection error to %s (attempt %d/%d): %s, retrying in %.1fs",
                    url, attempt + 1, policy.max_retries + 1, error.reason, delay,
                )
                time.sleep(delay)
                delay = min(delay * policy.backoff_multiplier, policy.max_delay_seconds)
                continue
            raise HttpError(
                f"Connection failed to {url}: {error.reason}",
                url=url,
            ) from error

        except TimeoutError as error:
            last_error = error
            if attempt < policy.max_retries:
                logger.warning(
                    "Timeout from %s (attempt %d/%d), retrying in %.1fs",
                    url, attempt + 1, policy.max_retries + 1, delay,
                )
                time.sleep(delay)
                delay = min(delay * policy.backoff_multiplier, policy.max_delay_seconds)
                continue
            raise HttpError(
                f"Request timed out: {url}",
                url=url,
            ) from error

    raise HttpError(
        f"All {policy.max_retries + 1} attempts failed for {url}",
        url=url,
    ) from last_error


class HttpError(Exception):
    """HTTP request error with status code and URL context."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
