"""Concurrent timeseries retrieval from ``dados_csv.php`` (stateless).

Each station is fetched in its own worker thread (thread-local HTTP
sessions inside :class:`~get_snirh.client.SnirhClient` make this safe).
Output is long-format with columns ``timestamp, code, uid, parameter, value``.
"""

import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Union

import pandas as pd

from .client import SnirhClient
from .constants import Parameters, SnirhEncodings, SnirhUrls
from .exceptions import SnirhNetworkError, SnirhParsingError
from .utils import to_snirh_date

logger = logging.getLogger(__name__)

TIMESERIES_COLUMNS = ["timestamp", "code", "uid", "parameter", "value"]

_TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M"


def default_max_workers(n_stations: int) -> int:
    """Default concurrency: ``min(10, n)``, at least 1 (polite cap)."""
    return max(1, min(10, n_stations))


def station_map(stations) -> Dict[str, str]:
    """Normalize the stations argument to ``{uid: code}`` (both str).

    Accepts a DataFrame with ``uid`` (+ preferably ``code``) columns, a
    list/iterable of uids, a dict ``{uid: code}``, or a single uid.
    """
    if isinstance(stations, pd.DataFrame):
        if "uid" not in stations.columns:
            raise ValueError(
                "stations DataFrame must have a 'uid' column (a 'code' column "
                "is used for labelling when present)."
            )
        uids = stations["uid"].astype(str)
        if "code" in stations.columns:
            codes = stations["code"].astype(str)
        else:
            codes = uids
        return dict(zip(uids, codes))
    if isinstance(stations, dict):
        return {str(uid): str(code) for uid, code in stations.items()}
    if isinstance(stations, (str, int)):
        uid = str(stations)
        return {uid: uid}
    try:
        return {str(uid): str(uid) for uid in stations}
    except TypeError:
        raise TypeError(
            "stations must be a DataFrame with uid+code columns, a list of "
            f"uids, or a dict {{uid: code}}; got {type(stations).__name__}"
        ) from None


#: Start of the row SNIRH prints above the data rows. A station with no
#: observations still returns the full layout (header, flag legend, footer),
#: so a body without this row is a degraded response, not an empty one.
_DATA_HEADER = "DATA,"


def parse_timeseries_csv(csv_text: str) -> pd.DataFrame:
    """Parse a ``dados_csv.php`` response into (timestamp, value).

    Layout: 3 title lines, a header row, ``dd/mm/yyyy HH:MM`` data rows and
    a one-line footer.

    Raises:
        SnirhParsingError: if the body is not a CSV export at all. SNIRH is a
            legacy PHP server that serves maintenance pages and error dumps
            with HTTP 200, which must not be mistaken for "no observations".
    """
    if not any(line.startswith(_DATA_HEADER) for line in csv_text.splitlines()):
        raise SnirhParsingError(
            f"dados_csv.php response has no {_DATA_HEADER!r} header row, so it "
            "is not a CSV export; SNIRH is likely serving a maintenance or "
            f"error page. Body starts: {csv_text.strip()[:200]!r}"
        )
    try:
        df = pd.read_csv(
            io.StringIO(csv_text),
            sep=",",
            skiprows=3,
            header=0,
            skipfooter=1,
            usecols=[0, 1],
            names=["timestamp", "value"],
            engine="python",
        )
    except (ValueError, pd.errors.ParserError) as exc:
        raise SnirhParsingError(
            f"Could not parse the dados_csv.php CSV body: {exc}"
        ) from exc
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "value"])
    timestamps = pd.to_datetime(
        df["timestamp"], format=_TIMESTAMP_FORMAT, errors="coerce"
    )
    fallback = timestamps.isna() & df["timestamp"].notna()
    if fallback.any():
        timestamps.loc[fallback] = pd.to_datetime(
            df.loc[fallback, "timestamp"], dayfirst=True, errors="coerce"
        )
    df["timestamp"] = timestamps
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[df["timestamp"].notna()].reset_index(drop=True)


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns]"),
            "code": pd.Series(dtype="object"),
            "uid": pd.Series(dtype="object"),
            "parameter": pd.Series(dtype="object"),
            "value": pd.Series(dtype="float64"),
        }
    )


