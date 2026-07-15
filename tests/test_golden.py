"""Golden-file tests: replay real SNIRH responses through the real parsers.

The fixtures under tests/golden/ are raw bytes captured live from SNIRH
on 2026-07-15 (see tests/golden/MANIFEST.txt for the URL, capture date
and truncation notes per file). These tests run fully offline: goldens
are local files, decoded per get_snirh.constants.SnirhEncodings, and
fed to the same parsing code the live client uses.

Expected row counts and spot values are the ones recorded in
MANIFEST.txt at capture time.
"""

from pathlib import Path

import pandas as pd
import pytest

from get_snirh.constants import Parameters, SnirhEncodings, SnirhUrls
from get_snirh.networks import NETWORK_COLUMNS, fetch_networks, parse_networks_html
from get_snirh.parameters import (
    PARAMETER_COLUMNS,
    fetch_parameters,
    parse_parameters_html,
)
from get_snirh.stations import (
    UID_COLUMNS,
    fetch_station_uids,
    parse_markers_xml,
    parse_metadata_csv,
    parse_station_select_html,
)
from get_snirh.timeseries import TIMESERIES_COLUMNS, fetch_timeseries, parse_timeseries_csv
from _fakes import FakeClient

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

#: UTF-8-decoded-as-latin1 pairs (Ã©=é, Ã§=ç, ...), stray marker chars,
#: unescaped entities and the replacement char. Bare 'Ã' is legitimate
#: uppercase Portuguese (SÃO, DÃO).
MOJIBAKE = ("Ã©", "Ã¡", "Ã­", "Ã³", "Ãº", "Ã§", "Ã£", "Ãµ", "Ã¢", "Ãª",
            "Ã´", "â–", "■", "&#", "&amp;", "�")


def golden_bytes(name: str) -> bytes:
    return (GOLDEN_DIR / name).read_bytes()


def golden_text(name: str, encoding: str) -> str:
    return golden_bytes(name).decode(encoding)


def assert_no_mojibake(df: pd.DataFrame):
    """Every string cell in the frame must be free of mojibake markers."""
    for column in df.columns:
        for value in df[column].dropna():
            if not isinstance(value, str):
                continue
            for bad in MOJIBAKE:
                assert bad not in value, (
                    f"mojibake {bad!r} in column {column!r}: {value!r}"
                )


# -- home page -> networks -----------------------------------------------------

@pytest.fixture(scope="module")
def networks():
    return parse_networks_html(golden_text("home_page.html", SnirhEncodings.HOME))


class TestGoldenNetworks:
    def test_columns(self, networks):
        assert list(networks.columns) == NETWORK_COLUMNS

    def test_row_count_matches_manifest(self, networks):
        assert len(networks) == 15

    def test_uids_unique_and_nonempty(self, networks):
        assert networks["uid"].is_unique
        assert (networks["uid"].str.len() > 0).all()

    def test_piezometria_star_stripped(self, networks):
        row = networks.set_index("uid").loc["100290946"]
        assert row["name"] == "Piezometria"
        assert row["slug"] == "piezometria"

    def test_accented_names_and_slugs(self, networks):
        by_uid = networks.set_index("uid")
        assert by_uid.loc["111307207", "name"] == "Hidrométrica Açores"
        assert by_uid.loc["111307207", "slug"] == "hidrometrica_acores"
        assert by_uid.loc["100406000", "name"] == "Águas Balneares"
        assert by_uid.loc["100406000", "slug"] == "aguas_balneares"
        assert by_uid.loc["100290952", "slug"] == "qualidade_aguas_subterraneas"

    def test_known_network_uids_present(self, networks):
        uids = set(networks["uid"])
        assert {"100290946", "920123705", "458192970", "100406019"} <= uids

    def test_no_mojibake(self, networks):
        assert_no_mojibake(networks)

    def test_fetch_networks_via_fake_client(self, networks):
        client = FakeClient({SnirhUrls.HOME: golden_bytes("home_page.html")})
        df = fetch_networks(client)
        pd.testing.assert_frame_equal(df, networks)
        assert client.calls == [
            {"url": SnirhUrls.HOME, "params": None, "session_scoped": False}
        ]


# -- home page after network selection -> station select fallback ---------------

@pytest.fixture(scope="module")
def eta_select():
    return parse_station_select_html(
        golden_text("home_stations_selected.html", SnirhEncodings.HOME)
    )


