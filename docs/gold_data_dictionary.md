# Gold Layer Data Dictionary

Schema reference for `airline_analytics.gold`. Six tables: one atomic-grain
fact table, three dimensions, and two pre-aggregated summary tables at
different grains. See `README.md` (Phase 3) for the design rationale and
data quality findings behind these tables — this document covers schema
and join mechanics only.

---

## Join patterns (read this before querying)

Two of the three dimensions do **not** join to the fact table with a plain
`carrier_code = carrier_code` / `airport_code = airport_code` equi-join.
Getting this wrong silently produces wrong or duplicated rows.

**`dim_carrier` — time-bounded join.** The `OH` carrier code is shared by
two different airlines across different date ranges (see README, Phase 3
Findings). A plain equi-join on `carrier_code` will match every `OH`
flight to *both* `dim_carrier` rows, doubling those rows in any aggregate.
Always join on:

```sql
FROM gold.fct_flights f
JOIN gold.dim_carrier c
  ON f.carrier_code = c.carrier_code
 AND f.flight_date BETWEEN c.effective_start AND c.effective_end
```

**`dim_airport` — role-playing dimension.** One physical table represents
both "origin airport" and "destination airport." To get both names in one
row, join it twice with different aliases:

```sql
FROM gold.fct_flights f
JOIN gold.dim_airport o ON f.origin = o.airport_code
JOIN gold.dim_airport d ON f.dest   = d.airport_code
-- o.city_name = origin city, d.city_name = destination city
```

**`dim_date` — plain equi-join.** No special handling; join on
`flight_date = date_key`.

---

## `gold.fct_flights`

**Grain:** one row per flight. **Rows:** 146,715,805. **Coverage:**
2004–2026. Curated from `silver.flights` — DQ-internal columns dropped,
`_dq_warnings` array collapsed into two booleans, three derived columns
added. This is the atomic-grain table intended for Genie and any ad hoc
querying; use the aggregate tables below for high-volume dashboard tiles.

