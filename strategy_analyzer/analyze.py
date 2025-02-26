import os
import json
import logging
import importlib
import sqlalchemy
from sqlalchemy import create_engine, text
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('strategy_analyzer')

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
        config_path = os.environ.get('CONFIG_PATH', '/app/config/strategies.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Config file not found, using default strategies")
        return {
            "symbols": [
                "PKO", "PKN", "PZU", "PEO", "DNP", "SPL", "KGH", "LPP", 
                "ALE", "CPS", "CDR", "MBK", "OPL", "MIL", "KRU", "BDX"
            ],
            "strategies": [
                {
                    "name": "moving_average",
                    "class": "MovingAverageStrategy",
                    "settings": {
                        "short_ma": 50,
                        "long_ma": 100,
                        "min_volume": 10000
                    }
                }
            ]
        }

# Load strategy modules dynamically
def load_strategies(engine, config):
    strategies = []
    
    for strategy_config in config.get("strategies", []):
        try:
            module_name = f"strategies.{strategy_config['name']}"
            class_name = strategy_config["class"]
            
            # Import the module
            module = importlib.import_module(module_name)
            
            # Get the strategy class
            strategy_class = getattr(module, class_name)
            
            # Create instance
            strategy = strategy_class(engine, strategy_config.get("settings"))
            strategies.append(strategy)
            
            logger.info(f"Loaded strategy: {strategy_class.__name__}")
            
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_config['name']}: {str(e)}")
    
    return strategies

# Save signal to database
def save_signal(engine, signal):
    try:
        with engine.connect() as conn:
            # Check if this signal was already generated recently
            result = conn.execute(
                text("""
                    SELECT id FROM alerts
                    WHERE symbol = :symbol
                    AND strategy = :strategy
                    AND signal_type = :signal_type
                    AND created_at > NOW() - INTERVAL '24 hours'
                    LIMIT 1
                """),
                signal
            )
            
            existing = result.fetchone()
            if existing:
                logger.info(f"Signal already exists for {signal['symbol']} ({signal['strategy']})")
                return
            
            # Insert new signal
            conn.execute(
                text("""
                    INSERT INTO alerts
                    (symbol, strategy, signal_type, price, volume, ma50, ma100, status)
                    VALUES
                    (:symbol, :strategy, :signal_type, :price, :volume, :ma50, :ma100, 'PENDING')
                """),
                signal
            )
            conn.commit()
            
            logger.info(f"Saved new {signal['signal_type']} signal for {signal['symbol']} ({signal['strategy']})")
            
    except Exception as e:
        logger.error(f"Error saving signal: {str(e)}")

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
                    "component": "strategy_analyzer",
                    "status": status,
                    "details": details
                }
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update health status: {str(e)}")

# Main function
def main():
    logger.info("Starting strategy analyzer")
    
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
        
        # Load strategy modules
        strategies = load_strategies(engine, config)
        
        if not strategies:
            logger.error("No strategies loaded")
            update_health_status(engine, "ERROR", "No strategies loaded")
            return
        
        signal_count = 0
        
        # Analyze each symbol with each strategy
        for symbol in symbols:
            for strategy in strategies:
                signal = strategy.analyze(symbol)
                
                if signal:
                    save_signal(engine, signal)
                    signal_count += 1
        
        logger.info(f"Analysis complete. Generated {signal_count} signals")
        update_health_status(engine, "OK", f"Generated {signal_count} signals")
        
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        try:
            update_health_status(engine, "ERROR", str(e))
        except:
            pass

if __name__ == "__main__":
    main()