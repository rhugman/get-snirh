# get-snirh
# Readme LC test

[![PyPI version](https://badge.fury.io/py/get-snirh.svg)](https://badge.fury.io/py/get-snirh)
[![Tests](https://github.com/rhugman/get-snirh/actions/workflows/test.yml/badge.svg)](https://github.com/rhugman/get-snirh/actions/workflows/test.yml)
[![Downloads](https://static.pepy.tech/badge/get-snirh)](https://pepy.tech/project/get-snirh)

A Python package to automate the retrieval of water resource data from the Portuguese Environment Agency (SNIRH).

## Installation

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

## Usage

### Basic Example

```python
from get_snirh import Snirh, Parameters

# Initialize the client for a specific network
# Currently supported: "piezometria" (default), "meteorologica"
snirh = Snirh(network="piezometria")

# 1. Get Stations
# Fetch all stations and filter by basin
# This uses bundled metadata for fast access
stations = snirh.stations.get_stations_with_metadata(basin_filter=['RIBEIRAS DO ALGARVE'])
print(f"Found {len(stations)} stations.")

# 2. Fetch Data
# Fetch Groundwater Level Depth for the year 2023
# Passing the stations DataFrame allows the output to include station names
df = snirh.data.get_timeseries(
    station_codes=stations.head(5), # Limit to first 5 for demo
    parameter=Parameters.GWL_DEPTH,
    start_date='01/01/2023',
    end_date='31/12/2023'
)

print(df.head())

# 3. Save to CSV
df.to_csv('algarve_gwl_2023.csv', index=False)
```

## Testing

To run the standard unit tests (mocked):
```bash
pytest
```

To run the live integration tests (hits SNIRH servers):
```bash
RUN_LIVE_TESTS=1 pytest tests/test_live.py
```

## Features & Limitations

- **Supported Networks**: Currently fully supports **Piezometria** (Groundwater) and **Meteorologica** (Meteorology).
- **Station Database**: Station lists are currently **limited to a hardcoded local database**. Remote access to the live station list is currently unresolved, so the bundled metadata files must be updated manually for now.
- **Data Retrieval**: Downloads time-series data for various parameters (Rainfall, Groundwater Level, Temperature, etc.).
- **Robust Parsing**: Handles SNIRH's specific CSV formats and encoding (ISO-8859-1).
- **Clean API**: Simple, object-oriented interface.

## Examples

Check the `examples/` folder for more detailed usage scripts and notebooks.

## Parameters

Available parameters in `get_snirh.Parameters`:
- `PRECIPITATION_DAILY`
- `PRECIPITATION_MONTHLY`
- `GWL_DEPTH`
- `AIR_TEMP_AVG_DAILY`
- And more...

## Disclaimer & Data Acknowledgment

This software is an unofficial tool and is **not** affiliated with, endorsed by, or maintained by the **Agência Portuguesa do Ambiente (APA)** or the **Sistema Nacional de Informação de Recursos Hídricos (SNIRH)**.

All data retrieved by this tool belongs to SNIRH/APA. Users are responsible for adhering to SNIRH's terms of use and data policies. Please ensure you cite the source appropriately when using the data.

- **Data Source**: [SNIRH - Sistema Nacional de Informação de Recursos Hídricos](https://snirh.apambiente.pt/)
- **Owner**: Agência Portuguesa do Ambiente (APA)

This tool is provided "as is", without warranty of any kind. Use it responsibly to avoid overloading the SNIRH servers.

## Citation

If you use this software in your research, please cite it as:

> Costa, L., & Hugman, R. (2025). get-snirh (Version 0.1.1) [Computer software]. https://github.com/rhugman/get-snirh

## License

GNU GPLv3
