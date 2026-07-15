"""Live discovery of SNIRH monitoring networks.

The network list is parsed from the public home page (stateless): the
``<select name="f_redes_todas[]">`` element holds one ``<option>`` per
network, with the network uid as the option value.
"""

import logging

import pandas as pd
from bs4 import BeautifulSoup

from .client import SnirhClient
from .constants import SnirhEncodings, SnirhUrls
from .exceptions import SnirhParsingError
from .utils import slugify, unescape_html

logger = logging.getLogger(__name__)

NETWORK_COLUMNS = ["uid", "name", "slug"]


def parse_networks_html(html_text: str) -> pd.DataFrame:
    """Parse the home-page HTML into a networks DataFrame (uid, name, slug)."""
    soup = BeautifulSoup(html_text, "html.parser")
    select = soup.find("select", {"name": "f_redes_todas[]"})
    if select is None:
        raise SnirhParsingError(
            "Could not find the network <select name='f_redes_todas[]'> on the "
            "SNIRH home page; the page layout may have changed."
        )
    rows = []
    for option in select.find_all("option"):
        uid = (option.get("value") or "").strip()
        if not uid:
            continue
        # Names may carry a leading '*' marker (e.g. '* Piezometria').
        name = unescape_html(option.get_text()).strip().lstrip("*").strip()
        rows.append({"uid": uid, "name": name, "slug": slugify(name)})
    if not rows:
        raise SnirhParsingError("The network <select> contained no options.")
    df = pd.DataFrame(rows, columns=NETWORK_COLUMNS)
    logger.info("Discovered %d networks", len(df))
    return df


def fetch_networks(client: SnirhClient) -> pd.DataFrame:
    """Fetch and parse the live network list (stateless)."""
    response = client.get(SnirhUrls.HOME)
    html_text = response.content.decode(SnirhEncodings.HOME)
    return parse_networks_html(html_text)
