"""
Replenishment Algorithm Implementation

This module implements a periodic review replenishment algorithm.
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from pathlib import Path
from typing import Dict, Tuple, Set, Any
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ReplenishmentAlgorithm:
    """
    Main class for running the replenishment algorithm.
    """

    def __init__(self, data_dir: str, run_date: str) -> None:
        """
        Initialize the algorithm with data directory and run date.

        Args:
            data_dir: Path to directory containing input CSV files
            run_date: Date to run the algorithm (YYYY-MM-DD format)
        """
        # Validate data directory
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
        if not self.data_dir.is_dir():
            raise ValueError(f"Path is not a directory: {data_dir}")

        # Validate and parse run date
        try:
            self.run_date = pd.to_datetime(run_date)
        except Exception as e:
            raise ValueError(f"Invalid run_date format '{run_date}'. Expected YYYY-MM-DD format. Error: {e}")

        logger.info(f"Initializing ReplenishmentAlgorithm for run_date={self.run_date.date()}")

        # Load all input tables
        self.load_data()

        # Load policy configuration
        self.load_policy_config()

        # Validate vendor configuration
        self.active_vendors = self.get_active_vendor_ids()

    def load_data(self) -> None:
        """Load all input tables from CSV files with validation."""
        logger.info(f"Loading data from {self.data_dir}...")

        try:
            # Load sales history
            self.sales_history = pd.read_csv(self.data_dir / 'sales_history.csv')
            self._validate_columns(self.sales_history,
                                  ['STORE_ID', 'SKU', 'TRAN_DATE', 'UNIT_SALES'],
                                  'sales_history.csv')
            self.sales_history['TRAN_DATE'] = pd.to_datetime(self.sales_history['TRAN_DATE'], errors='coerce')
            if self.sales_history['TRAN_DATE'].isna().any():
                raise ValueError("sales_history.csv contains invalid date values in TRAN_DATE column")

            # Load SKU master data
            self.sku_master = pd.read_csv(self.data_dir / 'sku_master_data.csv')
            self._validate_columns(self.sku_master,
                                  ['SKU', 'VENDOR_ID', 'CASE_SIZE'],
                                  'sku_master_data.csv')

            # Load vendor schedule
            self.vendor_schedule = pd.read_csv(self.data_dir / 'vendor_schedule.csv')
            self._validate_columns(self.vendor_schedule,
                                  ['VENDOR_ID', 'VENDOR_LEAD_TIME_DAYS'],
                                  'vendor_schedule.csv')

            # Load DC shipping schedule
            self.dc_shipping = pd.read_csv(self.data_dir / 'dc_to_store_shipping.csv')
            self._validate_columns(self.dc_shipping,
                                  ['STORE_ID', 'DC_ID', 'DEPARTURE_DATE_NEXT', 'ARRIVAL_DATE_NEXT',
                                   'TRANSIT_DAYS', 'FREQUENCY_DAYS'],
                                  'dc_to_store_shipping.csv')
            self.dc_shipping['DEPARTURE_DATE_NEXT'] = pd.to_datetime(self.dc_shipping['DEPARTURE_DATE_NEXT'], errors='coerce')
            self.dc_shipping['ARRIVAL_DATE_NEXT'] = pd.to_datetime(self.dc_shipping['ARRIVAL_DATE_NEXT'], errors='coerce')
            if self.dc_shipping['DEPARTURE_DATE_NEXT'].isna().any() or self.dc_shipping['ARRIVAL_DATE_NEXT'].isna().any():
                raise ValueError("dc_to_store_shipping.csv contains invalid date values")

            # Load store-vendor-DC mapping
            self.store_vendor_mapping = pd.read_csv(self.data_dir / 'store_vendor_dc_mapping.csv')
            self._validate_columns(self.store_vendor_mapping,
                                  ['STORE_ID', 'VENDOR_ID', 'DC_ID', 'REVIEW_BUFFER_DAYS'],
                                  'store_vendor_dc_mapping.csv')

            # Load inventory position
            self.inventory = pd.read_csv(self.data_dir / 'inventory_position.csv')
            self._validate_columns(self.inventory,
                                  ['STORE_ID', 'SKU', 'BALANCE_ON_HAND', 'STOCK_ON_HAND',
                                   'STOCK_IN_TRANSIT', 'LAST_UPDATED'],
                                  'inventory_position.csv')
            self.inventory['LAST_UPDATED'] = pd.to_datetime(self.inventory['LAST_UPDATED'], errors='coerce')
            if self.inventory['LAST_UPDATED'].isna().any():
                raise ValueError("inventory_position.csv contains invalid date values in LAST_UPDATED column")

            logger.info("Data loaded successfully")

        except FileNotFoundError as e:
            logger.error(f"Required data file not found: {e}")
            raise
        except pd.errors.EmptyDataError as e:
            logger.error(f"Data file is empty: {e}")
            raise ValueError(f"One of the required CSV files is empty: {e}")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise

    def _validate_columns(self, df: pd.DataFrame, required_columns: List[str], filename: str) -> None:
        """Validate that required columns exist in a DataFrame."""
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"{filename} is missing required columns: {missing_columns}")

    def load_policy_config(self) -> None:
        """Load policy configuration parameters with validation."""
        try:
            config_df = pd.read_csv(self.data_dir / 'policy_configuration.csv')
            self._validate_columns(config_df, ['PARAMETER_NAME', 'PARAMETER_VALUE'], 'policy_configuration.csv')

            self.config: Dict[str, float] = {}
            for _, row in config_df.iterrows():
                try:
                    self.config[row['PARAMETER_NAME']] = float(row['PARAMETER_VALUE'])
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not convert parameter {row['PARAMETER_NAME']} to float: {e}")

            # Set key parameters with validation
            self.z_score = self.config.get('Z_SCORE', 1.96)
            self.velocity_threshold = self.config.get('VELOCITY_THRESHOLD_WEEKLY', 12.0)
            self.low_vel_multiplier = self.config.get('LOW_VEL_MAX_MULTIPLIER', 10.0)
            self.low_vel_min_units = self.config.get('LOW_VEL_MIN_UNITS', 2.0)
            self.lookback_days = int(self.config.get('HISTORICAL_LOOKBACK_DAYS', 56))

            # Validate parameters are positive
            if self.z_score <= 0:
                raise ValueError(f"Z_SCORE must be positive, got {self.z_score}")
            if self.velocity_threshold < 0:
                raise ValueError(f"VELOCITY_THRESHOLD_WEEKLY must be non-negative, got {self.velocity_threshold}")
            if self.lookback_days <= 0:
                raise ValueError(f"HISTORICAL_LOOKBACK_DAYS must be positive, got {self.lookback_days}")

            logger.info(f"Policy config loaded (Z={self.z_score}, velocity_threshold={self.velocity_threshold})")

        except FileNotFoundError as e:
            logger.error(f"Policy configuration file not found: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading policy configuration: {e}")
            raise

    def get_active_vendor_ids(self) -> Set[Any]:
        """
        Identify vendors that are both mapped to stores and have delivery schedules.
        Returns set of vendor IDs that are properly configured for ordering.
        """
        # Get all vendors mapped to stores
        mapped_vendors = set(self.store_vendor_mapping['VENDOR_ID'].unique())

        # Get all vendors with defined schedules
        scheduled_vendors = set(self.vendor_schedule['VENDOR_ID'].unique())

        # Find vendors that have both mappings and schedules
        active_vendors = mapped_vendors & scheduled_vendors

        # Identify configuration issues
        missing_schedules = mapped_vendors - scheduled_vendors
        unmapped_vendors = scheduled_vendors - mapped_vendors

        if missing_schedules:
            logger.warning(f"{len(missing_schedules)} vendors mapped to stores but missing delivery schedules")

        if unmapped_vendors:
            logger.warning(f"{len(unmapped_vendors)} vendors have schedules but no store mappings")

        logger.info(f"Validated {len(active_vendors)} active vendors")

        return active_vendors

    def step1_identify_store_vendor_combos(self) -> pd.DataFrame:
        """Determine which Store-Vendor combinations need orders TODAY."""
        logger.info("\n=== Step 1: Identifying Store-Vendor Combinations ===")

        combos = []

        for _, mapping in self.store_vendor_mapping.iterrows():
            store_id = mapping['STORE_ID']
            vendor_id = mapping['VENDOR_ID']
            dc_id = mapping['DC_ID']
            review_buffer = mapping['REVIEW_BUFFER_DAYS']

            # Get DC shipping schedule for this store
            dc_sched = self.dc_shipping[
                (self.dc_shipping['STORE_ID'] == store_id) &
                (self.dc_shipping['DC_ID'] == dc_id)
            ]

            if dc_sched.empty:
                continue

            dc_sched = dc_sched.iloc[0]

            # Get vendor lead time
            vendor = self.vendor_schedule[self.vendor_schedule['VENDOR_ID'] == vendor_id]
            if vendor.empty:
                continue

            try:
                vendor_lead_time = int(vendor.iloc[0]['VENDOR_LEAD_TIME_DAYS'])
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid vendor lead time for vendor {vendor_id}: {e}")
                continue

            # Calculate when order must be placed
            dc_departure = dc_sched['DEPARTURE_DATE_NEXT']
            order_by_date = dc_departure - timedelta(days=int(vendor_lead_time + review_buffer))

            # Check if we need to order TODAY
            if order_by_date.date() == self.run_date.date():
                combos.append({
                    'STORE_ID': store_id,
                    'VENDOR_ID': vendor_id,
                    'DC_ID': dc_id,
                    'REVIEW_BUFFER_DAYS': review_buffer,
                    'VENDOR_LEAD_TIME_DAYS': vendor_lead_time,
                    'DC_TRANSIT_DAYS': dc_sched['TRANSIT_DAYS'],
                    'ORDER_CYCLE_DAYS': dc_sched['FREQUENCY_DAYS'],
                    'DC_DEPARTURE_DATE': dc_departure,
                    'STORE_ARRIVAL_DATE': dc_sched['ARRIVAL_DATE_NEXT']
                })

        combos_df = pd.DataFrame(combos)
        logger.info(f"Found {len(combos_df)} Store-Vendor combinations to process today")

        if len(combos_df) > 0:
            logger.debug(f"  Combinations: {combos_df[['STORE_ID', 'VENDOR_ID']].to_dict('records')}")

        return combos_df

    def step4_calculate_historical_stats(self, store_id: Any, sku: Any) -> Tuple[float, float]:
        """Calculate historical sales average and std dev for a store-SKU."""
        # Get last N days of sales history
        end_date = self.run_date
        start_date = end_date - timedelta(days=self.lookback_days)

        sales = self.sales_history[
            (self.sales_history['STORE_ID'] == store_id) &
            (self.sales_history['SKU'] == sku) &
            (self.sales_history['TRAN_DATE'] >= start_date) &
            (self.sales_history['TRAN_DATE'] < end_date)
        ]

        if sales.empty:
            # No sales history
            return 0.0, 0.0

        # Create complete date range with zeros for missing days
        date_range = pd.date_range(start=start_date, end=end_date - timedelta(days=1), freq='D')
        sales_by_date = sales.groupby('TRAN_DATE')['UNIT_SALES'].sum()

        # Reindex to include all dates (missing dates = 0 sales)
        sales_series = sales_by_date.reindex(date_range, fill_value=0.0)

        daily_avg = sales_series.mean()
        daily_std = sales_series.std()

        # Handle NaN values (can happen with all zeros or single value)
        if pd.isna(daily_avg):
            daily_avg = 0.0
        if pd.isna(daily_std):
            daily_std = 0.0

        return float(daily_avg), float(daily_std)

    def calculate_order_for_sku(self, combo_row: pd.Series, sku_row: pd.Series) -> Dict[str, Any]:
        """Calculate order quantity for a single SKU (implements Steps 2-14)."""
        store_id = combo_row['STORE_ID']
        vendor_id = combo_row['VENDOR_ID']
        sku = sku_row['SKU']

        # Step 2: Order cycle
        order_cycle_days = combo_row['ORDER_CYCLE_DAYS']

        # Step 3: Check if on promotion
        is_on_promo = sku_row.get('IS_ON_PROMO', False)
        promo_uplift = sku_row.get('PROMO_UPLIFT_FACTOR', 1.0)

        # Step 4: Historical stats
        daily_avg, daily_std = self.step4_calculate_historical_stats(store_id, sku)

        # Step 5: Velocity classification
        weekly_demand = daily_avg * 7
        is_high_velocity = weekly_demand >= self.velocity_threshold
        velocity_class = "HIGH" if is_high_velocity else "LOW"

        # Step 6: Forecasted daily demand
        if is_on_promo:
            daily_demand = daily_avg * promo_uplift
        else:
            daily_demand = daily_avg

        # Step 7: Cycle stock
        cycle_stock = daily_demand * order_cycle_days

        # Get inventory position
        inv = self.inventory[
            (self.inventory['STORE_ID'] == store_id) &
            (self.inventory['SKU'] == sku)
        ]

        if not inv.empty:
            boh = float(inv.iloc[0]['BALANCE_ON_HAND'])
            stock_on_hand = float(inv.iloc[0]['STOCK_ON_HAND'])
            stock_in_transit = float(inv.iloc[0]['STOCK_IN_TRANSIT'])
        else:
            # No inventory record - assume zero
            boh = 0.0
            stock_on_hand = 0.0
            stock_in_transit = 0.0

        # Lead time
        total_lead_time = combo_row['VENDOR_LEAD_TIME_DAYS'] + combo_row['DC_TRANSIT_DAYS']
        lead_time_demand = daily_demand * total_lead_time

        # Get SKU details with validation
        case_size = sku_row['CASE_SIZE']

        # Validate case_size
        if case_size <= 0:
            logger.error(f"Invalid case_size {case_size} for SKU {sku}. Must be positive.")
            raise ValueError(f"case_size must be positive for SKU {sku}, got {case_size}")

        double_facings = sku_row.get('DOUBLE_FACINGS', case_size)

        # Initialize output fields
        safety_stock = None
        max_1 = None
        max_2 = None
        max_inventory_target = None
        min_qty = None
        max_qty = None

        if is_high_velocity:
            # Steps 10-13: High velocity calculations

            # Step 10: Safety stock
            safety_stock = self.z_score * daily_std * np.sqrt(order_cycle_days)

            # Step 11: Max 1
            max_1 = cycle_stock + safety_stock

            # Step 12: Max 2 (presentation)
            max_2 = max(double_facings, case_size)

            # Step 13: Max inventory target
            max_inventory_target = max(max_1, max_2, case_size)

            # Order quantity
            order_qty = max_inventory_target - boh + lead_time_demand

        else:
            # Steps 8-9: Low velocity calculations

            # Step 8: Min and Max
            min_qty = cycle_stock
            max_qty = max(self.low_vel_multiplier * daily_demand, self.low_vel_min_units)

            # Step 9: Order quantity (reorder point logic)
            if boh > min_qty:
                # Inventory above min threshold - don't order
                order_qty = 0.0
            else:
                # Inventory at or below min threshold - order up to max
                order_qty = max_qty - boh + lead_time_demand

        # Ensure non-negative
        order_qty = max(0.0, order_qty)

        # Step 14: Round to cases
        if order_qty > 0:
            order_cases = np.ceil(order_qty / case_size)
            order_units = order_cases * case_size
        else:
            order_cases = 0.0
            order_units = 0.0

        # Build result dictionary
        result = {
            'RUN_DATE': self.run_date.date(),
            'STORE_ID': store_id,
            'VENDOR_ID': vendor_id,
            'SKU': sku,
            'DESCRIPTION': sku_row.get('DESCRIPTION', ''),
            'CATEGORY': sku_row.get('CATEGORY', ''),
            'VELOCITY_CLASS': velocity_class,
            'DAILY_AVG_UNITS_SOLD': round(daily_avg, 2),
            'DAILY_SD_UNITS_SOLD': round(daily_std, 2),
            'IS_ON_PROMO': is_on_promo,
            'PROMO_UPLIFT_FACTOR': promo_uplift if is_on_promo else None,
            'DAILY_DEMAND': round(daily_demand, 2),
            'ORDER_CYCLE_DAYS': order_cycle_days,
            'CYCLE_STOCK': round(cycle_stock, 1),
            'VENDOR_LEAD_TIME_DAYS': combo_row['VENDOR_LEAD_TIME_DAYS'],
            'DC_TRANSIT_DAYS': combo_row['DC_TRANSIT_DAYS'],
            'TOTAL_LEAD_TIME_DAYS': total_lead_time,
            'LEAD_TIME_DEMAND': round(lead_time_demand, 1),
            'STOCK_ON_HAND': stock_on_hand,
            'STOCK_IN_TRANSIT': stock_in_transit,
            'BALANCE_ON_HAND': boh,
            'Z_SCORE': self.z_score if is_high_velocity else None,
            'SAFETY_STOCK': round(safety_stock, 1) if safety_stock is not None else None,
            'MAX_1': round(max_1, 1) if max_1 is not None else None,
            'MAX_2_PRESENTATION': max_2 if max_2 is not None else None,
            'MAX_INVENTORY_TARGET': round(max_inventory_target, 1) if max_inventory_target is not None else None,
            'MIN_QTY': round(min_qty, 1) if min_qty is not None else None,
            'MAX_QTY': round(max_qty, 1) if max_qty is not None else None,
            'GAP_BEFORE_ROUNDING': round(order_qty, 1),
            'ORDER_UNITS': order_units,
            'ORDER_CASES': order_cases,
            'CASE_SIZE': case_size,
            'DC_DEPARTURE_DATE': combo_row['DC_DEPARTURE_DATE'].date(),
            'STORE_ARRIVAL_DATE': combo_row['STORE_ARRIVAL_DATE'].date()
        }

        return result

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Execute the full replenishment algorithm."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Running Replenishment Algorithm for {self.run_date.date()}")
        logger.info(f"{'='*60}")

        # Step 1: Identify store-vendor combinations
        combos = self.step1_identify_store_vendor_combos()

        if combos.empty:
            logger.warning("No store-vendor combinations need orders today.")
            return pd.DataFrame(), pd.DataFrame()

        # Process each combination
        all_results = []

        for _, combo_row in combos.iterrows():
            store_id = combo_row['STORE_ID']
            vendor_id = combo_row['VENDOR_ID']

            logger.info(f"\n=== Processing Store: {store_id}, Vendor: {vendor_id} ===")

            # Get all SKUs for this vendor
            skus = self.sku_master[self.sku_master['VENDOR_ID'] == vendor_id]

            logger.info(f"  Found {len(skus)} SKUs for this vendor")

            for _, sku_row in skus.iterrows():
                sku = sku_row['SKU']
                try:
                    result = self.calculate_order_for_sku(combo_row, sku_row)
                    all_results.append(result)

                    # Log summary
                    logger.debug(f"    {sku} ({result['DESCRIPTION'][:30]:30s}): "
                          f"{result['VELOCITY_CLASS']:4s} | "
                          f"Avg={result['DAILY_AVG_UNITS_SOLD']:5.1f} | "
                          f"Order={result['ORDER_UNITS']:6.1f} units ({result['ORDER_CASES']:.0f} cases)")
                except Exception as e:
                    logger.error(f"    Error processing SKU {sku}: {e}")
                    continue

        # Create DataFrames
        if not all_results:
            logger.warning("No orders could be calculated - all SKUs failed processing")
            return pd.DataFrame(), pd.DataFrame()

        order_details = pd.DataFrame(all_results)

        # Create simplified orders table
        orders = order_details[[
            'RUN_DATE', 'STORE_ID', 'VENDOR_ID', 'SKU', 'DESCRIPTION',
            'ORDER_UNITS', 'ORDER_CASES', 'CASE_SIZE',
            'DC_DEPARTURE_DATE', 'STORE_ARRIVAL_DATE'
        ]].copy()

        logger.info(f"\n{'='*60}")
        logger.info(f"Algorithm complete: Generated {len(orders)} order lines")
        logger.info(f"{'='*60}")

        return orders, order_details

    def save_outputs(self, orders: pd.DataFrame, order_details: pd.DataFrame,
                     output_dir: str = 'output') -> Tuple[Path, Path]:
        """Save output tables to CSV files."""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(exist_ok=True)

            run_date_str = self.run_date.strftime('%Y-%m-%d')

            # Save orders
            orders_file = output_path / f'orders_{run_date_str}.csv'
            orders.to_csv(orders_file, index=False)
            logger.info(f"Orders saved to: {orders_file}")

            # Save order details
            details_file = output_path / f'order_details_{run_date_str}.csv'
            order_details.to_csv(details_file, index=False)
            logger.info(f"Order details saved to: {details_file}")

            return orders_file, details_file

        except OSError as e:
            logger.error(f"Error saving output files: {e}")
            raise


def main() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Main entry point for running the algorithm."""
    # Default parameters
    data_dir = 'data'
    run_date = '2025-06-16'  # Date from example that should trigger orders
    output_dir = 'output'

    # Parse command line arguments if provided
    if len(sys.argv) > 1:
        data_dir = sys.argv[1]
    if len(sys.argv) > 2:
        run_date = sys.argv[2]
    if len(sys.argv) > 3:
        output_dir = sys.argv[3]

    logger.info("="*60)
    logger.info("REPLENISHMENT ALGORITHM")
    logger.info("="*60)

    try:
        # Initialize and run algorithm
        algo = ReplenishmentAlgorithm(data_dir=data_dir, run_date=run_date)
        orders, order_details = algo.run()

        # Save outputs
        if not orders.empty:
            algo.save_outputs(orders, order_details, output_dir=output_dir)

            # Print summary statistics
            logger.info(f"\n{'='*60}")
            logger.info("SUMMARY STATISTICS")
            logger.info(f"{'='*60}")
            logger.info(f"Total Order Lines: {len(orders)}")
            logger.info(f"Total Units Ordered: {orders['ORDER_UNITS'].sum():.0f}")
            logger.info(f"Total Cases Ordered: {orders['ORDER_CASES'].sum():.0f}")
            logger.info(f"\nBy Velocity:")
            velocity_summary = order_details.groupby('VELOCITY_CLASS').agg({
                'SKU': 'count',
                'ORDER_UNITS': 'sum',
                'ORDER_CASES': 'sum'
            }).round(0)
            logger.info(f"\n{velocity_summary}")
            logger.info(f"{'='*60}\n")

        return orders, order_details

    except Exception as e:
        logger.error(f"Algorithm execution failed: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    orders, details = main()
