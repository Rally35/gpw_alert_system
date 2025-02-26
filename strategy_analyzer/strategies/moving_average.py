import pandas as pd
import numpy as np
import logging

logger = logging.getLogger('strategy.moving_average')

class MovingAverageStrategy:
    """
    Strategy that generates signals based on MA50/MA100 crossovers
    """
    
    def __init__(self, db_engine, settings=None):
        self.engine = db_engine
        self.name = "MA Crossover"
        self.settings = settings or {
            "short_ma": 50,
            "long_ma": 100,
            "min_volume": 10000
        }
    
    def get_data(self, symbol, days=120):
        """Get historical data for analysis"""
        try:
            # Calculate how many hours we need (assuming hourly data)
            hours = days * 24
            
            query = f"""
            SELECT timestamp, close, volume
            FROM historical_stock_prices
            WHERE symbol = '{symbol}'
            ORDER BY timestamp DESC
            LIMIT {hours}
            """
            
            df = pd.read_sql(query, self.engine)
            
            # Sort by timestamp ascending for proper calculation
            return df.sort_values('timestamp')
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def analyze(self, symbol):
        """Analyze the symbol and return signals if any"""
        df = self.get_data(symbol)
        
        if len(df) < self.settings["long_ma"]:
            logger.warning(f"Not enough data for {symbol}. Need {self.settings['long_ma']} points but got {len(df)}")
            return None
        
        # Calculate moving averages
        df['MA_short'] = df['close'].rolling(window=self.settings["short_ma"]).mean()
        df['MA_long'] = df['close'].rolling(window=self.settings["long_ma"]).mean()
        
        # Clean NaN values
        df = df.dropna()
        
        if len(df) < 2:
            return None
        
        # Check for crossover
        prev_row = df.iloc[-2]
        curr_row = df.iloc[-1]
        
        # Buy signal: short MA crosses above long MA
        buy_signal = (prev_row['MA_short'] <= prev_row['MA_long']) and (curr_row['MA_short'] > curr_row['MA_long'])
        
        # Sell signal: short MA crosses below long MA
        sell_signal = (prev_row['MA_short'] >= prev_row['MA_long']) and (curr_row['MA_short'] < curr_row['MA_long'])
        
        # Check volume requirement
        recent_volume = float(curr_row['volume'])
        if recent_volume < self.settings["min_volume"]:
            logger.info(f"Volume too low for {symbol}: {recent_volume} < {self.settings['min_volume']}")
            return None
        
        if buy_signal:
            return {
                "symbol": symbol,
                "signal_type": "BUY",
                "strategy": self.name,
                "price": float(curr_row['close']),
                "ma50": float(curr_row['MA_short']),
                "ma100": float(curr_row['MA_long']),
                "volume": int(recent_volume)
            }
        elif sell_signal:
            return {
                "symbol": symbol,
                "signal_type": "SELL",
                "strategy": self.name,
                "price": float(curr_row['close']),
                "ma50": float(curr_row['MA_short']),
                "ma100": float(curr_row['MA_long']),
                "volume": int(recent_volume)
            }
        
        return None