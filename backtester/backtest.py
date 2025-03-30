import pandas as pd
import numpy as np
import logging
import os
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from strategy_analyzer.strategies.momentum_trend_breakout import MomentumTrendBreakoutStrategy

logger = logging.getLogger('backtest')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_db_connection():
    db_host = os.environ.get("DB_HOST", "database")
    db_user = os.environ.get("DB_USER", "user")
    db_password = os.environ.get("DB_PASSWORD", "password")
    db_name = os.environ.get("DB_NAME", "stocks")
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
    return create_engine(connection_string)

def create_backtest_closed_positions_table(engine):
    """
    Creates the backtest_closed_positions table if it doesn't already exist.
    """
    query = text("""
        CREATE TABLE IF NOT EXISTS backtest_closed_positions (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            signal_type VARCHAR(20),
            signal_date TIMESTAMP,
            entry_date TIMESTAMP,
            entry_price DOUBLE PRECISION,
            stop_loss DOUBLE PRECISION,
            target DOUBLE PRECISION,
            conditions_met INT,
            exit_date TIMESTAMP,
            exit_price DOUBLE PRECISION,
            profit DOUBLE PRECISION,
            profit_pct DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    with engine.connect() as conn:
        conn.execute(query)
        conn.commit()
    logger.info("Ensured backtest_closed_positions table exists.")

def load_symbols_config():
    """
    Loads symbols from /app/config/symbols.json (the same approach as in analyze.py).
    You can adjust the path or environment variable if needed.
    """
    config_path = os.environ.get('SYMBOLS_CONFIG_PATH', '/app/config/symbols.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            symbols = config.get("symbols", [])
            if not symbols:
                logger.warning("No symbols found in symbols.json.")
            return symbols
    except FileNotFoundError:
        logger.error(f"Symbols configuration file not found at {config_path}.")
        return []

def fetch_full_history(engine, symbol):
    """Fetch all historical price data for the given symbol from the database."""
    try:
        query = text("""
            SELECT timestamp, open, high, low, close, volume
            FROM historical_stock_prices
            WHERE symbol = :symbol
            ORDER BY timestamp ASC
        """)
        df = pd.read_sql(query, engine, params={"symbol": symbol})
        if df.empty:
            logger.warning(f"No data found for {symbol}")
        return df
    except Exception as e:
        logger.error(f"Error fetching full history for {symbol}: {str(e)}")
        return pd.DataFrame()

def run_backtest(engine, symbol, strategy_params=None):
    """
    Perform backtesting for the specified symbol, allowing only one open position at a time.
    A new position is opened only when there are no currently open positions.
    """
    df = fetch_full_history(engine, symbol)
    if df.empty:
        logger.warning(f"No data for {symbol}")
        return []
    if len(df) < 200:
        logger.warning(f"Not enough data for {symbol}: {len(df)} days")
        return []

    # Ensure chronological order
    df = df.sort_values("timestamp").reset_index(drop=True)

    strategy = MomentumTrendBreakoutStrategy(engine, settings=strategy_params)
    min_days = strategy_params.get("trend_period", 5)  # minimum lookback period

    open_positions = []
    closed_positions = []

    # Go through each day from min_days to the end minus 1
    for i in range(min_days, len(df) - 1):
        # 1) Check/close existing positions for day i
        today_high = df["high"].iloc[i]
        today_low = df["low"].iloc[i]
        today_date = df["timestamp"].iloc[i]

        # For each open position, see if day i hits stop-loss or target
        for pos in open_positions[:]:
            # Skip if we haven't reached the day after the position was opened
            if i < pos["entry_index"]:
                continue

            stop_loss = pos["stop_loss"]
            target = pos["target"]

            stop_hit = (today_low <= stop_loss <= today_high)
            target_hit = (today_low <= target <= today_high)

            # If both triggered on the same day, pick which triggers first
            if stop_hit and target_hit:
                day_open = df["open"].iloc[i]
                dist_stop = abs(day_open - stop_loss)
                dist_target = abs(day_open - target)
                if dist_stop < dist_target:
                    target_hit = False
                else:
                    stop_hit = False

            if stop_hit:
                pos["exit_date"] = today_date
                pos["exit_index"] = i
                pos["exit_price"] = stop_loss
                pos["profit"] = stop_loss - pos["entry_price"]
                closed_positions.append(pos)
                open_positions.remove(pos)
            elif target_hit:
                pos["exit_date"] = today_date
                pos["exit_index"] = i
                pos["exit_price"] = target
                pos["profit"] = target - pos["entry_price"]
                closed_positions.append(pos)
                open_positions.remove(pos)

        # 2) If no position is open, check for a new signal on day i
        if not open_positions:
            window = df.iloc[:i+1].copy()
            strategy.get_historical_data = lambda sym, days=30, window=window: window

            signal = strategy.analyze(symbol)
            if signal:
                entry_index = i + 1
                if entry_index >= len(df):
                    # we can't open a position if we're at the end of the data
                    break

                entry_date = df["timestamp"].iloc[entry_index]
                next_day_open = df["open"].iloc[entry_index]

                # Suppose signal["price"] is the intended breakout entry
                if next_day_open < signal["price"]:  # NEW
                    logger.info(f"Skipping trade for {symbol} on {entry_date}, "
                                f"next day open={next_day_open} < trigger={signal['price']}")
                    continue  # do not open position

                open_positions.append({
                    "symbol": symbol,
                    "signal_type": signal["signal_type"],
                    "signal_date": df["timestamp"].iloc[i],
                    "entry_date": entry_date,
                    "entry_index": entry_index,
                    "entry_price": next_day_open,
                    "stop_loss": signal["stop_loss"],
                    "target": signal["target"],
                    "conditions_met": signal["conditions_met"],
                    "exit_date": None,
                    "exit_index": None,
                    "exit_price": None,
                    "profit": None,
                })

    return closed_positions

def backtest_report(closed_positions, label=""):
    """
    Summarizes the performance of a list of closed positions:
    - total trades
    - number of wins vs. losses
    - average gain/loss
    - simple win rate
    """
    if not closed_positions:
        logger.info(f"[{label}] No closed positions. No trades triggered or none reached stop/target.")
        return

    df_report = pd.DataFrame(closed_positions)
    df_report["pct_change"] = (
        (df_report["exit_price"] - df_report["entry_price"]) / df_report["entry_price"]
    ) * 100

    total_trades = len(df_report)
    wins = df_report[df_report["profit"] > 0]
    losses = df_report[df_report["profit"] <= 0]

    avg_gain = wins["pct_change"].mean() if not wins.empty else 0.0
    avg_loss = losses["pct_change"].mean() if not losses.empty else 0.0
    win_rate = len(wins) / total_trades * 100.0

    logger.info(f"===== Backtest Results [{label}] =====")
    logger.info(f"Total closed trades: {total_trades}")
    logger.info(f"Wins: {len(wins)} | Losses: {len(losses)}")
    logger.info(f"Win rate: {win_rate:.2f}%")
    logger.info(f"Average gain (wins only): {avg_gain:.2f}%")
    logger.info(f"Average loss (losses only): {avg_loss:.2f}%")
    overall_pct = df_report["pct_change"].mean()
    logger.info(f"Overall average change: {overall_pct:.2f}%")
    logger.info(df_report[["symbol","signal_type","entry_date","exit_date","profit","pct_change"]].tail(5))

def save_closed_positions(engine, closed_positions):
    """
    Insert each closed position into backtest_closed_positions table.
    """
    if not closed_positions:
        return

    insert_query = text("""
        INSERT INTO backtest_closed_positions (
            symbol,
            signal_type,
            signal_date,
            entry_date,
            entry_price,
            stop_loss,
            target,
            conditions_met,
            exit_date,
            exit_price,
            profit,
            profit_pct
        )
        VALUES (
            :symbol,
            :signal_type,
            :signal_date,
            :entry_date,
            :entry_price,
            :stop_loss,
            :target,
            :conditions_met,
            :exit_date,
            :exit_price,
            :profit,
            :profit_pct
        )
    """)

    with engine.begin() as conn:
        for pos in closed_positions:
            # Convert np.float64 to Python float
            entry_price = float(pos["entry_price"]) if pos["entry_price"] is not None else None
            stop_loss   = float(pos["stop_loss"])   if pos["stop_loss"]   is not None else None
            target      = float(pos["target"])      if pos["target"]      is not None else None
            exit_price  = float(pos["exit_price"])  if pos["exit_price"]  is not None else None
            profit      = float(pos["profit"])      if pos["profit"]      is not None else None

            # Compute a percentage gain/loss
            if entry_price is not None and exit_price is not None:
                profit_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                profit_pct = None

            conn.execute(insert_query, {
                "symbol": pos["symbol"],
                "signal_type": pos["signal_type"],
                "signal_date": pos["signal_date"],
                "entry_date": pos["entry_date"],
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target": target,
                "conditions_met": pos["conditions_met"],
                "exit_date": pos["exit_date"],
                "exit_price": exit_price,
                "profit": profit,
                "profit_pct": profit_pct
            })

    logger.info(f"Inserted {len(closed_positions)} closed positions into database.")

if __name__ == "__main__":
    engine = get_db_connection()

    # 1) Ensure the table exists
    create_backtest_closed_positions_table(engine)

    # 2) Load the symbol list from the same config used by analyze.py
    symbols = load_symbols_config()
    if not symbols:
        logger.warning("No symbols to backtest. Exiting.")
        exit(0)

    # 3) Define the strategy parameters
    strategy_params = {
        "trend_period": 5,
        "momentum_period": 14,
        "min_volume_multiplier": 1.2,
        "rsi_threshold": 50,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "min_conditions": 2,
        "risk_reward_ratio": 3,
        "atr_multiplier": 1.5,
    }

    # 4) Run the backtest for EACH symbol and aggregate the results
    all_closed_positions = []
    for sym in symbols:
        closed_positions = run_backtest(engine, sym, strategy_params)
        logger.info(f"Backtest for {sym} returned {len(closed_positions)} closed trades.")
        all_closed_positions.extend(closed_positions)

    # 5) Print a single consolidated summary of all trades
    backtest_report(all_closed_positions, label="ALL SYMBOLS")

    # 6) Save them all to the DB table
    save_closed_positions(engine, all_closed_positions)
    logger.info("Done.")
