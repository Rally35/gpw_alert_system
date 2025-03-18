class ConsecutiveGainsStrategy:
    """
    Strategy that identifies stocks with consecutive daily gains
    """

    def __init__(self, db_engine, settings=None):
        self.engine = db_engine
        self.name = "Consecutive Gains"
        self.settings = settings or {
            "min_days": 5,
            "min_volume": 10000,
            "min_gain_percent": 0.1  # Minimum daily gain (0.1%)
        }

    def get_data(self, symbol, days=10):  # We need more than 5 days to check the pattern
        """Get historical data for analysis"""
        try:
            query = f"""
            SELECT timestamp, close, volume
            FROM historical_stock_prices
            WHERE symbol = '{symbol}'
            ORDER BY timestamp DESC
            LIMIT {days}
            """

            df = pd.read_sql(query, self.engine)

            # Sort by timestamp ascending for proper calculation
            return df.sort_values('timestamp')

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            return pd.DataFrame()

    def analyze(self, symbol):
        """Analyze the symbol for consecutive gains"""
        df = self.get_data(symbol)

        if len(df) < self.settings["min_days"] + 1:  # We need one extra day for comparison
            logger.warning(f"Not enough data for {symbol}. Need {self.settings['min_days']+1} points but got {len(df)}")
            return None

        # Calculate daily returns
        df['prev_close'] = df['close'].shift(1)
        df = df.dropna()  # Remove the first row which has NaN for prev_close
        df['daily_return'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100

        # Check if we have enough consecutive gains
        recent_days = df.tail(self.settings["min_days"])
        consecutive_gains = all(ret >= self.settings["min_gain_percent"] for ret in recent_days['daily_return'])

        # Check volume requirement
        recent_volume = float(df.iloc[-1]['volume'])
        if recent_volume < self.settings["min_volume"]:
            return None

        if consecutive_gains:
            # Calculate total gain over the period
            total_gain = (df.iloc[-1]['close'] / df.iloc[-self.settings["min_days"]-1]['close'] - 1) * 100

            return {
                "symbol": symbol,
                "signal_type": "UPTREND",
                "strategy": self.name,
                "price": float(df.iloc[-1]['close']),
                "volume": int(recent_volume),
                "days_up": self.settings["min_days"],
                "total_gain": float(total_gain)
            }

        return None
