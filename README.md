# get-snirh

[![PyPI version](https://badge.fury.io/py/get-snirh.svg)](https://badge.fury.io/py/get-snirh)
[![Tests](https://github.com/rhugman/get-snirh/actions/workflows/test.yml/badge.svg)](https://github.com/rhugman/get-snirh/actions/workflows/test.yml)
[![Downloads](https://static.pepy.tech/badge/get-snirh)](https://pepy.tech/project/get-snirh)

A Python package to automate the retrieval of water resource data from the Portuguese Environment Agency (SNIRH).

## Installation

Needs Python 3.10 or newer; tested on 3.10, 3.12 and 3.14 (Ubuntu and
Windows).

Install from PyPI:

```bash
pip install get-snirh
```

Or install from source:

```bash
git clone https://github.com/rhugman/get-snirh.git
cd get-snirh
pip install .
```

## Quickstart

The workflow is: **networks → stations → parameters → timeseries**.

```python
from get_snirh import Snirh, Parameters

# Bind a client to a network by slug (or uid)
snirh = Snirh("piezometria")

# 1. Networks — discover what exists (live)
print(snirh.networks())           # columns: uid, name, slug

# 2. Stations — merged live table for the bound network,
#    filtered by basin (str or list; case-insensitive exact match)
stations = snirh.stations(basin="RIBEIRAS DO ALGARVE")
print(f"Found {len(stations)} stations.")

# 3. Parameters — live discovery of what has data at a station
pars = snirh.parameters(stations["uid"].iloc[0])
print(pars)                       # columns: uid, name

# 4. Timeseries — one parameter across stations, ISO dates only
df = snirh.timeseries(
    stations.head(5),             # DataFrame with uid + code columns
    Parameters.GWL_DEPTH,         # or any parameter uid string from step 3
    start="2023-01-01",
    end="2023-12-31",
)
print(df.head())                  # columns: timestamp, code, uid, parameter, value

df.to_csv("algarve_gwl_2023.csv", index=False)
```

The `parameter` argument accepts either a member of the curated
`get_snirh.Parameters` enum (kept as a convenience) or any raw parameter
uid string — live discovery via `snirh.parameters(...)` is the source of
truth for what a station actually measures.

Other station filters work the same way: any canonical column can be used
as a keyword argument, e.g. `snirh.stations(status="EM SERVIÇO")` or
`snirh.stations(basin=["MONDEGO", "VOUGA/RIBEIRAS COSTEIRAS"], district="COIMBRA")`.

Values are SNIRH's own and matching is exact (if case-insensitive), so take
them from the table rather than guessing: `"VOUGA"` matches nothing, because
the basin is called `VOUGA/RIBEIRAS COSTEIRAS`. Which values exist is also
per-network — `status="ATIVA"` is a meteorological/hydrometric value and
returns zero rows against `piezometria`, whose stations are `EM SERVIÇO`,
`EM RESERVA`, `ABANDONADO` and so on.

## Examples

Runnable notebooks in [`examples/`](examples/), saved with their output so
you can read them without fetching anything. Both hit SNIRH live when run;
the plotting one also needs `matplotlib` (see `environment.yml`).

| Notebook | What it covers |
|---|---|
| [`example_gwl_algarve.ipynb`](examples/example_gwl_algarve.ipynb) | The basics: bind a network, filter stations by basin, fetch a parameter, save a CSV. |
| [`example_area_querenca_silves.ipynb`](examples/example_area_querenca_silves.ipynb) | Everything SNIRH holds for one area (the Querença-Silves aquifer): surveying all 15 networks for coverage, selecting stations by aquifer vs. by coordinates, then downloading, mapping and plotting hydraulic head, spring discharge, chemistry (nitrate, chloride, conductivity), rainfall and river level — every station in the area, 133k observations. |

The second is the one to read if your question is *"what data exists for
this place?"* — it also works through the traps: parameters that discover
but return nothing, abandoned stations, a station that silently switches
from hourly to monthly logging, plots that bridge gaps with lines that are
not data, and why hydraulic head is the column you want rather than depth
to water. Note it queries every station in the area, so it is a few hundred
requests and several minutes.

## How it works

- **Live-first discovery.** Networks, stations and parameters are scraped
  live from SNIRH, so results reflect the current state of the portal —
  no hardcoded station database.
- **Session-scoped endpoints handled automatically.** Some SNIRH endpoints
  only respond within a per-network browser session (cookie + network
  selection). The client establishes and reuses that session lazily; you
  never deal with it.
- **Bundled snapshots as a dated offline fallback.** If SNIRH is
  unreachable, `stations()` falls back to a snapshot shipped with the
  package and warns loudly, including the date the snapshot was fetched.
  `snirh.refresh_snapshot()` regenerates the snapshot from a live fetch.
- **SNIRH blocks non-Portuguese IPs.** The portal returns `403 Forbidden`
  to requests from outside Portugal (this includes most cloud/CI runners,
  e.g. GitHub Actions), so live calls surface as `SnirhNetworkError`. Run
  from a Portuguese IP (or a proxy/VPN into Portugal) to reach the live
  service; otherwise you get the bundled-snapshot fallback described above.

## Supported networks

All 15 SNIRH networks were exercised end-to-end (stations → parameters →
timeseries) against the live service on 2026-07-15:

| Slug | Stations | Status | Notes |
|---|---:|---|---|
| `piezometria` | 1127 | verified | Groundwater levels. |
| `qualidade_aguas_subterraneas` | 1528 | verified | Groundwater quality; irregular grab-sample timestamps. |
| `hidrometrica` | 719 | verified | River stage/flow, daily and hourly series. |
| `meteorologica` | 789 | verified | Rainfall, temperature, wind, evaporation, etc. |
| `qualidade` | 4202 | verified | Surface-water quality; sparse grab samples with time-of-day timestamps. |
| `qualidade_automatica` | 112 | verified | Discontinued automatic network; tested station records end mid-2000s — use historic windows. No `status` column. |
| `aguas_balneares` | 758 | verified | Bathing water; very sparse seasonal samples, many empty station×parameter combinations. No `status` column. |
| `sedimentologica` | 305 | verified | Historic; tested station records end ~1982. No `status` column. |
| `nascentes` | 83 | verified | Springs; spot-sampled, sparse. Station `name` holds short AF-codes (SNIRH's own labeling). |
| `hidrometrica_acores` | 15 | verified | Tested station records end ~2002 — use historic windows. No `status` column. |
| `meteorologica_acores` | 72 | verified | Discontinued conventional network; tested records end ~1995. Often 1 parameter per station. No `status` column. |
| `hidrometrica_madeira` | 9 | verified | Coordinate-less network (uids discovered via the home-page fallback); historic daily flow (1987–1990). |
| `meteorologica_madeira` | 52 | verified | Tested station records end ~2011 — use historic windows. |
| `eta` | 13 | verified | Water-treatment plants; coordinate-less (home-page fallback); sampling data, e.g. pesticide analyses from 2003. No `status` column. |
| `hidrometrica_algarve` | 29 | works | Network reports almost no data (2 active stations; the rest are installation-status entries). |

Caveats that apply across networks:

- **A discovered parameter can still be empty for your window.**
  `parameters()` lists parameters the station has *ever* had data for,
  with no date qualifier. `timeseries()` then returns a well-formed empty
  DataFrame (correct columns, 0 rows) when the window holds no records —
  widen the date range before concluding a station is dead.
- **Column sets vary by network.** Some networks have no `status` column,
  some no coordinates; filter accordingly.
- Passing a raw parameter uid string puts that uid (not the human-readable
  name) in the output `parameter` column; `Parameters` enum members use
  the member name.

## Migrating from 0.1.x

Version 0.2.0 is a **hard break** with the 0.1.x API:

- `StationFetcher` / `DataFetcher` (and the `snirh.stations.…` /
  `snirh.data.…` accessor objects) are removed. Use the flat facade:
  `Snirh(...)` with `.networks()`, `.stations()`, `.parameters()`,
  `.timeseries()`, `.refresh_snapshot()`.
- Column names are now canonical English: `marker_site` → `uid`,
  `CÓDIGO` → `code`, and the remaining Portuguese CSV headers map to
  `name`, `basin`, `status`, `district`, `municipality`, `parish`,
  `altitude`, `coord_x`, `coord_y`, `aquifer_system`, …
- Dates are ISO only: `'dd/mm/yyyy'` strings are rejected with an error;
  pass `'YYYY-MM-DD'` strings or `datetime.date`/`datetime.datetime`
  objects.
- `get_stations_with_metadata(basin_filter=[...])` →
  `stations(basin=[...])`.
- `update_local_database` → `refresh_snapshot()`.

## Politeness

This tool talks to a public service — please keep bulk pulls reasonable.

- Timeseries fetches default to `min(10, n_stations)` worker threads; pass
  `max_workers` to change it (there's no enforced upper bound, so please
  don't raise it past 10 against the public SNIRH server).
- Every request retries up to 3 times with exponential backoff on
  429/500/502/503/504.
- Requests carry an honest User-Agent
  (`get-snirh/<version> (+https://github.com/rhugman/get-snirh)`) so SNIRH
  can identify and, if needed, contact or throttle the tool.

## Testing

To run the offline test suite (mocked, plus golden tests against recorded
SNIRH fixtures):

```bash
pytest
```

To run the live integration tests (hits SNIRH servers):

```bash
RUN_LIVE_TESTS=1 pytest tests/test_live.py
```

Regular CI runs the offline suite only. A separate scheduled workflow runs
the live suite weekly to detect drift in SNIRH's page layout, endpoints or
encodings. Because SNIRH blocks non-Portuguese IPs (see *How it works*),
the live tests **skip** rather than fail when the server is unreachable
(`403`/`SnirhNetworkError`) — from a cloud runner they will almost always
skip, and a red run means genuine drift, not an outage.

## Disclaimer & Data Acknowledgment

This software is an unofficial tool and is **not** affiliated with, endorsed by, or maintained by the **Agência Portuguesa do Ambiente (APA)** or the **Sistema Nacional de Informação de Recursos Hídricos (SNIRH)**.

All data retrieved by this tool belongs to SNIRH/APA. Users are responsible for adhering to SNIRH's terms of use and data policies. Please ensure you cite the source appropriately when using the data.

- **Data Source**: [SNIRH - Sistema Nacional de Informação de Recursos Hídricos](https://snirh.apambiente.pt/)
- **Owner**: Agência Portuguesa do Ambiente (APA)

This tool is provided "as is", without warranty of any kind. Use it responsibly to avoid overloading the SNIRH servers.

## Acknowledgements

The 0.2.0 rework owes a lot to two earlier MIT-licensed projects by
[Francisco Macedo](https://github.com/franciscobmacedo), which had already
worked out much of how SNIRH actually behaves:

- **[snirhcrawler](https://github.com/franciscobmacedo/snirhcrawler)** — works
  the same four endpoints this package does, and reads the network list from
  the same `f_redes_todas[]` home-page select. Having a correct prior reading
  of SNIRH's undocumented behaviour to check against saved a great deal of
  guesswork here.
- **[recursoshidricos](https://github.com/franciscobmacedo/recursoshidricos)**
  — a fuller application over the same data, useful for seeing which endpoints
  hold up in practice.

Where this package differs (a flat client facade, canonical English columns,
snapshot fallback) those are choices for a different audience, not
corrections. Both projects are MIT licensed and neither is affiliated with
this one.

## Citation

If you use this software in your research, please cite it as:

> Costa, L., & Hugman, R. (2026). get-snirh (Version 0.2.0) [Computer software]. https://github.com/rhugman/get-snirh

## License

GNU GPLv3
