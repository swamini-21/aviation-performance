# Data Dictionary — Airline On-Time Performance Analytics

## Sources

| Source | Table | Coverage | Status |
|---|---|---|---|
| Databricks built - in (`/databricks-datasets/airlines`) | `bronze.flights_historical` | 2004 - 2008 | Verified, deduplicated |
| BTS TranStats - Reporting Carrier On - Time Performance | `bronze.flights_recent` | 2009 - 2026 | **Verified** (confirmed via BTS - provided readme.html, 2011 - 01) |

---

## `bronze.flights_historical` (verified against actual data)

Source: ASA Data Expo airline dataset, as distributed via Databricks' built-in
`/databricks-datasets/airlines` sample data. Original files have no true header
row (first line of `part-00000` only); schema applied explicitly during ingestion.

**Known data quality note:** raw source contained 10x duplicate rows (identical
records repeated across 10 of 1,867 part - files). Deduplicated on business key
(Year, Month, DayofMonth, UniqueCarrier, FlightNum, DepTime, Origin, Dest)
during Bronze ingestion. Raw: 358,747,310 rows → after dedup: 35,874,667 rows
(90.0% reduction). Per-year counts (~7.0M - 7.5M/year) match real - world US
domestic flight volume for 2004 - 2008. Remaining gap between total rows and
distinct-column count (680,412) fully explained by cancelled flights with
NULL `DepTime`, not leftover duplication.

| Column | Type | Description |
|---|---|---|
| Year | Integer | Flight year |
| Month | Integer | Flight month (1 - 12) |
| DayofMonth | Integer | Day of month (1 - 31) |
| DayOfWeek | Integer | Day of week (1=Monday ... 7=Sunday) |
| DepTime | Integer | Actual departure time (local, hhmm). NULL for cancelled flights |
| CRSDepTime | Integer | Scheduled departure time (local, hhmm) |
| ArrTime | Integer | Actual arrival time (local, hhmm). NULL for cancelled flights |
| CRSArrTime | Integer | Scheduled arrival time (local, hhmm) |
| UniqueCarrier | String | Carrier code (e.g. AA, UA, DL) |
| FlightNum | String | Flight number |
| TailNum | String | Aircraft tail number |
| ActualElapsedTime | Integer | Actual flight time in minutes |
| CRSElapsedTime | Integer | Scheduled flight time in minutes |
| AirTime | Integer | Airborne time in minutes |
| ArrDelay | Integer | Arrival delay in minutes (negative = early) |
| DepDelay | Integer | Departure delay in minutes (negative = early) |
| Origin | String | Origin airport code |
| Dest | String | Destination airport code |
| Distance | Integer | Distance flown, miles |
| TaxiIn | Integer | Taxi-in time, minutes |
| TaxiOut | Integer | Taxi-out time, minutes |
| Cancelled | Integer | 1 = cancelled, 0 = not |
| CancellationCode | String | Reason code for cancellation |
| Diverted | Integer | 1 = diverted, 0 = not |
| CarrierDelay | Integer | Delay minutes attributed to carrier |
| WeatherDelay | Integer | Delay minutes attributed to weather |
| NASDelay | Integer | Delay minutes attributed to National Airspace System |
| SecurityDelay | Integer | Delay minutes attributed to security |
| LateAircraftDelay | Integer | Delay minutes attributed to late-arriving aircraft |
| IsArrDelayed | String | YES/NO flag - appears to flag any arrival delay (>0 min); semantics differ from recent set's ArrDel15, see mapping notes below |
| IsDepDelayed | String | YES/NO flag - appears to flag any departure delay (>0 min) |
| _source_system | String | Added by us: `databricks_datasets_airlines` |
| _ingestion_timestamp | Timestamp | Added by us: when the row was loaded |
| _source_file | String | Added by us: originating part - file path |

---

## `bronze.flights_recent` — VERIFIED against BTS readme.html (2011-01)

Source: BTS TranStats, "Reporting Carrier On-Time Performance (1987-present)".
**109 columns**, confirmed field-for-field from the readme.html BTS ships
alongside each monthly zip. Column order below matches the actual record layout.

