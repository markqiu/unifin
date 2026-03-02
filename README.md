# unifin

**Unified intelligent global financial data platform.**

A next-generation financial data platform that unifies data from multiple providers behind a single, consistent interface.

## Quick Start

```python
import unifin

# Auto-routes to the best provider based on symbol
df = unifin.equity.historical("000001.XSHE", start_date="2024-01-01")  # A-share → eastmoney
df = unifin.equity.historical("AAPL", start_date="2024-01-01")          # US → yfinance

# Explicit provider
df = unifin.equity.historical("000001.XSHE", provider="yfinance")

# Results are Polars DataFrames
print(df.head())
```

## Key Features

- **Unified data models** — One schema, all providers map to it
- **Smart routing** — Auto-selects the best provider for each symbol/exchange
- **ISO 10383 symbols** — Standard exchange codes (e.g., `000001.XSHE`)
- **Local persistence** — DuckDB storage with incremental sync
- **9 providers** — eastmoney, akshare, tushare, joinquant, fmp, yfinance, EODHD, J-Quants, jugaad-data

## Install

```bash
pip install unifin
pip install "unifin[yfinance]"    # with Yahoo Finance
pip install "unifin[all]"         # all providers
```

## License

MIT
