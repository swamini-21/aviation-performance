# Airline On-Time Performance Analytics

An end-to-end data engineering project on Databricks, built to demonstrate
medallion architecture (Bronze → Silver → Gold), Unity Catalog, Delta Lake,
and AI/BI fundamentals - using U.S. domestic flight on-time performance data
from 2004 through June 2026.

Design rationale, data quality findings, and known limitations for every
phase are documented separately in
[`docs/design_decisions.md`](docs/design_decisions.md).

## Why this project

Built as a portfolio project while transitioning from a Data Analyst
background (Power BI, Azure Data Factory, T-SQL) toward Data Engineering,
using tools directly relevant to current Databricks-based roles: Unity
Catalog, Delta Lake, serverless SQL Warehouses, PySpark/Spark SQL, AI/BI
dashboards, and a Genie natural-language query agent.

## Tech stack

- **Platform:** Databricks Free Edition (Unity Catalog, serverless compute only)
- **Languages:** PySpark, Spark SQL
- **Storage:** Delta Lake tables, Unity Catalog Volumes
- **BI / NL querying:** AI/BI Dashboards, Genie Agent
- **Version control:** GitHub, via Databricks Git folders
- **Tooling:** Databricks CLI (bulk file upload to Volumes)

## Architecture

```
airline_analytics (catalog)
├── bronze
│ ├── flights_historical (2004-2008, Databricks built-in dataset)
│ ├── flights_recent (2009-2026, BTS TranStats)
│ └── landing (volume) (raw CSV landing zone for manual uploads)
├── silver
│ ├── flights (146,715,805 rows, conformed 2004-2026)
│ └── flights_quarantine (hard-failure rejects - empty by design)
└── gold
├── fct_flights (146,715,805 rows, flight grain)
├── dim_date (8,401 rows)
├── dim_carrier (29 rows, time-bounded)
├── dim_airport (426 rows, role-playing dimension)
├── agg_daily_carrier_route_performance (52,154,788 rows)
├── agg_monthly_carrier_performance (4,421 rows)
└── mv_carrier_route_performance (Unity Catalog Metric View)
```

Two Bronze tables are kept deliberately separate, one per source, rather
than merged on ingestion - see `docs/design_decisions.md` for why.

## Data sources

| Source | Table | Coverage | Rows | Columns |
|---|---|---|---|---|
| Databricks built-in (`/databricks-datasets/airlines`) | `bronze.flights_historical` | 2004-2008 | 35,874,667 | 31 + 3 metadata |
| BTS TranStats - Reporting Carrier On-Time Performance | `bronze.flights_recent` | 2009-2026 | 110,841,156 | 109 + 3 metadata |

Full column-level documentation, including the confirmed mapping between the
two schemas, lives in [`docs/data_dictionary.md`](docs/data_dictionary.md).
The conformed Silver schema, including the mapping from both sources and all
data quality reason codes, is documented in
[`docs/data_dictionary_silver.md`](docs/data_dictionary_silver.md). Gold
tables and Metric View measures are documented in
[`docs/data_dictionary_gold.md`](docs/data_dictionary_gold.md).

Recent data (2009+) has no public API and is bulk-downloaded locally, then
uploaded to a Unity Catalog Volume (`airline_analytics.bronze.landing`) via
the Databricks CLI - see `docs/design_decisions.md` for why this is a manual
step rather than a direct notebook download.

## AI/BI Dashboards

Three published dashboard pages, built on `gold.mv_carrier_route_performance`:

1. **On-Time Performance Overview** - KPI counters, monthly on-time trend,
   cancellation rate trend, delay-cause breakdown, on-time % heatmap by
   month × year.
2. **Carrier Comparison** - ranked bar charts, flight-volume-vs-on-time-%
   scatter, sortable carrier stats table.
3. **Route Analysis** - busiest routes, best/worst on-time routes,
   distance-vs-delay scatter, sortable route stats table.

## Genie Agent

A Genie Agent ("Airline Flight Performance") grounded in `gold.fct_flights`
and its three dimension tables answers natural-language questions across
carrier performance, route analysis, delay causes, and time trends -
matching the scope of the AI/BI dashboards above. Design decisions, tested
question patterns, and known behavioral limitations are documented in
`docs/design_decisions.md`.

## Roadmap

- [x] **Phase 1 - Bronze:** ingestion for both sources, verified and deduplicated
- [x] **Phase 2 - Silver:** schema conformance, unified 146.7M-row table, two-tier data quality
- [x] **Phase 3 - Gold:** star schema + aggregate tables, dashboard- and Genie-ready
- [x] **Phase 4 - AI/BI Dashboards:** On-Time Overview, Carrier Comparison, and Route Analysis pages on a Unity Catalog Metric View
- [x] **Phase 5 - Genie:** natural-language querying over the Gold layer
- [ ] Extend toward a fuller DE stack (Airflow orchestration, dbt transformations) as a stretch goal

## Repository structure
```
aviation-performance/
├── README.md
├── .gitignore
├── notebooks/
│   ├── 01_bronze_ingestion.ipynb
│   ├── 02_silver_profiling.ipynb
│   ├── 03_silver_flights.ipynb
│   ├── 04_silver_dq_investigation.ipynb
│   ├── 05_gold_flights.ipynb
│   └── 06_metric_view.ipynb
├── scripts/
│   └── download_bts_ontime.py
├── genie/
│   └── airline_flight_performance.geniespace.json
└── docs/
    ├── data_dictionary.md
    ├── data_dictionary_silver.md
    ├── data_dictionary_gold.md
    └── design_decisions.md

```