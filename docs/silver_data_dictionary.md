# Data Dictionary — Silver Layer

`airline_analytics.silver.flights`

**Grain:** one row per scheduled flight leg.
**Coverage:** 2004-01-01 → 2026-06-30 (2026 partial).
**Rows:** 146,715,805.
**Clustering:** `CLUSTER BY (flight_date, origin)`.

Two source columns are listed for each field. `—` means the source has no equivalent.
`derived` means the value is computed in `_add_derived()` rather than read from either source.

Source A = `bronze.flights_historical` (ASA Data Expo, 2004–2008)
Source B = `bronze.flights_recent` (BTS TranStats, 2009–2026)

---

## Identity and date

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `flight_key` | STRING | derived | derived | SHA-256 of the natural key. Used for dedup; not a stable business key. |
| `flight_date` | DATE | `make_date(Year, Month, DayofMonth)` | `FlightDate` | Source A has no date column; constructed from parts. |
| `year` | INT | `Year` | `Year` | Predicate column for `replaceWhere` writes. |
| `quarter` | INT | derived | derived | `quarter(flight_date)`. Source A has no `Quarter`; derived on both for consistency. |
| `month` | INT | `Month` | `Month` | |
| `day_of_month` | INT | `DayofMonth` | `DayofMonth` | |
| `day_of_week` | INT | `DayOfWeek` | `DayOfWeek` | 1 = Monday … 7 = Sunday. |

**Natural key:** `(flight_date, carrier_code, flight_number, origin, dest, crs_dep_time_hhmm)`

## Carrier and route

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `carrier_code` | STRING | `UniqueCarrier` | `Reporting_Airline` | IATA-style code, uppercased. Not stable across 22 years — codes are reused and carriers merge. |
| `tail_number` | STRING | `TailNum` | `Tail_Number` | Aircraft registration. Placeholder junk (`0`, `000000`, `UNKNOW`) and values under 3 chars mapped to NULL. |
| `flight_number` | STRING | `FlightNum` | `Flight_Number_Reporting_Airline` | STRING in A, INT in B; conformed to STRING. |
| `origin` | STRING | `Origin` | `Origin` | 3-letter airport code, uppercased. |
| `dest` | STRING | `Dest` | `Dest` | |

City and state are deliberately **not** carried here — they are attributes of the airport,
not the flight, and Source A does not supply them. They belong in a `silver.airports`
reference table that both eras join to.

## Times

All times are **local to the relevant airport**. Neither source provides a timezone column.

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `crs_dep_time_hhmm` | INT | `CRSDepTime` | `CRSDepTime` | Scheduled departure as hhmm. `2400` normalised to `0`; values that don't decompose into a valid hour/minute → NULL. |
| `dep_time_hhmm` | INT | `DepTime` | `DepTime` | Actual departure. NULL for cancelled flights. |
| `crs_arr_time_hhmm` | INT | `CRSArrTime` | `CRSArrTime` | |
| `arr_time_hhmm` | INT | `ArrTime` | `ArrTime` | NULL for cancelled flights. |
| `crs_dep_hour` | INT | derived | derived | `floor(crs_dep_time_hhmm / 100)`. Convenience column for time-of-day grouping. |
| `scheduled_departure_local_ts` | TIMESTAMP | derived | derived | `flight_date` + `crs_dep_time_hhmm`. **Local wall-clock, not UTC** — see limitation below. |

> **`scheduled_departure_local_ts` is not UTC.** Spark renders it with a `+00:00` suffix
> because it has no way to represent "no timezone". The value is the correct local time at
> the origin airport; the suffix is meaningless. Do not use this column for cross-timezone
> duration arithmetic — use `crs_elapsed_min`.

## Delay measures

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `dep_delay_min` | INT | `DepDelay` | `DepDelay` | Signed. Negative = departed early. |
| `arr_delay_min` | INT | `ArrDelay` | `ArrDelay` | Signed. Negative = arrived early. |
| `dep_delay_min_pos` | INT | derived | derived | `greatest(dep_delay_min, 0)`. BTS convention for "delay minutes". |
| `arr_delay_min_pos` | INT | derived | derived | |
| `dep_del15` | BOOLEAN | **derived** | **derived** | `dep_delay_min >= 15`. NULL when delay is NULL. |
| `arr_del15` | BOOLEAN | **derived** | **derived** | `arr_delay_min >= 15`. NULL when delay is NULL. |

