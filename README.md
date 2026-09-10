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

## Phase 3 — Gold Layer

**Purpose**

Silver produces one clean, conformed table at flight grain — but a single
flat table serves BI dashboards and a natural-language query agent poorly
for different reasons. Dashboards run the same handful of aggregate queries
repeatedly and need speed; Genie needs to answer questions no one
anticipated, which requires atomic grain to compose on the fly. Gold
resolves this with a hybrid design: one curated atomic-grain fact table for
Genie, and two pre-aggregated summary tables at different grains for
dashboard performance.

**Design decisions**

- **Hybrid atomic + aggregate modeling.** `gold.fct_flights` stays at
  flight grain — curated and renamed for business use, but not
  pre-aggregated — so Genie can compose arbitrary `GROUP BY`/`SUM`/`AVG`
  queries without being limited to groupings decided in advance.
  `gold.agg_daily_carrier_route_performance` (day × carrier × route) and
  `gold.agg_monthly_carrier_performance` (month × carrier) serve dashboard
  trend views without scanning 146.7M rows per refresh.
- **Star schema dimensions** — `dim_date`, `dim_carrier`, `dim_airport` —
  join to `fct_flights` on natural keys, attaching business-friendly names
  and hierarchies without duplicating them across every fact row.
- **Null vs. zero, made explicit in aggregates.** The five delay-cause
  columns (`carrier_delay_min`, `weather_delay_min`, etc.) are legitimately
  `NULL` at flight grain — populated only for delays of 15+ minutes, per
  BTS convention. At flight grain that's correct. But `SUM()` over an
  all-`NULL` group also returns `NULL`, which in an *aggregate* table reads
  as "unknown" when it should read as "zero delay-cause minutes occurred."
  Both aggregate tables `COALESCE` these sums to `0` to avoid that
  ambiguity.
- **`dim_carrier` is time-bounded, not a flat lookup**, to correctly handle
  a genuine airline-code reuse case (see Findings below). Most carrier
  codes get one open-ended row; `OH` gets two, and joins to `fct_flights`
  require `flight_date BETWEEN effective_start AND effective_end` rather
  than a plain equi-join.
- **`dim_airport` is a role-playing dimension** — one physical table keyed
  by airport code, joined twice (aliased) wherever a query needs both an
  origin and a destination name in the same row.

**Findings**

- Carrier code reuse (`OH`): Comair → dormant → PSA Airlines. Year-range
  analysis showed `OH` continuously present 2004–2026 with no gap, which
  looked at first like one continuously-operating carrier. Cross-checking
  against `DOT_ID_Reporting_Airline` (BTS's permanent carrier identifier,
  available 2009+) proved otherwise: two distinct DOT IDs (`20397`,
  `20417`) share the `OH` code. Digging into the year-by-year breakdown
  showed the code was actually dormant for seven years (last used by
  Comair in 2010, reassigned to PSA Airlines starting 2018) — not a
  continuous handoff. `dim_carrier` models this with two time-bounded rows
  rather than picking one name and silently misattributing years of
  history to the wrong airline.
- **17 airport codes exist only in pre-2009 data.** The 2004–2008 source
  has no city/state/ID metadata, only bare 3-letter codes. Cross-checked
  against the 2009+ source, 17 codes (e.g. `DUT`, `LNY`, `MKK`, `CBM`,
  `RCA`) never reappear — consistent with small regional airports and
  military airfields that stopped being served, or dropped below
  reporting thresholds, after 2008. Rather than leave these with `NULL`
  metadata, they were manually researched and enriched, flagged with
  `data_coverage = 'pre_2009_only'` so the gap stays visible rather than
  silently patched over.

  **Tables built and reconciled**

| Table | Grain | Rows |
|---|---|---|
| `gold.fct_flights` | flight | 146,715,805 |
| `gold.dim_date` | day | 8,401 |
| `gold.dim_carrier` | carrier code (time-bounded) | 29 |
| `gold.dim_airport` | airport code | 426 |
| `gold.agg_daily_carrier_route_performance` | day × carrier × route | 52,154,788 |
| `gold.agg_monthly_carrier_performance` | month × carrier | 4,421 |

`gold.fct_flights` reconciles exactly against `silver.flights`
(146,715,805 rows both, including a year-by-year check across all 8
backfill batch boundaries). Both aggregate tables reconcile exactly
against `gold.fct_flights` on flight counts, cancellations, diversions,
and delay-cause minute sums.

## Phase 4 — AI/BI Dashboards

Three published dashboard pages consuming a Unity Catalog **Metric View**
(`gold.mv_carrier_route_performance`) built on top of
`agg_daily_carrier_route_performance`, rather than wiring dashboard tiles
directly to Gold tables. See `docs/data_dictionary_gold.md` for the full
measure/dimension reference.

**Why a Metric View:** defining KPIs (on-time %, cancellation rate, etc.)
once in a governed semantic layer means the dashboard and any future
Genie space read identical definitions — they can't silently drift apart
the way they could if each dashboard tile and each Genie query
re-implemented the same aggregation logic independently.

