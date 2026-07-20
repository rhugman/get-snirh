"""Live tests against the real SNIRH servers.

Skipped by default; set RUN_LIVE_TESTS=1 to run. Keep request volume low —
these exist to detect SNIRH drift, not to exercise every code path.
"""

import functools
import os
import unittest

from get_snirh import Parameters, Snirh, SnirhClient
from get_snirh.exceptions import SnirhNetworkError
from get_snirh.networks import fetch_networks
from get_snirh.stations import fetch_stations
from get_snirh.timeseries import TIMESERIES_COLUMNS


def skip_on_network_error(func):
    """Turn a SNIRH outage into a skip, not a failure.

    These tests exist to catch *drift* — SNIRH changing shape underneath us.
    An unreachable server (e.g. the 403s SNIRH returns to non-Portuguese IPs,
    which is what CI runners get) is not drift, so skip rather than fail and
    keep the red signal meaningful.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SnirhNetworkError as exc:
            raise unittest.SkipTest(f"SNIRH unreachable: {exc}")
    return wrapper


#: UTF-8-decoded-as-latin1 pairs (Ã©=é, Ã§=ç, ...), stray marker chars and
#: unescaped entities. Bare 'Ã' is legitimate uppercase Portuguese (SÃO).
_MOJIBAKE = ("Ã©", "Ã¡", "Ã­", "Ã³", "Ãº", "Ã§", "Ã£", "Ãµ", "Ã¢", "Ãª",
             "Ã´", "â–", "■", "&#", "&amp;")


def _no_mojibake(text: str) -> bool:
    return not any(bad in text for bad in _MOJIBAKE)


@unittest.skipUnless(os.getenv("RUN_LIVE_TESTS"),
                     "Skipping live tests. Set RUN_LIVE_TESTS=1 to run.")
class TestLiveDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snirh = Snirh("piezometria")

    @skip_on_network_error
    def test_01_networks(self):
        networks = self.snirh.networks()
        self.assertEqual(len(networks), 15)
        self.assertEqual(list(networks.columns), ["uid", "name", "slug"])
        self.assertIn("piezometria", set(networks["slug"]))
        self.assertIn("hidrometrica_acores", set(networks["slug"]))
        for name in networks["name"]:
            self.assertTrue(_no_mojibake(name), f"mojibake in network name {name!r}")

    @skip_on_network_error
    def test_02_stations(self):
        stations = self.snirh.stations()
        type(self).stations = stations  # reuse downstream to save requests
        self.assertGreater(len(stations), 1000)
        self.assertEqual(list(stations.columns[:2]), ["uid", "code"])
        for column in ("name", "basin", "status", "latitude", "longitude",
                       "coord_x", "coord_y", "aquifer_system"):
            self.assertIn(column, stations.columns)
        accented = stations["district"].dropna().str.contains("Ú|Á|É|Ã", regex=True)
        self.assertTrue(accented.any(), "expected accented district names")
        for value in stations["name"].dropna().head(200):
            self.assertTrue(_no_mojibake(str(value)), f"mojibake in {value!r}")

    @skip_on_network_error
    def test_03_parameters(self):
        stations = getattr(type(self), "stations", None)
        if stations is None:
            stations = self.snirh.stations()
        parameters = self.snirh.parameters(stations["uid"].iloc[0])
        self.assertFalse(parameters.empty)
        self.assertEqual(list(parameters.columns), ["uid", "name"])
        for name in parameters["name"]:
            self.assertTrue(_no_mojibake(name), f"mojibake in parameter {name!r}")

    @skip_on_network_error
    def test_04_timeseries(self):
        stations = getattr(type(self), "stations", None)
        if stations is None:
            stations = self.snirh.stations()
        subset = stations[stations["code"].isin(["3/N1", "3/N2"])]
        if len(subset) < 2:
            subset = stations.head(2)
        df = self.snirh.timeseries(subset, Parameters.GWL_DEPTH,
                                   start="2023-01-01", end="2023-06-30")
        self.assertEqual(list(df.columns), TIMESERIES_COLUMNS)
        self.assertGreater(len(df), 0)
        self.assertTrue(str(df["timestamp"].dtype).startswith("datetime64"))
        self.assertEqual(df["value"].dtype, "float64")


@unittest.skipUnless(os.getenv("RUN_LIVE_TESTS"),
                     "Skipping live tests. Set RUN_LIVE_TESTS=1 to run.")
class TestLiveParametersEnum(unittest.TestCase):
    """The curated Parameters enum must stay true to live discovery.

    Discovery is the source of truth; the enum is convenience constants. If
    SNIRH ever renumbers a parameter, the stale enum id would silently fetch
    the wrong quantity (or nothing), so pin the ids against live discovery.

    One request's worth of stations from each of two networks covers all 28,
    because the enum is meteorological apart from the two groundwater-level
    ids. Probed 2026-07-15: meteorologica's first 50 stations yield 26,
    piezometria's the remaining 2.
    """

    #: {network slug: stations to discover parameters for}. One
    #: _CHUNK_SIZE-sized request each.
    SOURCES = {"meteorologica": 50, "piezometria": 50}

    @classmethod
    @skip_on_network_error
    def setUpClass(cls):
        cls.discovered = set()
        for slug, n_stations in cls.SOURCES.items():
            snirh = Snirh(slug)
            uids = snirh.stations()["uid"].astype(str).tolist()[:n_stations]
            pars = snirh.parameters(uids)
            cls.discovered |= set(pars["uid"].astype(str))

    def test_every_enum_id_exists_in_discovery(self):
        missing = {p.name: p.value for p in Parameters
                   if str(p.value) not in self.discovered}
        self.assertEqual(
            missing, {},
            f"Parameter uids in the curated enum that live discovery no longer "
            f"reports: {missing}. Either SNIRH renumbered them (fix the enum) "
            f"or the sampled stations no longer carry them (fix SOURCES)."
        )


@unittest.skipUnless(os.getenv("RUN_LIVE_TESTS"),
                     "Skipping live tests. Set RUN_LIVE_TESTS=1 to run.")
class TestLiveStationsSmokeAllNetworks(unittest.TestCase):
    """stations() smoke across every discovered network.

    A single shared client keeps the request count down: 1 home fetch for
    the network list, then ~3 requests per network (network-select POST +
    markers XML + metadata CSV; +1 home-page fallback for the coordinate-less
    networks, e.g. 'eta' and 'hidrometrica_madeira'). ~49 requests for the
    15 known networks, all sequential (single thread, no worker pool).
    """

    @classmethod
    @skip_on_network_error
    def setUpClass(cls):
        cls.client = SnirhClient()
        cls.networks = fetch_networks(cls.client)

    @skip_on_network_error
    def test_stations_every_network(self):
        for network in self.networks.itertuples(index=False):
            with self.subTest(network=network.slug):
                stations = fetch_stations(self.client, network.uid)
                self.assertGreater(len(stations), 0,
                                   f"no stations for network {network.slug}")
                self.assertEqual(list(stations.columns[:2]), ["uid", "code"])
                self.assertTrue(
                    stations["uid"].astype(str).str.strip().str.len().gt(0).all(),
                    f"empty station uid(s) in network {network.slug}",
                )
                if "name" in stations.columns:
                    for value in stations["name"].dropna().head(20):
                        self.assertTrue(
                            _no_mojibake(str(value)),
                            f"mojibake in {network.slug} station name {value!r}",
                        )


if __name__ == "__main__":
    unittest.main()
