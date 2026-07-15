# Changelog

Notable changes to get-snirh. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - Unreleased

Complete rework around live discovery. **Breaking release** — see the
"Migrating from 0.1.x" section of the README.

### Added

- **Live discovery** end to end: `Snirh.networks()` parses the current
  network list from the SNIRH home page; `Snirh.stations()` builds a merged
  stations table live (map-marker XML for uids/coordinates joined with the
  metadata CSV), with a home-page station-list fallback for coordinate-less
  networks (`eta`, `hidrometrica_madeira`); `Snirh.parameters(station)`
  discovers per-station parameters live. No more hardcoded station database.
- New flat facade: `Snirh(slug_or_uid)` with `.networks()`,
  `.stations(basin=..., status=..., **filters)`, `.parameters(station)`,
  `.timeseries(stations, parameter, start, end, max_workers=None)` and
  `.refresh_snapshot()`. Station filters match canonical columns
  case-insensitively and accept single values or lists.
- Session-scoped SNIRH endpoints (station uid XML, parameter ajax) handled
  automatically: the client lazily establishes the cookie + network-selection
  session and reuses it; stateless endpoints run on thread-local sessions so
  timeseries fetches can be concurrent.
- Bundled, dated station snapshots for all 15 networks
  (`src/get_snirh/data/snapshot_<slug>.csv`) as an offline fallback for
  `stations()` when SNIRH is unreachable, with a staleness warning that
  reports the snapshot's fetch date. `refresh_snapshot()` regenerates a
  snapshot from a live fetch.
- HTTP hardening: up to 3 retries with exponential backoff on
  429/500/502/503/504, connect/read timeouts on every request, and an honest
  User-Agent (`get-snirh/<version> (+https://github.com/rhugman/get-snirh)`).
- Typed exceptions: `SnirhError`, `SnirhNetworkError`, `SnirhParsingError`,
  `SnirhDiscoveryError`. A timeseries call where every station fails with a
  network error raises instead of silently returning an empty frame.
- Golden offline tests against recorded SNIRH fixtures (`tests/golden/`),
  plus per-module offline test suites.
- CI split: the offline suite runs on push/PR (`test.yml`, Ubuntu + Windows,
  Python 3.10/3.12/3.14 — 3.14 resolves pandas 3.x, so the open-ended
  `pandas>=2.0.0` floor is exercised rather than assumed); a separate
  scheduled workflow (`live-drift.yml`) runs the gated live suite weekly to
  detect drift in SNIRH's page layout, endpoints or encodings.
- All 15 SNIRH networks verified end to end against the live service
  (14 fully; `hidrometrica_algarve` works but the network itself reports
  almost no data). See the "Supported networks" table in the README.

### Changed (breaking)

- Minimum Python is now **3.10** (`requires-python = ">=3.10"`), up from 3.8.
  3.8 and 3.9 are both end-of-life, and neither was ever tested — CI has
  never run below 3.10, so the old floor was a claim rather than a promise.
  The tested range is now 3.10 through 3.14.
- `StationFetcher` / `DataFetcher` and the `snirh.stations.…` /
  `snirh.data.…` accessor objects are removed in favor of the flat facade.
- Station columns are canonical English: `marker_site` → `uid`,
  `CÓDIGO` → `code`, and the other Portuguese CSV headers map to `name`,
  `basin`, `status`, `district`, `municipality`, `parish`, `altitude`,
  `coord_x`, `coord_y`, `aquifer_system`, … (values stay in Portuguese).
- Dates are ISO only: `start`/`end` take `'YYYY-MM-DD'` strings or
  `datetime.date`/`datetime.datetime` objects; `'dd/mm/yyyy'` strings are
  rejected with an error.
- `get_stations_with_metadata(basin_filter=[...])` → `stations(basin=[...])`.
- `update_local_database` → `refresh_snapshot()`.
- Timeseries output is long format with columns
  `timestamp, code, uid, parameter, value` (sorted by code, then timestamp);
  an empty result keeps those columns.
- `Parameters` enum is kept as a convenience, but live discovery via
  `parameters(station)` is the source of truth; raw parameter uid strings
  are accepted everywhere a `Parameters` member is.

### Fixed

- Encodings fixed at the root: each endpoint is decoded with its verified
  charset (home page and CSV endpoints ISO-8859-1; marker XML and parameter
  ajax UTF-8 with HTML entities — including double-escaped ones — unescaped
  during parsing). No more mojibake in station or parameter names.

## [0.1.2]

### Changed

- Raised the pandas floor to `pandas>=2.0.0`.
- Comment cleanup.

### Removed

- Deduplicated dead code in `stations.py`.
