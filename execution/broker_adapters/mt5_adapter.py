"""
محوّل MetaTrader 5
المسؤول عن: الاتصال، جلب البيانات، تنفيذ الأوامر
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from loguru import logger
from typing import Optional
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

        if not mt5.initialize():
            logger.error(f"فشل تهيئة MT5: {mt5.last_error()}")
            return False

        if login and password and server:
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

    def get_account_info(self) -> dict:
        """معلومات الحساب الكاملة"""
        info = mt5.account_info()
        if not info:
            return {}
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
    # بيانات السوق
    # ─────────────────────────────────────────

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
            logger.warning(f"لا توجد بيانات لـ {symbol} {timeframe}")
            return pd.DataFrame()

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
            "time":   datetime.fromtimestamp(tick.time),
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
            return mt5.ORDER_FILLING_IOC
        filling = info.filling_mode
        if filling & mt5.SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        elif filling & mt5.SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def place_order(
        self,
        symbol: str,
        order_type: str,       # "BUY" أو "SELL"
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "ForexAI",
    ) -> dict:
        """تنفيذ أمر تداول"""
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"لا يمكن جلب سعر {symbol}")
            return {"success": False}

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
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"فشل الأمر: {result.comment} (كود: {result.retcode})")
            return {"success": False, "error": result.comment}

        logger.success(
            f"Order executed | {order_type} {volume} {symbol} @ {price:.5f} | "
            f"Ticket: {result.order}"
        )
        return {"success": True, "ticket": result.order, "price": price}

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
                "profit":      p.profit,
                "swap":        p.swap,
                "open_time":   datetime.fromtimestamp(p.time),
                "comment":     p.comment,
            })
        return pd.DataFrame(data)