**Final verified load:** 210 monthly files (Jan 2009 - mid 2026, accounting for
BTS's 3 month reporting lag), 110,841,156 rows, 112 columns (109 source +
3 metadata). Confirmed 210 distinct `_source_file` values, matching the 210
uploaded files exactly — no duplicates, no gaps. Per-year counts (~5.6M - 7.4M/year)
match real-world US domestic flight volume, including a visible dip in 2020
(4,688,354 rows) consistent with the COVID-19 travel collapse - a good
independent sanity check that the data reflects reality, not just internal
consistency.

**Data quality note:** one of the 210 uploaded files initially failed to land
correctly (dropped during a transient upload retry), caught via a distinct-file-count
check (209 vs. 210 expected) before being re-uploaded and re-ingested successfully.

| # | Column | Description |
|---|---|---|
| 1 | Year | Year |
| 2 | Quarter | Quarter (1-4) |
| 3 | Month | Month |
| 4 | DayofMonth | Day of Month |
| 5 | DayOfWeek | Day of Week |
| 6 | FlightDate | Flight Date (yyyymmdd) |
| 7 | Reporting_Airline | Unique Carrier Code (use for analysis across years — same code may be reused with numeric suffix for earlier carriers) |
| 8 | DOT_ID_Reporting_Airline | DOT-assigned unique airline ID |
| 9 | IATA_CODE_Reporting_Airline | IATA carrier code (not always unique over time) |
| 10 | Tail_Number | Aircraft tail number |
| 11 | Flight_Number_Reporting_Airline | Flight number |
| 12 | OriginAirportID | DOT airport ID (stable across code/name changes) |
| 13 | OriginAirportSeqID | DOT airport sequence ID (time-specific) |
| 14 | OriginCityMarketID | City market ID (consolidates airports serving same city) |
| 15 | Origin | Origin airport code |
| 16 | OriginCityName | Origin city name |
| 17 | OriginState | Origin state code |
| 18 | OriginStateFips | Origin state FIPS code |
| 19 | OriginStateName | Origin state name |
| 20 | OriginWac | Origin World Area Code |
| 21 | DestAirportID | Destination DOT airport ID |
| 22 | DestAirportSeqID | Destination airport sequence ID |
| 23 | DestCityMarketID | Destination city market ID |
| 24 | Dest | Destination airport code |
| 25 | DestCityName | Destination city name |
| 26 | DestState | Destination state code |
| 27 | DestStateFips | Destination state FIPS code |
| 28 | DestStateName | Destination state name |
| 29 | DestWac | Destination World Area Code |
| 30 | CRSDepTime | Scheduled departure time (local, hhmm) |
| 31 | DepTime | Actual departure time (local, hhmm) |
| 32 | DepDelay | Departure delay, minutes (negative = early) |
| 33 | DepDelayMinutes | Departure delay, minutes (early departures set to 0, not negative) |
| 34 | DepDel15 | Departure delay indicator, 15+ min (1=Yes) |
| 35 | DepartureDelayGroups | Departure delay bucketed in 15-min intervals |
| 36 | DepTimeBlk | Scheduled departure hourly time block |
| 37 | TaxiOut | Taxi-out time, minutes |
| 38 | WheelsOff | Wheels-off time (local, hhmm) |
| 39 | WheelsOn | Wheels-on time (local, hhmm) |
| 40 | TaxiIn | Taxi-in time, minutes |
| 41 | CRSArrTime | Scheduled arrival time (local, hhmm) |
| 42 | ArrTime | Actual arrival time (local, hhmm) |
| 43 | ArrDelay | Arrival delay, minutes (negative = early) |
| 44 | ArrDelayMinutes | Arrival delay, minutes (early arrivals set to 0) |
| 45 | ArrDel15 | Arrival delay indicator, 15+ min (1=Yes) |
| 46 | ArrivalDelayGroups | Arrival delay bucketed in 15-min intervals |
| 47 | ArrTimeBlk | Scheduled arrival hourly time block |
| 48 | Cancelled | Cancelled flight indicator (1=Yes) |
| 49 | CancellationCode | Reason for cancellation |
| 50 | Diverted | Diverted flight indicator (1=Yes) |
| 51 | CRSElapsedTime | Scheduled flight time, minutes |
| 52 | ActualElapsedTime | Actual flight time, minutes |
| 53 | AirTime | Airborne time, minutes |
| 54 | Flights | Number of flights (usually 1 per record) |
| 55 | Distance | Distance between airports, miles |
| 56 | DistanceGroup | Distance bucketed in 250-mile intervals |
| 57 | CarrierDelay | Delay minutes attributed to carrier |
| 58 | WeatherDelay | Delay minutes attributed to weather |
| 59 | NASDelay | Delay minutes attributed to National Airspace System |
| 60 | SecurityDelay | Delay minutes attributed to security |
| 61 | LateAircraftDelay | Delay minutes attributed to late-arriving aircraft |
| 62 | FirstDepTime | First gate departure time at origin (for gate returns) |
| 63 | TotalAddGTime | Total ground time away from gate (gate return/cancellation) |
| 64 | LongestAddGTime | Longest ground time away from gate |
| 65 | DivAirportLandings | Number of diverted airport landings |
| 66 | DivReachedDest | Diverted flight reached scheduled destination (1=Yes) |
| 67 | DivActualElapsedTime | Elapsed time for diverted flight reaching destination (ActualElapsedTime is NULL for diverted flights) |
| 68 | DivArrDelay | Arrival delay for diverted flight reaching destination (ArrDelay is NULL for diverted flights) |
| 69 | DivDistance | Distance between scheduled and actual diverted destination |
| 70-77 | Div1Airport ... Div1TailNum | Diverted airport 1 details (code, IDs, times, ground time, tail number) |
| 78-85 | Div2Airport ... Div2TailNum | Diverted airport 2 details |
| 86-93 | Div3Airport ... Div3TailNum | Diverted airport 3 details |
| 94-101 | Div4Airport ... Div4TailNum | Diverted airport 4 details |
| 102-109 | Div5Airport ... Div5TailNum | Diverted airport 5 details |