| Column | Type | Description |
|---|---|---|
| `flight_key` | string | SHA-256 hash of the natural key. Primary key. |
| `flight_date` | date | Flight date. Join key to `dim_date.date_key`. |
| `year` | int | Calendar year. |
| `quarter` | int | Calendar quarter (1–4). |
| `month` | int | Calendar month (1–12). |
| `day_of_month` | int | Day of month. |
| `day_of_week` | int | 1 = Monday … 7 = Sunday. |
| `carrier_code` | string | `UniqueCarrier` (pre-2009) / `Reporting_Airline` (2009+). Join key to `dim_carrier` — see time-bounded join above. **Not a stable identifier across the full range** (see `OH` reuse case in README). |
| `tail_number` | string | Aircraft tail number. |
| `flight_number` | string | Flight number as reported. |
| `origin` | string | Origin airport code. Join key to `dim_airport`. |
| `dest` | string | Destination airport code. Join key to `dim_airport`. |
| `crs_dep_time_hhmm` | int | Scheduled departure, local time, hhmm. `2400` normalized to `0`. |
| `dep_time_hhmm` | int | Actual departure, local time, hhmm. Null if cancelled. |
| `crs_arr_time_hhmm` | int | Scheduled arrival, local time, hhmm. |
| `arr_time_hhmm` | int | Actual arrival, local time, hhmm. Null if cancelled. |
| `scheduled_departure_local_ts` | timestamp | Local wall-clock timestamp at origin — **not UTC**. |
| `dep_delay_min` | int | Signed departure delay in minutes; negative = early. Null if cancelled. |
| `arr_delay_min` | int | Signed arrival delay in minutes; negative = early. Null if cancelled. |
| `dep_del15` | boolean | `dep_delay_min >= 15`. Null if cancelled. |
| `arr_del15` | boolean | `arr_delay_min >= 15`. Null if cancelled. |
| `crs_elapsed_min` | int | Scheduled elapsed flight time, minutes. |
| `actual_elapsed_min` | int | Actual elapsed flight time, minutes. Null if cancelled. |
| `air_time_min` | int | Airborne time, minutes. Null if cancelled. See `air_time_unreliable` below. |
| `taxi_out_min` | int | Taxi-out time, minutes. Null if cancelled. |
| `taxi_in_min` | int | Taxi-in time, minutes. Null if cancelled. |
| `distance_mi` | int | Route distance, miles. |
| `is_cancelled` | boolean | Flight was cancelled. |
| `cancellation_reason` | string | Carrier / Weather / NAS / Security. Null unless cancelled (~98.5% null — structural, not missing data). |
| `is_diverted` | boolean | Flight was diverted. |
| `carrier_delay_min` | int | Minutes of carrier-caused delay. Populated only when `arr_delay_min >= 15` (~81.7% null by design). |
| `weather_delay_min` | int | Minutes of weather-caused delay. Same null pattern as above. |
| `nas_delay_min` | int | Minutes of National Airspace System delay. Same null pattern. |
| `security_delay_min` | int | Minutes of security-caused delay. Same null pattern. |
| `late_aircraft_delay_min` | int | Minutes of delay from a late-arriving aircraft. Same null pattern. |
| `has_delay_cause_detail` | boolean | True when the five delay-cause columns above are populated. |
| `origin_airport_id` | int | BTS numeric airport ID. Null pre-2009 (not collected in the historical source). |
| `dest_airport_id` | int | BTS numeric airport ID. Null pre-2009. |
| `wheels_off_hhmm` | int | Wheels-off time, local, hhmm. BTS only; null pre-2009. |
| `wheels_on_hhmm` | int | Wheels-on time, local, hhmm. BTS only; null pre-2009. |
| `div_airport_landings` | int | Count of diversion landings. `0` for non-diverted flights (fully populated, not sparse). |
| `data_source` | string | Which Bronze source the row came from (renamed from `_source_system`). |
| `has_dq_warning` | boolean | True if any Silver-layer DQ warning was raised for this row. |
| `air_time_unreliable` | boolean | True specifically for the JetBlue/Hawaiian/SkyWest `AIRTIME_ELAPSED_MISMATCH` cases documented in Phase 2 — treat `air_time_min` with caution when true. |
| `_gold_processed_at` | timestamp | Pipeline timestamp when this row was written to Gold. |
| `route` | string | `origin` + `dest` concatenated, e.g. `"JFK-LAX"`. Engineered for grouping/filtering. |
| `departure_time_block` | string | Scheduled-departure bucket: Early Morning / Morning / Afternoon / Evening / Night. Uses scheduled (not actual) time, so cancelled flights still get a value. |
| `haul_length` | string | Distance bucket: Short-haul (<500mi) / Medium-haul (500–1500mi) / Long-haul (>1500mi). |

**Columns dropped from Silver during Gold curation** (redundant or
derivable, no analytical loss): `cancellation_code` (superseded by
`cancellation_reason`), `crs_dep_hour` (derivable from
`crs_dep_time_hhmm`), `dep_delay_min_pos`, `arr_delay_min_pos` (BTS's
zero-floored delay convention — derivable via `GREATEST(x, 0)`),
`_ingestion_timestamp`, `_silver_processed_at`, `_dq_warnings` (collapsed
into the two booleans above).

---

## `gold.dim_date`

**Grain:** one row per calendar day. **Rows:** 8,401. **Coverage:**
2004-01-01 through 2026-12-31, generated (not derived from flight data),
so every calendar day exists whether or not flights occurred.

