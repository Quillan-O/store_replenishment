# Replenishment Algorithm Logic

***Note: Algorithm and data has been sanitized*** 



## Purpose

- Decide daily order quantities for each SKU to hit a target cycle service level while controlling inventory cost
- Use a periodic review policy with constant lead time and a configurable service target
- Calculate order quantities for both high and low velocity items

## Algorithm Overview

### How It Works

Every day, the algorithm answers one question: **"How much of each product should we order today?"**

Here's the logic in simple terms:

**1. Which orders do we need to place today?**

   - If a DC truck leaves for a store in 7 days, and the vendor takes 5 days to deliver to the DC, plus we need 1 day to review, then we must order from that vendor TODAY (7 - 5 - 1 = 1 day from now = today)
   - We only calculate orders for store-vendor combinations where the timing works out to "order today"

**2. How much demand should we plan for?**
   - Look at the last 8 weeks of sales history to understand typical daily demand
   - Adjust for promotions: if a SKU is on promotion during the order cycle, multiply demand by its uplift factor
   - Calculate how much we'll need to cover the time until the next delivery arrives (the "order cycle")

**3. Do we use a simple or sophisticated approach?**
   - **Low velocity items** (< 12 units/week): Use a simple min/max system. These items don't sell often enough to predict variability, so we just set safe minimum and maximum inventory levels.
   - **High velocity items** (≥ 12 units/week): Use safety stock calculations. These items sell consistently, so we can statistically model demand variability and calculate a buffer to prevent stockouts.

