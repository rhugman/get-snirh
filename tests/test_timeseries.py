import pandas as pd
import pytest

from get_snirh.constants import Parameters, SnirhUrls
from get_snirh.timeseries import (
    TIMESERIES_COLUMNS,
    default_max_workers,
    fetch_timeseries,
    parse_timeseries_csv,
    station_map,
)
from _fakes import FakeClient

# Real shape of dados_csv.php output (probed 2026-07-15)
DATA_CSV = "\n".join(
    [
        "SNIRH - SISTEMA NACIONAL DE INFORMAÇÃO DE RECURSOS HÍDRICOS",
        "",
        "DATA,",
        ",Profundidade Nível Água (m),FLAG,",
        "30/01/2023 10:00,3.35,,",
        "27/02/2023 10:15,3.2,,",
        "",
        "",
        "Dados obtidos através do site http://snirh.apambiente.pt em 15/07/2026 11:42",
    ]
)

EMPTY_CSV = "\n".join(
    [
        "SNIRH - SISTEMA NACIONAL DE INFORMAÇÃO DE RECURSOS HÍDRICOS",
        "",
        "DATA,",
        ",Profundidade Nível Água (m),FLAG,",
        "",
        "Dados obtidos através do site http://snirh.apambiente.pt em 15/07/2026 11:42",
    ]
)


class TestParseTimeseriesCsv:
    def test_rows_and_values(self):
        df = parse_timeseries_csv(DATA_CSV)
        assert len(df) == 2
        assert df["value"].tolist() == [3.35, 3.2]

    def test_timestamps_parsed_dayfirst(self):
        df = parse_timeseries_csv(DATA_CSV)
        assert df["timestamp"].iloc[0] == pd.Timestamp(2023, 1, 30, 10, 0)
        assert str(df["timestamp"].dtype).startswith("datetime64")

    def test_footer_not_parsed_as_data(self):
        df = parse_timeseries_csv(DATA_CSV)
        assert len(df) == 2

    def test_empty_data(self):
        df = parse_timeseries_csv(EMPTY_CSV)
        assert df.empty


class TestDefaultMaxWorkers:
    @pytest.mark.parametrize("n,expected", [(0, 1), (1, 1), (5, 5), (10, 10), (50, 10)])
    def test_cap(self, n, expected):
        assert default_max_workers(n) == expected


class TestStationMap:
    def test_dataframe_with_uid_and_code(self):
        df = pd.DataFrame({"uid": ["1", "2"], "code": ["A", "B"]})
        assert station_map(df) == {"1": "A", "2": "B"}

    def test_dataframe_uid_only(self):
        df = pd.DataFrame({"uid": [1, 2]})
        assert station_map(df) == {"1": "1", "2": "2"}

    def test_dataframe_without_uid_rejected(self):
        with pytest.raises(ValueError, match="uid"):
            station_map(pd.DataFrame({"code": ["A"]}))

    def test_list_of_uids(self):
        assert station_map(["1", 2]) == {"1": "1", "2": "2"}

    def test_dict(self):
        assert station_map({1: "A"}) == {"1": "A"}

    def test_single_uid(self):
        assert station_map("42") == {"42": "42"}

    def test_bad_type(self):
        with pytest.raises(TypeError):
            station_map(3.14)


def _routed_client(payloads):
    """payloads: {station_uid: csv_text or Exception}"""

    def handler(params):
        payload = payloads[params["sites"]]
        if isinstance(payload, Exception):
            raise payload
        return payload.encode("ISO-8859-1")

    return FakeClient({SnirhUrls.DATA_CSV: handler})


class TestFetchTimeseries:
    def test_output_columns_and_sort(self):
        client = _routed_client({"1": DATA_CSV, "2": DATA_CSV})
        stations = pd.DataFrame({"uid": ["1", "2"], "code": ["Z9", "A1"]})
        df = fetch_timeseries(client, stations, Parameters.GWL_DEPTH,
                              "2023-01-01", "2023-06-30")
        assert list(df.columns) == TIMESERIES_COLUMNS
        assert len(df) == 4
        # sorted by code then timestamp
        assert df["code"].tolist() == ["A1", "A1", "Z9", "Z9"]
        assert df["timestamp"].iloc[0] < df["timestamp"].iloc[1]

    def test_parameter_enum_label(self):
        client = _routed_client({"1": DATA_CSV})
        df = fetch_timeseries(client, ["1"], Parameters.GWL_DEPTH,
                              "2023-01-01", "2023-06-30")
        assert set(df["parameter"]) == {"GWL_DEPTH"}

    def test_parameter_raw_uid_label(self):
        client = _routed_client({"1": DATA_CSV})
        df = fetch_timeseries(client, ["1"], "2277", "2023-01-01", "2023-06-30")
        assert set(df["parameter"]) == {"2277"}

    def test_dates_converted_to_snirh_format(self):
        client = _routed_client({"1": DATA_CSV})
        fetch_timeseries(client, ["1"], "2277", "2023-01-01", "2023-06-30")
        params = client.calls[0]["params"]
        assert params["tmin"] == "01/01/2023"
        assert params["tmax"] == "30/06/2023"

    def test_ddmmyyyy_rejected(self):
        client = _routed_client({})
        with pytest.raises(ValueError, match="ISO"):
            fetch_timeseries(client, ["1"], "2277", "01/01/2023", "2023-06-30")
        assert client.calls == []  # rejected before any request

    def test_value_is_float(self):
        client = _routed_client({"1": DATA_CSV})
        df = fetch_timeseries(client, ["1"], "2277", "2023-01-01", "2023-06-30")
        assert df["value"].dtype == "float64"

    def test_empty_result_has_columns(self):
        client = _routed_client({"1": EMPTY_CSV})
        df = fetch_timeseries(client, ["1"], "2277", "2023-01-01", "2023-06-30")
        assert df.empty
        assert list(df.columns) == TIMESERIES_COLUMNS
        assert str(df["timestamp"].dtype).startswith("datetime64")

    def test_one_station_failing_does_not_sink_others(self):
        client = _routed_client({"1": RuntimeError("boom"), "2": DATA_CSV})
        stations = {"1": "BAD", "2": "GOOD"}
        df = fetch_timeseries(client, stations, "2277", "2023-01-01", "2023-06-30")
        assert set(df["code"]) == {"GOOD"}
        assert len(df) == 2

    def test_stateless_requests(self):
        client = _routed_client({"1": DATA_CSV})
        fetch_timeseries(client, ["1"], "2277", "2023-01-01", "2023-06-30")
        assert client.calls[0]["session_scoped"] is False
        assert client.ensured == []  # no network session needed

    def test_bad_max_workers(self):
        client = _routed_client({"1": DATA_CSV})
        with pytest.raises(ValueError, match="max_workers"):
            fetch_timeseries(client, ["1"], "2277", "2023-01-01",
                             "2023-06-30", max_workers=0)

    def test_concurrent_fetch_many_stations(self):
        payloads = {str(i): DATA_CSV for i in range(25)}
        client = _routed_client(payloads)
        df = fetch_timeseries(client, list(payloads), "2277",
                              "2023-01-01", "2023-06-30")
        assert len(df) == 50
        assert len(client.calls) == 25
