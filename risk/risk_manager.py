"""
إدارة المخاطر — Risk Manager
Position sizing, exposure limits, drawdown protection
"""
import yaml
from loguru import logger


class RiskManager:
    """مدير المخاطر — يتحكم بحجم الصفقات والحدود"""

    def __init__(self, config_path: str = "config/base.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        risk_cfg = cfg.get("risk", {})
        self.max_risk_per_trade = risk_cfg.get("max_risk_per_trade", 0.01)
        self.max_daily_drawdown = risk_cfg.get("max_daily_drawdown", 0.05)
        self.max_open_positions = risk_cfg.get("max_open_positions", 5)
        self.max_correlated = risk_cfg.get("max_correlated_positions", 2)

        self.daily_pnl = 0.0
        self.starting_balance = 0.0

    def set_balance(self, balance: float):
        """Set starting balance for the day"""
        self.starting_balance = balance

    def update_pnl(self, pnl: float):
        """Update daily P&L tracker"""
        self.daily_pnl = pnl

    def calculate_position_size(
        self,
        balance: float,
        stop_loss_pips: float,
        pip_value: float,
    ) -> float:
        """
        Calculate lot size based on risk per trade.
        risk_amount = balance * max_risk_per_trade
        lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)
        """
        if stop_loss_pips <= 0:
            logger.warning("Stop loss must be positive")
            return 0.0

        risk_amount = balance * self.max_risk_per_trade
        # pip_value is per standard lot (100,000 units)
        # For most pairs: 1 pip = $10 per standard lot
        pip_value_per_lot = pip_value * 100_000
        lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)

        # Clamp to valid MT5 range
        lot_size = max(0.01, round(lot_size, 2))
        lot_size = min(lot_size, 10.0)

        logger.debug(
            f"Position size: {lot_size} lots | "
            f"Risk: ${risk_amount:.2f} | SL: {stop_loss_pips} pips"
        )
        return lot_size

    def can_open_trade(self, open_positions_count: int) -> bool:
        """Check if we can open a new position"""
        if open_positions_count >= self.max_open_positions:
            logger.warning(
                f"Max positions reached ({self.max_open_positions})"
            )
            return False

        # Check daily drawdown
        if self.starting_balance > 0:
            drawdown = -self.daily_pnl / self.starting_balance
            if drawdown >= self.max_daily_drawdown:
                logger.warning(
                    f"Daily drawdown limit hit: {drawdown:.2%} >= {self.max_daily_drawdown:.2%}"
                )
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
        if lot_size > 10.0:
            return False, "Lot size too large"
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
