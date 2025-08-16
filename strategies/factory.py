from typing import Dict, Any

from strategies.base import Strategy
from strategies.emacci import EMACCIStrategy
from strategies.trf import TRFStrategy
from strategies.rsicci import RSICCIStrategy

def get_strategy(strategy_name: str, config: Dict[str, Any]) -> Strategy:
    """
    Factory function to get a strategy instance by name.
    """
    strategies = {
        'main_strategy': EMACCIStrategy,
        'rsi_cci_strategy': RSICCIStrategy,
        'trf_strategy': TRFStrategy
    }
    strategy_class = strategies.get(strategy_name)

    if not strategy_class:
        raise ValueError(f"Unsupported strategy: {strategy_name}")

    return strategy_class(config)
