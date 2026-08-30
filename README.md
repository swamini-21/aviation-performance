# Airline On-Time Performance Analytics

An end-to-end data engineering project on Databricks, built to demonstrate
medallion architecture (Bronze → Silver → Gold), Unity Catalog, Delta Lake,
and AI/BI fundamentals - using U.S. domestic flight on-time performance data
from 1987 through the present.

## Why this project

Built as a portfolio project while transitioning from a Data Analyst
background (Power BI, Azure Data Factory, T-SQL) toward Data Engineering,
using tools directly relevant to current Databricks-based roles: Unity
Catalog, Delta Lake, serverless SQL Warehouses, PySpark/Spark SQL, and
(planned) AI/BI dashboards with a Genie natural-language query agent.

## Tech stack

- **Platform:** Databricks Free Edition (Unity Catalog, serverless compute only)
- **Languages:** PySpark, Spark SQL
- **Storage:** Delta Lake tables, Unity Catalog Volumes
- **Version control:** GitHub, via Databricks Git folders
- **Tooling:** Databricks CLI (bulk file upload to Volumes)

## Architecture

```
airline_analytics (catalog)
├── bronze
│   ├── flights_historical    (2004-2008, Databricks built-in dataset)
│   ├── flights_recent        (2009-2026, BTS TranStats)
│   └── landing (volume)      (raw CSV landing zone for manual uploads)
├── silver                    (planned - conformed, unified schema)
└── gold                      (planned - aggregated, dashboard-ready tables)
```

Two Bronze tables are kept **deliberately separate**, one per source, rather
than merged on ingestion. Medallion architecture principle: Bronze preserves
each source exactly as it landed, with no conforming decisions made yet.
Keeping them separate also made both data quality bugs below far easier to
catch, each table could be sanity-checked against real-world numbers in
isolation. The merge into one unified schema is Silver's job (see Roadmap).

## Data sources

| Source | Table | Coverage | Rows | Columns |
|---|---|---|---|---|
| Databricks built-in (`/databricks-datasets/airlines`) | `bronze.flights_historical` | 2004–2008 | 35,874,667 | 31 + 3 metadata |
| BTS TranStats — Reporting Carrier On-Time Performance | `bronze.flights_recent` | 2009–2026 | 110,841,156 | 109 + 3 metadata |

Full column-level documentation, including the confirmed mapping between the
two schemas, lives in [`docs/data_dictionary.md`](docs/data_dictionary.md).

**Why two different sources instead of one continuous dataset:** Databricks'
built-in sample only covers 1987-2008. Rather than manually downloading and
uploading 22 years of BTS files, the built-in copy covers the older years for
free, and BTS TranStats fills 2009 onward - which also happens to be the data
that makes the project demonstrably "current." The two sources have real
structural differences (see Known Limitations), which is itself a realistic
data engineering scenario, not a shortcut.

### Getting the recent data (BTS TranStats)

BTS does not offer a public API. Files are hosted at a predictable static
URL pattern and were bulk-downloaded locally, then uploaded to a Unity
Catalog Volume (`airline_analytics.bronze.landing`) via the Databricks CLI -
Free Edition's serverless compute has allowlisted outbound internet access
and cannot reliably reach transtats.bts.gov directly, so this is a manual
landing-zone step by design, not a workaround.

## Data quality findings

Two real issues were found and resolved during Bronze ingestion - documented
here rather than hidden, since catching them is part of the point:

**1. Historical dataset: ~10x row duplication.**
The built-in `/databricks-datasets/airlines` sample contains identical
records repeated across 10 of its 1,867 part-files. Caught by comparing
per-year row counts (71M/year) against known real-world U.S. domestic
flight volume (7M/year) - a 10x mismatch. Confirmed by finding the exact
same flight records appearing under 10 different `_source_file` paths.
Fixed with `dropDuplicates()` on business key (Year, Month, DayofMonth,
UniqueCarrier, FlightNum, DepTime, Origin, Dest) during ingestion.
Result: 358,747,310 raw rows → 35,874,667 after dedup (90.0% reduction),
now matching real-world scale.

**2. Recent dataset: one file silently dropped during upload.**
A transient `TEMPORARILY_UNAVAILABLE` error during a large CLI bulk-upload
(210 files) caused one file to fail without an obvious downstream error.
Caught by checking `COUNT(DISTINCT _source_file)` against the actual
uploaded file count (209 vs. 210 expected). Re-uploaded and re-ingested;
final count matches exactly (210/210), and the fixed table shows a visible,
realistic dip in 2020 (4,688,354 rows) consistent with the COVID-19 collapse
in air travel - independent confirmation the data reflects reality, not
just internal consistency.

## Known limitations

- **Historical data covers only 2004-2008**, not the full 1987-2008 available
  in the built-in dataset - scoped down to fit Free Edition's compute/storage
  quota. This creates an intentional, documented gap rather than a continuous
  1987-2026 timeline.
- **Schema mismatch between sources is not yet resolved** - that's Silver's
  job. Notably, `IsArrDelayed`/`IsDepDelayed` (historical, flags any delay)
  and `ArrDel15`/`DepDel15` (recent, flags 15+ minute delay specifically)
  look like equivalent fields but use different thresholds - they cannot be
  treated as directly interchangeable.
- **The recent dataset carries ~80 columns with no historical equivalent**
  (airport IDs, city/state detail, delay-bucket fields, full diversion
  tracking). Whether to carry these forward or drop them for a clean Silver
  union is an open decision.

## Roadmap

- [x] **Phase 1 - Data Collection:** Bronze ingestion for both sources, verified and deduplicated
- [ ] **Phase 2 - Silver:** Schema conformance, unified table, resolved delay-flag semantics
- [ ] **Phase 3 - Gold:** Aggregated, dashboard-ready tables
- [ ] **Phase 4 - AI/BI Dashboard:** Visual analytics on Gold tables
- [ ] **Phase 5 - Genie:** Natural-language querying over the Gold layer
- [ ] Extend toward a fuller DE stack (Airflow orchestration, dbt transformations) as a stretch goal

## Repository structure

```
aviation-performance/
├── README.md
├── .gitignore
├── notebooks/
│   └── 01_bronze_ingestion.py
├── scripts/
│   └── download_bts_ontime.py
└── docs/
    └── data_dictionary.md
```