class TestGoldenStationSelect:
    def test_columns(self, eta_select):
        assert list(eta_select.columns) == UID_COLUMNS

    def test_row_count_matches_manifest(self, eta_select):
        assert len(eta_select) == 13

    def test_spot_row_eta_13(self, eta_select):
        row = eta_select.set_index("uid").loc["596197002"]
        assert row["code"] == "ETA_13"
        assert row["name"] == "ALBUFEIRA DA AGUIEIRA - PINHEIRO DO ÁZERE (ETA)"

    def test_coordinates_all_nan(self, eta_select):
        assert eta_select["latitude"].isna().all()
        assert eta_select["longitude"].isna().all()

    def test_no_mojibake(self, eta_select):
        assert_no_mojibake(eta_select)

    def test_unselected_home_page_has_empty_station_select(self):
        # Before a network is selected, the f_estacoes[] select exists but
        # carries no options: the golden home page must parse to 0 stations.
        df = parse_station_select_html(
            golden_text("home_page.html", SnirhEncodings.HOME)
        )
        assert list(df.columns) == UID_COLUMNS
        assert df.empty

    def test_fetch_station_uids_fallback_path(self, eta_select):
        # ETA stations have no coordinates, so the live markers endpoint
        # returns literally '<markers></markers>' (verified live in the
        # 2026-07-15 network matrix) and fetch_station_uids falls back to
        # the home-page station select.
        client = FakeClient({
            SnirhUrls.STATION_MARKERS_XML: b"<markers></markers>",
            SnirhUrls.HOME: golden_bytes("home_stations_selected.html"),
        })
        df = fetch_station_uids(client, "458192970")
        pd.testing.assert_frame_equal(df, eta_select)
        assert client.ensured == ["458192970"]
        assert [c["url"] for c in client.calls] == [
            SnirhUrls.STATION_MARKERS_XML, SnirhUrls.HOME,
        ]


# -- markers XML -> station uid mapping -----------------------------------------

@pytest.fixture(scope="module")
def markers():
    return parse_markers_xml(
        golden_text("markers_piezometria.xml", SnirhEncodings.STATION_MARKERS_XML)
    )


class TestGoldenMarkers:
    def test_columns(self, markers):
        assert list(markers.columns) == UID_COLUMNS

    def test_row_count_matches_manifest(self, markers):
        assert len(markers) == 50

    def test_uids_unique_and_nonempty(self, markers):
        assert markers["uid"].is_unique
        assert (markers["uid"].str.len() > 0).all()

    def test_coordinates_numeric(self, markers):
        assert markers["latitude"].dtype == "float64"
        assert markers["longitude"].dtype == "float64"
        assert markers["latitude"].notna().all()
        assert markers["longitude"].notna().all()
        # Piezometria is mainland Portugal: sane WGS84 bounds.
        assert markers["latitude"].between(36.5, 42.5).all()
        assert markers["longitude"].between(-10.0, -6.0).all()

    def test_spot_row_3n1(self, markers):
        row = markers.iloc[0]
        assert row["uid"] == "2028876"
        assert row["code"] == "3/N1"
        assert row["name"] == "3/N1"
        assert row["latitude"] == pytest.approx(42.0474)
        assert row["longitude"] == pytest.approx(-8.38867)

    def test_no_mojibake(self, markers):
        assert_no_mojibake(markers)

    def test_fetch_station_uids_via_fake_client(self, markers):
        client = FakeClient({
            SnirhUrls.STATION_MARKERS_XML: golden_bytes("markers_piezometria.xml"),
        })
        df = fetch_station_uids(client, "100290946")
        pd.testing.assert_frame_equal(df, markers)
        assert client.ensured == ["100290946"]
        assert client.calls[0]["session_scoped"] is True


# -- metadata CSVs ---------------------------------------------------------------

@pytest.fixture(scope="module")
def piezometria_metadata():
    return parse_metadata_csv(
        golden_text("metadata_piezometria.csv", SnirhEncodings.STATION_LIST_CSV)
    )


