import pytest

from get_snirh.exceptions import SnirhParsingError
from get_snirh.networks import parse_networks_html

HOME_HTML = """
<html><body><form>
<select name="f_redes_todas[]" size="10" class="form_select">
  <option value="458192970">ETA</option>
  <option value="920123705">Hidrométrica</option>
  <option value="111307207">Hidrométrica Açores</option>
  <option value="100290946">* Piezometria</option>
  <option value="123456789">Águas Balneares</option>
</select>
<select name="f_redes_seleccao[]"></select>
</form></body></html>
"""


class TestParseNetworksHtml:
    def test_columns(self):
        df = parse_networks_html(HOME_HTML)
        assert list(df.columns) == ["uid", "name", "slug"]

    def test_all_options_parsed(self):
        df = parse_networks_html(HOME_HTML)
        assert len(df) == 5
        assert set(df["uid"]) == {
            "458192970", "920123705", "111307207", "100290946", "123456789",
        }

    def test_name_cleaned_of_star(self):
        df = parse_networks_html(HOME_HTML)
        row = df[df["uid"] == "100290946"].iloc[0]
        assert row["name"] == "Piezometria"
        assert row["slug"] == "piezometria"

    def test_accented_slugs(self):
        df = parse_networks_html(HOME_HTML)
        assert df.set_index("uid").loc["111307207", "slug"] == "hidrometrica_acores"
        assert df.set_index("uid").loc["123456789", "slug"] == "aguas_balneares"

    def test_accented_names_preserved(self):
        df = parse_networks_html(HOME_HTML)
        assert df.set_index("uid").loc["111307207", "name"] == "Hidrométrica Açores"

    def test_missing_select_raises(self):
        with pytest.raises(SnirhParsingError):
            parse_networks_html("<html><body>nothing here</body></html>")
