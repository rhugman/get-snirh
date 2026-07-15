"""Live tests against the real SNIRH servers.

Skipped by default; set RUN_LIVE_TESTS=1 to run. Keep request volume low —
these exist to detect SNIRH drift, not to exercise every code path.
"""

import os
import unittest

from get_snirh import Parameters, Snirh, SnirhClient
from get_snirh.networks import fetch_networks
from get_snirh.stations import fetch_stations
from get_snirh.timeseries import TIMESERIES_COLUMNS


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

    def test_01_networks(self):
        networks = self.snirh.networks()
        self.assertEqual(len(networks), 15)
        self.assertEqual(list(networks.columns), ["uid", "name", "slug"])
        self.assertIn("piezometria", set(networks["slug"]))
        self.assertIn("hidrometrica_acores", set(networks["slug"]))
        for name in networks["name"]:
            self.assertTrue(_no_mojibake(name), f"mojibake in network name {name!r}")

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

    def test_03_parameters(self):
        stations = getattr(type(self), "stations", None)
        if stations is None:
            stations = self.snirh.stations()
        parameters = self.snirh.parameters(stations["uid"].iloc[0])
        self.assertFalse(parameters.empty)
        self.assertEqual(list(parameters.columns), ["uid", "name"])
        for name in parameters["name"]:
            self.assertTrue(_no_mojibake(name), f"mojibake in parameter {name!r}")

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
class TestLiveStationsSmokeAllNetworks(unittest.TestCase):
    """stations() smoke across every discovered network.

    A single shared client keeps the request count down: 1 home fetch for
    the network list, then ~3 requests per network (network-select POST +
    markers XML + metadata CSV; +1 home-page fallback for the coordinate-less
    networks, e.g. 'eta' and 'hidrometrica_madeira'). ~49 requests for the
    15 known networks, all sequential (single thread, no worker pool).
    """

    @classmethod
    def setUpClass(cls):
        cls.client = SnirhClient()
        cls.networks = fetch_networks(cls.client)

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
