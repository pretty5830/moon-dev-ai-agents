import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
import talib

def compute_up_fractals(high):
    up = np.full(len(high), np.nan)
    n = len(high)
    for i in range(2, n - 2):
        h2 = high[i]
        if (h2 > high[i - 1] and h2 > high[i - 2] and
            h2 > high[i + 1] and h2 > high[i + 2]):
            up[i] = h2
    return up

def compute_down_fractals(low):
    down = np.full(len(low), np.nan)
    n = len(low)
    for i in range(2, n - 2):
        l2 = low[i]
        if (l2 < low[i - 1] and l2 < low[i - 2] and
            l2 < low[i + 1] and l2 < low[i + 2]):
            down[i] = l2
    return down

def compute_ffill_fractal(fractal):
    filled = np.full(len(fractal), np.nan)
    prev = np.nan
    for i in range(len(fractal)):
        if not np.isnan(fractal[i]):
            prev = fractal[i]
        filled[i] = prev
    return filled

def compute_shifted_ema(s, period, shift):
    ema = talib.EMA(s, timeperiod=period)
    shifted = np.full_like(ema, np.nan)
    if len(ema) > shift:
        shifted[shift:] = ema[:len(ema) - shift]
    return shifted

class FractalCascade(Strategy):
    trail_mult = 3.0  # 🌙 Moon Dev: ATR multiplier for trailing stop, looser to let profits run longer
    adx_threshold = 30  # 🌙 Moon Dev: Increased from 25 to 30 for stronger trend filter, reduces whipsaws
    volume_mult = 1.5  # 🌙 Moon Dev: Increased volume threshold for higher conviction entries

    def init(self):
        self.current_sl = None
        # 🌙 Moon Dev: Removed initial_cash fixation; now use current equity for compounding risk
        median = (self.data.High + self.data.Low) / 2
        
        jaw_period = 13
        self.jaw = self.I(compute_shifted_ema, median, jaw_period, 8)
        
        teeth_period = 8
        self.teeth = self.I(compute_shifted_ema, median, teeth_period, 5)
        
        lips_period = 5
        self.lips = self.I(compute_shifted_ema, median, lips_period, 3)
        
        ao_fast = 5
        ao_slow = 34
        # 🌙 Moon Dev: Changed to SMA for accurate Awesome Oscillator calculation
        smma_fast = self.I(talib.SMA, median, timeperiod=ao_fast)
        smma_slow = self.I(talib.SMA, median, timeperiod=ao_slow)
        self.ao = smma_fast - smma_slow
        
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, timeperiod=14)
        self.adx = self.I(talib.ADX, self.data.High, self.data.Low, self.data.Close, timeperiod=14)
        self.volume_ma = self.I(talib.SMA, self.data.Volume, timeperiod=20)
        # 🌙 Moon Dev: Added SMA200 for longer-term trend filter to avoid counter-trend trades
        self.sma200 = self.I(talib.SMA, self.data.Close, timeperiod=200)
        
        self.up_fractal = self.I(compute_up_fractals, self.data.High)
        self.down_fractal = self.I(compute_down_fractals, self.data.Low)
        self.ffill_up = self.I(compute_ffill_fractal, self.up_fractal)
        self.ffill_down = self.I(compute_ffill_fractal, self.down_fractal)

    def next(self):
        # 🌙 Moon Dev: Check for NaN and stronger ADX threshold
        if np.isnan(self.adx[-1]) or self.adx[-1] < self.adx_threshold:
            return

        # 🌙 Moon Dev: Increased risk per trade to 2% for higher returns, compounded on current equity
        risk_per_trade = 0.02
        risk_amount = risk_per_trade * self._broker.get_equity()
        entry_price = self.data.Close[-1]
        atr_buffer = self.atr[-1]

        if not self.position:
            # Long entry with added trend filter
            if (self.data.Close[-1] > self.lips[-1] and
                self.lips[-1] > self.teeth[-1] > self.jaw[-1] and
                self.ao[-1] > 0 and self.ao[-1] > self.ao[-2] and
                self.data.Volume[-1] > self.volume_mult * self.volume_ma[-1] and
                self.data.Close[-1] > self.ffill_up[-1] and
                self.data.Close[-2] <= self.ffill_up[-2] and
                self.data.Close[-1] > self.sma200[-1]):  # 🌙 Moon Dev: Trend filter for longs only in uptrend
                
                sl = self.ffill_down[-1] - atr_buffer
                if sl < entry_price:
                    risk_dist = entry_price - sl
                    size = risk_amount / risk_dist
                    size = int(round(size))
                    if size > 0:
                        self.buy(size=size, sl=sl)
                        self.current_sl = sl
                        print(f"🌙 Moon Dev: Long entry at {entry_price:.2f}, Size: {size}, SL: {sl:.2f} 🚀")

            # Short entry with added trend filter
            elif (self.data.Close[-1] < self.lips[-1] and
                  self.lips[-1] < self.teeth[-1] < self.jaw[-1] and
                  self.ao[-1] < 0 and self.ao[-1] < self.ao[-2] and
                  self.data.Volume[-1] > self.volume_mult * self.volume_ma[-1] and
                  self.data.Close[-1] < self.ffill_down[-1] and
                  self.data.Close[-2] >= self.ffill_down[-2] and
                  self.data.Close[-1] < self.sma200[-1]):  # 🌙 Moon Dev: Trend filter for shorts only in downtrend
                
                sl = self.ffill_up[-1] + atr_buffer
                if sl > entry_price:
                    risk_dist = sl - entry_price
                    size = risk_amount / risk_dist
                    size = int(round(size))
                    if size > 0:
                        self.sell(size=size, sl=sl)
                        self.current_sl = sl
                        print(f"🌙 Moon Dev: Short entry at {entry_price:.2f}, Size: {size}, SL: {sl:.2f} 📉")

        if self.position:
            if self.position.is_long:
                # 🌙 Moon Dev: Removed Teeth exit to let profits run longer; only Jaw as hard exit
                if self.data.Close[-1] < self.jaw[-1]:
                    self.position.close()
                    self.current_sl = None
                    print(f"🌙 Moon Dev: Long hard exit - below Jaw 😤")
                    return
                
                # 🌙 Moon Dev: ATR-based trailing stop for smoother, more frequent adjustments in trends
                if not np.isnan(self.atr[-1]):
                    trail_sl = self.data.Close[-1] - self.trail_mult * self.atr[-1]
                    if not np.isnan(trail_sl) and trail_sl > self.current_sl:
                        trade_size = self.position.size
                        self.position.close()
                        self.buy(size=trade_size, sl=trail_sl)
                        self.current_sl = trail_sl
                        print(f"🌙 Moon Dev: Trailing SL long to {trail_sl:.2f} ✨")
            
            elif self.position.is_short:
                # 🌙 Moon Dev: Removed Teeth exit to let profits run longer; only Jaw as hard exit
                if self.data.Close[-1] > self.jaw[-1]:
                    self.position.close()
                    self.current_sl = None
                    print(f"🌙 Moon Dev: Short hard exit - above Jaw 😤")
                    return
                
                # 🌙 Moon Dev: ATR-based trailing stop for shorts
                if not np.isnan(self.atr[-1]):
                    trail_sl = self.data.Close[-1] + self.trail_mult * self.atr[-1]
                    if not np.isnan(trail_sl) and trail_sl < self.current_sl:
                        trade_size = abs(self.position.size)
                        self.position.close()
                        self.sell(size=trade_size, sl=trail_sl)
                        self.current_sl = trail_sl
                        print(f"🌙 Moon Dev: Trailing SL short to {trail_sl:.2f} ✨")

if __name__ == '__main__':
    data_path = '/Users/md/Dropbox/dev/github/moon-dev-ai-agents-for-trading/src/data/rbi/BTC-USD-15m.csv'
    data = pd.read_csv(data_path)
    data.columns = data.columns.str.strip().str.lower()
    data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
    data = data.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    })
    data['datetime'] = pd.to_datetime(data['datetime'])
    data = data.set_index(data['datetime'])
    bt = Backtest(data, FractalCascade, cash=1000000, commission=0.001)
    stats = bt.run()
    print(stats)