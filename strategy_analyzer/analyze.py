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

# Load strategies configuration from strategies.json
def load_strategies_config():
    try:
        config_path = os.environ.get('STRATEGIES_CONFIG_PATH', '/app/config/strategies.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        logger.error("Strategies configuration file not found at /app/config/strategies.json. Please ensure the file is present.")
        return None

# Load symbols configuration from symbols.json
def load_symbols_config():
    try:
        config_path = os.environ.get('SYMBOLS_CONFIG_PATH', '/app/config/symbols.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
            symbols = config.get("symbols", [])
            return symbols
    except FileNotFoundError:
        logger.error("Symbols configuration file not found at /app/config/symbols.json. Please ensure the file is present.")
        return []

# Dynamically load strategy modules based on the strategies configuration
def load_strategies(engine, strategies_config):
    strategies = []
    for strategy_config in strategies_config.get("strategies", []):
        try:
            module_name = f"strategies.{strategy_config['name']}"
            class_name = strategy_config["class"]
            
            # Import the module dynamically
            module = importlib.import_module(module_name)
            
            # Get the strategy class
            strategy_class = getattr(module, class_name)
            
            # Create an instance of the strategy, passing the database engine and settings
            strategy = strategy_class(engine, strategy_config.get("settings"))
            strategies.append(strategy)
            
            logger.info(f"Loaded strategy: {strategy_class.__name__}")
            
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_config['name']}: {str(e)}")
    
    return strategies

# Save generated signal into the alerts table
def save_signal(engine, signal):
    try:
        common_fields = {
            "symbol": signal.get("symbol"),
            "strategy": signal.get("strategy"),
            "signal_type": signal.get("signal_type"),
            "price": float(signal.get("price"))
        }
        details = signal.get("details", {})
        details.update({
            "stop_loss": float(signal.get("stop_loss")),
            "target": float(signal.get("target")),
            "conditions_met": signal.get("conditions_met")
        })
        status = signal.get("status", "PENDING")

        with engine.connect() as conn:
            # Dla WATCH sygnałów czyścimy stare zapisy, aby dashboard widział tylko bieżące obserwacje.
            if status == "WATCH":
                conn.execute(text("DELETE FROM alerts WHERE status = 'WATCH'"))

            result = conn.execute(
                text("""
                    SELECT id FROM alerts
                    WHERE symbol = :symbol
                    AND strategy = :strategy
                    AND signal_type = :signal_type
                    AND created_at > NOW() - INTERVAL '24 hours'
                    LIMIT 1
                """),
                common_fields
            )
            if result.fetchone():
                logger.info(f"Signal already exists for {common_fields['symbol']} ({common_fields['strategy']})")
                return

            conn.execute(
                text("""
                    INSERT INTO alerts
                    (symbol, strategy, signal_type, price, details, status)
                    VALUES
                    (:symbol, :strategy, :signal_type, :price, :details, :status)
                """),
                {
                    **common_fields,
                    "details": json.dumps(details, default=lambda o: o.item() if hasattr(o, "item") else o),
                    "status": status
                }
            )
            conn.commit()
            logger.info(f"Saved new {common_fields['signal_type']} signal for {common_fields['symbol']} ({common_fields['strategy']})")
    except Exception as e:
        logger.error(f"Error saving signal: {str(e)}")

# Update the system health status in the database
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

def main():
    logger.info("Starting strategy analyzer")
    
    try:
        # Establish database connection
        engine = get_db_connection()
        
        # Load strategies configuration from strategies.json
        strategies_config = load_strategies_config()
        if strategies_config is None:
            logger.error("Strategies configuration did not load. Aborting strategy analysis.")
            update_health_status(engine, "ERROR", "Strategies configuration did not load from /app/config/strategies.json")
            return
        
        # Load symbols configuration from symbols.json
        symbols = load_symbols_config()
        if not symbols:
            logger.error("No symbols loaded from /app/config/symbols.json. Aborting analysis.")
            update_health_status(engine, "ERROR", "No symbols provided in /app/config/symbols.json")
            return
        
        # Load strategy modules dynamically
        strategies = load_strategies(engine, strategies_config)
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
