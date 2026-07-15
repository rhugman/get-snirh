"""Station discovery for a network.

Two sources, merged on the station ``code``:

- **uid mapping** (session-scoped): ``xml_listaestacoes.php`` returns
  ``<marker>`` elements with the station uid (``site``), a display label
  (``estacao``: ``■ CODE`` or ``■ NAME (CODE)``) and WGS84 coordinates
  (``lat``/``lng``).
- **metadata** (stateless): ``lista_csv.php?s_cover=<network uid>`` returns an
  ISO-8859-1 CSV whose Portuguese headers are mapped to canonical English
  column names via :data:`CANONICAL_COLUMNS`.
"""

import io
import logging
import re

import pandas as pd
from bs4 import BeautifulSoup

from .client import SnirhClient
from .constants import MARKER_CHAR, SnirhEncodings, SnirhUrls
from .exceptions import SnirhDiscoveryError, SnirhParsingError
from .utils import strip_accents, unescape_html

logger = logging.getLogger(__name__)

UID_COLUMNS = ["uid", "code", "name", "latitude", "longitude"]

#: SNIRH metadata CSV header -> canonical column name. Headers not listed
#: here fall back to :func:`fallback_column` (de-accented, lowercased,
#: non-alphanumeric runs -> ``_``). Values remain in Portuguese.
CANONICAL_COLUMNS = {
    "CÓDIGO": "code",
    "NOME": "name",
    "DISTRITO": "district",
    "CONCELHO": "municipality",
    "FREGUESIA": "parish",
    "BACIA": "basin",
    "ALTITUDE (M)": "altitude",
    "COORD_X (M)": "coord_x",
    "COORD_Y (M)": "coord_y",
    "SISTEMA AQUÍFERO": "aquifer_system",
    "ESTADO": "status",
}

#: Canonical columns coerced to numeric (errors coerced to NaN).
_NUMERIC_COLUMNS = ("altitude", "coord_x", "coord_y")

_TRAILING_PARENS = re.compile(r"^(?P<name>.*)\((?P<code>[^()]+)\)\s*$")


# -- uid mapping (session-scoped XML) ----------------------------------------

def _split_label(label: str):
    """Split a marker label into (code, name).

    Labels unescape to ``■ CODE`` or ``■ NAME (CODE)``. The code is the
    content of the trailing parentheses if present, else the whole string;
    the name is the part before the parentheses, or equals the code.
    """
    text = unescape_html(label).replace(MARKER_CHAR, " ").strip()
    match = _TRAILING_PARENS.match(text)
    if match:
        code = match.group("code").strip()
        name = match.group("name").strip() or code
        return code, name
    return text, text


def parse_markers_xml(xml_text: str) -> pd.DataFrame:
    """Parse ``xml_listaestacoes.php`` output into (uid, code, name,
    latitude, longitude)."""
    soup = BeautifulSoup(xml_text, "html.parser")
    rows = []
    for marker in soup.find_all("marker"):
        label = marker.get("estacao") or marker.get("estacao3") or ""
        code, name = _split_label(label)
        rows.append(
            {
                "uid": (marker.get("site") or "").strip(),
                "code": code,
                "name": name,
                "latitude": marker.get("lat"),
                "longitude": marker.get("lng"),
            }
        )
    df = pd.DataFrame(rows, columns=UID_COLUMNS)
    if not df.empty:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df


