import pandas as pd
import pytest

from get_snirh.exceptions import SnirhError
from get_snirh.snapshots import load_snapshot, save_snapshot, snapshot_path


@pytest.fixture
def stations_df():
    return pd.DataFrame(
        {
            "uid": ["2028876", "920685966"],
            "code": ["3/N1", "612/45"],
            "name": ["Poço São Brás", "Furo Açoteias"],
            "basin": ["RIBEIRAS DO ALGARVE", "RIBEIRAS DO ALGARVE"],
            "latitude": [37.1, 37.2],
        }
    )


class TestSaveLoadRoundtrip:
    def test_roundtrip(self, tmp_path, stations_df):
        path = save_snapshot(tmp_path, "piezometria", stations_df)
        assert path == tmp_path / "snapshot_piezometria.csv"
        loaded = load_snapshot("piezometria", tmp_path)
        assert len(loaded) == 2
        assert list(loaded.columns) == list(stations_df.columns)

    def test_utf8_accents_roundtrip(self, tmp_path, stations_df):
        save_snapshot(tmp_path, "piezometria", stations_df)
        loaded = load_snapshot("piezometria", tmp_path)
        assert loaded.iloc[0]["name"] == "Poço São Brás"
        raw = (tmp_path / "snapshot_piezometria.csv").read_bytes()
        raw.decode("utf-8")  # must be valid UTF-8

    def test_uid_and_code_stay_strings(self, tmp_path):
        df = pd.DataFrame({"uid": ["0123"], "code": ["001"]})
        save_snapshot(tmp_path, "x", df)
        loaded = load_snapshot("x", tmp_path)
        assert loaded.iloc[0]["uid"] == "0123"
        assert loaded.iloc[0]["code"] == "001"

    def test_creates_directory(self, tmp_path, stations_df):
        target = tmp_path / "deep" / "dir"
        save_snapshot(target, "piezometria", stations_df)
        assert (target / "snapshot_piezometria.csv").exists()


class TestLoadMissing:
    def test_clear_error(self, tmp_path):
        with pytest.raises(SnirhError, match="No bundled snapshot.*nope"):
            load_snapshot("nope", tmp_path)


class TestSnapshotPath:
    def test_naming(self, tmp_path):
        assert snapshot_path("hidrometrica_acores", tmp_path).name == (
            "snapshot_hidrometrica_acores.csv"
        )
