import os
import json
import time
import logging
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('data_fetcher')

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
        logger.warning("Config file not found, using default symbols")
        return {
            "symbols": [
                "PKO", "PKN", "PZU", "PEO", "DNP", "SPL", "KGH", "LPP", 
                "ALE", "CPS", "CDR", "MBK", "OPL", "MIL", "KRU", "BDX"
            ]
        }

# Fetch data from Yahoo Finance
def fetch_stock_data(symbol):
    try:
        # Add .WA suffix for Warsaw Stock Exchange
        ticker = f"{symbol}.WA"
        logger.info(f"Fetching data for {ticker}")
        
        # Get data for the last 2 days with 1h interval
        stock_data = yf.download(
            ticker,
            period="2d",
            interval="1h",
            progress=False
        )
        
        if stock_data.empty:
            logger.warning(f"No data retrieved for {symbol}")
            return None
            
        # Reset index to make timestamp a column
        stock_data = stock_data.reset_index()
        
        # Add symbol column
        stock_data['symbol'] = symbol
        
        return stock_data
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {str(e)}")
        return None

# Save data to staging table
def save_to_staging(engine, data):
    if data is None or data.empty:
        return 0
    
    try:
        # Rename columns to match database schema
        data = data.rename(columns={
            'Datetime': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Select only required columns
        data = data[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # Insert into staging table
        data.to_sql('staging_stock_prices', engine, if_exists='append', index=False)
        
        return len(data)
    except Exception as e:
        logger.error(f"Error saving data to staging: {str(e)}")
        return 0

# Transfer data from staging to historical table
def transfer_to_historical(engine):
    try:
        with engine.connect() as conn:
            # Execute SQL to transfer data
            result = conn.execute(text("""
                INSERT INTO historical_stock_prices 
                (symbol, timestamp, open, high, low, close, volume)
                SELECT symbol, timestamp, open, high, low, close, volume 
                FROM staging_stock_prices
                ON CONFLICT (symbol, timestamp) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume;
            """))
            
            # Clear staging table
            conn.execute(text("TRUNCATE TABLE staging_stock_prices;"))
            conn.commit()
            
            logger.info("Data transferred to historical table")
            
    except Exception as e:
        logger.error(f"Error transferring data to historical: {str(e)}")

# Record health status
def update_health_status(engine, status, details=None):
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO system_health (component, status, details)
                    VALUES (:component, :status, :details)
                """),
                {
                    "component": "data_fetcher",
                    "status": status,
                    "details": details
                }
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update health status: {str(e)}")

# Main function
def main():
    logger.info("Starting data fetcher")
    
    try:
        # Get database connection
        engine = get_db_connection()
        
        # Load configuration
        config = load_config()
        symbols = config.get("symbols", [])
        
        if not symbols:
            logger.error("No symbols configured")
            update_health_status(engine, "ERROR", "No symbols configured")
            return
        
        total_records = 0
        
        # Fetch data for each symbol
        for symbol in symbols:
            data = fetch_stock_data(symbol)
            records = save_to_staging(engine, data)
            total_records += records
            
            # Sleep to avoid rate limiting
            time.sleep(1)
        
        # Transfer data from staging to historical
        transfer_to_historical(engine)
        
        logger.info(f"Completed data fetch. Processed {total_records} records for {len(symbols)} symbols")
        update_health_status(engine, "OK", f"Processed {total_records} records")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        try:
            update_health_status(engine, "ERROR", str(e))
        except:
            pass

if __name__ == "__main__":
    main()