| Column | Type | Description |
|---|---|---|
| `date_key` | date | Calendar date. Join key from `fct_flights.flight_date`. |
| `year` | int | Calendar year. |
| `quarter` | int | Calendar quarter (1–4). |
| `month` | int | Calendar month (1–12). |
| `month_name` | string | Full month name, e.g. "January". |
| `day_of_month` | int | Day of month. |
| `day_of_week` | int | 1 = Monday … 7 = Sunday — matches `fct_flights.day_of_week`. |
| `day_name` | string | Full weekday name, e.g. "Monday". |
| `is_weekend` | boolean | True for Saturday/Sunday. |
| `is_us_federal_holiday` | boolean | True on US federal holidays, including weekend-observed shifts (e.g. July 4th falling on Sunday also flags the Monday observed date). Derived using the Python `holidays` package. |
| `holiday_name` | string | Holiday name if `is_us_federal_holiday` is true, else null. |

---

## `gold.dim_carrier`

**Grain:** one row per carrier code per effective date range. **Rows:**
29 (28 carrier codes, one of which — `OH` — has two rows). **Time-bounded
dimension** — see join pattern above before querying.

| Column | Type | Description |
|---|---|---|
| `carrier_code` | string | Two-letter carrier code. Join key from `fct_flights.carrier_code`. Not unique alone for `OH`. |
| `carrier_name` | string | Airline name. |
| `effective_start` | date | Start of the date range this code→name mapping is valid for. `1900-01-01` for codes with no known reuse. |
| `effective_end` | date | End of the date range this mapping is valid for. `9999-12-31` for codes with no known reuse. |

**`OH` rows specifically:**

| carrier_code | carrier_name | effective_start | effective_end |
|---|---|---|---|
| OH | Comair | 1900-01-01 | 2010-12-31 |
| OH | PSA Airlines | 2018-01-01 | 9999-12-31 |

Confirmed via `DOT_ID_Reporting_Airline` (BTS's permanent carrier
identifier, available 2009+): DOT ID `20417` (Comair) last appears in
2010; DOT ID `20397` (PSA Airlines) first appears in 2018. The code was
unused 2011–2017 — a dormancy gap, not an overlapping handoff, so there is
no ambiguous transition period. The 2004–2008 portion of the Comair range
relies on continuity-of-operation reasoning rather than a DOT ID match,
since the pre-2009 source has no DOT ID field (see README, Known
Limitations).

---

## `gold.dim_airport`

**Grain:** one row per airport code. **Rows:** 426 (409 from BTS 2009+
source metadata, 17 manually enriched). Role-playing dimension — see join
pattern above.

