import os
import json
import logging
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from tqdm import tqdm
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/historical_import.log"),
        logging.StreamHandler()
    ]
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
        logger.warning("Config file not found, using default symbols")
        return {
            "symbols": [
                "PKO", "PKN", "PZU", "PEO", "DNP", "SPL", "KGH", "LPP", 
                "ALE", "CPS", "CDR", "MBK", "OPL", "MIL", "KRU", "BDX"
            ]
        }

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
            
        # Reset index to make timestamp a column
        stock_data = stock_data.reset_index()
        
        # Add symbol column
        stock_data['symbol'] = symbol
        
        return stock_data
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        return None

def save_to_historical(engine, data):
    if data is None or data.empty:
        return 0
    
    try:
        # Rename columns to match database schema
        data = data.rename(columns={
            'Date': 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Select only required columns
        data = data[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # Insert directly into historical table with conflict handling
        with engine.connect() as conn:
            # First insert to staging table
            data.to_sql('staging_stock_prices', conn, if_exists='append', index=False)
            
            # Then move to historical with conflict handling
            conn.execute(text("""
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
        
        return len(data)
    except Exception as e:
        logger.error(f"Error saving historical data: {str(e)}")
        return 0

def main():
    logger.info("Starting historical data import")
    
    try:
        # Get database connection
        engine = get_db_connection()
        
        # Load configuration
        config = load_config()
        symbols = config.get("symbols", [])
        
        if not symbols:
            logger.error("No symbols configured")
            return
        
        # Get number of years to import
        years = int(os.environ.get('HISTORY_YEARS', 5))
        logger.info(f"Importing {years} years of historical data")
        
        total_records = 0
        
        # Fetch data for each symbol
        for symbol in tqdm(symbols, desc="Importing symbols"):
            data = fetch_historical_data(symbol, years)
            records = save_to_historical(engine, data)
            total_records += records
            logger.info(f"Imported {records} records for {symbol}")
            
            # Sleep to avoid rate limiting
            time.sleep(1)
        
        logger.info(f"Completed historical data import. Processed {total_records} records for {len(symbols)} symbols")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs("/app/logs", exist_ok=True)
    main()