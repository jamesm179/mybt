import pandas as pd
from typing import Dict, Any

class Strategy:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__

    def get_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Subclasses must implement get_indicators")

    async def check_signals(self, latest_row: pd.Series, active_trades: Dict) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement check_signals")