class TestGoldenMetadataPiezometria:
    def test_canonical_columns(self, piezometria_metadata):
        assert list(piezometria_metadata.columns) == [
            "code", "name", "district", "municipality", "parish", "basin",
            "altitude", "coord_x", "coord_y", "aquifer_system", "status",
        ]

    def test_row_count_matches_manifest(self, piezometria_metadata):
        assert len(piezometria_metadata) == 50

    def test_numeric_dtypes(self, piezometria_metadata):
        for column in ("altitude", "coord_x", "coord_y"):
            assert piezometria_metadata[column].dtype == "float64", column

    def test_spot_row_3n1(self, piezometria_metadata):
        df = piezometria_metadata
        row = df[df["code"] == "3/N1"].iloc[0]
        assert row["name"] == "A21"
        assert row["district"] == "VIANA DO CASTELO"
        assert row["municipality"] == "MONÇÃO"
        assert row["parish"] == "SEGUDE"
        assert row["basin"] == "MINHO/ÂNCORA"
        assert row["altitude"] == pytest.approx(40.0)
        assert row["coord_x"] == pytest.approx(178843.0)
        assert row["coord_y"] == pytest.approx(564242.0)
        assert row["aquifer_system"] == "A0 - MACIÇO ANTIGO INDIFERENCIADO"

    def test_accents_decoded(self, piezometria_metadata):
        # Real ISO-8859-1 accented bytes must decode to proper Portuguese.
        assert (piezometria_metadata["district"] == "SETÚBAL").any()

    def test_footer_not_parsed_as_row(self, piezometria_metadata):
        assert not piezometria_metadata["code"].str.contains("Dados obtidos").any()

    def test_no_mojibake(self, piezometria_metadata):
        assert_no_mojibake(piezometria_metadata)


@pytest.fixture(scope="module")
def madeira_metadata():
    return parse_metadata_csv(
        golden_text("metadata_hidrometrica_madeira.csv",
                    SnirhEncodings.STATION_LIST_CSV)
    )


class TestGoldenMetadataMadeira:
    """Hidrométrica Madeira has an odd schema: LATITUDE (ºN)/LONGITUDE (ºW)
    instead of grid coordinates, and no district/municipality/parish."""

    def test_odd_schema_columns(self, madeira_metadata):
        assert list(madeira_metadata.columns) == [
            "code", "name", "status", "basin", "latitude_n", "longitude_w",
        ]

    def test_no_district_column(self, madeira_metadata):
        assert "district" not in madeira_metadata.columns
        assert "coord_x" not in madeira_metadata.columns

    def test_row_count_matches_manifest(self, madeira_metadata):
        assert len(madeira_metadata) == 9

    def test_spot_row_h09(self, madeira_metadata):
        row = madeira_metadata[madeira_metadata["code"] == "H09"].iloc[0]
        assert row["name"] == "LEVADA DO NORTE"
        assert row["status"] == "ATIVA"
        assert row["basin"] == "RIBEIRAS DA  MADEIRA"

    def test_coordinates_are_placeholder_dashes(self, madeira_metadata):
        assert (madeira_metadata["latitude_n"] == "-").all()
        assert (madeira_metadata["longitude_w"] == "-").all()

    def test_no_mojibake(self, madeira_metadata):
        assert_no_mojibake(madeira_metadata)


# -- parameter discovery ajax ----------------------------------------------------

@pytest.fixture(scope="module")
def station_parameters():
    return parse_parameters_html(
        golden_text("parameters_station_2028876.html",
                    SnirhEncodings.STATION_PARAMETERS)
    )


class TestGoldenParameters:
    def test_columns(self, station_parameters):
        assert list(station_parameters.columns) == PARAMETER_COLUMNS

    def test_row_count_matches_manifest(self, station_parameters):
        assert len(station_parameters) == 2

    def test_exact_parameters(self, station_parameters):
        assert station_parameters.to_dict("records") == [
            {"uid": "100290981", "name": "Nível piezométrico"},
            {"uid": "2277", "name": "Profundidade Nível Água"},
        ]

    def test_entities_unescaped(self, station_parameters):
        # Raw payload carries &#9632; and &iacute;-style entities; parsed
        # names must be clean of both markers and entity remnants.
        assert_no_mojibake(station_parameters)
        assert not station_parameters["name"].str.contains("&").any()

    def test_fetch_parameters_via_fake_client(self, station_parameters):
        client = FakeClient({
            SnirhUrls.STATION_PARAMETERS:
                golden_bytes("parameters_station_2028876.html"),
        })
        df = fetch_parameters(client, "100290946", "2028876")
        pd.testing.assert_frame_equal(df, station_parameters)
        assert client.ensured == ["100290946"]
        assert client.calls[0]["params"] == {"sites": "2028876"}
        assert client.calls[0]["session_scoped"] is True


# -- timeseries CSVs ---------------------------------------------------------------

