import pandas as pd
import pytest

from get_snirh.constants import SnirhUrls
from get_snirh.exceptions import SnirhDiscoveryError, SnirhParsingError
from get_snirh.stations import (
    canonical_column,
    fallback_column,
    fetch_station_uids,
    fetch_stations,
    parse_markers_xml,
    parse_metadata_csv,
    parse_station_select_html,
)
from _fakes import FakeClient

MARKERS_XML = """<markers>
<marker site="2028876" cover="100290946" redenome="Piezometria"
        lat="42.0474" lng="-8.38867"
        estacao3="&amp;#9632; 3/N1" estacao="&#9632; 3/N1" activa="0"/>
<marker site="920685966" lat="37.1" lng="-8.5"
        estacao="&#9632; Po&ccedil;o S&atilde;o Br&aacute;s (612/45)"/>
<marker site="555" lat="" lng="notanumber" estacao="&#9632; 700/1"/>
</markers>"""

METADATA_CSV = "\n".join(
    [
        "SNIRH - SISTEMA NACIONAL DE INFORMAÇÃO DE RECURSOS HÍDRICOS",
        "",
        "REDE:,Piezometria",
        "",
        "CÓDIGO,NOME,DISTRITO,CONCELHO,FREGUESIA,BACIA,ALTITUDE (M),COORD_X (M),COORD_Y (M),SISTEMA AQUÍFERO,ESTADO",
        "3/N1,Poço São Brás,FARO,OLHÃO,QUELFES,RIBEIRAS DO ALGARVE,10,25000.5,12000.1,M12 - CAMPINA DE FARO,ATIVA",
        "420/8,01,SETÚBAL,MONTIJO,CANHA,TEJO,44,152403.4,204253.4,T3 - BACIA DO TEJO-SADO / MARGEM ESQUERDA,",
        "",
        "Dados obtidos através do site http://snirh.apambiente.pt em 15/07/2026 11:42",
    ]
)


class TestParseMarkersXml:
    def test_columns(self):
        df = parse_markers_xml(MARKERS_XML)
        assert list(df.columns) == ["uid", "code", "name", "latitude", "longitude"]
        assert len(df) == 3

    def test_code_only_label(self):
        row = parse_markers_xml(MARKERS_XML).iloc[0]
        assert row["uid"] == "2028876"
        assert row["code"] == "3/N1"
        assert row["name"] == "3/N1"
        assert row["latitude"] == pytest.approx(42.0474)
        assert row["longitude"] == pytest.approx(-8.38867)

    def test_name_code_label_with_accents(self):
        row = parse_markers_xml(MARKERS_XML).iloc[1]
        assert row["code"] == "612/45"
        assert row["name"] == "Poço São Brás"

    def test_marker_char_stripped(self):
        df = parse_markers_xml(MARKERS_XML)
        assert not df["code"].str.contains("■").any()
        assert not df["name"].str.contains("&#").any()

    def test_unparseable_coords_are_nan(self):
        row = parse_markers_xml(MARKERS_XML).iloc[2]
        assert pd.isna(row["latitude"])
        assert pd.isna(row["longitude"])

    def test_empty_document(self):
        df = parse_markers_xml("<markers></markers>")
        assert df.empty
        assert list(df.columns) == ["uid", "code", "name", "latitude", "longitude"]


SELECT_HTML = """<html><body>
<select name="f_estacoes[]" multiple>
<option value="">-- todas --</option>
<option value="458000111">&#9632; ALBUFEIRA DA AGUIEIRA - PINHEIRO DO &Aacute;ZERE (ETA_13)</option>
<option value="458000222">&#9632; H09</option>
</select>
</body></html>"""


class TestParseStationSelectHtml:
    def test_columns_and_values(self):
        df = parse_station_select_html(SELECT_HTML)
        assert list(df.columns) == ["uid", "code", "name", "latitude", "longitude"]
        assert len(df) == 2  # placeholder option (empty value) skipped
        assert df["uid"].tolist() == ["458000111", "458000222"]
        assert df["code"].tolist() == ["ETA_13", "H09"]
        assert df["name"].iloc[0] == "ALBUFEIRA DA AGUIEIRA - PINHEIRO DO ÁZERE"
        assert df["latitude"].isna().all()

    def test_no_select_element(self):
        df = parse_station_select_html("<html><body>nothing here</body></html>")
        assert df.empty
        assert list(df.columns) == ["uid", "code", "name", "latitude", "longitude"]


