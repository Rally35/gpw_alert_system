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
    """Pobiera pełne dane historyczne dla danego symbolu z bazy."""
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
    Przeprowadza backtesting dla danego symbolu.
    Iteruje po dniach i symuluje działanie strategii.
    Zwraca listę sygnałów z dodatkową informacją o dacie, dla której sygnał został wygenerowany.
    """
    df = fetch_full_history(engine, symbol)
    if df.empty:
        return []
    if len(df) < 200:
        logger.warning(f"Not enough data for {symbol}: {len(df)} dni")
        return []

    signals = []
    min_days = 5  # minimalny okres analizy

    strategy = MomentumTrendBreakoutStrategy(engine, settings=strategy_params)

    # Symulujemy backtesting: dla każdego dnia (od min_days do końca danych)
    for i in range(min_days, len(df)):
        window = df.iloc[:i].copy()
        if len(window) < min_days:
            continue
        # Nadpisujemy metodę get_historical_data, by symulować, że mamy tylko dane do tego dnia
        strategy.get_historical_data = lambda symbol, days=30, window=window: window

        signal = strategy.analyze(symbol)
        if signal:
            signal["backtest_date"] = window["timestamp"].iloc[-1]
            signals.append(signal)

    return signals

def backtest_report(signals):
    if not signals:
        logger.info("No signals generated during backtesting.")
        return

    report_data = []
    wins = 0
    losses = 0
    for s in signals:
        entry = s["price"]
        target = s["target"]
        stop_loss = s["stop_loss"]

        profit_pct = ((target - entry) / entry) * 100
        loss_pct = ((entry - stop_loss) / entry) * 100

        # Symulacja: jeśli potencjalny zysk jest większy niż potencjalna strata, uznajemy transakcję za "wygraną"
        if profit_pct > loss_pct:
            wins += 1
        else:
            losses += 1

        report_data.append({
            "symbol": s["symbol"],
            "backtest_date": s.get("backtest_date"),
            "signal_type": s["signal_type"],
            "entry": entry,
            "target": target,
            "stop_loss": stop_loss,
            "profit_pct": profit_pct,
            "loss_pct": loss_pct,
            "conditions_met": s["conditions_met"]
        })

    df_report = pd.DataFrame(report_data)
    logger.info("Backtest Report:")
    logger.info(df_report)

    total_trades = len(df_report)
    avg_profit = df_report["profit_pct"].mean() if total_trades > 0 else 0
    avg_loss = df_report["loss_pct"].mean() if total_trades > 0 else 0
    risk_reward = avg_profit / avg_loss if avg_loss != 0 else np.nan
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0

    logger.info(f"Total trades: {total_trades}")
    logger.info(f"Average potential profit (%): {avg_profit:.2f}")
    logger.info(f"Average potential loss (%): {avg_loss:.2f}")
    logger.info(f"Average Risk/Reward Ratio: {risk_reward:.2f}")
    logger.info(f"Win rate: {win_rate:.2f}%")

if __name__ == "__main__":
    engine = get_db_connection()
    symbol = "PKO"  # Przykładowy symbol – możesz testować również inne
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
    signals = run_backtest(engine, symbol, strategy_params)
    logger.info(f"Backtest for {symbol} generated {len(signals)} signals")
    backtest_report(signals)
