"""HTTP client for SNIRH with lazy network-session handling.

SNIRH has two kinds of endpoints:

- **Session-scoped**: ``xml_listaestacoes.php`` and
  ``_ajax_listaparscomdados.php`` return empty documents unless the client
  first GETs the home page (obtaining a ``PHPSESSID`` cookie) and POSTs the
  network selection back to it. These go through a single, lazily-created
  *network session* which tracks the currently selected network uid.
- **Stateless**: everything else (home page, ``lista_csv.php``,
  ``dados_csv.php``). These go through thread-local sessions so timeseries
  fetching can run concurrently (``requests.Session`` is not thread-safe).
"""

import logging
import threading
from typing import Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import USER_AGENT, SnirhUrls
from .exceptions import SnirhNetworkError

logger = logging.getLogger(__name__)

#: (connect, read) timeout in seconds, applied to every request.
DEFAULT_TIMEOUT = (30, 120)


def _build_session() -> requests.Session:
    """New requests session with retries, backoff and an honest User-Agent."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "POST"},
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


class SnirhClient:
    """Client for SNIRH endpoints.

    Nothing is fetched at construction. The network session is established
    lazily by the first session-scoped call (via :meth:`ensure_network`).
    The network session itself is single-threaded; only stateless requests
    (``session_scoped=False``) are safe to issue from worker threads.
    """

    def __init__(self, timeout: Tuple[float, float] = DEFAULT_TIMEOUT):
        self._timeout = timeout
        self._network_session: Optional[requests.Session] = None
        self._selected_network: Optional[str] = None
        self._local = threading.local()
        logger.debug("SnirhClient initialized (lazy; no requests issued yet)")

    # -- sessions ----------------------------------------------------------

    @property
    def _session_scoped(self) -> requests.Session:
        """The single network session (session-scoped endpoints)."""
        if self._network_session is None:
            self._network_session = _build_session()
        return self._network_session

    @property
    def _stateless(self) -> requests.Session:
        """Thread-local session for stateless endpoints (concurrency-safe)."""
        if not hasattr(self._local, "session"):
            self._local.session = _build_session()
        return self._local.session

    # -- network session lifecycle ------------------------------------------

    def ensure_network(self, uid: Union[str, int]) -> None:
        """Make sure the network session is scoped to network ``uid``.

        First call: GET the home page (sets ``PHPSESSID``), then POST the
        network selection. Later calls re-POST only when the uid changes.
        """
        uid = str(uid)
        if self._selected_network == uid:
            return
        session = self._session_scoped
        if "PHPSESSID" not in session.cookies:
            logger.debug("Establishing SNIRH session (GET home page)")
            self._request(session, "GET", SnirhUrls.HOME)
        logger.debug("Selecting network uid %s (POST home page)", uid)
        self._request(
            session,
            "POST",
            SnirhUrls.HOME,
            data={"f_redes_seleccao[]": uid, "aplicar_filtro": 1},
        )
        self._selected_network = uid

    # -- requests ------------------------------------------------------------

    def get(self, url: str, params: Optional[dict] = None,
            session_scoped: bool = False) -> requests.Response:
        """GET ``url`` and return the response.

        ``session_scoped=True`` routes the request through the network
        session (callers must :meth:`ensure_network` first); otherwise a
        thread-local stateless session is used.
        """
        session = self._session_scoped if session_scoped else self._stateless
        return self._request(session, "GET", url, params=params)

    def _request(self, session: requests.Session, method: str, url: str,
                 **kwargs) -> requests.Response:
        try:
            response = session.request(
                method, url, timeout=self._timeout, allow_redirects=True, **kwargs
            )
            response.raise_for_status()
            logger.debug("%s %s -> %s (%d bytes)", method, url,
                         response.status_code, len(response.content))
            return response
        except requests.exceptions.RequestException as exc:
            logger.error("%s %s failed: %s", method, url, exc)
            raise SnirhNetworkError(f"{method} {url} failed: {exc}") from exc