def fetch_timeseries(
    client: SnirhClient,
    stations,
    parameter: Union[Parameters, str],
    start,
    end,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch timeseries for one parameter across stations, concurrently.

    Args:
        client: the HTTP client (only stateless requests are issued).
        stations: DataFrame with ``uid``+``code`` columns (preferred), a
            list of uids, or a dict ``{uid: code}``.
        parameter: a :class:`Parameters` member or a raw parameter uid str.
        start, end: ISO ``'YYYY-MM-DD'`` strings or date/datetime objects.
        max_workers: worker threads; defaults to ``min(10, n_stations)``.

    Returns:
        DataFrame with columns ``timestamp, code, uid, parameter, value``,
        sorted by code then timestamp. Empty (with those columns) when no
        station returned data.
    """
    if isinstance(parameter, Parameters):
        parameter_uid, parameter_label = parameter.value, parameter.name
    else:
        parameter_uid = parameter_label = str(parameter)

    tmin = to_snirh_date(start, name="start")
    tmax = to_snirh_date(end, name="end")

    stations_by_uid = station_map(stations)
    if not stations_by_uid:
        return _empty_result()

    if max_workers is None:
        max_workers = default_max_workers(len(stations_by_uid))
    if max_workers < 1:
        raise ValueError(f"max_workers must be >= 1, got {max_workers}")

    logger.info(
        "Fetching timeseries for %d stations, parameter %s (%s), %s..%s, %d workers",
        len(stations_by_uid), parameter_label, parameter_uid, tmin, tmax, max_workers,
    )

    errors = []

    def fetch_single(uid: str, code: str) -> Optional[pd.DataFrame]:
        try:
            response = client.get(
                SnirhUrls.DATA_CSV,
                params={
                    "sites": uid,
                    "pars": parameter_uid,
                    "tmin": tmin,
                    "tmax": tmax,
                    "formato": "csv",
                },
            )
            csv_text = response.content.decode(SnirhEncodings.DATA_CSV)
            df = parse_timeseries_csv(csv_text)
            if df.empty:
                logger.debug("No data for station %s (uid %s)", code, uid)
                return None
            df["code"] = code
            df["uid"] = uid
            df["parameter"] = parameter_label
            return df[TIMESERIES_COLUMNS]
        except Exception as exc:  # per-station failures are logged, not fatal
            logger.error("Failed to fetch station %s (uid %s): %s", code, uid, exc)
            errors.append((code, uid, exc))
            return None

    frames = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_single, uid, code): uid
            for uid, code in stations_by_uid.items()
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None and not result.empty:
                frames.append(result)

    if errors:
        logger.warning(
            "%d of %d station fetches failed.", len(errors), len(stations_by_uid)
        )

    if not frames:
        # An empty result must mean "no observations in the window", never a
        # silent total outage: if every station errored, raise instead of
        # returning an empty frame, whatever the failures were.
        if errors and len(errors) == len(stations_by_uid):
            network_errors = [
                e for _, _, e in errors if isinstance(e, SnirhNetworkError)
            ]
            if network_errors:
                raise SnirhNetworkError(
                    f"All {len(stations_by_uid)} station fetches failed "
                    f"({len(network_errors)} network errors); SNIRH appears "
                    f"unreachable. First error: {network_errors[0]}"
                ) from network_errors[0]
            cause = errors[0][2]
            raise SnirhParsingError(
                f"All {len(stations_by_uid)} station fetches failed and none "
                f"returned usable data; SNIRH is likely serving degraded "
                f"responses. First error: {cause}"
            ) from cause
        logger.warning("No data fetched for any station.")
        return _empty_result()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["code", "timestamp"]).reset_index(drop=True)
    logger.info("Fetched %d rows total", len(combined))
    return combined
