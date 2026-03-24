# Client/Vehicle Bridge Dataset Schema

## Dataset role
This dataset is a **reference bridge layer** between historical exports and future integrations. It is **not** the runtime production database used by the bot.

## Physical files
- `lira_normalized_database.xlsx` — analyst-friendly workbook with human-readable sheets and guidance rows.
- `lira_normalized_database.sqlite` — query-friendly snapshot for deterministic joins and scripted checks.

## Detected entities (current snapshot)
- `clients`
- `vehicles`
- `vehicle_owner_history`
- `invalid_phones`
- `schema_dictionary`
- `summary_metrics`
- XLSX `SourceMap` sheet (source lineage map)

## Canonical temporary format (for next imports)

### A) `clients` (canonical target fields)
| Field | Required | Meaning |
|---|---|---|
| `client_external_id` | yes | Source-side unique client id (maps from current `client_code`) |
| `full_name` | yes | Client full name (maps from `client_name`) |
| `normalized_phone` | no | 10-digit phone for matching (maps from `phone_norm`) |
| `raw_phone` | no | Original raw phone from source (maps from `phone_raw`) |
| `email` | no | Optional email from source imports |
| `source_system` | yes | Source label (`1c_export`, etc.) |
| `source_record_id` | yes | Record id in source batch |
| `match_status` | no | Matching quality/status if precomputed |
| `notes` | no | Free-form normalization notes |

### B) `vehicles` (canonical target fields)
| Field | Required | Meaning |
|---|---|---|
| `vehicle_external_id` | yes | Source-side unique vehicle id (maps from `vehicle_code`) |
| `owner_external_id` | no | Linked owner id (maps from `owner_client_code`) |
| `owner_name` | no | Owner display name |
| `vin` | no | Raw VIN if present |
| `normalized_vin` | no | Clean VIN/placeholder (maps from `vin_norm`) |
| `plate_number` | no | Plate number |
| `brand_model` | no | Model/brand text (maps from `vehicle_model`) |
| `year` | no | Manufacturing year |
| `latest_mileage` | no | Latest known mileage |
| `max_mileage` | no | Maximum observed mileage |
| `last_mileage_date` | no | Date of latest mileage |
| `source_system` | yes | Source label (`1c_export`, etc.) |
| `source_record_id` | yes | Record id in source batch |

### C) Linkage rules
1. Primary owner linkage: `vehicles.owner_client_code -> clients.client_code`.
2. Supportive linkage evidence: `vehicle_owner_history` by `vehicle_code`, date, and owner match status.
3. Missing owner:
   - allow `owner_external_id = NULL`;
   - keep `owner_name` if available;
   - mark `match_status` as unresolved/ambiguous in enrichment layers.
4. Placeholder VIN (`no_vin_*`) is **not** a real VIN and must not be used as strong identity key.
5. Incomplete/invalid phones must stay in `invalid_phones` or equivalent rejected bucket.

## Mandatory normalization rules
1. `normalized_phone`: exactly 10 digits, no `+7`, no leading `8`, no spaces/quotes/brackets/dashes.
2. Email is not a primary matching key.
3. Client matching priority: `phone` -> `fio` -> `vin`.
4. Placeholder VIN (`no_vin_*`) treated as synthetic placeholder only.
5. Mileage fields are independent matching signals:
   - `latest_mileage`
   - `max_mileage`
   - `last_mileage_date`

## Field mapping from current snapshot
- `clients.client_code` -> `client_external_id`
- `clients.client_name` -> `full_name`
- `clients.phone_norm` -> `normalized_phone`
- `clients.phone_raw` -> `raw_phone`
- `vehicles.vehicle_code` -> `vehicle_external_id`
- `vehicles.owner_client_code` -> `owner_external_id`
- `vehicles.vin_norm` -> `normalized_vin`
- `vehicles.plate_norm` -> `plate_number`
- `vehicles.vehicle_model` -> `brand_model`

## Update strategy (future batches)
1. Load next export into staging (`xlsx` or `sqlite`).
2. Re-run normalization rules (phone/VIN/name cleanup).
3. Upsert by `client_external_id` and `vehicle_external_id`.
4. Rebuild owner linkage confidence from latest history.
5. Recompute summary metrics and invalid phone bucket.
6. Record source batch metadata (`source_system`, export date, checksum).
