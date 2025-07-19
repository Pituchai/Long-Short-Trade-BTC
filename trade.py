import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import datetime as dt
import time
import requests
import json
from binance.client import Client
import creds2

class LongShortTrader():
    
    def __init__(self,client, symbol, bar_length, return_thresh, volume_thresh, units, position=0):
        self.client = client
        self.symbol = symbol
        self.bar_length = bar_length
        self.available_intervals = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
        self.units = units
        self.position = position
        self.trades = 0 
        self.trade_values = []
        
        # Strategy-specific attributes
        self.return_thresh = return_thresh
        self.volume_thresh = volume_thresh
        
        # Convert interval to milliseconds for polling
        self.interval_ms = self._interval_to_ms(bar_length)
        self.last_kline_time = None
        self.stop_trading = False
    
    def _interval_to_ms(self, interval):
        """Convert interval string to milliseconds"""
        interval_map = {
            "1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000, "30m": 1800000,
            "1h": 3600000, "2h": 7200000, "4h": 14400000, "6h": 21600000,
            "8h": 28800000, "12h": 43200000, "1d": 86400000
        }
        return interval_map.get(interval, 60000)
    
    def start_trading(self, historical_days):
        """Start trading with polling approach instead of WebSocket"""
        if self.bar_length in self.available_intervals:
            print("Starting trading session...")
            self.get_most_recent(symbol=self.symbol, interval=self.bar_length, days=historical_days)
            print(f"Historical data loaded. Starting live trading on {self.symbol} {self.bar_length}")
            
            # Start polling loop
            self.polling_loop()
    
    def get_most_recent(self, symbol, interval, days):
        """Get historical kline data"""
        now = datetime.now(dt.timezone.utc)
        past = str(now - timedelta(days=days))
        
        bars = client.get_historical_klines(symbol=symbol, interval=interval,
                                            start_str=past, end_str=None, limit=1000)
        df = pd.DataFrame(bars)
        df["Date"] = pd.to_datetime(df.iloc[:,0], unit="ms")
        df.columns = ["Open Time", "Open", "High", "Low", "Close", "Volume",
                      "Close Time", "Quote Asset Volume", "Number of Trades",
                      "Taker Buy Base Asset Volume", "Taker Buy Quote Asset Volume", "Ignore", "Date"]
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df.set_index("Date", inplace=True)
        for column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["Complete"] = [True for row in range(len(df)-1)] + [False]
        
        self.data = df
        self.last_kline_time = df.index[-1]
        print(f"Loaded {len(df)} historical bars. Last bar: {self.last_kline_time}")
    
    def polling_loop(self):
        """Main polling loop to check for new klines"""
        while not self.stop_trading and self.trades < 100:
            try:
                # Get the latest kline
                klines = client.get_klines(symbol=self.symbol, interval=self.bar_length, limit=2)
                
                if klines:
                    # Process the latest complete kline (second to last)
                    if len(klines) >= 2:
                        latest_kline = klines[-2]  # Get the completed kline
                        current_kline = klines[-1]  # Get the current (incomplete) kline
                        
                        # Convert to timestamp
                        kline_time = pd.to_datetime(latest_kline[0], unit="ms")
                        
                        # Check if this is a new kline
                        if self.last_kline_time is None or kline_time > self.last_kline_time:
                            print(f"\nNew completed kline detected: {kline_time}")
                            self.process_new_kline(latest_kline, completed=True)
                            self.last_kline_time = kline_time
                        
                        # Update the current incomplete kline
                        current_time = pd.to_datetime(current_kline[0], unit="ms")
                        self.process_new_kline(current_kline, completed=False)
                
                print(".", end="", flush=True)
                time.sleep(5)  # Poll every 5 seconds
                
            except Exception as e:
                print(f"\nError in polling loop: {e}")
                time.sleep(10)  # Wait longer on error
    
    def process_new_kline(self, kline_data, completed):
        """Process new kline data"""
        try:
            start_time = pd.to_datetime(kline_data[0], unit="ms")
            open_price = float(kline_data[1])
            high_price = float(kline_data[2])
            low_price = float(kline_data[3])
            close_price = float(kline_data[4])
            volume = float(kline_data[5])
            
            # Update data
            self.data.loc[start_time] = [open_price, high_price, low_price, close_price, volume, completed]
            
            # Execute strategy only on completed klines
            if completed:
                print(f"\nProcessing completed kline: {start_time}")
                self.define_strategy()
                self.execute_trades()
                
                # Check if we should stop
                if self.trades >= 100:
                    self.stop_trading = True
                    self.close_all_positions()
                    
        except Exception as e:
            print(f"Error processing kline: {e}")
    
    def close_all_positions(self):
        """Close all open positions before stopping"""
        print("\nClosing all positions before stopping...")
        if self.position == 1:
            order = client.create_order(symbol=self.symbol, side="SELL", type="MARKET", quantity=self.units)
            self.report_trade(order, "GOING NEUTRAL AND STOP")
            self.position = 0
        elif self.position == -1:
            order = client.create_order(symbol=self.symbol, side="BUY", type="MARKET", quantity=self.units)
            self.report_trade(order, "GOING NEUTRAL AND STOP")
            self.position = 0
        print("Trading session completed!")
    
    def define_strategy(self):
        """Define trading strategy"""
        df = self.data.copy()
        
        # Only use completed klines for strategy
        df = df[df["Complete"] == True].copy()
        df = df[["Close", "Volume"]].copy()
        
        if len(df) < 2:  # Need at least 2 bars for returns calculation
            self.prepared_data = df.copy()
            self.prepared_data["position"] = 0
            return
        
        df["returns"] = np.log(df.Close / df.Close.shift())
        df["vol_ch"] = np.log(df.Volume.div(df.Volume.shift(1)))
        df.loc[df.vol_ch > 3, "vol_ch"] = np.nan
        df.loc[df.vol_ch < -3, "vol_ch"] = np.nan  
        
        cond1 = df.returns <= self.return_thresh[0]
        cond2 = df.vol_ch.between(self.volume_thresh[0], self.volume_thresh[1])
        cond3 = df.returns >= self.return_thresh[1]
        
        df["position"] = 0
        df.loc[cond1 & cond2, "position"] = 1
        df.loc[cond3 & cond2, "position"] = -1
        
        self.prepared_data = df.copy()
        
        # Print strategy signals
        if len(df) > 0:
            latest_return = df["returns"].iloc[-1] if not pd.isna(df["returns"].iloc[-1]) else 0
            latest_vol_ch = df["vol_ch"].iloc[-1] if not pd.isna(df["vol_ch"].iloc[-1]) else 0
            latest_position = df["position"].iloc[-1]
            print(f"Strategy signal - Return: {latest_return:.4f}, Vol_ch: {latest_vol_ch:.4f}, Position: {latest_position}")
    
    def execute_trades(self):
        """Execute trades based on strategy signals"""
        if len(self.prepared_data) == 0 or pd.isna(self.prepared_data["position"].iloc[-1]):
            return
            
        target_position = int(self.prepared_data["position"].iloc[-1])
        
        if target_position == self.position:
            return  # No change needed
        
        try:
            if target_position == 1:  # Go long
                if self.position == 0:
                    order = client.create_order(symbol=self.symbol, side="BUY", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING LONG")
                elif self.position == -1:
                    order = client.create_order(symbol=self.symbol, side="BUY", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING NEUTRAL")
                    time.sleep(0.1)
                    order = client.create_order(symbol=self.symbol, side="BUY", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING LONG")
                self.position = 1
                
            elif target_position == 0:  # Go neutral
                if self.position == 1:
                    order = client.create_order(symbol=self.symbol, side="SELL", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING NEUTRAL")
                elif self.position == -1:
                    order = client.create_order(symbol=self.symbol, side="BUY", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING NEUTRAL")
                self.position = 0
                
            elif target_position == -1:  # Go short
                if self.position == 0:
                    order = client.create_order(symbol=self.symbol, side="SELL", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING SHORT")
                elif self.position == 1:
                    order = client.create_order(symbol=self.symbol, side="SELL", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING NEUTRAL")
                    time.sleep(0.1)
                    order = client.create_order(symbol=self.symbol, side="SELL", type="MARKET", quantity=self.units)
                    self.report_trade(order, "GOING SHORT")
                self.position = -1
                
        except Exception as e:
            print(f"Error executing trade: {e}")
    
    def report_trade(self, order, going):
        """Report trade details"""
        try:
            side = order["side"]
            trade_time = pd.to_datetime(order["transactTime"], unit="ms")
            base_units = float(order["executedQty"])
            quote_units = float(order["cummulativeQuoteQty"])
            price = round(quote_units / base_units, 5)
            
            # Calculate trading profits
            self.trades += 1
            if side == "BUY":
                self.trade_values.append(-quote_units)
            elif side == "SELL":
                self.trade_values.append(quote_units)
            
            if self.trades % 2 == 0:
                real_profit = round(np.sum(self.trade_values[-2:]), 3)
                self.cum_profits = round(np.sum(self.trade_values), 3)
            else:
                real_profit = 0
                self.cum_profits = round(np.sum(self.trade_values[:-1]), 3)
            
            # Print trade report
            print(2 * "\n" + 100 * "-")
            print("{} | {}".format(trade_time, going))
            print("{} | Base_Units = {} | Quote_Units = {} | Price = {}".format(
                trade_time, base_units, quote_units, price))
            print("{} | Profit = {} | CumProfits = {}".format(
                trade_time, real_profit, self.cum_profits))
            print(100 * "-" + "\n")
            
        except Exception as e:
            print(f"Error reporting trade: {e}")

# Initialize and run
if __name__ == "__main__":
    # Initialize client, hahaha I don't api here stupid boss 
    api_key = creds2.api_key
    secret_key = creds2.secret_key
    client = Client(api_key=api_key, api_secret=secret_key, tld="com", testnet=True)
    
    # Test connection
    try:
        account = client.get_account()
        print("Connected to Binance testnet successfully")
        for bal in account['balances']:
             if bal['asset'] == 'USDT':
                  print(f"USDT Balance: {bal['free']} (Free), {bal['locked']} (Locked)")

    except Exception as e:
        print(f"Connection error: {e}")
        exit(1)
    
    # Trading parameters
    symbol = "BTCUSDT"
    bar_length = "1m"
    return_thresh = [-0.0001, 0.0001]  # Changed from [-0.01, 0.01] to [-0.0001, 0.0001] (0.01% threshold)
    volume_thresh = [-3, 3]            # Changed from [1, 3] to [-3, 3] (wider range)
    units = 0.01                       # Trade size in BTC
    position = 0
    
    # Create and start trader
    trader = LongShortTrader(
        client=client,
        symbol=symbol,
        bar_length=bar_length,
        return_thresh=return_thresh,
        volume_thresh=volume_thresh,
        units=units,
        position=position
    )
    
    try:
        trader.start_trading(historical_days=1/24)  # Get 1 hour of historical data
    except KeyboardInterrupt:
        print("\nTrading interrupted by user")
        trader.stop_trading = True
        trader.close_all_positions()
    except Exception as e:
        print(f"\nTrading error: {e}")
        trader.stop_trading = True
        trader.close_all_positions()



