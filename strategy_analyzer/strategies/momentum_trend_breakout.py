import pandas as pd
import numpy as np
from sqlalchemy import text
import logging

logger = logging.getLogger('MomentumTrendBreakoutStrategy')

class MomentumTrendBreakoutStrategy:
    """
    Momentum Trend Breakout Strategy:

    Analyzes daily closing prices to detect an uptrend and generates an entry signal if:
      - The stock’s closing price is above its 5-day SMA for at least the last 2 days.
      - In addition, at least 2 of the following conditions are met:
          • Volume condition: Last day’s volume is >= 1.2 times the 5-day average volume.
          • RSI condition: RSI (14) > 50.
          • MACD bullish crossover: Yesterday MACD <= signal and today MACD > signal.
          • Breakout condition: Current close equals (or exceeds) the maximum close over the last 5 days.

    Exit triggers (for risk management) are calculated as:
      - Stop-loss: Current price minus 1.5 times the ATR (14).
      - Target price: Current price plus 3 times the risk (i.e. using a 1:3 risk-reward ratio).

    The strategy returns a signal containing the entry price, stop-loss, target price,
    and details of the conditions met.
    """

    def __init__(self, db_engine, settings=None):
        self.engine = db_engine
        self.name = "Momentum Trend Breakout"
        default_settings = {
            "trend_period": 5,            # 5-day SMA period
            "momentum_period": 14,        # for RSI and ATR calculations
            "min_volume_multiplier": 1.2, # last day volume must be at least 120% of 5-day average
            "rsi_threshold": 50,          # RSI must be above 50
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "min_conditions": 2,          # need at least 2 additional conditions to trigger a signal
            "risk_reward_ratio": 3,       # target = entry + 3*(entry - stop_loss)
            "atr_multiplier": 1.5,        # stop_loss = entry - (1.5 * ATR)
        }
        if settings:
            default_settings.update(settings)
        self.settings = default_settings

    def calculate_sma(self, series, window):
        return series.rolling(window=window).mean()

    def calculate_rsi(self, series, period):
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_ema(self, series, span):
        return series.ewm(span=span, adjust=False).mean()

    def calculate_macd(self, series):
        ema_fast = self.calculate_ema(series, self.settings["macd_fast"])
        ema_slow = self.calculate_ema(series, self.settings["macd_slow"])
        macd_line = ema_fast - ema_slow
        signal_line = self.calculate_ema(macd_line, self.settings["macd_signal"])
        return macd_line, signal_line

    def calculate_atr(self, df, period):
        high = df['high']
        low = df['low']
        close = df['close']
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=period).mean()
        return atr

    def get_historical_data(self, symbol, days=30):
        """Retrieve historical data for a given symbol from the database."""
        try:
            query = text("""
                SELECT timestamp, open, high, low, close, volume
                FROM historical_stock_prices
                WHERE symbol = :symbol
                ORDER BY timestamp DESC
                LIMIT :limit
            """)
            df = pd.read_sql(query, self.engine, params={"symbol": symbol, "limit": days})
            if df.empty:
                logger.warning(f"No historical data for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
            return pd.DataFrame()

    def analyze(self, symbol):
        """
        Analizuje spółkę i zwraca sygnał, jeśli warunki są spełnione.
        Zwraca sygnał typu WATCH, jeśli spełniono 2 kryteria,
        oraz sygnał ALERT (ENTRY) gdy spełniono 3 lub więcej kryteriów.
        """
        df = self.get_historical_data(symbol, days=30)
        if df.empty or len(df) < self.settings["trend_period"]:
            logger.warning(f"Not enough data for {symbol}")
            return None

        df = df.sort_values('timestamp').reset_index(drop=True)
        df['sma5'] = self.calculate_sma(df['close'], self.settings["trend_period"])

        if len(df) < 2:
            return None
        uptrend = (df['close'].iloc[-1] > df['sma5'].iloc[-1]) and (df['close'].iloc[-2] > df['sma5'].iloc[-2])
        if not uptrend:
            logger.info(f"{symbol}: Uptrend condition not met")
            return None

        current_price = df['close'].iloc[-1]
        turnover = df['volume'].iloc[-1] * current_price
        if turnover < 500000:
            logger.info(f"{symbol}: Daily turnover {turnover:.2f} PLN is below threshold")
            return None

        conditions_met = 0
        avg_volume = df['volume'].rolling(window=self.settings["trend_period"]).mean().iloc[-1]
        if df['volume'].iloc[-1] >= self.settings["min_volume_multiplier"] * avg_volume:
            conditions_met += 1

        rsi = self.calculate_rsi(df['close'], self.settings["momentum_period"])
        if not rsi.empty and rsi.iloc[-1] > self.settings["rsi_threshold"]:
            conditions_met += 1

        macd_line, signal_line = self.calculate_macd(df['close'])
        if len(macd_line) >= 2:
            if macd_line.iloc[-2] <= signal_line.iloc[-2] and macd_line.iloc[-1] > signal_line.iloc[-1]:
                conditions_met += 1

        recent_max = df['close'].rolling(window=self.settings["trend_period"]).max().iloc[-1]
        breakout = df['close'].iloc[-1] >= recent_max
        if breakout:
            conditions_met += 1

        logger.info(f"{symbol}: Additional conditions met: {conditions_met}")

        # Ustal typ sygnału i status na podstawie liczby spełnionych warunków.
        if conditions_met >= 3:
            signal_type = "ALERT"
            status = "ALERT"
        elif conditions_met == 2:
            signal_type = "WATCH"
            status = "WATCH"
        else:
            return None

        # Oblicz trigger_entry jako maksymalną cenę z ostatnich 5 dni
        trigger_entry = df['close'].rolling(window=self.settings["trend_period"]).max().iloc[-1]

        atr_series = self.calculate_atr(df, self.settings["momentum_period"])
        current_atr = atr_series.iloc[-1] if not atr_series.empty else 0
        stop_loss = current_price - (self.settings["atr_multiplier"] * current_atr) if current_atr > 0 else current_price * 0.98
        target = current_price + self.settings["risk_reward_ratio"] * (current_price - stop_loss)

        signal = {
            "symbol": symbol,
            "signal_type": signal_type,
            "strategy": self.name,
            "price": current_price,
            "stop_loss": stop_loss,
            "target": target,
            "conditions_met": conditions_met,
            "status": status,
            "details": {
                "uptrend": True,
                "volume": df['volume'].iloc[-1],
                "avg_volume": avg_volume,
                "rsi": rsi.iloc[-1] if not rsi.empty else None,
                "macd": macd_line.iloc[-1],
                "macd_signal": signal_line.iloc[-1],
                "breakout": breakout,
                "atr": current_atr,
                "turnover": turnover,
                "trigger_entry": trigger_entry
            }
        }
        logger.info(f"{symbol}: Signal generated: {signal}")
        return signal