class TestFetchStationUids:
    def test_session_scoped_and_network_selected(self):
        client = FakeClient({SnirhUrls.STATION_MARKERS_XML: MARKERS_XML.encode("utf-8")})
        df = fetch_station_uids(client, "100290946")
        assert client.ensured == ["100290946"]
        assert client.calls[0]["session_scoped"] is True
        assert len(df) == 3

    def test_falls_back_to_home_select_when_markers_empty(self):
        client = FakeClient({
            SnirhUrls.STATION_MARKERS_XML: b"<markers></markers>",
            SnirhUrls.HOME: SELECT_HTML.encode("ISO-8859-1"),
        })
        df = fetch_station_uids(client, "458192970")
        assert df["code"].tolist() == ["ETA_13", "H09"]
        assert df["latitude"].isna().all()
        # fallback request goes through the network session too
        assert client.calls[1]["url"] == SnirhUrls.HOME
        assert client.calls[1]["session_scoped"] is True

    def test_raises_when_both_sources_empty(self):
        client = FakeClient({
            SnirhUrls.STATION_MARKERS_XML: b"<markers></markers>",
            SnirhUrls.HOME: b"<html><body>no select</body></html>",
        })
        with pytest.raises(SnirhDiscoveryError, match="Neither the map markers"):
            fetch_station_uids(client, "458192970")


class TestColumnMapping:
    @pytest.mark.parametrize(
        "header,expected",
        [
            ("CÓDIGO", "code"),
            ("NOME", "name"),
            ("DISTRITO", "district"),
            ("CONCELHO", "municipality"),
            ("FREGUESIA", "parish"),
            ("BACIA", "basin"),
            ("ALTITUDE (M)", "altitude"),
            ("COORD_X (M)", "coord_x"),
            ("COORD_Y (M)", "coord_y"),
            ("SISTEMA AQUÍFERO", "aquifer_system"),
            ("ESTADO", "status"),
        ],
    )
    def test_known_headers(self, header, expected):
        assert canonical_column(header) == expected

    def test_unknown_header_fallback(self):
        assert fallback_column("ENTIDADE RESPONSÁVEL (AUTOMÁTICA)") == (
            "entidade_responsavel_automatica"
        )
        assert canonical_column("TELEMETRIA") == "telemetria"
        assert canonical_column("ÍNDICE QUALIDADE*") == "indice_qualidade"


class TestParseMetadataCsv:
    def test_canonical_columns(self):
        df = parse_metadata_csv(METADATA_CSV)
        assert list(df.columns) == [
            "code", "name", "district", "municipality", "parish", "basin",
            "altitude", "coord_x", "coord_y", "aquifer_system", "status",
        ]

    def test_footer_dropped(self):
        df = parse_metadata_csv(METADATA_CSV)
        assert len(df) == 2
        assert not df["code"].str.contains("Dados obtidos").any()

    def test_values_stay_portuguese(self):
        df = parse_metadata_csv(METADATA_CSV)
        assert df.iloc[0]["name"] == "Poço São Brás"
        assert df.iloc[1]["district"] == "SETÚBAL"

    def test_codes_are_strings(self):
        df = parse_metadata_csv(METADATA_CSV)
        # NOME '01' must survive as a string, codes untouched
        assert df.iloc[1]["name"] == "01"
        assert df.iloc[1]["code"] == "420/8"

    def test_numeric_coords(self):
        df = parse_metadata_csv(METADATA_CSV)
        assert df.iloc[0]["coord_x"] == pytest.approx(25000.5)
        assert df.iloc[0]["altitude"] == pytest.approx(10)

    def test_missing_header_raises(self):
        with pytest.raises(SnirhParsingError):
            parse_metadata_csv("just\nsome\nrandom,text")


class TestFetchStationsMerged:
    def _client(self):
        return FakeClient(
            {
                SnirhUrls.STATION_MARKERS_XML: MARKERS_XML.encode("utf-8"),
                SnirhUrls.STATION_LIST_CSV: METADATA_CSV.encode("ISO-8859-1"),
            }
        )

    def test_inner_merge_on_code(self):
        df = fetch_stations(self._client(), "100290946")
        # 3/N1 and 420/8 in metadata; 3/N1, 612/45, 700/1 in markers -> only 3/N1
        assert len(df) == 1
        assert df.iloc[0]["code"] == "3/N1"
        assert df.iloc[0]["uid"] == "2028876"

    def test_uid_code_first_and_both_coordinate_sets(self):
        df = fetch_stations(self._client(), "100290946")
        assert list(df.columns[:3]) == ["uid", "code", "name"]
        for column in ("latitude", "longitude", "coord_x", "coord_y"):
            assert column in df.columns

    def test_metadata_name_preferred(self):
        df = fetch_stations(self._client(), "100290946")
        assert df.iloc[0]["name"] == "Poço São Brás"