class TestGoldenTimeseries:
    def test_columns_and_row_count(self):
        df = parse_timeseries_csv(
            golden_text("timeseries_3n1_gwl.csv", SnirhEncodings.DATA_CSV)
        )
        assert list(df.columns) == ["timestamp", "value"]
        assert len(df) == 12  # monthly GWL depth readings, calendar 2023

    def test_dtypes(self):
        df = parse_timeseries_csv(
            golden_text("timeseries_3n1_gwl.csv", SnirhEncodings.DATA_CSV)
        )
        assert str(df["timestamp"].dtype).startswith("datetime64")
        assert df["value"].dtype == "float64"
        assert df["value"].notna().all()

    def test_spot_values(self):
        df = parse_timeseries_csv(
            golden_text("timeseries_3n1_gwl.csv", SnirhEncodings.DATA_CSV)
        )
        assert df["timestamp"].iloc[0] == pd.Timestamp("2023-01-30 10:00")
        assert df["value"].iloc[0] == pytest.approx(3.35)
        assert df["timestamp"].iloc[-1] == pd.Timestamp("2023-12-28 10:45")
        assert df["value"].iloc[-1] == pytest.approx(3.2)

    def test_all_timestamps_within_requested_window(self):
        df = parse_timeseries_csv(
            golden_text("timeseries_3n1_gwl.csv", SnirhEncodings.DATA_CSV)
        )
        assert (df["timestamp"].dt.year == 2023).all()
        assert df["timestamp"].is_monotonic_increasing

    def test_fetch_timeseries_via_fake_client(self):
        client = FakeClient({
            SnirhUrls.DATA_CSV: golden_bytes("timeseries_3n1_gwl.csv"),
        })
        df = fetch_timeseries(client, {"2028876": "3/N1"}, Parameters.GWL_DEPTH,
                              start="2023-01-01", end="2023-12-31")
        assert list(df.columns) == TIMESERIES_COLUMNS
        assert len(df) == 12
        assert (df["code"] == "3/N1").all()
        assert (df["uid"] == "2028876").all()
        assert (df["parameter"] == "GWL_DEPTH").all()
        assert df["value"].dtype == "float64"
        assert client.calls[0]["params"] == {
            "sites": "2028876", "pars": "2277", "tmin": "01/01/2023",
            "tmax": "31/12/2023", "formato": "csv",
        }

    def test_empty_combo_parses_to_zero_rows(self):
        # Hidrométrica 19B/01H x 'Nível instantâneo máximo anual',
        # 2015-2024: SNIRH returns header + FLAG legend + footer with no
        # data rows; the parser must drop the legend lines cleanly.
        df = parse_timeseries_csv(
            golden_text("timeseries_empty.csv", SnirhEncodings.DATA_CSV)
        )
        assert list(df.columns) == ["timestamp", "value"]
        assert df.empty

    def test_fetch_timeseries_empty_combo_returns_empty_frame(self):
        client = FakeClient({
            SnirhUrls.DATA_CSV: golden_bytes("timeseries_empty.csv"),
        })
        df = fetch_timeseries(client, {"1627743378": "19B/01H"}, "436115734",
                              start="2015-01-01", end="2024-12-31")
        assert list(df.columns) == TIMESERIES_COLUMNS
        assert df.empty


# -- fixture hygiene -----------------------------------------------------------------

class TestGoldenFixtureFiles:
    """The golden files themselves must stay present and structurally real."""

    EXPECTED_FILES = {
        "home_page.html",
        "home_stations_selected.html",
        "markers_piezometria.xml",
        "metadata_piezometria.csv",
        "metadata_hidrometrica_madeira.csv",
        "parameters_station_2028876.html",
        "timeseries_3n1_gwl.csv",
        "timeseries_empty.csv",
        "MANIFEST.txt",
    }

    def test_all_fixtures_present(self):
        assert {p.name for p in GOLDEN_DIR.iterdir()} == self.EXPECTED_FILES

    def test_manifest_mentions_every_fixture(self):
        manifest = (GOLDEN_DIR / "MANIFEST.txt").read_text(encoding="utf-8")
        for name in self.EXPECTED_FILES - {"MANIFEST.txt"}:
            assert f"file: {name}" in manifest

    def test_home_page_carries_network_select(self):
        assert b"f_redes_todas" in golden_bytes("home_page.html")

    def test_selected_home_page_carries_station_select(self):
        assert b"f_estacoes" in golden_bytes("home_stations_selected.html")

    def test_truncated_markers_xml_still_well_formed(self):
        text = golden_text("markers_piezometria.xml",
                           SnirhEncodings.STATION_MARKERS_XML)
        assert text.startswith("<markers>")
        assert text.rstrip().endswith("</markers>")

    def test_truncated_metadata_keeps_header_and_footer(self):
        text = golden_text("metadata_piezometria.csv",
                           SnirhEncodings.STATION_LIST_CSV)
        assert "CÓDIGO" in text.splitlines()[4]
        assert "Dados obtidos" in text.splitlines()[-1]
