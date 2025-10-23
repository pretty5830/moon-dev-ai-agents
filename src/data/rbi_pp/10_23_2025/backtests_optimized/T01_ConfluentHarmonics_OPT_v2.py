import pandas as pd
import talib
from backtesting import Backtest, Strategy

path = '/Users/md/Dropbox/dev/github/moon-dev-ai-agents-for-trading/src/data/rbi/BTC-USD-15m.csv'
data = pd.read_csv(path)
data.columns = data.columns.str.strip().str.lower()
data = data.drop(columns=[col for col in data.columns if 'unnamed' in col.lower()])
data = data.rename(columns={'datetime': 'Datetime', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
data = data.set_index(pd.to_datetime(data['Datetime']))

class ConfluentHarmonics(Strategy):
    bb_period = 20
    bb_std = 2
    adx_period = 14
    adx_threshold = 20  # 🌙 Optimized: Lowered from 25 to 20 for more entry opportunities in moderate trends while maintaining quality
    bb_squeeze_threshold = 0.03  # 🌙 Optimized: Tightened from 0.04 to 0.03 for higher-quality squeeze setups, reducing false signals
    atr_period = 14
    atr_sl_mult = 1.5  # 🌙 Optimized: Reduced from 2 to 1.5 for tighter stops, allowing larger position sizes for the same risk level
    rr_ratio = 3  # 🌙 Optimized: Increased from 2 to 3 for better reward potential, aiming to capture larger moves post-squeeze
    risk_per_trade = 0.015  # 🌙 Optimized: Increased from 0.01 to 0.015 for higher exposure per trade to accelerate returns, still conservative
    rsi_period = 14
    rsi_oversold = 30
    rsi_overbought = 70
    sma_trend_period = 200  # 🌙 New: Added long-term SMA for trend filter to only trade in direction of major trend
    vol_sma_period = 20  # 🌙 New: Added volume SMA filter to confirm momentum on entries
    early_adx_exit = 15  # 🌙 Optimized: Lowered early exit threshold from 20 to 15 for quicker exits on trend weakening

    def init(self):
        self.closes = self.I(lambda c: c, self.data.Close)
        self.atr = self.I(talib.ATR, self.data.High, self.data.Low, self.data.Close, timeperiod=self.atr_period)
        bb_upper, bb_middle, bb_lower = self.I(talib.BBANDS, self.data.Close, timeperiod=self.bb_period, nbdevup=self.bb_std, nbdevdn=self.bb_std, matype=0)
        self.bb_upper = bb_upper
        self.bb_middle = bb_middle
        self.bb_lower = bb_lower
        self.adx = self.I(talib.ADX, self.data.High, self.data.Low, self.data.Close, timeperiod=self.adx_period)
        self.pdi = self.I(talib.PLUS_DI, self.data.High, self.data.Low, self.data.Close, timeperiod=self.adx_period)
        self.mdi = self.I(talib.MINUS_DI, self.data.High, self.data.Low, self.data.Close, timeperiod=self.adx_period)
        # 🌙 New: RSI for oversold/overbought confirmation on BB touches to filter low-quality reversals
        self.rsi = self.I(talib.RSI, self.data.Close, timeperiod=self.rsi_period)
        # 🌙 New: SMA200 for trend regime filter - longs only above, shorts only below to avoid counter-trend trades
        self.sma_trend = self.I(talib.SMA, self.data.Close, timeperiod=self.sma_trend_period)
        # 🌙 New: Volume SMA for momentum filter - only enter on above-average volume to confirm conviction
        self.vol_sma = self.I(talib.SMA, self.data.Volume, timeperiod=self.vol_sma_period)
        print("🌙 Moon Dev's ConfluentHarmonics Strategy Initialized ✨")

    def next(self):
        price = self.closes[-1]
        prev_price = self.closes[-2]
        upper = self.bb_upper[-1]
        middle = self.bb_middle[-1]
        lower = self.bb_lower[-1]
        prev_lower = self.bb_lower[-2]
        prev_upper = self.bb_upper[-2]
        adx_val = self.adx[-1]
        pdi_val = self.pdi[-1]
        mdi_val = self.mdi[-1]
        atr_val = self.atr[-1]
        bb_width = (upper - lower) / middle
        prev_bb_width = (prev_upper - prev_lower) / self.bb_middle[-2]
        squeeze = bb_width < self.bb_squeeze_threshold or prev_bb_width < self.bb_squeeze_threshold

        # Early exits for weakening trend
        if self.position:
            if self.position.is_long and adx_val < self.early_adx_exit:
                self.position.close()
                print(f"🌙 Early Long Exit: ADX Weakening at {self.data.index[-1]} 🚀 Price: {price}")
            elif self.position.is_short and adx_val < self.early_adx_exit:
                self.position.close()
                print(f"🌙 Early Short Exit: ADX Weakening at {self.data.index[-1]} ✨ Price: {price}")

        # Entry logic only if no position
        if not self.position:
            # Bullish Reversal Proxy: Previous close at/touching lower BB, current close above middle, ADX strong, +DI > -DI, squeeze
            # 🌙 Optimized: Added RSI oversold filter, trend filter (above SMA200), and volume confirmation for better entry quality
            if (prev_price <= prev_lower and
                price > middle and
                adx_val > self.adx_threshold and
                pdi_val > mdi_val and
                squeeze and
                self.rsi[-2] < self.rsi_oversold and  # 🌙 New: Confirm oversold at BB touch
                price > self.sma_trend[-1] and  # 🌙 New: Trend filter - only long in uptrend
                self.data.Volume[-1] > self.vol_sma[-1]):  # 🌙 New: Volume surge for momentum
                entry = price
                risk_dist = self.atr_sl_mult * atr_val
                sl = entry - risk_dist
                size_frac = self.risk_per_trade / (risk_dist / entry)
                size_frac = min(size_frac, 1.0)
                tp = entry + (self.rr_ratio * risk_dist)
                self.buy(size=size_frac, sl=sl, tp=tp)
                print(f"🌙 Bullish ConfluentHarmonics Entry at {self.data.index[-1]} 🚀 Size Frac: {size_frac}, Entry: {entry}, SL: {sl}, TP: {tp}")

            # Bearish Reversal Proxy: Previous close at/touching upper BB, current close below middle, ADX strong, -DI > +DI, squeeze
            # 🌙 Optimized: Added RSI overbought filter, trend filter (below SMA200), and volume confirmation for better entry quality
            elif (prev_price >= prev_upper and
                  price < middle and
                  adx_val > self.adx_threshold and
                  mdi_val > pdi_val and
                  squeeze and
                  self.rsi[-2] > self.rsi_overbought and  # 🌙 New: Confirm overbought at BB touch
                  price < self.sma_trend[-1] and  # 🌙 New: Trend filter - only short in downtrend
                  self.data.Volume[-1] > self.vol_sma[-1]):  # 🌙 New: Volume surge for momentum
                entry = price
                risk_dist = self.atr_sl_mult * atr_val
                sl = entry + risk_dist
                size_frac = self.risk_per_trade / (risk_dist / entry)
                size_frac = min(size_frac, 1.0)
                tp = entry - (self.rr_ratio * risk_dist)
                self.sell(size=size_frac, sl=sl, tp=tp)
                print(f"🌙 Bearish ConfluentHarmonics Entry at {self.data.index[-1]} ✨ Size Frac: {size_frac}, Entry: {entry}, SL: {sl}, TP: {tp}")

bt = Backtest(data, ConfluentHarmonics, cash=1000000, commission=0.001, exclusive_orders=True)
stats = bt.run()
print(stats)