| Column | Type | Description |
|---|---|---|
| `airport_code` | string | 3-letter airport code. Join key from `fct_flights.origin` / `fct_flights.dest`. |
| `airport_id` | int | BTS numeric airport ID. Null for the 17 manually-enriched pre-2009-only airports (BTS ID doesn't exist for them). |
| `city_name` | string | City name. Casing normalized (`initcap`) to fix inconsistent casing found in the BTS source (e.g. `"CONCORD, NC"` vs `"Concord, NC"` both resolving to one row). Note: `initcap` can mis-capitalize names like McAllen → "Mcallen" — not corrected. |
| `state_code` | string | 2-letter state code. |
| `state_name` | string | Full state name. Casing normalized as above. |
| `data_coverage` | string | `full_history` (metadata sourced from BTS 2009+ data) or `pre_2009_only` (metadata manually researched — the airport code appears only in 2004–2008 data and never recurs in 2009+). |

---

## `gold.agg_daily_carrier_route_performance`

**Grain:** one row per `(flight_date, carrier_code, origin, dest)`. **Rows:**
52,154,788. Pre-aggregated from `gold.fct_flights` for dashboard
performance — reconciles exactly against it on flight counts,
cancellations, diversions, and delay-cause minute sums.

| Column | Type | Description |
|---|---|---|
| `flight_date` | date | Join key to `dim_date`. |
| `carrier_code` | string | Join key to `dim_carrier` (time-bounded — see join pattern above). |
| `origin` | string | Join key to `dim_airport`. |
| `dest` | string | Join key to `dim_airport`. |
| `route` | string | `origin`-`dest`, carried through from `fct_flights` to avoid re-deriving. |
| `flight_count` | bigint | Total scheduled flights in this group. |
| `completed_count` | bigint | Flights neither cancelled nor diverted. |
| `cancelled_count` | bigint | Cancelled flights. |
| `diverted_count` | bigint | Diverted flights. |
| `avg_dep_delay_min` | double | Average signed departure delay, non-cancelled flights only. |
| `avg_arr_delay_min` | double | Average signed arrival delay, non-cancelled flights only. |
| `dep_del15_count` | bigint | Count of flights with `dep_del15 = true`. |
| `arr_del15_count` | bigint | Count of flights with `arr_del15 = true`. |
| `avg_taxi_out_min` | double | Average taxi-out time. |
| `avg_taxi_in_min` | double | Average taxi-in time. |
| `total_distance_mi` | bigint | Sum of distance across all flights in the group. |
| `carrier_delay_min` | bigint | Sum of carrier-caused delay minutes. **Coalesced to `0`** when no flight in the group had delay-cause detail (never null — see README design decisions). |
| `weather_delay_min` | bigint | Sum of weather-caused delay minutes. Coalesced to `0`. |
| `nas_delay_min` | bigint | Sum of NAS delay minutes. Coalesced to `0`. |
| `security_delay_min` | bigint | Sum of security delay minutes. Coalesced to `0`. |
| `late_aircraft_delay_min` | bigint | Sum of late-aircraft delay minutes. Coalesced to `0`. |
| `_gold_processed_at` | timestamp | Pipeline timestamp when this row was written. |

---

## `gold.agg_monthly_carrier_performance`

**Grain:** one row per `(year, month, carrier_code)`. **Rows:** 4,421 (well
under the ~7,700 theoretical maximum of 23 years × 12 months × 28 carrier
codes, since not every carrier operated in every month — e.g. `VX` only
spans 2012–2018). Built directly from `gold.fct_flights` (not from the
daily aggregate, to avoid averaging already-averaged delay columns).
Intended for dashboard trend-line tiles that don't need route-level
detail. Reconciles exactly against `gold.fct_flights` on flight counts and
delay-cause minute sums.

| Column | Type | Description |
|---|---|---|
| `year` | int | Calendar year. |
| `month` | int | Calendar month (1–12). |
| `carrier_code` | string | Join key to `dim_carrier` (time-bounded — see join pattern above). |
| `flight_count` | bigint | Total scheduled flights in this group. |
| `completed_count` | bigint | Flights neither cancelled nor diverted. |
| `cancelled_count` | bigint | Cancelled flights. |
| `diverted_count` | bigint | Diverted flights. |
| `avg_dep_delay_min` | double | Average signed departure delay, non-cancelled flights only. |
| `avg_arr_delay_min` | double | Average signed arrival delay, non-cancelled flights only. |
| `dep_del15_count` | bigint | Count of flights with `dep_del15 = true`. |
| `arr_del15_count` | bigint | Count of flights with `arr_del15 = true`. |
| `avg_taxi_out_min` | double | Average taxi-out time. |
| `avg_taxi_in_min` | double | Average taxi-in time. |
| `total_distance_mi` | bigint | Sum of distance across all flights in the group. |
| `carrier_delay_min` | bigint | Sum of carrier-caused delay minutes. Coalesced to `0`. |
| `weather_delay_min` | bigint | Sum of weather-caused delay minutes. Coalesced to `0`. |
| `nas_delay_min` | bigint | Sum of NAS delay minutes. Coalesced to `0`. |
| `security_delay_min` | bigint | Sum of security delay minutes. Coalesced to `0`. |
| `late_aircraft_delay_min` | bigint | Sum of late-aircraft delay minutes. Coalesced to `0`. |
| `_gold_processed_at` | timestamp | Pipeline timestamp when this row was written. |
