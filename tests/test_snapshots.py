import datetime

import pandas as pd
import pytest

from get_snirh.exceptions import SnirhError
from get_snirh.snapshots import (
    SNAPSHOT_DATE_PREFIX,
    load_snapshot,
    save_snapshot,
    snapshot_date,
    snapshot_path,
)


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


class TestSnapshotDate:
    def test_header_line_written(self, tmp_path, stations_df):
        path = save_snapshot(tmp_path, "piezometria", stations_df)
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first == (
            f"{SNAPSHOT_DATE_PREFIX} {datetime.date.today().isoformat()}"
        )

    def test_snapshot_date_defaults_to_today(self, tmp_path, stations_df):
        save_snapshot(tmp_path, "piezometria", stations_df)
        assert snapshot_date("piezometria", tmp_path) == (
            datetime.date.today().isoformat()
        )

    def test_explicit_fetched_on(self, tmp_path, stations_df):
        save_snapshot(tmp_path, "piezometria", stations_df,
                      fetched_on=datetime.date(2026, 1, 2))
        assert snapshot_date("piezometria", tmp_path) == "2026-01-02"

    def test_explicit_fetched_on_string(self, tmp_path, stations_df):
        save_snapshot(tmp_path, "piezometria", stations_df,
                      fetched_on="2025-12-31")
        assert snapshot_date("piezometria", tmp_path) == "2025-12-31"

    def test_missing_snapshot_has_no_date(self, tmp_path):
        assert snapshot_date("nope", tmp_path) is None

    def test_legacy_snapshot_without_header(self, tmp_path, stations_df):
        # Snapshots written before date stamping: no header line.
        stations_df.to_csv(tmp_path / "snapshot_piezometria.csv",
                           index=False, encoding="utf-8")
        assert snapshot_date("piezometria", tmp_path) is None
        loaded = load_snapshot("piezometria", tmp_path)
        assert len(loaded) == 2
        assert list(loaded.columns) == list(stations_df.columns)

    def test_header_not_in_loaded_frame(self, tmp_path, stations_df):
        save_snapshot(tmp_path, "piezometria", stations_df)
        loaded = load_snapshot("piezometria", tmp_path)
        assert len(loaded) == 2
        assert list(loaded.columns) == list(stations_df.columns)
        assert not loaded.iloc[0].astype(str).str.contains("#").any()


class TestLoadMissing:
    def test_clear_error(self, tmp_path):
        with pytest.raises(SnirhError, match="No bundled snapshot.*nope"):
            load_snapshot("nope", tmp_path)


class TestSnapshotPath:
    def test_naming(self, tmp_path):
        assert snapshot_path("hidrometrica_acores", tmp_path).name == (
            "snapshot_hidrometrica_acores.csv"
        )