**4. For low velocity items:**
   - Min = enough to cover expected demand during the order cycle
   - Max = greater of (10× daily demand) or (2 units)
   - If current inventory > Min, don't order
   - If current inventory ≤ Min, order enough to reach Max (plus what we'll need during shipping time)

**5. For high velocity items:**
   - Calculate a "safety stock" buffer based on how unpredictable the demand is
   - Set target inventory = expected demand + safety stock
   - But also make sure we have enough for good shelf presentation (at least 2 facings)
   - Take the higher of these two requirements
   - Order enough to reach that target (accounting for what we have and what we'll use while the order is in transit)

**6. Round up to full cases**
   - Can't order partial cases, so round up to the nearest case pack size
   - Submit orders to vendors at their cutoff time

## Output Tables

### Table 1: Orders (Primary Output)
Bare-bones order file showing what to order for each store-SKU-vendor combination.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| RUN_DATE | Date | Date when algorithm was executed | 2025-06-15 |
| STORE_ID | String/Int | Store identifier | "STORE_001" |
| VENDOR_ID | String | Vendor identifier | "VENDOR_A" |
| SKU | String | Stock Keeping Unit identifier | "SKU12345" |
| DESCRIPTION | String | Product description | "Organic Bananas 1lb" |
| ORDER_UNITS | Float | Final order quantity in units | 168.0 |
| **ORDER_CASES** | **Float** | **Order quantity in cases** | **7.0** |
| CASE_SIZE | Int | Units per case | 24 |
| DC_DEPARTURE_DATE | Date | When truck leaves DC | 2025-06-22 |
| STORE_ARRIVAL_DATE | Date | When order arrives at store | 2025-06-24 |

### Table 2: Order Details (Supporting Calculations)
Detailed calculations showing why each order quantity was recommended.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| RUN_DATE | Date | Date when algorithm was executed | 2025-06-15 |
| STORE_ID | String/Int | Store identifier | "STORE_001" |
| VENDOR_ID | String | Vendor identifier | "VENDOR_A" |
| SKU | String | Stock Keeping Unit identifier | "SKU12345" |
| DESCRIPTION | String | Product description | "Organic Bananas 1lb" |
| CATEGORY | String | Product category | "PRODUCE" |
| VELOCITY_CLASS | String | High or Low velocity | "HIGH" |
| **Demand Metrics** | | | |
| DAILY_AVG_UNITS_SOLD | Float | Mean daily demand (μ) | 12.5 |
| DAILY_SD_UNITS_SOLD | Float | Std dev of daily demand (σ) | 6.2 |
| ORDER_CYCLE_DAYS | Int | Days between shipments | 7 |
| CYCLE_STOCK | Float | Expected demand over cycle | 93.16 |
| **Lead Time** | | | |
| VENDOR_LEAD_TIME_DAYS | Int | Vendor to DC lead time | 5 |
| DC_TRANSIT_DAYS | Int | DC to store transit time | 2 |
| TOTAL_LEAD_TIME_DAYS | Int | Total lead time | 7 |
| LEAD_TIME_DEMAND | Float | Expected demand during lead time | 87.5 |
| **Inventory Position** | | | |
| STOCK_ON_HAND | Float | Physical inventory in store | 45.0 |
| STOCK_IN_TRANSIT | Float | Units already ordered | 24.0 |
| BALANCE_ON_HAND | Float | BOH = On hand + in transit | 69.0 |
| **Safety Stock (High Velocity Only)** | | | |
| Z_SCORE | Float | Service level z-score | 1.96 |
| SAFETY_STOCK | Float | Safety buffer units | 32.1 |
| MAX_2_PRESENTATION | Float | Max(double facings, case pack) | 24.0 |
| **Order Calculation** | | | |
| MAX_INVENTORY_TARGET | Float | Max inventory level | 125.26 |
| GAP_BEFORE_ROUNDING | Float | Max - BOH + lead time demand | 143.76 |
| ORDER_UNITS | Float | Final order quantity | 168.0 |
| ORDER_CASES | Float | Order in cases | 7.0 |

### Output File Format Notes
- **Orders Table**: Save as `orders_{STORE_ID}_{RUN_DATE}.csv`
- **Order Details Table**: Save as `order_details_{STORE_ID}_{RUN_DATE}.csv`
- All dates in ISO format (YYYY-MM-DD)
- All numeric fields rounded to 1 decimal place for units, 2 decimals for statistics
- Include header row with field names
- UTF-8 encoding

## Preprocessing and Initial Calculations

### Step 1: Determine Which Store-Vendor Combinations to Process Today

**Backward calculation from store need to vendor order timing:**

For each Store-Vendor-DC combination:
1. Get next DC departure date for the store (from Table 4: DC to Store Shipping Schedule)
2. Get vendor lead time to DC (from Table 3: Vendor Schedule)
3. Get review buffer days (from Table 5: Store-Vendor-DC Mapping, typically 1 day)
4. Calculate vendor order must be placed by: `DC_DEPARTURE_DATE - VENDOR_LEAD_TIME_DAYS - REVIEW_BUFFER_DAYS`
5. **If this date = TODAY**: Process this store-vendor combination
6. For each Store-Vendor combination identified, process all SKUs supplied by that vendor (from Table 2 where VENDOR_ID matches)

**Example:**
- Today = 2025-06-15
- Next DC truck departs for Store_001 = 2025-06-22 (Monday)
- Vendor A lead time = 5 days
- Review buffer = 1 day
- Order must be placed by: 2025-06-22 - 5 - 1 = 2025-06-16
- Since 2025-06-16 ≠ TODAY, do NOT process Vendor A for Store_001 today

**Another Example:**
- Today = 2025-06-16
- Next DC truck departs for Store_001 = 2025-06-22 (Monday)
- Vendor A lead time = 5 days
- Review buffer = 1 day
- Order must be placed by: 2025-06-22 - 5 - 1 = 2025-06-16
- Since 2025-06-16 = TODAY, **DO process Vendor A for Store_001 today**

### Step 2: Calculate Order Cycle
- Get FREQUENCY_DAYS from DC to Store Shipping Schedule (Table 4)
- This is the number of days between shipments to the store
- This determines the ORDER_CYCLE_DAYS (number of days of demand required)
- Order Cycle = Days between consecutive DC truck arrivals at store

### Step 3: Check if SKU is On Promotion
- Look up the SKU in Table 2 (SKU Master Data) to get IS_ON_PROMO field
- If IS_ON_PROMO = TRUE, this SKU will use promotional demand
- If IS_ON_PROMO = FALSE, this SKU will use baseline demand

### Step 4: Obtain Historical Sales Average
- Calculate last 8 week moving daily sales average for each store-SKU combination
- Formula: Total sales / 56 days (zero-sales days included as zeros)
- Calculate standard deviation of daily sales over the same 56 days
- **Note**: SKUs with no sales history are treated as having daily avg = 0 and std dev = 0

### Step 5: Identify Velocity Type of Each Item
- **Low Velocity**: Daily sales average × 7 < 12 units/week
  - **Why this approach?** Demand is too sparse/intermittent for statistical safety stock modeling. Use simple min/max bounds instead.
- **High Velocity**: Daily sales average × 7 ≥ 12 units/week
  - **Why this approach?** Sufficient demand history to model variability statistically. Use cycle stock + safety stock approach.

**Note**: Velocity classification uses the baseline daily sales average, NOT the promotional uplifted demand.

## Cycle Stock Calculation (Steps 6-7)

**Purpose**: Calculate expected demand over the order cycle, accounting for promotions.

### Step 6: Calculate Forecasted Daily Demand
- **If IS_ON_PROMO = FALSE** (from Table 2):
  - Daily Demand = Daily sales average (from Step 4)
- **If IS_ON_PROMO = TRUE** (from Table 2):
  - Daily Demand = Daily sales average × PROMO_UPLIFT_FACTOR (from Table 2)
  - Example: If daily avg = 12 units and uplift factor = 1.35, then Daily Demand = 16.2 units/day

### Step 7: Calculate Cycle Stock (Final Output)
**Formula:**
```
Cycle Stock = Daily Demand × Order Cycle Days
```

**Example (Non-Promotional):**
- Daily sales average = 12 units
- Order cycle = 7 days
- Cycle Stock = 12 × 7 = **84 units**

**Example (Promotional):**
- Daily sales average = 12 units
- Uplift factor = 1.35
- Daily demand = 12 × 1.35 = 16.2 units/day
- Order cycle = 7 days
- Cycle Stock = 16.2 × 7 = **113.4 units**

This represents the expected demand over one full order cycle.

## Low Velocity Item Calculations

### Step 8: Calculate Min and Max Quantities (Low Velocity Only)
- **Min** = Cycle Stock (from Step 7)
- **Max** = Greater of:
  - 10 × forecasted daily demand (from Step 6), OR
  - 2 units
- These bounds control inventory for slow-moving items

### Step 9: Calculate Order Quantity for Low Velocity Items
- **If BOH > Min**: Order Quantity = 0 (inventory is sufficient, don't order)
- **If BOH ≤ Min**: Order Quantity = Max - BOH + Lead Time Demand
- Where: Lead Time Demand = Forecasted daily demand (from Step 6) × Total Lead Time
- **Important**: Order Quantity = max(0, Order Quantity) — ensure non-negative

**Logic**: Low velocity items use a reorder point system. Only order when inventory drops to or below the Min threshold, then order enough to reach Max plus cover lead time demand.

## High Velocity Item Calculations

### Step 10: Calculate Safety Stock (High Velocity Only)
- Formula: Z × SD of daily demand × SQRT(order cycle in # of days)
- Where Z is from policy configuration (same for all SKUs)
- This adds buffer for demand variability

### Step 11: Calculate Maximum Inventory - Step 1 of 3 (Max 1)
- Max 1 = Cycle Stock + Safety Stock
- Covers expected demand plus safety buffer

### Step 12: Calculate Store Minimum Presentation Value (Max 2)
- Max 2 = Greater of:
  - Double facings, OR
  - Case pack
- Ensures adequate shelf presence

### Step 13: Calculate Order Quantity for High Velocity Items

**First: Determine Max Inventory Target**

We need to satisfy two different constraints:
1. **Demand-driven target (Max 1)**: Cycle stock + safety stock (from Step 11)
   - Ensures we meet expected demand + buffer for variability
2. **Presentation-driven target (Max 2)**: Shelf presentation minimum (from Step 12)
   - Ensures adequate shelf presence for customers

**Max Inventory Target** = Greater of:
- Max 1 (demand + safety), OR
- Max 2 (presentation), OR
- Case pack (can't order less than one case)

**Then: Calculate Order Quantity**
```
Order Quantity = Max Inventory Target - BOH + Lead Time Demand
Order Quantity = max(0, Order Quantity)  // Ensure non-negative
```

Where:
- **BOH (Balance On Hand)** = Stock on hand + stock in transit
- **Lead Time Demand** = Daily demand × Total Lead Time

**Logic**:
- Start with target inventory level
- Subtract what you already have (BOH)
- Add what you'll consume during lead time (while order is in transit)
- Ensure result is non-negative (if BOH already exceeds target, order quantity = 0)


## Lead Time Definitions

### Supply Chain Timing Components
1. **Vendor Lead Time**: Days for vendor to deliver to DC (from Table 3)
2. **DC Transit Time**: Days from DC departure to store arrival (from Table 4)
3. **Review Buffer**: Days needed to review order (typically 1 day, from Table 5)

### Total Lead Time Calculation
- **Total Lead Time to Store** = Vendor Lead Time + DC Transit Time
- This represents the total time from placing vendor order to product arriving at store

### Key Formulas
- **Balance On Hand (BOH)** = Stock on hand + stock in transit
- **Lead Time Demand** = Daily demand unit × Total Lead Time to Store
- **DC Departure Date** = Store arrival date - DC Transit Time
- **Vendor Order Must Be Placed By** = DC Departure Date - Vendor Lead Time - Review Buffer
- **Store Receiving Date** = DC Departure Date + DC Transit Time

## Final Processing Steps

### Step 14: Round Calculated Quantities to Nearest Case
- Apply rounding logic to all items for all velocities
- Round to nearest case pack multiple
- Formula: ceil(quantity ÷ case_pack) × case_pack

### Step 15: Submit Orders to Vendors
- Submit at cutoff time
- Orders placed with vendor systems

## Worked Example (High Velocity)
- Order cycle = 7 days
- Total lead time = 7 days
- μ (daily avg) = 12 units per day
- σ (daily std dev) = 6 units per day
- z = 1.96 for desired service level
- Current inventory = 50 units
- Case pack = 24 units

**Step 10: Calculate Safety Stock**
- Safety Stock = Z × σ × sqrt(Order Cycle)
- Safety Stock = 1.96 × 6 × sqrt(7) = 1.96 × 6 × 2.646 ≈ 31.1 units

**Step 11: Calculate Max 1**
- First need Cycle Stock (from Step 7) = assume 84 units (12 units/day × 7 days)
- Max 1 = Cycle Stock + Safety Stock = 84 + 31.1 = 115.1 units

**Step 13: Calculate Order Quantity**
- Lead Time Demand = 12 × 7 = 84 units
- BOH = 50 units
- Order Quantity = Max 1 - BOH + Lead Time Demand
- Order Quantity = 115.1 - 50 + 84 = 149.1 units

**Step 14: Round to Cases**
- Rounded = ceil(149.1 ÷ 24) × 24 = ceil(6.21) × 24 = 7 × 24 = **168 units (7 cases)**

## Implementation Notes

### Data Structures
- Config object with policy parameters for clarity and auditability
- Pandas DataFrame operations for groupby and joins
- Dictionaries for per SKU inventory state
- Conditionals and clamps to enforce nonnegativity and pack rounding logic

### File IO
- Read sales history and master data from CSV/Excel files
- Write order recommendations to CSV outputs as specified in Output Tables

### Assumptions
- Lead times are constant (vendor lead time + DC transit time)
- Demand within the historical lookback window is representative of near term demand
- Promotional calendar is maintained and up-to-date

## Key Business Rules

### Velocity Threshold
- **Low Velocity**: Weekly demand (base daily demand × 7) < 12 units
- **High Velocity**: Weekly demand (base daily demand × 7) ≥ 12 units

### Promotional Logic
- Promotional status is determined by the IS_ON_PROMO field in SKU Master Data (Table 2)
- If IS_ON_PROMO = TRUE, the uplift factor applies to the **entire order cycle**
- Each SKU has its own PROMO_UPLIFT_FACTOR defined in Table 2
- Non-promotional SKUs (IS_ON_PROMO = FALSE) use baseline demand

### Historical Lookback
- Current: 8 weeks (56 days)
- Under consideration: 180 days

## Required Input Tables

### Table 1: Sales History (Transaction Data)
Daily grain sales data for historical lookback period.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| STORE_ID | String/Int | Unique store identifier | "STORE_001" |
| SKU | String | Stock Keeping Unit identifier | "SKU12345" |
| UPC | String | Universal Product Code | "012345678905" |
| DESCRIPTION | String | Product description/name | "Organic Bananas 1lb" |
| CATEGORY | String | Product category code | "PRODUCE" |
| CATEGORY_NAME | String | Product category name | "Fresh Produce" |
| TRAN_DATE | Date | Transaction date | 2025-06-15 |
| UNIT_SALES | Float | Units sold on that date | 12.5 |
| REVENUE | Float | Dollar revenue for that date | 18.75 |
| UNIT_PRICE_POS | Float | Point of sale unit price | 1.50 |
| UNIT_PRICE_REGULAR | Float | Regular (non-promotional) unit price | 1.99 |

### Table 2: SKU Master Data
Static attributes for each SKU.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| SKU | String | Stock Keeping Unit identifier (PK) | "SKU12345" |
| VENDOR_ID | String | Vendor that supplies this SKU | "VENDOR_A" |
| UPC | String | Universal Product Code | "012345678905" |
| DESCRIPTION | String | Product description/name | "Organic Bananas 1lb" |
| CATEGORY | String | Product category code | "PRODUCE" |
| CATEGORY_NAME | String | Product category name | "Fresh Produce" |
| CASE_SIZE | Int | Units per case pack | 24 |
| INNER_PACK_SIZE | Int | Units per inner pack (optional) | 6 |
| DOUBLE_FACINGS | Int | Minimum units for shelf presentation (e.g., 8 = 2 facings × 4 units per facing) | 8 |
| IS_ON_PROMO | Boolean | Whether SKU is currently on promotion | TRUE |
| PROMO_UPLIFT_FACTOR | Float | Demand multiplier when on promotion | 1.35 |

### Table 3: Vendor Schedule
Vendor delivery schedules and lead times to DC.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| VENDOR_ID | String | Vendor identifier | "VENDOR_A" |
| VENDOR_NAME | String | Vendor name | "Acme Foods Supply" |
| VENDOR_LEAD_TIME_DAYS | Int | Days for vendor to deliver to DC | 5 |
| ORDER_CUTOFF_TIME | Time | Daily order cutoff time for vendor | "14:00:00" |
| DELIVERY_DAYS_OF_WEEK | String | Days vendor delivers to DC (comma-separated) | "Mon,Wed,Fri" |
| IS_ACTIVE | Boolean | Whether vendor is currently active | TRUE |

### Table 4: DC to Store Shipping Schedule
Fixed schedule for trucks leaving DC and arriving at stores.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| STORE_ID | String/Int | Store identifier | "STORE_001" |
| DC_ID | String | Distribution center identifier | "DC_EAST" |
| DEPARTURE_DAY_OF_WEEK | String | Day truck leaves DC | "Monday" |
| TRANSIT_DAYS | Int | Days from DC departure to store arrival | 2 |
| ARRIVAL_DAY_OF_WEEK | String | Day truck arrives at store | "Wednesday" |
| DEPARTURE_DATE_NEXT | Date | Next scheduled departure from DC | 2025-06-22 |
| ARRIVAL_DATE_NEXT | Date | Next scheduled arrival at store | 2025-06-24 |
| DEPARTURE_DATE_AFTER_NEXT | Date | Following scheduled departure from DC | 2025-06-29 |
| ARRIVAL_DATE_AFTER_NEXT | Date | Following scheduled arrival at store | 2025-06-30 |
| FREQUENCY_DAYS | Int | Days between shipments (for order cycle) | 7 |
| IS_ACTIVE | Boolean | Whether route is currently active | TRUE |

### Table 5: Store-Vendor-DC Mapping
Maps which vendors supply which stores through which DC.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| STORE_ID | String/Int | Store identifier | "STORE_001" |
| VENDOR_ID | String | Vendor identifier | "VENDOR_A" |
| DC_ID | String | Distribution center identifier | "DC_EAST" |
| CATEGORY | String | Product category (optional filter) | "PRODUCE" |
| IS_ACTIVE | Boolean | Whether this supply route is active | TRUE |
| REVIEW_BUFFER_DAYS | Int | Days needed to review order before submit | 1 |

### Table 6: Inventory Position
Current inventory levels by store and SKU.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| STORE_ID | String/Int | Store identifier | "STORE_001" |
| SKU | String | Stock Keeping Unit identifier | "SKU12345" |
| STOCK_ON_HAND | Float | Physical units in store | 45.0 |
| STOCK_IN_TRANSIT | Float | Units ordered but not yet received | 24.0 |
| BALANCE_ON_HAND | Float | BOH = Stock on hand + in transit (pre-calculated) | 69.0 |
| LAST_UPDATED | DateTime | Timestamp of inventory snapshot | 2025-06-15 08:00:00 |

**Note**: SKUs without inventory records are assumed to have STOCK_ON_HAND = 0, STOCK_IN_TRANSIT = 0, and BOH = 0.

### Table 7: Policy Configuration
Algorithm parameters and service level targets.

| Field Name | Data Type | Description | Example |
|------------|-----------|-------------|---------|
| PARAMETER_NAME | String | Configuration parameter name | "REVIEW_BUFFER_DAYS" |
| PARAMETER_VALUE | Float | Numeric value for parameter | 1.0 |
| PARAMETER_TEXT | String | Text value for parameter (optional) | NULL |
| DESCRIPTION | String | Parameter description | "Days needed to review order before submitting" |

**Key Configuration Parameters:**
- `REVIEW_BUFFER_DAYS`: Days needed to review order before submitting (1 day)
- `Z_SCORE`: Z-score for safety stock calculation (e.g., 1.96 for service level)
- `VELOCITY_THRESHOLD_WEEKLY`: Weekly demand threshold for high/low classification (12 units)
- `LOW_VEL_MAX_MULTIPLIER`: Multiplier for low velocity max calculation (10)
- `LOW_VEL_MIN_UNITS`: Absolute minimum for low velocity items (2 units)
- `HISTORICAL_LOOKBACK_DAYS`: Days of history to analyze (56 or 180)
- `MIN_ORDER_QUANTITY`: Minimum order units (if applicable)
- `MAX_ORDER_QUANTITY`: Maximum order cap (if applicable)

