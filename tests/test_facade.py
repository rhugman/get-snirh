import pandas as pd
import pytest

import get_snirh
import get_snirh.snapshots as snapshots_module
from get_snirh import Parameters, Snirh, SnirhError, SnirhNetworkError

NETWORKS_DF = pd.DataFrame(
    {
        "uid": ["100290946", "111307207", "920123705"],
        "name": ["Piezometria", "Hidrométrica Açores", "Hidrométrica"],
        "slug": ["piezometria", "hidrometrica_acores", "hidrometrica"],
    }
)

STATIONS_DF = pd.DataFrame(
    {
        "uid": ["1", "2", "3"],
        "code": ["A1", "B2", "C3"],
        "name": ["Poço Um", "Poço Dois", "Poço Três"],
        "basin": ["RIBEIRAS DO ALGARVE", "TEJO", "Ribeiras do Algarve"],
        "status": ["ATIVA", "EXTINTA", "ATIVA"],
    }
)


@pytest.fixture
def live_ok(monkeypatch):
    monkeypatch.setattr(get_snirh, "fetch_networks", lambda client: NETWORKS_DF.copy())
    monkeypatch.setattr(
        get_snirh, "fetch_stations", lambda client, uid: STATIONS_DF.copy()
    )


class TestNetworkResolution:
    def test_slug(self, live_ok):
        snirh = Snirh("piezometria")
        assert snirh._resolve_network() == "100290946"

    def test_accented_input_slugified(self, live_ok):
        snirh = Snirh("Hidrométrica Açores")
        assert snirh._resolve_network() == "111307207"

    def test_uid_string(self, live_ok):
        snirh = Snirh("100290946")
        assert snirh._resolve_network() == "100290946"
        assert snirh._network_slug == "piezometria"

    def test_uid_int(self, live_ok):
        snirh = Snirh(100290946)
        assert snirh._resolve_network() == "100290946"

    def test_unknown_network_name(self, live_ok):
        snirh = Snirh("not_a_network")
        with pytest.raises(SnirhError, match="Available networks.*piezometria"):
            snirh.stations()

    def test_resolution_cached(self, live_ok, monkeypatch):
        snirh = Snirh("piezometria")
        snirh._resolve_network()
        # break discovery: resolution must not hit it again
        monkeypatch.setattr(get_snirh, "fetch_networks",
                            lambda client: (_ for _ in ()).throw(AssertionError))
        assert snirh._resolve_network() == "100290946"

    def test_construction_is_lazy(self, monkeypatch):
        def explode(client):
            raise AssertionError("network touched at construction")

        monkeypatch.setattr(get_snirh, "fetch_networks", explode)
        Snirh("piezometria")  # must not raise


class TestNetworks:
    def test_networks_without_binding(self, live_ok):
        df = Snirh("piezometria").networks()
        assert list(df.columns) == ["uid", "name", "slug"]
        assert len(df) == 3


class TestStationsFilters:
    def test_no_filters(self, live_ok):
        assert len(Snirh("piezometria").stations()) == 3

    def test_basin_case_insensitive(self, live_ok):
        df = Snirh("piezometria").stations(basin="ribeiras do algarve")
        assert set(df["code"]) == {"A1", "C3"}

    def test_basin_list(self, live_ok):
        df = Snirh("piezometria").stations(
            basin=["RIBEIRAS DO ALGARVE", "TEJO"]
        )
        assert len(df) == 3

    def test_status_filter(self, live_ok):
        df = Snirh("piezometria").stations(status="ativa")
        assert set(df["code"]) == {"A1", "C3"}

    def test_extra_kwarg_filter(self, live_ok):
        df = Snirh("piezometria").stations(code="b2")
        assert df.iloc[0]["uid"] == "2"

    def test_unknown_filter_column(self, live_ok):
        with pytest.raises(ValueError, match="Unknown station filter"):
            Snirh("piezometria").stations(bacia="TEJO")


