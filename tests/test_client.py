import threading

from get_snirh.client import DEFAULT_TIMEOUT, SnirhClient, _build_session
from get_snirh.constants import USER_AGENT, SnirhUrls


class RecordingClient(SnirhClient):
    """SnirhClient with _request replaced by a recorder (no real HTTP)."""

    def __init__(self):
        super().__init__()
        self.requests_made = []

    def _request(self, session, method, url, **kwargs):
        self.requests_made.append((method, url, kwargs))
        if method == "GET" and url == SnirhUrls.HOME:
            session.cookies.set("PHPSESSID", "fake", domain="snirh.apambiente.pt")

        class FakeResponse:
            content = b""

        return FakeResponse()


class TestLaziness:
    def test_no_requests_at_construction(self):
        client = RecordingClient()
        assert client.requests_made == []
        assert client._network_session is None


class TestEnsureNetwork:
    def test_first_call_gets_home_then_posts(self):
        client = RecordingClient()
        client.ensure_network("100290946")
        methods = [(m, u) for m, u, _ in client.requests_made]
        assert methods == [("GET", SnirhUrls.HOME), ("POST", SnirhUrls.HOME)]
        post_kwargs = client.requests_made[1][2]
        assert post_kwargs["data"] == {
            "f_redes_seleccao[]": "100290946",
            "aplicar_filtro": 1,
        }

    def test_same_uid_is_noop(self):
        client = RecordingClient()
        client.ensure_network("100290946")
        client.ensure_network("100290946")
        assert len(client.requests_made) == 2

    def test_changed_uid_reposts_only(self):
        client = RecordingClient()
        client.ensure_network("100290946")
        client.ensure_network("920123705")
        methods = [m for m, _, _ in client.requests_made]
        assert methods == ["GET", "POST", "POST"]  # cookie kept, only re-POST

    def test_int_uid_normalized(self):
        client = RecordingClient()
        client.ensure_network(100290946)
        client.ensure_network("100290946")
        assert len(client.requests_made) == 2


class TestSessions:
    def test_honest_user_agent(self):
        session = _build_session()
        assert session.headers["User-Agent"] == USER_AGENT
        assert USER_AGENT.startswith("get-snirh/")
        assert "github.com/rhugman/get-snirh" in USER_AGENT

    def test_retry_mounted(self):
        session = _build_session()
        adapter = session.get_adapter("https://snirh.apambiente.pt/")
        assert adapter.max_retries.total == 3
        assert adapter.max_retries.backoff_factor == 1
        assert set(adapter.max_retries.status_forcelist) == {429, 500, 502, 503, 504}

    def test_default_timeout(self):
        assert DEFAULT_TIMEOUT == (30, 120)
        client = RecordingClient()
        client.get("https://example.invalid/x")
        # timeout injected by _request wrapper in the real client; here we
        # just confirm the stateless path routes through _request
        assert client.requests_made[-1][0] == "GET"

    def test_stateless_sessions_are_thread_local(self):
        client = SnirhClient()
        sessions = {}

        def grab(key):
            sessions[key] = client._stateless

        threads = [threading.Thread(target=grab, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sessions[0] is not sessions[1]

    def test_network_session_is_shared(self):
        client = SnirhClient()
        assert client._session_scoped is client._session_scoped
