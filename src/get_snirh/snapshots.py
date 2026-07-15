"""Bundled snapshots: the offline fallback for station discovery.

A snapshot is a UTF-8 CSV copy of a past merged-stations discovery result,
one file per network (``snapshot_<slug>.csv``), shipped inside the package
``data/`` directory. Snapshots are always potentially stale; they are only
used when SNIRH is unreachable (with a loud warning) or on explicit request.

The first line of a snapshot is a metadata header comment recording the
fetch date (``# snapshot_date: YYYY-MM-DD``), so the staleness warning can
say how old the fallback data is. Snapshots written before date stamping
(no header line) still load; their date is reported as unknown.
"""

import datetime as _dt
import logging
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .exceptions import SnirhError

logger = logging.getLogger(__name__)

#: Directory holding the snapshots bundled with the package.
BUNDLED_DIR = Path(__file__).resolve().parent / "data"

#: Prefix of the metadata header line carrying the fetch date.
SNAPSHOT_DATE_PREFIX = "# snapshot_date:"


def snapshot_path(network: str, directory: Union[str, Path, None] = None) -> Path:
    """Path of the snapshot file for a network slug."""
    base = Path(directory) if directory is not None else BUNDLED_DIR
    return base / f"snapshot_{network}.csv"


def save_snapshot(
    directory: Union[str, Path, None],
    network: str,
    stations_df: pd.DataFrame,
    fetched_on: Union[str, _dt.date, None] = None,
) -> Path:
    """Write ``stations_df`` as the snapshot for ``network`` (a slug).

    ``directory=None`` targets the bundled package data directory. The fetch
    date (``fetched_on``, default today) is embedded as a metadata header
    line. Returns the written path.
    """
    base = Path(directory) if directory is not None else BUNDLED_DIR
    base.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(network, base)
    if fetched_on is None:
        fetched_on = _dt.date.today()
    stamp = fetched_on if isinstance(fetched_on, str) else fetched_on.isoformat()
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"{SNAPSHOT_DATE_PREFIX} {stamp}\n")
        stations_df.to_csv(fh, index=False)
    logger.info("Saved snapshot for network '%s' to %s (fetched %s)",
                network, path, stamp)
    return path


def snapshot_date(
    network: str, directory: Union[str, Path, None] = None
) -> Optional[str]:
    """ISO date on which the snapshot for ``network`` was fetched.

    Returns ``None`` when the snapshot is missing or predates date stamping
    (no metadata header line).
    """
    path = snapshot_path(network, directory)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        first = fh.readline().strip()
    if first.startswith(SNAPSHOT_DATE_PREFIX):
        return first[len(SNAPSHOT_DATE_PREFIX):].strip() or None
    return None


def load_snapshot(
    network: str, directory: Union[str, Path, None] = None
) -> pd.DataFrame:
    """Load the snapshot for ``network`` (a slug).

    Raises :class:`SnirhError` when no snapshot exists for the network.
    """
    path = snapshot_path(network, directory)
    if not path.exists():
        raise SnirhError(
            f"No bundled snapshot for network '{network}' (looked for {path}). "
            "SNIRH could not be reached and there is no offline fallback for "
            "this network."
        )
    with path.open("r", encoding="utf-8") as fh:
        has_header = fh.readline().startswith("#")
    dtypes: Optional[dict] = {"uid": str, "code": str}
    df = pd.read_csv(path, encoding="utf-8", dtype=dtypes,
                     skiprows=1 if has_header else 0)
    logger.info("Loaded snapshot for network '%s' from %s (%d rows)",
                network, path, len(df))
    return df
