"""get-snirh: retrieval of Portuguese water-resources monitoring data from
SNIRH (Agência Portuguesa do Ambiente).

Usage::

    from get_snirh import Snirh, Parameters

    snirh = Snirh("piezometria")                 # slug or uid
    nets = snirh.networks()
    stations = snirh.stations(basin="RIBEIRAS DO ALGARVE")
    pars = snirh.parameters(stations["uid"].iloc[0])
    df = snirh.timeseries(stations, Parameters.GWL_DEPTH,
                          start="2023-01-01", end="2023-12-31")
"""

import logging
import warnings
from typing import Optional, Union

import pandas as pd

# Add NullHandler to prevent "No handler found" warnings
logging.getLogger(__name__).addHandler(logging.NullHandler())

from .client import SnirhClient
from .constants import Parameters, __version__
from .exceptions import (
    SnirhDiscoveryError,
    SnirhError,
    SnirhNetworkError,
    SnirhParsingError,
)
from .networks import fetch_networks
from .parameters import fetch_parameters
from .snapshots import load_snapshot, save_snapshot, snapshot_date
from .stations import fetch_stations, station_map
from .timeseries import fetch_timeseries
from .utils import slugify


def _filter_stations(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Filter on canonical columns with case-insensitive exact matching.

    Each filter value may be a single value or a list/iterable of values.
    """
    for column, wanted in filters.items():
        if wanted is None:
            continue
        if column not in df.columns:
            raise ValueError(
                f"Unknown station filter {column!r}. Available columns: "
                f"{', '.join(df.columns)}"
            )
        if isinstance(wanted, str):
            values = [wanted]
        else:
            try:
                values = list(wanted)
            except TypeError:
                values = [wanted]
        targets = {str(v).casefold() for v in values}
        df = df[df[column].astype(str).str.casefold().isin(targets)]
    return df.reset_index(drop=True)


def _station_uids(station) -> list:
    """Normalize a station argument to a list of uid strings."""
    return list(station_map(station))


class Snirh:
    """Flat facade over live SNIRH discovery and retrieval.

    Args:
        network: network slug (e.g. ``'piezometria'``) or uid (str or int).
            Resolved lazily via live discovery and cached per instance.
        verbose: when True, log INFO messages to stderr.
    """

    def __init__(self, network: Union[str, int] = "piezometria",
                 verbose: bool = False):
        if verbose:
            logger = logging.getLogger(__name__)
            # Only add handler if one doesn't exist to avoid duplicates
            if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
                handler = logging.StreamHandler()
                handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)

        self.client = SnirhClient()
        self._network_spec = network
        self._network_uid: Optional[str] = None
        self._network_slug: Optional[str] = None
        self._networks_cache: Optional[pd.DataFrame] = None

    # -- discovery -----------------------------------------------------------

    def networks(self) -> pd.DataFrame:
        """All SNIRH networks (uid, name, slug), live-discovered.

        Works without a bound network. Cached per instance.
        """
        if self._networks_cache is None:
            self._networks_cache = fetch_networks(self.client)
        return self._networks_cache.copy()

    def _resolve_network(self) -> str:
        """Resolve the bound network spec to a uid via live discovery."""
        if self._network_uid is not None:
            return self._network_uid

        spec = self._network_spec
        text = str(spec).strip()

        if isinstance(spec, int) or text.isdigit():
            self._network_uid = text
            # Best effort: learn the slug (used for snapshot fallback).
            # uid-bound usage must not depend on discovery, so any SnirhError
            # here (network down, home page drift) is non-fatal.
            try:
                networks = self.networks()
            except SnirhError:
                return self._network_uid
            match = networks[networks["uid"] == text]
            if not match.empty:
                self._network_slug = match["slug"].iloc[0]
            return self._network_uid

        slug = slugify(text)
        # Remember the slug before hitting the network, so the snapshot
        # fallback still works when discovery is unreachable.
        self._network_slug = slug
        networks = self.networks()
        match = networks[networks["slug"] == slug]
        if match.empty:
            available = ", ".join(sorted(networks["slug"]))
            raise SnirhError(
                f"Unknown network {spec!r}. Available networks: {available}"
            )
        self._network_uid = str(match["uid"].iloc[0])
        return self._network_uid

    # -- stations ------------------------------------------------------------

    def stations(self, basin=None, status=None, **filters) -> pd.DataFrame:
        """Merged stations table for the bound network (live-first).

        Falls back to the bundled snapshot (with a staleness warning) when
        SNIRH is unreachable. Keyword arguments filter on canonical columns
        with case-insensitive exact matching; ``basin`` (str or list) and
        ``status`` are shortcuts for the corresponding columns.
        """
        try:
            uid = self._resolve_network()
            df = fetch_stations(self.client, uid)
        except SnirhNetworkError as exc:
            if self._network_slug is None:
                raise
            stamp = snapshot_date(self._network_slug)
            age = f"fetched {stamp}" if stamp else "of unknown date"
            warnings.warn(
                f"SNIRH is unreachable ({exc}); falling back to the bundled "
                f"snapshot for network '{self._network_slug}' ({age}). "
                "Snapshot data may be STALE — retry live or run "
                "refresh_snapshot() once SNIRH is reachable again.",
                stacklevel=2,
            )
            df = load_snapshot(self._network_slug)

        if basin is not None:
            filters["basin"] = basin
        if status is not None:
            filters["status"] = status
        return _filter_stations(df, filters)

    # -- parameters ------------------------------------------------------------

    def parameters(self, station) -> pd.DataFrame:
        """Parameters with data for a station (uid str/int) or DataFrame
        row(s) with a ``uid`` column. Live, session-scoped."""
        uid = self._resolve_network()
        return fetch_parameters(self.client, uid, _station_uids(station))

    # -- timeseries ------------------------------------------------------------

    def timeseries(self, stations, parameter, start, end,
                   max_workers: Optional[int] = None) -> pd.DataFrame:
        """Timeseries for one parameter across stations.

        Args:
            stations: DataFrame with ``uid``+``code`` columns (preferred),
                list of uids, or dict ``{uid: code}``.
            parameter: :class:`Parameters` member or raw parameter uid str.
            start, end: ISO ``'YYYY-MM-DD'`` strings or date/datetime objects.
            max_workers: worker threads (default ``min(10, n_stations)``).

        Returns:
            DataFrame with columns ``timestamp, code, uid, parameter, value``.
        """
        return fetch_timeseries(
            self.client, stations, parameter, start, end, max_workers=max_workers
        )

    # -- snapshots ------------------------------------------------------------

    def refresh_snapshot(self, output_dir: Optional[str] = None):
        """Regenerate the offline snapshot for the bound network (live fetch).

        ``output_dir=None`` refreshes the snapshot bundled inside the
        package. Returns the written path.
        """
        uid = self._resolve_network()
        slug = self._network_slug or uid
        df = fetch_stations(self.client, uid)
        return save_snapshot(output_dir, slug, df)


__all__ = [
    "Snirh",
    "SnirhClient",
    "Parameters",
    "SnirhError",
    "SnirhNetworkError",
    "SnirhParsingError",
    "SnirhDiscoveryError",
    "__version__",
]
