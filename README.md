# Replenishment Algorithm

***Note: Algorithm and data has been sanitized***



A production-ready implementation of a periodic review replenishment algorithm.

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Run with default settings (data from data/ folder, date: 2025-06-16)
python3 replenishment_algorithm.py

# Run with custom date
python3 replenishment_algorithm.py data 2025-06-12 output

# The algorithm will generate:
# - output/orders_YYYY-MM-DD.csv (primary order file)
# - output/order_details_YYYY-MM-DD.csv (detailed calculations)
```

## What It Does

The algorithm determines daily order quantities for each SKU to maintain target service levels while controlling inventory costs. It:

1. **Identifies** which store-vendor combinations need orders today based on shipping schedules and lead times
2. **Forecasts** demand using 56 days of historical sales data, adjusting for promotions
3. **Classifies** items as high velocity (≥12 units/week) or low velocity (<12 units/week)
4. **Calculates** order quantities using:
   - **High velocity**: Safety stock + cycle stock approach
   - **Low velocity**: Reorder point system (min/max)
5. **Rounds** to full case quantities
6. **Outputs** order recommendations with detailed calculations

## Key Features

- **Promotional handling**: Applies SKU-specific uplift factors for promoted items
- **Velocity-based logic**: Different calculation methods for fast vs slow-moving items
- **Safety stock**: Statistical buffer for high-velocity items based on demand variability
- **Presentation minimums**: Ensures adequate shelf presence (double facings)
- **Zero-data handling**: Gracefully handles new products with no sales history
- **Production-ready**: Comprehensive error handling, input validation, and logging
- **Type-safe**: Full type hints for better code maintainability and IDE support

## Input Files Required

Place all input CSV files in the `data/` directory:

1. `sales_history.csv` - Daily transaction data (56+ days)
2. `sku_master_data.csv` - Product catalog with vendor assignments
3. `vendor_schedule.csv` - Vendor lead times and delivery schedules
4. `dc_to_store_shipping.csv` - DC truck schedules to stores
5. `store_vendor_dc_mapping.csv` - Supply chain routing
6. `inventory_position.csv` - Current stock levels (on-hand + in-transit)
7. `policy_configuration.csv` - Algorithm parameters (Z-score, thresholds, etc.)

See `data/README.md` for detailed file specifications.

## Output Files

The algorithm generates two output files per run:

### 1. Orders (Primary Output)
Bare-bones order file with essential information:
- Store, Vendor, SKU identification
- Order quantity in units and cases
- DC departure and store arrival dates

### 2. Order Details (Supporting Calculations)
Comprehensive file showing all intermediate calculations:
- Demand metrics (daily avg, std dev, velocity class)
- Cycle stock and safety stock
- Inventory position
- Max inventory targets
- Gap calculations before rounding

## Algorithm Logic

Detailed step-by-step logic is documented in `replenishment_algorithm_logic_overview.md`.

**High-level flow:**
```
1. Which orders to place today? (timing calculation)
   ↓
2. What's the demand forecast? (56-day history + promotions)
   ↓
3. High or low velocity? (≥12 units/week threshold)
   ↓
4a. LOW velocity: Use min/max system
4b. HIGH velocity: Calculate safety stock
   ↓
5. Round to full cases
   ↓
6. Generate orders
```

## Configuration

Key parameters in `policy_configuration.csv`:

- **Z_SCORE**: 1.96
- **VELOCITY_THRESHOLD_WEEKLY**: 12 units
- **LOW_VEL_MAX_MULTIPLIER**: 10x daily demand
- **HISTORICAL_LOOKBACK_DAYS**: 56 days
- **REVIEW_BUFFER_DAYS**: 1 day

## Technical Details

- **Language**: Python 3.8+
- **Dependencies**: pandas>=1.3.0, numpy>=1.21.0 (see `requirements.txt`)
- **Type hints**: Full typing support for better code quality
- **Logging**: Structured logging with configurable levels (INFO, WARNING, ERROR, DEBUG)
- **Error handling**: Comprehensive validation and error messages
- **Data format**: CSV files with UTF-8 encoding
- **Date format**: ISO 8601 (YYYY-MM-DD)
- **Precision**: 1 decimal for units, 2 decimals for statistics

## File Structure

```
Algorithm/
├── README.md                       # This file
├── requirements.txt                # Python dependencies
├── replenishment_algorithm.py      # Main implementation
├── replenishment_algorithm_logic_overview.md  # Detailed specification
├── data/                           # Input data
│   ├── README.md
│   ├── sales_history.csv
│   ├── sku_master_data.csv
│   ├── vendor_schedule.csv
│   ├── dc_to_store_shipping.csv
│   ├── store_vendor_dc_mapping.csv
│   ├── inventory_position.csv
│   └── policy_configuration.csv
└── output/                         # Generated orders
    ├── orders_YYYY-MM-DD.csv
    └── order_details_YYYY-MM-DD.csv
```

## Notes

- The algorithm runs for a specific date and identifies which store-vendor combinations need orders on that date
- Order timing is calculated backward from DC departure dates minus vendor lead times and review buffer
- Zero-sales days are included in historical averages (not excluded)
- Promotional uplift applies to the entire order cycle when IS_ON_PROMO = TRUE
- All order quantities are constrained to be non-negative
