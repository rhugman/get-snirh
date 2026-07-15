"""URLs, encodings and parameter constants for SNIRH endpoints."""

from enum import Enum

#: Package version. Keep in sync with ``pyproject.toml``.
__version__ = "0.2.0.dev0"

#: Honest User-Agent, verified accepted by all SNIRH endpoints (2026-07-15).
USER_AGENT = f"get-snirh/{__version__} (+https://github.com/rhugman/get-snirh)"

#: Marker character SNIRH prefixes to station and parameter labels
#: (arrives as the HTML entity ``&#9632;``).
MARKER_CHAR = "■"  # '■'


class SnirhUrls:
    """SNIRH endpoints.

    Session-scoped (require the lazily-established network session):
    ``STATION_MARKERS_XML``, ``STATION_PARAMETERS``.
    Everything else is stateless.
    """

    BASE_URL = "https://snirh.apambiente.pt"
    #: Home page: sets PHPSESSID; also serves the network <select> for discovery,
    #: and receives the network-selection POST.
    HOME = f"{BASE_URL}/index.php?idMain=2&idItem=1"

    _DADOSBASE = f"{BASE_URL}/snirh/_dadosbase/site"
    #: Session-scoped station uid/code/coordinate markers for the selected network.
    STATION_MARKERS_XML = f"{_DADOSBASE}/xml/xml_listaestacoes.php"
    #: Session-scoped per-station parameter discovery (?sites=<uid>[,<uid>...]).
    STATION_PARAMETERS = f"{_DADOSBASE}/_ajax_listaparscomdados.php"
    #: Stateless station metadata CSV (?s_cover=<network uid>).
    STATION_LIST_CSV = f"{_DADOSBASE}/paraCSV/lista_csv.php"
    #: Stateless timeseries CSV.
    DATA_CSV = f"{_DADOSBASE}/paraCSV/dados_csv.php"


class SnirhEncodings:
    """Correct decoding per endpoint (probed live 2026-07-15).

    - Home page: no charset in Content-Type; accented network names are
      ISO-8859-1 bytes.
    - Marker XML: declares ``charset=utf-8``; non-ASCII arrives as HTML
      entities (``&#9632;``, sometimes double-escaped) which the parser
      unescapes.
    - Parameter ajax: entity-encoded ASCII (``&iacute;`` etc.); UTF-8-safe.
    - CSV endpoints: ISO-8859-1 with real accented bytes.
    """

    HOME = "ISO-8859-1"
    STATION_MARKERS_XML = "utf-8"
    STATION_PARAMETERS = "utf-8"
    STATION_LIST_CSV = "ISO-8859-1"
    DATA_CSV = "ISO-8859-1"


class Parameters(Enum):
    """Curated SNIRH parameter uids (convenience constants).

    Live discovery via :meth:`get_snirh.Snirh.parameters` is the source of
    truth; these are kept for convenience.
    """

    # Meteorological
    WIND_DIRECTION_HOURLY = '1857'
    EVAPORATION_PICHE_DAILY = '4131'
    EVAPORATION_PICHE_MONTHLY = '1847'
    EVAPORATION_PAN_DAILY = '100733600'
    EVAPORATION_PAN_MONTHLY = '100733750'
    HUMIDITY_RELATIVE_HOURLY = '100750599'
    HUMIDITY_RELATIVE_AVG_DAILY = '439882260'
    CLOUD_COVER_DAILY = '1860'
    PAN_LEVEL_HOURLY = '100744027'
    PRECIPITATION_ANNUAL = '4237'
    PRECIPITATION_DAILY = '413026594'
    PRECIPITATION_DAILY_MAX_ANNUAL = '1578135698'
    PRECIPITATION_HOURLY = '100744007'
    PRECIPITATION_MONTHLY = '1436794570'
    RADIATION_DAILY = '490269378'
    RADIATION_HOURLY = '100749780'
    AIR_TEMP_HOURLY = '100745177'
    AIR_TEMP_MAX_DAILY = '1852'
    AIR_TEMP_AVG_DAILY = '490270830'
    AIR_TEMP_AVG_MONTHLY = '1520200094'
    AIR_TEMP_MIN_DAILY = '1853'
    WIND_SPEED_DAILY = '641792832'
    WIND_SPEED_HOURLY = '100750606'
    WIND_SPEED_INSTANT = '1041803938'
    WIND_SPEED_MAX_HOURLY = '100750612'
    WIND_SPEED_AVG_DAILY = '490270858'

    # Groundwater
    GWL_DEPTH = '2277'
    PIEZOMETRIC_LEVEL = '100290981'