def parse_station_select_html(html_text: str) -> pd.DataFrame:
    """Parse the home page ``<select name="f_estacoes[]">`` into the uid
    mapping columns (latitude/longitude NaN).

    Fallback uid source: stations without coordinates (all of the ETA and
    Hidrométrica Madeira networks, for instance) never appear on the map
    layer, but they are listed in the station select once the network
    session is established.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    select = soup.find("select", attrs={"name": "f_estacoes[]"})
    rows = []
    if select is not None:
        for option in select.find_all("option"):
            uid = (option.get("value") or "").strip()
            if not uid:
                continue
            code, name = _split_label(option.get_text())
            rows.append(
                {
                    "uid": uid,
                    "code": code,
                    "name": name,
                    "latitude": float("nan"),
                    "longitude": float("nan"),
                }
            )
    return pd.DataFrame(rows, columns=UID_COLUMNS)


def fetch_station_uids(client: SnirhClient, network_uid) -> pd.DataFrame:
    """Fetch the live uid mapping for a network (session-scoped).

    Primary source: the map markers XML. When it is empty (coordinate-less
    networks never appear on the map layer) the home page station select is
    used as fallback.
    """
    client.ensure_network(network_uid)
    response = client.get(SnirhUrls.STATION_MARKERS_XML, session_scoped=True)
    xml_text = response.content.decode(SnirhEncodings.STATION_MARKERS_XML)
    df = parse_markers_xml(xml_text)
    if df.empty:
        logger.info(
            "No map markers for network %s; falling back to the home page "
            "station list (coordinate-less network?)", network_uid,
        )
        response = client.get(SnirhUrls.HOME, session_scoped=True)
        html_text = response.content.decode(SnirhEncodings.HOME)
        df = parse_station_select_html(html_text)
    if df.empty:
        raise SnirhDiscoveryError(
            f"Neither the map markers XML nor the home page station list "
            f"returned stations for network uid {network_uid}. Either the "
            "network session was not established or the network has no "
            "stations."
        )
    logger.info("Discovered %d station uids for network %s", len(df), network_uid)
    return df


# -- metadata (stateless CSV) -------------------------------------------------

def fallback_column(header: str) -> str:
    """Generic canonicalization for headers not in CANONICAL_COLUMNS:
    de-accent, lowercase, non-alphanumeric runs -> ``_``, strip ``_``."""
    text = strip_accents(str(header)).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def canonical_column(header: str) -> str:
    """Map a SNIRH CSV header to its canonical column name."""
    normalized = " ".join(str(header).split())
    return CANONICAL_COLUMNS.get(normalized, fallback_column(normalized))


def parse_metadata_csv(csv_text: str) -> pd.DataFrame:
    """Parse ``lista_csv.php`` output into a canonical-column DataFrame.

    The CSV carries a few title lines before the header row (which starts
    with ``CÓDIGO``) and a footer line ("Dados obtidos ...") after the data.
    """
    lines = csv_text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        if line.lstrip('﻿" ').startswith("CÓDIGO"):
            header_index = i
            break
    if header_index is None:
        raise SnirhParsingError(
            "Could not find the CÓDIGO header row in lista_csv.php output."
        )
    body = "\n".join(lines[header_index:])
    df = pd.read_csv(io.StringIO(body), sep=",", dtype=str, index_col=False)
    df.columns = [canonical_column(c) for c in df.columns]
    # Footer rows parse as a value in the first column with all other
    # columns empty; drop them, plus any rows without a code.
    value_columns = [c for c in df.columns if c != "code"]
    if value_columns:
        df = df[~df[value_columns].isna().all(axis=1)]
    if "code" in df.columns:
        df = df[df["code"].notna()]
    for column in _NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.reset_index(drop=True)


def fetch_station_metadata(client: SnirhClient, network_uid) -> pd.DataFrame:
    """Fetch live station metadata for a network (stateless)."""
    params = {
        "obj_janela": "INFO_ESTACOES",
        "s_cover": str(network_uid),
        "tp_lista": "",
        "completa": 1,
        "formato": "csv",
    }
    response = client.get(SnirhUrls.STATION_LIST_CSV, params=params)
    csv_text = response.content.decode(SnirhEncodings.STATION_LIST_CSV)
    df = parse_metadata_csv(csv_text)
    logger.info("Fetched metadata for %d stations of network %s", len(df), network_uid)
    return df


# -- merged stations table ----------------------------------------------------

def fetch_stations(client: SnirhClient, network_uid) -> pd.DataFrame:
    """Merged stations table: uid mapping + metadata, inner-joined on code.

    ``uid`` and ``code`` come first; both the XML coordinates
    (``latitude``/``longitude``) and the metadata grid coordinates
    (``coord_x``/``coord_y``) are kept.
    """
    uids = fetch_station_uids(client, network_uid)
    metadata = fetch_station_metadata(client, network_uid)

    uids = uids.copy()
    uids["code"] = uids["code"].astype(str).str.strip()
    metadata = metadata.copy()
    metadata["code"] = metadata["code"].astype(str).str.strip()

    # Prefer the metadata 'name' (full station name) over the label-derived one.
    left = uids.drop(columns=["name"]) if "name" in metadata.columns else uids
    merged = pd.merge(left, metadata, on="code", how="inner")
    if merged.empty and not uids.empty and not metadata.empty:
        raise SnirhParsingError(
            f"Station codes from the uid mapping and the metadata CSV do not "
            f"align for network uid {network_uid} (0 of {len(uids)} matched)."
        )
    if len(merged) < len(uids):
        logger.warning(
            "%d of %d stations in the uid mapping have no metadata row and "
            "were dropped from the merged table.",
            len(uids) - len(merged), len(uids),
        )

    front = ["uid", "code"] + (["name"] if "name" in merged.columns else [])
    ordered = front + [c for c in merged.columns if c not in front]
    merged = merged[ordered].reset_index(drop=True)
    logger.info("Merged stations table has %d rows", len(merged))
    return merged
