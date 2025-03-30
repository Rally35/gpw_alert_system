import pandas as pd
import numpy as np
import logging
import os
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
    Perform backtesting for the specified symbol, actually "opening" positions
    and tracking them day-by-day until stop-loss or target is reached.

    Returns a list of closed positions with final P&L.
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
    # so we can open a position at "day i+1" if there's a signal on "day i".
    for i in range(min_days, len(df) - 1):
        # Data up to current day i (simulate we only know info up to day i)
        window = df.iloc[:i+1].copy()

        # Override get_historical_data so strategy only sees data up to this day
        strategy.get_historical_data = lambda sym, days=30, window=window: window

        # 1) Check if there's a new signal on day i
        signal = strategy.analyze(symbol)
        if signal:
            # "Open" a position at next day's open (day i+1), if available
            entry_index = i + 1
            entry_date = df["timestamp"].iloc[entry_index]
            entry_price = df["open"].iloc[entry_index]
            open_positions.append({
                "symbol": symbol,
                "signal_type": signal["signal_type"],
                "signal_date": df["timestamp"].iloc[i],
                "entry_date": entry_date,
                "entry_index": entry_index,
                "entry_price": entry_price,
                "stop_loss": signal["stop_loss"],
                "target": signal["target"],
                "conditions_met": signal["conditions_met"],
                "exit_date": None,
                "exit_index": None,
                "exit_price": None,
                "profit": None,  # will fill when closed
            })

        # 2) For each open position, check if day i hits stop-loss or target
        # We do this check using day i’s high/low to see if it crosses either level
        today_high = df["high"].iloc[i]
        today_low = df["low"].iloc[i]
        today_date = df["timestamp"].iloc[i]

        for pos in open_positions[:]:
            # Ensure we don't close on or before the day we opened
            # If i < pos["entry_index"], skip (haven't reached opening day yet)
            if i < pos["entry_index"]:
                continue

            stop_loss = pos["stop_loss"]
            target = pos["target"]

            # Check if stop-loss triggered
            stop_hit = (today_low <= stop_loss <= today_high)
            # Check if target triggered
            target_hit = (today_low <= target <= today_high)

            # If both could happen the same day, decide which triggers first
            # (you might need intraday logic or define your own priority).
            if stop_hit and target_hit:
                # Suppose we say whichever is closer to the open is triggered first, etc.
                # For simplicity, let's assume stop-loss triggers first if it is below the open.
                # We'll use day i's open to guess "who got hit first"
                day_open = df["open"].iloc[i]
                dist_stop = abs(day_open - stop_loss)
                dist_target = abs(day_open - target)
                if dist_stop < dist_target:
                    stop_hit = True
                    target_hit = False
                else:
                    stop_hit = False
                    target_hit = True

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

    return closed_positions

def backtest_report(closed_positions):
    """
    Summarizes the performance of all closed positions:
    - total trades
    - number of wins vs. losses
    - average gain/loss
    - simple win rate
    """
    if not closed_positions:
        logger.info("No closed positions. No trades triggered or none reached stop/target.")
        return

    df_report = pd.DataFrame(closed_positions)
    # Calculate percentage change from entry to exit
    df_report["pct_change"] = (df_report["exit_price"] - df_report["entry_price"]) / df_report["entry_price"] * 100

    total_trades = len(df_report)
    wins = df_report[df_report["profit"] > 0]
    losses = df_report[df_report["profit"] <= 0]

    avg_gain = wins["pct_change"].mean() if not wins.empty else 0.0
    avg_loss = losses["pct_change"].mean() if not losses.empty else 0.0
    win_rate = len(wins) / total_trades * 100.0

    logger.info("===== Backtest Results =====")
    logger.info(f"Total closed trades: {total_trades}")
    logger.info(f"Wins: {len(wins)} | Losses: {len(losses)}")
    logger.info(f"Win rate: {win_rate:.2f}%")
    logger.info(f"Average gain (wins only): {avg_gain:.2f}%")
    logger.info(f"Average loss (losses only): {avg_loss:.2f}%")
    logger.info(f"Overall average change: {df_report['pct_change'].mean():.2f}%")

    # Optional: show a few rows of results
    logger.info(df_report)

if __name__ == "__main__":
    engine = get_db_connection()
    symbol = "PKO"  # Example
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
    # Run the enhanced backtest that opens/closes real positions
    closed_positions = run_backtest(engine, symbol, strategy_params)
    logger.info(f"Backtest for {symbol} returned {len(closed_positions)} closed trades.")
    backtest_report(closed_positions)
