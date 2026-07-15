"""Test doubles: a fake SnirhClient that serves canned bytes."""


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content


class FakeClient:
    """Stands in for SnirhClient. ``routes`` maps url -> bytes or a
    callable(params) -> bytes."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []
        self.ensured = []

    def ensure_network(self, uid):
        self.ensured.append(str(uid))

    def get(self, url, params=None, session_scoped=False):
        self.calls.append({"url": url, "params": params,
                           "session_scoped": session_scoped})
        handler = self.routes[url]
        content = handler(params) if callable(handler) else handler
        return FakeResponse(content)