### Pages

1. **On-Time Performance Overview** — KPI counters (Total Flights, On-Time
   Departure %, On-Time Arrival %, Cancellation Rate, Avg Departure Delay,
   Diverted Flights), monthly on-time trend, cancellation rate trend,
   delay-cause breakdown, and an on-time % heatmap by month × year.
   Global filters: Year, Quarter, Month.
2. **Carrier Comparison** — ranked bar charts (on-time % top 10,
   cancellation rate all carriers), a flight-volume-vs-on-time-%
   scatter plot, and a sortable full-carrier stats table. No carrier
   filter by design — every visual compares carriers against each
   other, so filtering to a single carrier would collapse the comparison
   the page exists to show.
3. **Route Analysis** — busiest routes (top 10), best/worst on-time
   routes (top 10 each, via the shrinkage measure below), a
   distance-vs-delay scatter, and a sortable route stats table.
   Page-scoped Carrier filter (does not affect pages 1-2).

### Design decisions

- **OH code reuse resurfaces in the semantic layer.** The Metric View
  re-applies the same time-bounded join to `dim_carrier` established in
  Gold, exposing a `carrier_name` dimension so Carrier Comparison
  rankings don't merge Comair and PSA Airlines under one `OH` bucket.
- **Small-sample route rankings.** An early version of the "best/worst
  on-time routes" charts surfaced routes with as few as 2-3 total
  flights, producing meaningless 0%/100% extremes. Rather than a hard
  volume cutoff, a Bayesian-shrunk measure (`on_time_arr_score`) pulls
  low-volume routes toward the global average proportionally to sample
  size — see data dictionary for the formula and its carrier-filter
  limitation.
- **Rollup bugs caught during dashboard build.** Two Gold-layer fields
  (`avg_*_min`, `total_distance_mi`) are correct at their native daily
  grain but produce wrong results if naively re-aggregated further
  (average-of-averages, and distance-conflated-with-volume,
  respectively). Both required flight-weighted formulas in the Metric
  View.
- **Platform constraint.** Widget-level dashboard filters can only
  reference Metric View dimensions, not measures — a `HAVING`-style
  volume threshold isn't expressible through the no-code filter UI.
  Worked around with the shrinkage measure above instead of a separate
  filtered SQL dataset.

## Known limitations

Historical data covers only 2004–2008, not the full 1987–2008 available in the built-in dataset — scoped down to fit Free Edition's compute/storage quota. An intentional, documented gap rather than a continuous 1987–2026 timeline.

Flight counts are not comparable across 2017/2018. A DOT reporting-threshold change adds ~27% volume at 2018-01 with no change in actual air traffic. Rate metrics remain valid. See Phase 2.

air_time_min is unreliable for 2004–2006, affecting ~256K rows across two unrelated source defects. Filter on AIRTIME_ELAPSED_MISMATCH before aggregating that column.

Times are local, not UTC. Neither source supplies a timezone, so scheduled_departure_local_ts carries a misleading +00:00 suffix. Use crs_elapsed_min for duration arithmetic.

2026 is partial (January–June, 3,488,373 rows). Exclude from year-over-year volume comparisons.

Carrier codes are not stable identifiers across 22 years — codes are reused and carriers merge.

- Carrier identity resolution depends on data only available 2009+.
  `DOT_ID_Reporting_Airline` — the permanent key used to prove the `OH`
  code-reuse case — doesn't exist in the 2004–2008 historical source. The
  pre-2009 portion of the `OH` fix relies on continuity-of-operation
  reasoning (no DOT ID to confirm against), not a hard key match.
- 17 airport records in `dim_airport` are manually curated, not
  pipeline-derived — sourced from external research rather than BTS data,
  since these airports don't appear in the 2009+ source at all.
  No geographic route map — `dim_airport` lacks latitude/longitude;
  deferred to a future enhancement.
- `on_time_arr_score` uses a fixed global-average prior; carrier-filtered
  views of the best/worst route charts should be treated as directional
  only (see data dictionary).

## Roadmap

- [x] **Phase 1 - Data Collection: Bronze** ingestion for both sources, verified and deduplicated ✓
- [ ] **Phase 2 - Silver**: Schema conformance, unified 146.7M-row table, two-tier data quality ✓
- [ ] **Phase 3 - Gold:** Aggregated, dashboard-ready tables ✓
- [ ] **Phase 4 — AI/BI Dashboards:** On-Time Overview, Carrier
      Comparison, and Route Analysis pages on a Unity Catalog Metric View
- [ ] **Phase 5 - Genie:** Natural-language querying over the Gold layer
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
|   ├── 05_gold_flights.ipynb
|   └── 06_metric_view.ipynb
├── scripts/
│   └── download_bts_ontime.py
└── docs/
    ├── data_dictionary.md
    └── data_dictionary_silver.md
```