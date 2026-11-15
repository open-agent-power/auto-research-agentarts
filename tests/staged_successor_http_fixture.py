"""Bounded, single-attempt HTTP client for synthetic successor tests.

The page uses 15 seconds for reads and 60 seconds for save/resume POSTs. These
limits align the test client with that contract; they do not change the service
or imply that an operation completed within the former five-second limit.
"""
import http.client
import json

from autoresearch.contracts import canonical


def request(test, server, path, method="GET", body=None, headers=None):
    timeout = 15 if method == "GET" else 60
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)
    test.addCleanup(connection.close)
    raw = body if type(body) is bytes else canonical(body).encode("utf-8") if body is not None else None
    connection.request(method, path, body=raw, headers=headers or {})
    response = connection.getresponse()
    return response.status, json.loads(response.read())
