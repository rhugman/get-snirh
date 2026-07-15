"""Per-station parameter discovery (session-scoped).

``_ajax_listaparscomdados.php?sites=<uid>[,<uid>...]`` returns an
``<option value="PARAM_UID">■ Name</option>`` list of the parameters that
have data for the given station(s). Requires the network session.
"""

import logging
from typing import Iterable, Union

import pandas as pd
from bs4 import BeautifulSoup

from .client import SnirhClient
from .constants import SnirhEncodings, SnirhUrls
from .exceptions import SnirhDiscoveryError
from .utils import clean_marker_label

logger = logging.getLogger(__name__)

PARAMETER_COLUMNS = ["uid", "name"]


def parse_parameters_html(html_text: str) -> pd.DataFrame:
    """Parse the ajax response into a (uid, name) DataFrame."""
    soup = BeautifulSoup(html_text, "html.parser")
    rows = []
    for option in soup.find_all("option"):
        uid = (option.get("value") or "").strip()
        if not uid:
            continue
        name = clean_marker_label(option.get_text())
        rows.append({"uid": uid, "name": name})
    return pd.DataFrame(rows, columns=PARAMETER_COLUMNS)


#: Max station uids per request: keeps the query string well under common
#: ~8 KB server/proxy URL limits.
_CHUNK_SIZE = 50


def fetch_parameters(
    client: SnirhClient,
    network_uid,
    station_uids: Union[str, int, Iterable],
) -> pd.DataFrame:
    """Discover the parameters with data for one or more station uids.

    Requests are chunked at ``_CHUNK_SIZE`` uids; the result is the union of
    the chunks, deduplicated by parameter uid.
    """
    if isinstance(station_uids, (str, int)):
        station_uids = [station_uids]
    uids = [str(uid) for uid in station_uids]
    if not uids:
        raise ValueError("station_uids must contain at least one station uid.")

    client.ensure_network(network_uid)
    frames = []
    for start in range(0, len(uids), _CHUNK_SIZE):
        chunk = uids[start:start + _CHUNK_SIZE]
        response = client.get(
            SnirhUrls.STATION_PARAMETERS,
            params={"sites": ",".join(chunk)},
            session_scoped=True,
        )
        html_text = response.content.decode(SnirhEncodings.STATION_PARAMETERS)
        frames.append(parse_parameters_html(html_text))

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="uid")
    df = df.reset_index(drop=True)
    if df.empty:
        raise SnirhDiscoveryError(
            f"_ajax_listaparscomdados.php returned no parameters for station "
            f"uid(s) {', '.join(uids[:10])}{'...' if len(uids) > 10 else ''}. "
            "Either the network session was not established, the uids do not "
            "belong to the selected network, or the station(s) have no "
            "parameters with data."
        )
    logger.info(
        "Discovered %d parameters for %d station uid(s)", len(df), len(uids)
    )
    return df
