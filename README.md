# aviation-performance

### Data Quality Issues

Discovered the built-in sample data (/databricks-dataset/airlines) contains ~10x replicated rows (identical records repeated across ~10 of ~1867 part-files). Verifies via row-count v/s real-worls scale sanity checks (per-year counts were ~70< v/s expected ~7M for actual US domestic flight volume) and cross-file duplicate inspection. Deduplicated on business key (Years, Month, Day, Carrier, FlightNum, depTime, Origin, dest) during Bronze ingestion - reduced 358.7M raw rows to 35.9M (90% reduction), matching expected scale.