> **The 15-minute flags are computed, not mapped.** Source A's `IsArrDelayed` / `IsDepDelayed`
> are `YES`/`NO` for **any** delay ≥ 1 min; Source B's `ArrDel15` / `DepDel15` are `0`/`1` for
> delays ≥ 15 min. These are different metrics. Both are dropped and the flags recomputed from
> signed minutes on both sides using the BTS definition, so the two eras are comparable.

## Duration and distance

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `crs_elapsed_min` | INT | `CRSElapsedTime` | `CRSElapsedTime` | Scheduled gate-to-gate. |
| `actual_elapsed_min` | INT | `ActualElapsedTime` | `ActualElapsedTime` | Actual gate-to-gate. Reliable across the full range. |
| `air_time_min` | INT | `AirTime` | `AirTime` | Wheels-off to wheels-on. **Unreliable 2004–2006** — see the defects note below. |
| `taxi_out_min` | INT | `TaxiOut` | `TaxiOut` | |
| `taxi_in_min` | INT | `TaxiIn` | `TaxiIn` | |
| `distance_mi` | INT | `Distance` | `Distance` | Statute miles. |

Identity in clean data: `air_time_min = actual_elapsed_min − taxi_out_min − taxi_in_min`.
Deviation beyond 15 min raises `AIRTIME_ELAPSED_MISMATCH`.

> **`air_time_min` is unreliable for 2004–2006.** Two unrelated source defects — JetBlue and
> Hawaiian time-zone offsets (2004–2006) and a SkyWest reporting fault (Jan–Jul 2004) —
> affect ~256K rows. Filter out rows carrying `AIRTIME_ELAPSED_MISMATCH` before aggregating
> this column. `actual_elapsed_min` is unaffected.

## Status

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `is_cancelled` | BOOLEAN | `Cancelled` | `Cancelled` | INT `0`/`1` in A, DOUBLE `0.0`/`1.0` in B. NULL-safe to `false`. |
| `cancellation_code` | STRING | `CancellationCode` | `CancellationCode` | `A`/`B`/`C`/`D`. Same domain in both sources — no mapping required. NULL when not cancelled. |
| `cancellation_reason` | STRING | derived | derived | A → Carrier, B → Weather, C → National Air System, D → Security. |
| `is_diverted` | BOOLEAN | `Diverted` | `Diverted` | |

## Delay attribution

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `carrier_delay_min` | INT | `CarrierDelay` | `CarrierDelay` | Populated only when `arr_delay_min >= 15`. |
| `weather_delay_min` | INT | `WeatherDelay` | `WeatherDelay` | |
| `nas_delay_min` | INT | `NASDelay` | `NASDelay` | National Air System. |
| `security_delay_min` | INT | `SecurityDelay` | `SecurityDelay` | |
| `late_aircraft_delay_min` | INT | `LateAircraftDelay` | `LateAircraftDelay` | |
| `has_delay_cause_detail` | BOOLEAN | derived | derived | True when attribution is present. Use to avoid treating "not applicable" as zero. |

These five sum to `arr_delay_min_pos` when populated. They are NULL — not zero — for
on-time flights, so `AVG()` over the full table silently excludes them.

## BTS-only columns

NULL for all rows from Source A (2004–2008). Guarded by `opt()` so a missing source column
degrades to typed NULLs rather than failing the build.

| Column | Type | Source A | Source B | Notes |
|---|---|---|---|---|
| `origin_airport_id` | INT | — | `OriginAirportID` | Stable DOT airport ID. Survives code reuse; join key for BTS lookup tables. |
| `dest_airport_id` | INT | — | `DestAirportID` | |
| `wheels_off_hhmm` | INT | — | `WheelsOff` | ~1.8% NULL, matching the cancellation rate — cancelled aircraft never take off. |
| `wheels_on_hhmm` | INT | — | `WheelsOn` | |
| `div_airport_landings` | INT | — | `DivAirportLandings` | Count of diversion landings. |

