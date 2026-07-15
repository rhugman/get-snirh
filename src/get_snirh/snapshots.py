"""Bundled snapshots: the offline fallback for station discovery.

A snapshot is a UTF-8 CSV copy of a past merged-stations discovery result,
one file per network (``snapshot_<slug>.csv``), shipped inside the package
``data/`` directory. Snapshots are always potentially stale; they are only
used when SNIRH is unreachable (with a loud warning) or on explicit request.
"""

import logging
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .exceptions import SnirhError

logger = logging.getLogger(__name__)

#: Directory holding the snapshots bundled with the package.
BUNDLED_DIR = Path(__file__).resolve().parent / "data"


def snapshot_path(network: str, directory: Union[str, Path, None] = None) -> Path:
    """Path of the snapshot file for a network slug."""
    base = Path(directory) if directory is not None else BUNDLED_DIR
    return base / f"snapshot_{network}.csv"


def save_snapshot(
    directory: Union[str, Path, None],
    network: str,
    stations_df: pd.DataFrame,
) -> Path:
    """Write ``stations_df`` as the snapshot for ``network`` (a slug).

    ``directory=None`` targets the bundled package data directory.
    Returns the written path.
    """
    base = Path(directory) if directory is not None else BUNDLED_DIR
    base.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(network, base)
    stations_df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Saved snapshot for network '%s' to %s", network, path)
    return path


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
    dtypes: Optional[dict] = {"uid": str, "code": str}
    df = pd.read_csv(path, encoding="utf-8", dtype=dtypes)
    logger.info("Loaded snapshot for network '%s' from %s (%d rows)",
                network, path, len(df))
    return df
