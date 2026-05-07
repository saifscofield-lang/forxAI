"""
محوّل MetaTrader 5
المسؤول عن: الاتصال، جلب البيانات، تنفيذ الأوامر
IMP-05: Retry logic on all MT5 operations
IMP-29: modify_position() for trailing stops
IMP-01: get_symbol_info() for accurate pip value
"""
import MetaTrader5 as mt5
import pandas as pd
import time as _time
from datetime import datetime
from loguru import logger
from typing import Optional
from functools import wraps
import os


# خريطة الأطر الزمنية
TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
    "W1":  mt5.TIMEFRAME_W1,
}


def _retry(max_attempts: int = 3, delay: float = 2.0, fallback=None):
    """Retry decorator for MT5 operations (IMP-05)."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"[RETRY] {func.__name__} attempt {attempt}/{max_attempts} "
                            f"failed: {e} — retrying in {delay}s"
                        )
                        _time.sleep(delay)
                    else:
                        logger.error(
                            f"[RETRY] {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
            return fallback() if callable(fallback) else fallback
        return wrapper
    return decorator


class MT5Adapter:
    """محوّل MetaTrader 5 الكامل"""

    def __init__(self):
        self.connected = False

    # ─────────────────────────────────────────
    # الاتصال
    # ─────────────────────────────────────────

    def connect(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ) -> bool:
        """
        الاتصال بـ MT5
        إذا لم تُمرَّر بيانات، يقرأها من .env تلقائياً
        """
        login    = login    or int(os.getenv("MT5_LOGIN", 0))
        password = password or os.getenv("MT5_PASSWORD", "")
        server   = server   or os.getenv("MT5_SERVER", "")

        # Use MT5_PATH if set to ensure correct terminal (not Deriv)
        mt5_path = os.getenv("MT5_PATH", "")
        if mt5_path:
            if not mt5.initialize(path=mt5_path):
                logger.error(f"فشل تهيئة MT5: {mt5.last_error()}")
                return False
        elif not mt5.initialize():
            logger.error(f"فشل تهيئة MT5: {mt5.last_error()}")
            return False

        # Only login if connected to wrong account
        info = mt5.account_info()
        if info and info.login == login:
            pass  # Already logged in to correct account
        elif login and password and server:
            authorized = mt5.login(login, password=password, server=server)
            if not authorized:
                logger.error(f"فشل تسجيل الدخول: {mt5.last_error()}")
                mt5.shutdown()
                return False

        self.connected = True
        info = mt5.account_info()
        logger.success(
            f"Connected to MT5 | Account: {info.login} | "
            f"Broker: {info.company} | Balance: {info.balance:.2f} {info.currency}"
        )
        return True

    def disconnect(self):
        """قطع الاتصال"""
        mt5.shutdown()
        self.connected = False
        logger.info("Disconnected from MT5")

    # ─────────────────────────────────────────
    # بيانات الحساب
    # ─────────────────────────────────────────

    @_retry(max_attempts=3, delay=1.0, fallback=dict)
    def get_account_info(self) -> dict:
        """معلومات الحساب الكاملة"""
        info = mt5.account_info()
        if not info:
            raise ConnectionError("MT5 account_info() returned None")
        return {
            "login":       info.login,
            "balance":     info.balance,
            "equity":      info.equity,
            "margin":      info.margin,
            "free_margin": info.margin_free,
            "profit":      info.profit,
            "currency":    info.currency,
            "leverage":    info.leverage,
            "server":      info.server,
            "company":     info.company,
        }

    # ─────────────────────────────────────────
    # معلومات الرموز (IMP-01)
    # ─────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> dict:
        """Get symbol trading specifications from MT5 for accurate position sizing."""
        info = mt5.symbol_info(symbol)
        if not info:
            return {}
        return {
            "symbol": symbol,
            "point": info.point,
            "digits": info.digits,
            "trade_tick_value": info.trade_tick_value,
            "trade_tick_size": info.trade_tick_size,
            "trade_contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "spread": info.spread,
        }

    # ─────────────────────────────────────────
    # بيانات السوق
    # ─────────────────────────────────────────

    @_retry(max_attempts=3, delay=2.0, fallback=pd.DataFrame)
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "H1",
        bars: int = 500,
    ) -> pd.DataFrame:
        """
        جلب بيانات الشموع OHLCV
        يُرجع DataFrame مرتب بالوقت
        """
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            logger.error(f"إطار زمني غير صالح: {timeframe}")
            return pd.DataFrame()

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None or len(rates) == 0:
            raise ConnectionError(f"No data for {symbol} {timeframe}")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"tick_volume": "volume"})[
            ["time", "open", "high", "low", "close", "volume", "spread"]
        ]
        df["symbol"]    = symbol
        df["timeframe"] = timeframe
        return df.sort_values("time").reset_index(drop=True)

    def get_tick(self, symbol: str) -> dict:
        """آخر سعر فوري"""
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {}
        return {
            "symbol": symbol,
            "time":   datetime.utcfromtimestamp(tick.time),
            "bid":    tick.bid,
            "ask":    tick.ask,
            "spread": round((tick.ask - tick.bid) * 100000, 1),
        }

    def get_symbols(self) -> list[str]:
        """قائمة جميع الأدوات المتاحة"""
        symbols = mt5.symbols_get()
        return [s.name for s in symbols] if symbols else []

    # ─────────────────────────────────────────
    # تنفيذ الأوامر
    # ─────────────────────────────────────────

    def _get_filling_mode(self, symbol: str):
        """Auto-detect supported filling mode for a symbol."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_FOK
        filling = info.filling_mode
        if filling & 1:   # FOK
            return mt5.ORDER_FILLING_FOK
        elif filling & 2:  # IOC
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    @_retry(max_attempts=3, delay=2.0)
    def place_order(
        self,
        symbol: str,
        order_type: str,       # "BUY" أو "SELL"
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "ForexAI",
    ) -> dict:
        """تنفيذ أمر تداول مع retry (IMP-05)"""
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            raise ConnectionError(f"Cannot get tick for {symbol}")

        price = tick.ask if order_type == "BUY" else tick.bid
        order = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      volume,
            "type":        order,
            "price":       price,
            "sl":          stop_loss,
            "tp":          take_profit,
            "deviation":   20,
            "magic":       20240101,
            "comment":     comment,
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(symbol),
        }

        result = mt5.order_send(request)

        # IMP-50: Filling mode fallback — try all modes if first fails
        if result.retcode != mt5.TRADE_RETCODE_DONE and "filling" in (result.comment or "").lower():
            filling_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
            original_filling = request["type_filling"]
            for mode in filling_modes:
                if mode == original_filling:
                    continue
                request["type_filling"] = mode
                # Re-fetch price in case it changed
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    request["price"] = tick.ask if order_type == "BUY" else tick.bid
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"IMP-50: Filling fallback succeeded with mode {mode} for {symbol}")
                    break

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"فشل الأمر: {result.comment} (كود: {result.retcode})")
            return {"success": False, "error": result.comment}

        # GAP-FID-01: distinguish requested-price (what we sent) from
        # filled-price (what MT5 actually filled at). The previous
        # contract returned only `price` set to the requested value,
        # which silently discarded slippage. Both are now returned.
        requested_price = price
        filled_price = float(result.price) if result.price else price

        logger.success(
            f"Order executed | {order_type} {volume} {symbol} @ {filled_price:.5f} "
            f"(requested {requested_price:.5f}, slippage {abs(filled_price - requested_price):.5f}) | "
            f"Ticket: {result.order}"
        )
        return {
            "success": True,
            "ticket": result.order,
            "price": filled_price,           # back-compat: callers reading 'price' get the
                                              # filled price, which is what they actually want
                                              # for storing as Trade.open_price
            "filled_price": filled_price,    # explicit GAP-FID-01 keys
            "requested_price": requested_price,
            "volume": volume,
        }

    def modify_position(
        self,
        ticket: int,
        stop_loss: float = None,
        take_profit: float = None,
    ) -> dict:
        """تعديل SL/TP لصفقة مفتوحة (IMP-29)"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.error(f"Position {ticket} not found for modification")
            return {"success": False, "error": "Position not found"}

        pos = position[0]
        new_sl = stop_loss if stop_loss is not None else pos.sl
        new_tp = take_profit if take_profit is not None else pos.tp

        request = {
            "action":    mt5.TRADE_ACTION_SLTP,
            "symbol":    pos.symbol,
            "position":  ticket,
            "sl":        new_sl,
            "tp":        new_tp,
            "magic":     20240101,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"Modify failed #{ticket}: {result.comment} (code: {result.retcode})"
            )
            return {"success": False, "error": result.comment}

        logger.info(
            f"Position #{ticket} modified | SL={new_sl:.5f} TP={new_tp:.5f}"
        )
        return {"success": True, "sl": new_sl, "tp": new_tp}

    def partial_close(self, ticket: int, volume: float) -> dict:
        """إغلاق جزئي لصفقة مفتوحة (IMP-07 Phase 3)"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.error(f"Position {ticket} not found for partial close")
            return {"success": False, "error": "Position not found"}

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.type == 0 else tick.ask

        # Round volume to step
        info = mt5.symbol_info(pos.symbol)
        if info:
            step = info.volume_step
            volume = round(round(volume / step) * step, 2)
            volume = max(volume, info.volume_min)

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      pos.symbol,
            "volume":      volume,
            "type":        close_type,
            "position":    ticket,
            "price":       price,
            "deviation":   20,
            "magic":       20240101,
            "comment":     "ForexAI Partial",
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(pos.symbol),
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Partial close failed #{ticket}: {result.comment}")
            return {"success": False, "error": result.comment}

        logger.info(f"Partial close #{ticket}: {volume} lots @ {price:.5f}")
        return {"success": True, "volume_closed": volume, "price": price}

    def close_position(self, ticket: int) -> dict:
        """إغلاق صفقة مفتوحة"""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.error(f"لا توجد صفقة برقم {ticket}")
            return {"success": False}

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if pos.type == 0 else tick.ask

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      pos.symbol,
            "volume":      pos.volume,
            "type":        close_type,
            "position":    ticket,
            "price":       price,
            "deviation":   20,
            "magic":       20240101,
            "comment":     "ForexAI Close",
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(pos.symbol),
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"فشل الإغلاق: {result.comment}")
            return {"success": False, "error": result.comment}

        logger.success(f"Position {ticket} closed")
        return {"success": True}

    def get_open_positions(self) -> pd.DataFrame:
        """الصفقات المفتوحة الحالية"""
        positions = mt5.positions_get()
        if not positions:
            return pd.DataFrame()

        data = []
        for p in positions:
            data.append({
                "ticket":      p.ticket,
                "symbol":      p.symbol,
                "type":        "BUY" if p.type == 0 else "SELL",
                "volume":      p.volume,
                "open_price":  p.price_open,
                "current_price": p.price_current,
                "sl":          p.sl,
                "tp":          p.tp,
                "profit":      p.profit,
                "swap":        p.swap,
                "open_time":   datetime.utcfromtimestamp(p.time),
                "comment":     p.comment,
            })
        return pd.DataFrame(data)
