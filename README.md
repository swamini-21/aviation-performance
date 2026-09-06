# Airline On-Time Performance Analytics

An end-to-end data engineering project on Databricks, built to demonstrate
medallion architecture (Bronze → Silver → Gold), Unity Catalog, Delta Lake,
and AI/BI fundamentals - using U.S. domestic flight on-time performance data
from 2004 through June 2026.

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
├── silver   
│    ├── flights        (146,715,805 rows, conformed 2004-2026)
│   └── flights_quarantine    (hard-failure rejects - currently empty by design)
└── gold                      (planned - aggregated, dashboard-ready tables)
```

Two Bronze tables are kept **deliberately separate**, one per source, rather
than merged on ingestion. Medallion architecture principle: Bronze preserves
each source exactly as it landed, with no conforming decisions made yet.
Keeping them separate also made both data quality bugs below far easier to
catch, each table could be sanity-checked against real-world numbers in
isolation. The merge into one unified schema is Silver's job (see Phase 2 below).

## Data sources

| Source | Table | Coverage | Rows | Columns |
|---|---|---|---|---|
| Databricks built-in (`/databricks-datasets/airlines`) | `bronze.flights_historical` | 2004–2008 | 35,874,667 | 31 + 3 metadata |
| BTS TranStats — Reporting Carrier On-Time Performance | `bronze.flights_recent` | 2009–2026 | 110,841,156 | 109 + 3 metadata |

Full column-level documentation, including the confirmed mapping between the
two schemas, lives in [`docs/data_dictionary.md`](docs/data_dictionary.md). The conformed Silver Schema, including the mapping from both sources and all data quality reason codes, is documented separately in [`docs/data_dictionary_silver.md`](docs/data_dictionary_silver.md)

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

## Data quality findings - Bronze ingestion

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

### Phase 2

Purpose

Bronze holds two structurally incompatible sources. The ASA Data Expo extract (2004–2008) calls an airline UniqueCarrier; BTS TranStats (2009–2026) calls the same thing Reporting_Airline. That pattern repeats across most of the schema, and the two tables differ in width (34 vs 112 columns), typing (INT vs DOUBLE), and available fields.

Without a conformance step, no single query can span 2004–2026. The Silver layer exists to produce one table — airline_analytics.silver.flights — that can.

Reconciliation against Bronze is exact: 146,715,823 Bronze rows − 18 duplicates − 0 quarantined = 146,715,805. Verified per year via unexplained_gap = 0.

Design decisions
1. Delay flags are derived, never mapped

The two sources carry different late-flight indicators, and they are not the same metric:

Historical: IsArrDelayed / IsDepDelayed — YES/NO, true for any delay ≥ 1 min
BTS: ArrDel15 / DepDel15 — 0/1, true only for delays ≥ 15 min

Mapping one onto the other would have made 2004–2008 appear roughly twice as delayed as 2009+, producing an artificial "improvement" at the source boundary. Both sources do carry signed delay minutes, so arr_del15 and dep_del15 are computed from those on both sides using the BTS 15-minute definition. The source flags are dropped entirely.

Verification: delay rates across the 2008/2009 source changeover move 22.24% → 19.20% (arrivals 15+ min late) and 1.96% → 1.39% (cancellations) — ordinary year-over-year variation, with no step change at the seam. That continuity is the evidence the conformance worked.

2. Two-tier data quality, not all-or-nothing

Rows failing a hard rule (no date, no carrier, no route, origin = destination, no scheduled departure, invalid distance) are diverted to silver.flights_quarantine with reason codes. Rows failing a soft rule (internal inconsistencies that leave the row usable) stay in silver.flights tagged via a _dq_warnings ARRAY<STRING> column.

Quarantining everything would have removed ~256K otherwise-usable rows over the air-time defects alone, and broken row-count reconciliation against Bronze. The soft tier is where every real defect in this dataset actually surfaced.

3. Liquid clustering over partitioning

CLUSTER BY (flight_date, origin). Databricks now recommends liquid clustering for all managed tables; it replaces both PARTITIONED BY and ZORDER, and clustering keys can be redefined later without rewriting data. Partitioning by year on a 22-year table would have produced skewed partitions (2020 is 35% smaller than its neighbours) with no way to change the scheme afterward.

4. Idempotent, year-batched writes

Each year is written independently with .option("replaceWhere", f"year = {year}"), which atomically replaces that year's rows rather than appending. Any year can be re-run safely, and a build interrupted partway resumes by restarting the loop at the last year printed.

Built pilot-first (2005 + 2019, one year from each source to exercise both code paths), validated, then backfilled the remaining 20 years. Full build: ~15 minutes of serverless compute for 146.7M rows.

Findings

The January 2018 reporting break

Monthly volume jumps ~27% at 2018-01 with no corresponding change in air traffic: 5,674,618 flights in 2017 → 7,206,194 in 2018; reporting airports 320 → 358; carriers 12 → 18.

Cause: DOT's Enhancing Airline Passenger Protections III rulemaking lowered the mandatory reporting threshold from 1.0% to 0.5% of domestic scheduled passenger revenue effective 2018-01-01, bringing in Allegiant, Endeavor, Envoy, Mesa, PSA and Republic. The same rule expanded reportable airports from the top 30 by enplanements to all large, medium, small and non-hub airports.

Consequence: flight counts and airport counts are not comparable across 2017/2018. Rate metrics are. The rates confirm this — pct_arr_delayed_15 moves 18.45 → 19.12 and cancellations 1.46 → 1.62 across the same boundary where counts jump 27%.

Any Gold-layer volume trend spanning 2018 must annotate the break or restrict to carriers reporting throughout.

Air-time defects, 2004–2006

Root-cause analysis in notebooks/03_silver_dq_investigation. Two unrelated defects, both affecting AirTime only.

JetBlue and Hawaiian, 2004–2006 — uncorrected time-zone offsets. Air time was derived from raw local wheels-off/wheels-on clock times without adjusting for the zone change. The error scales with zones crossed: ~160 min on 3-zone transcons (LGB→JFK, OAK→JFK, HNL→LAX), ~103 min on 2-zone (DEN→JFK), ~41 min on 1-zone (MSY→JFK). Confined to B6 and HA; absent from 2007 onward and from the BTS source.

The defect is directional. Eastbound legs are overstated and trip AIRTIME_EXCEEDS_ELAPSED. Westbound legs are understated by the same offset — exactly 180 min on 3-zone routes — and can never exceed elapsed time, so they were invisible to that rule. A second rule, AIRTIME_ELAPSED_MISMATCH, compares air time against implied air time (actual_elapsed_min − taxi_out_min − taxi_in_min) with a 15-min tolerance and catches both directions. Adding it took 2005 from 24,070 flagged rows to 48,169 — roughly double, as the round-trip symmetry predicts — while 2019 stayed at zero.

SkyWest, January–July 2004 — mechanism undetermined. 168,473 rows across 424 routes, average gap 94.4 min. Not the time-zone mechanism: SkyWest is a regional feeder flying short hops within one or two zones, and a 94-min error on routes often under 90 min total cannot be an offset.

Not a fixed multiplier either. The ratio of reported to implied air time holds a stable mean of ~2.18 across all seven months, which initially suggested a constant — but the distribution spans 1.0 at p05 to 3.40 at p95 with a median of 2.39. A hard floor at exactly 1.0 means a substantial share of flights are perfectly correct and the rest are corrupted by varying amounts: a mixture, not a uniform transform. The stable mean was the average of two populations.

The defect stops abruptly in August 2004 — 23,631 affected rows in July, 57 in August. ActualElapsedTime tracks CRSElapsedTime normally throughout, so only AirTime is affected.

Consequence for Gold: any metric using air_time_min must exclude rows carrying AIRTIME_ELAPSED_MISMATCH, or 2004–2006 averages skew upward. actual_elapsed_min, taxi times and all delay fields are unaffected.

The quarantine table is empty, and that is the correct result

Zero hard failures across the full 146.7M-row build. Verified independently by running the same rules directly against Bronze for 2020–2021: zero failures across 10,683,751 rows.

Both sources are curated federal datasets, not scraped data. The hard rules are retained as guardrails against future ingestion faults rather than as remediation for observed problems. Every real defect in this dataset surfaced through the soft-warning tier.

2020

Cancellations reach 5.99%, more than triple any other year, while average arrival delay is −4.99 minutes — the only negative in the 22-year series. Flights arrived on average five minutes early into empty airports. Reporting airports rose to 367 while volume fell 35%.

## Known limitations

Historical data covers only 2004–2008, not the full 1987–2008 available in the built-in dataset — scoped down to fit Free Edition's compute/storage quota. An intentional, documented gap rather than a continuous 1987–2026 timeline.

Flight counts are not comparable across 2017/2018. A DOT reporting-threshold change adds ~27% volume at 2018-01 with no change in actual air traffic. Rate metrics remain valid. See Phase 2.

air_time_min is unreliable for 2004–2006, affecting ~256K rows across two unrelated source defects. Filter on AIRTIME_ELAPSED_MISMATCH before aggregating that column.

Times are local, not UTC. Neither source supplies a timezone, so scheduled_departure_local_ts carries a misleading +00:00 suffix. Use crs_elapsed_min for duration arithmetic.

2026 is partial (January–June, 3,488,373 rows). Exclude from year-over-year volume comparisons.

Carrier codes are not stable identifiers across 22 years — codes are reused and carriers merge.

## Roadmap

- [x] **Phase 1 - Data Collection: Bronze** ingestion for both sources, verified and deduplicated ✓
- [ ] **Phase 2 - Silver**: Schema conformance, unified 146.7M-row table, two-tier data quality ✓
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
│   ├── 01_bronze_ingestion.py
│   ├── 02_silver_profiling.py
│   ├── 03_silver_flights.py
│   └── 03_silver_dq_investigation.py
├── scripts/
│   └── download_bts_ontime.py
└── docs/
    ├── data_dictionary.md
    └── data_dictionary_silver.md
```