class TestSnapshotFallback:
    def _snapshotted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(snapshots_module, "BUNDLED_DIR", tmp_path)
        STATIONS_DF.to_csv(tmp_path / "snapshot_piezometria.csv",
                           index=False, encoding="utf-8")

    def test_fallback_on_network_error(self, monkeypatch, tmp_path):
        self._snapshotted(monkeypatch, tmp_path)
        monkeypatch.setattr(get_snirh, "fetch_networks",
                            lambda client: NETWORKS_DF.copy())

        def down(client, uid):
            raise SnirhNetworkError("SNIRH down")

        monkeypatch.setattr(get_snirh, "fetch_stations", down)
        snirh = Snirh("piezometria")
        with pytest.warns(UserWarning, match="STALE"):
            df = snirh.stations()
        assert len(df) == 3

    def test_fallback_when_discovery_is_down_too(self, monkeypatch, tmp_path):
        self._snapshotted(monkeypatch, tmp_path)

        def down(client, *args):
            raise SnirhNetworkError("SNIRH down")

        monkeypatch.setattr(get_snirh, "fetch_networks", down)
        monkeypatch.setattr(get_snirh, "fetch_stations", down)
        snirh = Snirh("piezometria")
        with pytest.warns(UserWarning, match="STALE"):
            df = snirh.stations()
        assert len(df) == 3

    def test_no_snapshot_clear_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(snapshots_module, "BUNDLED_DIR", tmp_path)

        def down(client, *args):
            raise SnirhNetworkError("SNIRH down")

        monkeypatch.setattr(get_snirh, "fetch_networks", down)
        monkeypatch.setattr(get_snirh, "fetch_stations", down)
        snirh = Snirh("piezometria")
        with pytest.warns(UserWarning, match="STALE"):
            with pytest.raises(SnirhError, match="No bundled snapshot"):
                snirh.stations()

    def test_uid_binding_without_slug_reraises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(snapshots_module, "BUNDLED_DIR", tmp_path)

        def down(client, *args):
            raise SnirhNetworkError("SNIRH down")

        monkeypatch.setattr(get_snirh, "fetch_networks", down)
        monkeypatch.setattr(get_snirh, "fetch_stations", down)
        snirh = Snirh(999999)  # uid unknown to discovery -> slug unknown
        with pytest.raises(SnirhNetworkError):
            snirh.stations()

    def test_parsing_errors_do_not_fall_back(self, monkeypatch, tmp_path):
        self._snapshotted(monkeypatch, tmp_path)
        monkeypatch.setattr(get_snirh, "fetch_networks",
                            lambda client: NETWORKS_DF.copy())

        def broken(client, uid):
            raise get_snirh.SnirhParsingError("layout changed")

        monkeypatch.setattr(get_snirh, "fetch_stations", broken)
        snirh = Snirh("piezometria")
        with pytest.raises(get_snirh.SnirhParsingError):
            snirh.stations()


class TestParametersInput:
    @pytest.fixture
    def capture(self, live_ok, monkeypatch):
        seen = {}

        def fake(client, network_uid, station_uids):
            seen["uids"] = list(station_uids)
            return pd.DataFrame({"uid": ["2277"], "name": ["Profundidade Nível Água"]})

        monkeypatch.setattr(get_snirh, "fetch_parameters", fake)
        return seen

    def test_uid_str(self, capture):
        Snirh("piezometria").parameters("42")
        assert capture["uids"] == ["42"]

    def test_uid_int(self, capture):
        Snirh("piezometria").parameters(42)
        assert capture["uids"] == ["42"]

    def test_dataframe_rows(self, capture):
        Snirh("piezometria").parameters(STATIONS_DF.head(2))
        assert capture["uids"] == ["1", "2"]

    def test_dataframe_row(self, capture):
        Snirh("piezometria").parameters(STATIONS_DF.iloc[0])
        assert capture["uids"] == ["1"]

    def test_uid_column(self, capture):
        Snirh("piezometria").parameters(STATIONS_DF["uid"])
        assert capture["uids"] == ["1", "2", "3"]


class TestTimeseriesFacade:
    def test_ddmmyyyy_rejected(self, live_ok):
        snirh = Snirh("piezometria")
        with pytest.raises(ValueError, match="ISO"):
            snirh.timeseries(["1"], Parameters.GWL_DEPTH,
                             "01/01/2023", "2023-06-30")


class TestExports:
    def test_public_api(self):
        assert hasattr(get_snirh, "__version__")
        for name in get_snirh.__all__:
            assert hasattr(get_snirh, name)

    def test_old_api_gone(self):
        assert not hasattr(get_snirh, "StationFetcher")
        assert not hasattr(get_snirh, "DataFetcher")

    def test_parameters_enum_kept(self):
        assert Parameters.GWL_DEPTH.value == "2277"
        assert Parameters.PIEZOMETRIC_LEVEL.value == "100290981"
        assert Parameters.PRECIPITATION_DAILY.value == "413026594"
