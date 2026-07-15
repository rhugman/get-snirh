import pytest

from get_snirh.constants import SnirhUrls
from get_snirh.exceptions import SnirhDiscoveryError
from get_snirh.parameters import fetch_parameters, parse_parameters_html
from _fakes import FakeClient

# Real shape of the ajax response (probed 2026-07-15)
AJAX_HTML = """\t<div id="select_parametros">
\t<select id="f_estacoes_parametros[]" name="f_estacoes_parametros[]" size="8" multiple="multiple" class="form_select">
\t\t\t<option value="100290981">&#9632; N&iacute;vel piezom&eacute;trico</option>
\t\t\t<option value="2277">&#9632; Profundidade N&iacute;vel &Aacute;gua</option>
\t</select>
</div>"""


class TestParseParametersHtml:
    def test_columns_and_rows(self):
        df = parse_parameters_html(AJAX_HTML)
        assert list(df.columns) == ["uid", "name"]
        assert len(df) == 2

    def test_names_unescaped_and_cleaned(self):
        df = parse_parameters_html(AJAX_HTML)
        names = list(df["name"])
        assert names == ["Nível piezométrico", "Profundidade Nível Água"]
        assert not any("■" in n or "&" in n for n in names)

    def test_uids(self):
        df = parse_parameters_html(AJAX_HTML)
        assert list(df["uid"]) == ["100290981", "2277"]

    def test_empty_html(self):
        assert parse_parameters_html("<div></div>").empty


class TestFetchParameters:
    def test_single_uid(self):
        client = FakeClient({SnirhUrls.STATION_PARAMETERS: AJAX_HTML.encode("utf-8")})
        df = fetch_parameters(client, "100290946", "2028876")
        assert len(df) == 2
        assert client.ensured == ["100290946"]
        call = client.calls[0]
        assert call["session_scoped"] is True
        assert call["params"] == {"sites": "2028876"}

    def test_multiple_uids_comma_joined(self):
        client = FakeClient({SnirhUrls.STATION_PARAMETERS: AJAX_HTML.encode("utf-8")})
        fetch_parameters(client, "100290946", ["1", 2, "3"])
        assert client.calls[0]["params"] == {"sites": "1,2,3"}

    def test_int_uid(self):
        client = FakeClient({SnirhUrls.STATION_PARAMETERS: AJAX_HTML.encode("utf-8")})
        df = fetch_parameters(client, "100290946", 2028876)
        assert client.calls[0]["params"] == {"sites": "2028876"}
        assert not df.empty

    def test_empty_response_raises_discovery_error(self):
        client = FakeClient({SnirhUrls.STATION_PARAMETERS: b""})
        with pytest.raises(SnirhDiscoveryError):
            fetch_parameters(client, "100290946", "2028876")

    def test_no_uids_rejected(self):
        client = FakeClient({})
        with pytest.raises(ValueError):
            fetch_parameters(client, "100290946", [])
