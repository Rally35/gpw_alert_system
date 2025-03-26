import os
import json
import logging
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('historical_importer')

# Database connection
def get_db_connection():
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_user = os.environ.get('DB_USER', 'user')
    db_password = os.environ.get('DB_PASSWORD', 'password')
    db_name = os.environ.get('DB_NAME', 'stocks')
    
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

# Load configuration
def load_config():
    try:
        config_path = os.environ.get('CONFIG_PATH', '/app/config/symbols.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Config file not found")
        return None

def clear_staging_table(engine):
    """Clear the staging table before importing new data."""
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE staging_stock_prices;"))
            logger.info("Cleared staging_stock_prices table.")
    except Exception as e:
        logger.error(f"Error clearing staging table: {str(e)}")

def fetch_historical_data(symbol, years=5):
    try:
        # Add .WA suffix for Warsaw Stock Exchange
        ticker = f"{symbol}.WA"
        logger.info(f"Fetching {years} years of data for {ticker}")
        
        # Get data for the specified number of years
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        # Use 1d interval for historical data
        stock_data = yf.download(
            ticker,
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            interval="1d",
            progress=False
        )
        
        if stock_data.empty:
            logger.warning(f"No data retrieved for {symbol}")
            return None
            
        return stock_data
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return None

def insert_stock_data(engine, symbol, data):
    """Insert stock data directly using SQL without handling duplicates,
       as the staging table is cleared before each run.
    """
    if data is None or data.empty:
        return 0
    
    try:
        count = 0
        # Use a transaction block that automatically commits
        with engine.begin() as conn:
            for index, row in data.iterrows():
                # Extract the date and values
                date = index.strftime('%Y-%m-%d')
                # Use .item() to extract a scalar from a single-element Series if necessary
                open_price = float(row['Open'].item() if hasattr(row['Open'], 'item') else row['Open'])
                high_price = float(row['High'].item() if hasattr(row['High'], 'item') else row['High'])
                low_price = float(row['Low'].item() if hasattr(row['Low'], 'item') else row['Low'])
                close_price = float(row['Close'].item() if hasattr(row['Close'], 'item') else row['Close'])
                volume = int(row['Volume'].item() if hasattr(row['Volume'], 'item') else row['Volume'])
                
                # Insert directly with SQL (no ON CONFLICT since table is cleared)
                query = """
                INSERT INTO staging_stock_prices
                (symbol, timestamp, open, high, low, close, volume)
                VALUES (:symbol, :timestamp, :open, :high, :low, :close, :volume)
                """
                
                conn.execute(
                    text(query),
                    {
                        "symbol": symbol,
                        "timestamp": date,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": volume
                    }
                )
                count += 1

            logger.info(f"Inserted {count} records for {symbol}")
        return count
    except Exception as e:
        logger.error(f"Error inserting data for {symbol}: {str(e)}")
        return 0

def update_health_status(engine, status, details=None):
    """Update the system_health table with the current status of the historical importer."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO system_health (component, status, details)
                    VALUES (:component, :status, :details)
                """),
                {
                    "component": "historical_importer",
                    "status": status,
                    "details": details
                }
            )
    except Exception as e:
        logger.error(f"Failed to update health status: {str(e)}")

def main():
    logger.info("Starting historical data import")
    
    try:
        # Get database connection
        engine = get_db_connection()
        
        # Clear the staging table first
        clear_staging_table(engine)

        # Load configuration
        config = load_config()
        if config is None:
            logger.error("Configuration could not be loaded")
            update_health_status(engine, "ERROR", "Configuration could not be loaded")
            return
        
        symbols = config.get("symbols", [])
        if not symbols:
            logger.error("No symbols configured")
            update_health_status(engine, "ERROR", "No symbols configured")
            return
        
        # Get number of years to import
        years = int(os.environ.get('HISTORY_YEARS', 5))
        logger.info(f"Importing {years} years of historical data")
        
        total_records = 0
        
        # Process each symbol
        for symbol in symbols:
            try:
                data = fetch_historical_data(symbol, years)
                if data is not None and not data.empty:
                    records = insert_stock_data(engine, symbol, data)
                    total_records += records
                else:
                    logger.info(f"Failed to insert data for {symbol}")
            except Exception as e:
                logger.error(f"Failed to process {symbol}: {str(e)}")
            
            time.sleep(1)  # Avoid rate limiting
        
        logger.info(f"Completed historical data import. Processed {total_records} records for {len(symbols)} symbols")
        update_health_status(engine, "OK", f"Processed {total_records} records")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        update_health_status(engine, "ERROR", str(e))

if __name__ == "__main__":
    main()
