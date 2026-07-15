import datetime

import pandas as pd
import pytest

from get_snirh.utils import slugify, strip_accents, to_snirh_date, unescape_html


class TestStripAccents:
    def test_portuguese_accents(self):
        assert strip_accents("Águas Balneares") == "Aguas Balneares"
        assert strip_accents("Hidrométrica Açores") == "Hidrometrica Acores"
        assert strip_accents("SISTEMA AQUÍFERO") == "SISTEMA AQUIFERO"

    def test_plain_ascii_unchanged(self):
        assert strip_accents("Piezometria") == "Piezometria"


class TestSlugify:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Hidrométrica Açores", "hidrometrica_acores"),
            ("* Piezometria", "piezometria"),
            ("Águas Balneares", "aguas_balneares"),
            ("Meteorológica Madeira", "meteorologica_madeira"),
            ("ETA", "eta"),
            ("  Qualidade -- superficial  ", "qualidade_superficial"),
        ],
    )
    def test_examples(self, name, expected):
        assert slugify(name) == expected


class TestUnescapeHtml:
    def test_single_escaped(self):
        assert unescape_html("&#9632; 3/N1") == "■ 3/N1"

    def test_double_escaped(self):
        assert unescape_html("&amp;#9632; 3/N1") == "■ 3/N1"

    def test_named_entities(self):
        assert unescape_html("N&iacute;vel piezom&eacute;trico") == "Nível piezométrico"

    def test_plain_text_unchanged(self):
        assert unescape_html("Profundidade Nível Água") == "Profundidade Nível Água"


class TestToSnirhDate:
    def test_iso_string(self):
        assert to_snirh_date("2023-01-01") == "01/01/2023"
        assert to_snirh_date("2023-06-30") == "30/06/2023"

    def test_iso_datetime_string(self):
        assert to_snirh_date("2023-06-30T12:00:00") == "30/06/2023"

    def test_date_object(self):
        assert to_snirh_date(datetime.date(2023, 1, 15)) == "15/01/2023"

    def test_datetime_object(self):
        assert to_snirh_date(datetime.datetime(2023, 12, 31, 23, 59)) == "31/12/2023"

    def test_ddmmyyyy_rejected_with_iso_hint(self):
        with pytest.raises(ValueError, match="ISO"):
            to_snirh_date("01/01/2023")

    def test_garbage_string_rejected(self):
        with pytest.raises(ValueError, match="ISO"):
            to_snirh_date("not-a-date")

    def test_wrong_type_rejected(self):
        with pytest.raises(TypeError):
            to_snirh_date(20230101)

    def test_z_suffix_iso_string(self):
        assert to_snirh_date("2023-01-01T00:00:00Z") == "01/01/2023"

    def test_pandas_nat_rejected_with_clear_message(self):
        with pytest.raises(TypeError, match="NaT"):
            to_snirh_date(pd.NaT)
