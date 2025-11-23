# Replenishment Algorithm Input Data

***Note: Algorithm and data has been sanitized*** 

## Files Overview

### Sales History (`sales_history.csv`)
- Historical transaction data covering 56 days (2025-04-20 to 2025-06-14)
- Daily grain sales by store and SKU
- Includes unit sales, revenue, and pricing information

### SKU Master Data (`sku_master_data.csv`)
- Product catalog with vendor assignments
- Packaging specifications (case sizes, inner packs)
- Presentation requirements and promotional settings

### Vendor Schedule (`vendor_schedule.csv`)
- Vendor delivery schedules and lead times to DC
- Order cutoff times and delivery day patterns
- Active vendor status tracking

### DC to Store Shipping (`dc_to_store_shipping.csv`)
- Fixed truck schedules from distribution centers to stores
- Transit times and arrival patterns
- Next scheduled departure and arrival dates

### Store-Vendor-DC Mapping (`store_vendor_dc_mapping.csv`)
- Supply chain routing configuration
- Links stores to vendors through distribution centers
- Category-specific routing and review buffer settings

### Inventory Position (`inventory_position.csv`)
- Current stock levels as of 2025-06-15 08:00:00
- On-hand and in-transit quantities by store and SKU
- Balance on hand (BOH) calculations

### Policy Configuration (`policy_configuration.csv`)
- Algorithm parameters and service level targets
- Z-score settings, velocity thresholds, and lookback periods
- Min/max order constraints

## Data Coverage

- **Stores**: STORE_001, STORE_002, STORE_003
- **Vendors**: VENDOR_A, VENDOR_B, VENDOR_C
- **Distribution Centers**: DC_EAST, DC_WEST
- **Product Categories**: PRODUCE, DAIRY, DELI
- **Time Period**: 56-day historical window through 2025-06-14