*(Div1–Div5 blocks each repeat the same 8 sub-fields: Airport, AirportID, AirportSeqID, WheelsOn, TotalGTime, LongestGTime, WheelsOff, TailNum — collapsed above for readability; expand if you end up using diversion data.)*

---

## Historical ↔ Recent column mapping (confirmed)

| Concept | Historical column | Recent column | Notes |
|---|---|---|---|
| Carrier | UniqueCarrier | Reporting_Airline | Direct match |
| Tail number | TailNum | Tail_Number | Direct match |
| Flight number | FlightNum | Flight_Number_Reporting_Airline | Direct match |
| Year/Month/Day | Year, Month, DayofMonth | Year, Month, DayofMonth | **Same column names in both - no conversion needed.** Recent also has bonus FlightDate (single date field) and Quarter, not present in historical. |
| Day of week | DayOfWeek | DayOfWeek | Direct match |
| Times, delays, distance, cancellation, diversion cause fields | Same names (CRSDepTime, DepTime, ArrTime, ArrDelay, DepDelay, TaxiIn, TaxiOut, Distance, Cancelled, CancellationCode, Diverted, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay, CRSElapsedTime, ActualElapsedTime, AirTime) | Same names | Direct match on all of these |
| Delay flag | IsArrDelayed / IsDepDelayed (YES/NO) | ArrDel15 / DepDel15 (1/0) | **Not a direct equivalent** - historical's flag appears to trigger on any delay >0 min; recent's flags specifically mean "delayed 15+ minutes." Needs an explicit decision in Silver: recompute a consistent threshold-based flag for both sources rather than treating these as the same field. |

## What's in `flights_recent` but not in `flights_historical`

The recent set is far richer - ~80 additional columns with no historical
equivalent, including: `Quarter`, all the airport ID/city/state fields
(`OriginAirportID`, `OriginCityName`, `OriginStateFips`, etc. and their Dest
equivalents), delay-bucket fields (`DepartureDelayGroups`, `DistanceGroup`,
`DepTimeBlk`), and the full diversion detail block (`Div1Airport` through
`Div5TailNum`).

**Open decision for Silver (Phase 2):** whether to carry these extra columns
forward (richer recent-years analysis, but an inconsistent schema pre/post
2009) or drop them at conformance time so historical and recent union cleanly
into one consistent table. No action needed now - just flagging it while both
schemas are fresh.