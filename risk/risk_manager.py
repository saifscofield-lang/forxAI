"""
إدارة المخاطر — Risk Manager
Position sizing, exposure limits, drawdown protection
IMP-01: Accurate position sizing using MT5 tick_value
IMP-13: Minimum SL = 1.5x ATR
IMP-17: Daily loss limit (realized)
IMP-18: Portfolio-level risk cap
IMP-30: Correlated pairs enforcement
IMP-32: Detailed risk logging
"""
import yaml
from loguru import logger
from datetime import datetime, timezone


# Static correlation groups (IMP-30)
# Pairs that move together when USD strengthens/weakens
CORRELATION_GROUPS = {
    "USD_WEAK": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],   # These go UP when USD weakens
    "USD_STRONG": ["USDJPY", "USDCAD", "USDCHF"],            # These go UP when USD strengthens
}


class RiskManager:
    """مدير المخاطر — يتحكم بحجم الصفقات والحدود"""

    def __init__(self, config_path: str = "config/base.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        risk_cfg = cfg.get("risk", {})
        self.max_risk_per_trade = risk_cfg.get("max_risk_per_trade", 0.01)
        self.max_daily_drawdown = risk_cfg.get("max_daily_drawdown", 0.05)
        self.max_daily_loss = risk_cfg.get("max_daily_loss", 0.02)  # IMP-17: 2% hard daily limit
        self.max_open_positions = risk_cfg.get("max_open_positions", 5)
        self.max_correlated = risk_cfg.get("max_correlated_positions", 3)
        self.max_total_risk_pct = risk_cfg.get("max_total_risk", 0.03)  # IMP-18: 3% portfolio cap
        self.min_sl_atr_multiplier = risk_cfg.get("min_sl_atr_multiplier", 1.5)  # IMP-13

        self.daily_pnl = 0.0
        self.starting_balance = 0.0
        self.daily_realized_loss = 0.0  # IMP-17: track realized losses today
        self.daily_loss_reset_date = None

    def set_balance(self, balance: float):
        """Set starting balance for the day"""
        self.starting_balance = balance

    def update_pnl(self, pnl: float):
        """Update daily P&L tracker"""
        self.daily_pnl = pnl

    def record_realized_loss(self, pnl: float):
        """Record a realized trade loss for daily limit tracking (IMP-17)."""
        today = datetime.now(timezone.utc).date()
        if self.daily_loss_reset_date != today:
            self.daily_realized_loss = 0.0
            self.daily_loss_reset_date = today
        if pnl < 0:
            self.daily_realized_loss += abs(pnl)

    def is_daily_loss_limit_hit(self) -> bool:
        """Check if daily realized loss limit is hit (IMP-17)."""
        if self.starting_balance <= 0:
            return False
        limit = self.starting_balance * self.max_daily_loss
        if self.daily_realized_loss >= limit:
            logger.warning(
                f"[RISK] Daily loss limit hit: ${self.daily_realized_loss:.2f} "
                f">= ${limit:.2f} ({self.max_daily_loss:.0%} of balance)"
            )
            return True
        return False

    def calculate_position_size(
        self,
        balance: float,
        stop_loss_pips: float,
        pip_value: float,
        tick_value: float = None,
        tick_size: float = None,
        contract_size: float = None,
    ) -> float:
        """
        Calculate lot size based on risk per trade.
        IMP-01: Use MT5 tick_value for accurate sizing when available.
        IMP-32: Log full risk breakdown.
        """
        if stop_loss_pips <= 0:
            logger.warning("Stop loss must be positive")
            return 0.0

        risk_amount = balance * self.max_risk_per_trade

        # IMP-01: Use MT5 tick_value for accurate pip cost if available
        if tick_value and tick_size and tick_size > 0:
            # tick_value = dollar value of 1 tick movement for 1 lot
            # pip_cost_per_lot = tick_value * (pip_value / tick_size)
            pip_cost_per_lot = tick_value * (pip_value / tick_size)
        else:
            # Fallback: original formula (works for standard forex pairs)
            pip_cost_per_lot = pip_value * 100_000

        lot_size = risk_amount / (stop_loss_pips * pip_cost_per_lot)

        # Clamp to valid MT5 range
        lot_size = max(0.01, round(lot_size, 2))
        lot_size = min(lot_size, 1.0)  # Max 1.0 lot per trade (safety cap)

        # IMP-32: Detailed risk logging
        actual_risk = lot_size * stop_loss_pips * pip_cost_per_lot
        logger.info(
            f"[RISK] lot={lot_size} | risk=${actual_risk:.2f} "
            f"({actual_risk/balance*100:.2f}%) | SL={stop_loss_pips:.1f} pips | "
            f"pip_cost/lot=${pip_cost_per_lot:.4f} | "
            f"{'MT5_tick' if tick_value else 'formula'}"
        )
        return lot_size

    def enforce_min_sl(
        self,
        entry_price: float,
        stop_loss: float,
        atr: float,
        action: str,
        pip_value: float,
    ) -> float:
        """Enforce minimum SL distance = min_sl_atr_multiplier * ATR (IMP-13).
        Returns adjusted SL if original is too tight.
        """
        min_sl_distance = atr * self.min_sl_atr_multiplier
        current_sl_distance = abs(entry_price - stop_loss)

        if current_sl_distance < min_sl_distance:
            if action == "BUY":
                new_sl = entry_price - min_sl_distance
            else:
                new_sl = entry_price + min_sl_distance

            old_pips = current_sl_distance / pip_value
            new_pips = min_sl_distance / pip_value
            logger.info(
                f"[RISK] SL widened: {old_pips:.1f} -> {new_pips:.1f} pips "
                f"(min {self.min_sl_atr_multiplier}x ATR)"
            )
            return round(new_sl, 5)

        return stop_loss

    def check_correlated_exposure(
        self,
        symbol: str,
        action: str,
        open_positions: list[dict],
    ) -> tuple[bool, str]:
        """Check if opening this trade would exceed correlated exposure (IMP-30).

        Args:
            symbol: The symbol to trade
            action: "BUY" or "SELL"
            open_positions: List of dicts with 'symbol' and 'type' keys

        Returns:
            (allowed, reason)
        """
        if not open_positions:
            return True, "OK"

        # Determine which group this trade's USD direction falls into
        # BUY EURUSD = betting USD weakens, SELL EURUSD = betting USD strengthens
        # BUY USDJPY = betting USD strengthens, SELL USDJPY = betting USD weakens
        usd_direction = self._get_usd_direction(symbol, action)
        if not usd_direction:
            return True, "OK"

        # Count how many open positions bet in the same USD direction
        same_direction_count = 0
        for pos in open_positions:
            pos_usd_dir = self._get_usd_direction(pos["symbol"], pos["type"])
            if pos_usd_dir == usd_direction:
                same_direction_count += 1

        if same_direction_count >= self.max_correlated:
            reason = (
                f"Correlated limit: {same_direction_count} positions already "
                f"betting USD_{usd_direction} (max {self.max_correlated})"
            )
            logger.warning(f"[RISK] {reason}")
            return False, reason

        return True, "OK"

    def _get_usd_direction(self, symbol: str, action: str) -> str | None:
        """Determine if this trade bets on USD strengthening or weakening."""
        if symbol in CORRELATION_GROUPS["USD_WEAK"]:
            # EURUSD BUY = USD weakens, EURUSD SELL = USD strengthens
            return "WEAK" if action == "BUY" else "STRONG"
        elif symbol in CORRELATION_GROUPS["USD_STRONG"]:
            # USDJPY BUY = USD strengthens, USDJPY SELL = USD weakens
            return "STRONG" if action == "BUY" else "WEAK"
        elif symbol == "XAUUSD":
            # Gold: BUY = USD weakens (gold up), SELL = USD strengthens
            return "WEAK" if action == "BUY" else "STRONG"
        return None

    def check_portfolio_risk(
        self,
        new_risk_amount: float,
        open_positions_risk: float,
    ) -> tuple[bool, str]:
        """Check if total portfolio risk exceeds cap (IMP-18).

        Args:
            new_risk_amount: Dollar risk of the new trade
            open_positions_risk: Sum of dollar risk of all open positions

        Returns:
            (allowed, reason)
        """
        if self.starting_balance <= 0:
            return True, "OK"

        total_risk = open_positions_risk + new_risk_amount
        max_risk = self.starting_balance * self.max_total_risk_pct

        if total_risk > max_risk:
            reason = (
                f"Portfolio risk cap: ${total_risk:.2f} > ${max_risk:.2f} "
                f"({self.max_total_risk_pct:.0%} of ${self.starting_balance:,.0f})"
            )
            logger.warning(f"[RISK] {reason}")
            return False, reason

        return True, "OK"

    def can_open_trade(self, open_positions_count: int) -> bool:
        """Check if we can open a new position"""
        if open_positions_count >= self.max_open_positions:
            logger.warning(
                f"Max positions reached ({self.max_open_positions})"
            )
            return False

        # Check daily drawdown (unrealized)
        if self.starting_balance > 0:
            drawdown = -self.daily_pnl / self.starting_balance
            if drawdown >= self.max_daily_drawdown:
                logger.warning(
                    f"Daily drawdown limit hit: {drawdown:.2%} >= {self.max_daily_drawdown:.2%}"
                )
                return False

        # IMP-17: Check realized daily loss limit
        if self.is_daily_loss_limit_hit():
            return False

        return True

    def validate_trade(
        self,
        symbol: str,
        order_type: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        entry_price: float,
    ) -> tuple[bool, str]:
        """Validate a trade before execution"""
        if lot_size < 0.01:
            return False, "Lot size too small"
        if lot_size > 2.0:
            return False, "Lot size too large (max 2.0)"
        if stop_loss <= 0:
            return False, "Stop loss required"

        # Check risk/reward ratio (minimum 1:1)
        if take_profit > 0:
            if order_type == "BUY":
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
            else:
                risk = stop_loss - entry_price
                reward = entry_price - take_profit

            if risk <= 0:
                return False, "Invalid stop loss placement"
            if reward / risk < 0.3:
                return False, f"Risk/reward {reward/risk:.2f} below 0.3 minimum"

        return True, "OK"
