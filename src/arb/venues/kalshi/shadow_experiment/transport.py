"""The one network-capable object in this package: a GET-only, accounted,
completeness-checked Kalshi Demo transport implementing the canonical
selector ``Transport`` protocol (``get(path=, query=, headers=)``).

* Exactly one GET per call; no retry, no redirect following, no proxy.
* Host/port pinned to the canonical selector's ``DEMO_HOST``/``DEMO_PORT``;
  path must start with the canonical ``BASE_PATH``.
* Body read through a hard cap (canonical selector ``MAX_RESPONSE_BYTES``).
* A parsed fixed Content-Length that is not fully consumed (residual
  ``response.length`` neither ``None`` nor ``0``) is ``INCOMPLETE_RESPONSE_BODY``
  -- the body is never returned as complete.
* Request accounting records method/path/query/status/byte count/body
  SHA-256 and whether auth headers were present -- never a header VALUE.
* A per-run request ceiling halts further requests.
"""

from __future__ import annotations

import hashlib
import http.client
import ssl
import time
from typing import Mapping, Sequence, Tuple
from urllib.parse import urlencode


class IncompleteResponseBody(RuntimeError):
    """Fixed secret-free classification for a short fixed-length body."""

    def __init__(self) -> None:
        super().__init__("INCOMPLETE_RESPONSE_BODY")


class RequestCeilingExceeded(RuntimeError):
    def __init__(self) -> None:
        super().__init__("REQUEST_CEILING_EXCEEDED")


_AUTH_HEADER_NAMES = ("KALSHI-ACCESS-KEY", "KALSHI-ACCESS-SIGNATURE", "KALSHI-ACCESS-TIMESTAMP")


class AccountedDemoTransport:
    """GET-only Demo transport.  There is deliberately no method parameter:
    the only verb this class can ever send is the literal ``GET``."""

    def __init__(self, selector_module, *, request_ceiling: int, timeout_s: float | None = None,
                 connection_factory=None, monotonic_ns=time.monotonic_ns) -> None:
        self._sel = selector_module
        self._host = selector_module.DEMO_HOST
        self._port = selector_module.DEMO_PORT
        self._base = selector_module.BASE_PATH
        self._cap = selector_module.MAX_RESPONSE_BYTES
        self._timeout = selector_module.REQUEST_TIMEOUT_S if timeout_s is None else timeout_s
        if self._host in selector_module.PRODUCTION_REST_HOSTS:
            raise RuntimeError("PRODUCTION_HOST_REFUSED")
        self._ceiling = request_ceiling
        self._connection_factory = connection_factory or self._default_connection
        self._monotonic_ns = monotonic_ns
        self.phase = "UNSET"
        self.records: list = []

    def _default_connection(self):
        return http.client.HTTPSConnection(self._host, self._port, timeout=self._timeout,
                                           context=ssl.create_default_context())

    def get(self, *, path: str, query: Sequence[Tuple[str, str]], headers: Mapping[str, str]):
        if len(self.records) >= self._ceiling:
            raise RequestCeilingExceeded()
        if type(path) is not str or not path.startswith(self._base + "/"):
            raise RuntimeError("PATH_OUTSIDE_DEMO_BASE")
        query_list = [(str(k), str(v)) for k, v in query]
        full_path = path if not query_list else f"{path}?{urlencode(query_list)}"
        record = {
            "seq": len(self.records) + 1,
            "phase": self.phase,
            "method": "GET",
            "host": self._host,
            "path": path,
            "query": [[k, v] for k, v in query_list],
            "authenticated": all(name in headers for name in _AUTH_HEADER_NAMES),
            "status": None,
            "body_bytes": None,
            "body_sha256": None,
            "outcome": "STARTED",
            "retry": False,
        }
        self.records.append(record)
        started = self._monotonic_ns()
        connection = self._connection_factory()
        try:
            connection.request("GET", full_path, headers=dict(headers))
            response = connection.getresponse()
            chunks, total = [], 0
            while total <= self._cap:
                chunk = response.read(min(65536, self._cap + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            body = b"".join(chunks)
            record["status"] = int(response.status)
            record["body_bytes"] = len(body)
            record["body_sha256"] = hashlib.sha256(body).hexdigest()
            if getattr(response, "length", None) not in (None, 0) and len(body) <= self._cap:
                record["outcome"] = "INCOMPLETE_RESPONSE_BODY"
                raise IncompleteResponseBody()
            record["outcome"] = "COMPLETED"
            return self._sel.HttpResponse(status=int(response.status), body=body)
        except IncompleteResponseBody:
            raise
        except Exception as exc:  # noqa: BLE001 - classified, secret-free
            if record["outcome"] == "STARTED":
                record["outcome"] = "TRANSPORT_FAILURE"
            raise RuntimeError("TRANSPORT_FAILURE:" + type(exc).__name__) from None
        finally:
            record["elapsed_ms"] = (self._monotonic_ns() - started) // 1_000_000
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - cleanup never overrides the result
                pass