## Lineage and data quality

| Column | Type | Notes |
|---|---|---|
| `_source_system` | STRING | `asa_data_expo` (2004–2008) or `bts_transtats` (2009–2026). |
| `_ingestion_timestamp` | TIMESTAMP | Carried from Bronze. Tie-breaker for dedup. |
| `_silver_processed_at` | TIMESTAMP | Set at write time. |
| `_dq_warnings` | ARRAY&lt;STRING&gt; | Soft anomalies. Empty array (not NULL) when clean. |

`silver.flights_quarantine` carries all 49 columns above plus:

| Column | Type | Notes |
|---|---|---|
| `_dq_errors` | ARRAY&lt;STRING&gt; | Hard failures. Currently empty — no row has ever been quarantined. |

---

## Data quality reason codes

### Hard failures → `silver.flights_quarantine`

Row cannot be dated, routed, or attributed. Zero occurrences across 146.7M rows.

| Code | Condition |
|---|---|
| `MISSING_FLIGHT_DATE` | `flight_date IS NULL` |
| `MISSING_CARRIER` | `carrier_code IS NULL` |
| `MISSING_ROUTE` | `origin IS NULL OR dest IS NULL` |
| `ORIGIN_EQUALS_DEST` | `origin = dest` |
| `MISSING_SCHEDULED_DEPARTURE` | `crs_dep_time_hhmm IS NULL` |
| `INVALID_DISTANCE` | `distance_mi IS NULL OR distance_mi <= 0` |

### Soft warnings → `_dq_warnings` on the retained row

| Code | Condition | Observed |
|---|---|---|
| `AIRTIME_ELAPSED_MISMATCH` | `abs(air_time_min − (actual_elapsed_min − taxi_out_min − taxi_in_min)) > 15` | 2004: 207,046 · 2006: 56,919 · 2005: 48,169 · 2021: 7 · 2024: 4 |
| `AIRTIME_EXCEEDS_ELAPSED` | `air_time_min > actual_elapsed_min` | 2004: 188,729 · 2006: 28,436 · 2005: 24,070 |
| `COMPLETED_WITHOUT_ARRIVAL_DATA` | not cancelled, not diverted, `arr_delay_min IS NULL` | 2018: 350 · elsewhere ≤ 1/year |
| `IMPLAUSIBLE_ARR_DELAY` | `abs(arr_delay_min) > 2880` (48 h) | 2–27 per year, 2020–2026. Genuine extreme delays. |
| `NON_POSITIVE_ELAPSED` | `actual_elapsed_min <= 0` | 2004: 39 · 2005: 5 |
| `CANCELLED_BUT_ARRIVED` | cancelled with an arrival time present | none |
| `NEGATIVE_TAXI` | `taxi_out_min < 0` | none |
| `IMPLAUSIBLE_DISTANCE` | `distance_mi > 6000` (longest US domestic ≈ 5,100 mi) | none |

`AIRTIME_EXCEEDS_ELAPSED` and `AIRTIME_ELAPSED_MISMATCH` overlap by design. The first flags a
physical impossibility and fires only on overstated air time. The second flags inconsistency
in either direction and catches the understated westbound legs the first rule structurally
cannot see.

---

## Source columns deliberately dropped

**From Source A:** `IsArrDelayed`, `IsDepDelayed` — superseded by derived `arr_del15` /
`dep_del15`; retaining them would invite the incorrect cross-era comparison.

**From Source B:** `DepDel15`, `ArrDel15` (same reason); `DepDelayMinutes`,
`ArrDelayMinutes` (recomputed as `*_min_pos`); `Quarter` (derived); `OriginCityName`,
`OriginState`, `DestCityName`, `DestState` (belong in `silver.airports`); plus ~70 further
BTS columns not carried into Silver — delay groupings, time blocks, diversion detail,
airport sequence and city-market IDs, WAC codes, and the always-`1` `Flights` column.

Bronze retains every source column, so anything dropped here can be recovered by extending
the conform functions and re-running the affected years.
