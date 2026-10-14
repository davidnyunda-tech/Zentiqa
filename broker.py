"""
Zentiqa — cloud broker gateway.

Abstracts away a direct `import MetaTrader5` call (which only works on a
Windows machine with the terminal installed — it cannot run on a server).
In production this class is where you'd plug in a real server-side bridge,
e.g. the MetaApi.cloud REST/WebSocket API or a custom MT5 Manager API
bridge. For now it returns realistic mock data so the rest of the stack
(engine + UI) can be built and tested independently of that integration.
"""

import asyncio
import random
import time


class CloudBrokerGateway:
    """Async gateway simulating server-side retrieval of MT5 account data."""

    def __init__(self, account_login: str, broker_server: str, access_token: str):
        self.account_login = account_login
        self.broker_server = broker_server
        self.access_token = access_token

    async def get_account_info(self) -> dict:
        """Simulates a server-side fetch of live account info."""
        await asyncio.sleep(0.3)  # simulate network latency
        return {
            "login": int(self.account_login),
            "balance": 10000.00,
            "equity": 10025.50,
            "currency": "USD",
            "company": "FTMO Evaluation Server",
            "leverage": 100,
        }

    async def fetch_deal_history(self, days_back: int = 90) -> list:
        """
        Simulates fetching raw deal records.
        entry 0 = IN (open), entry 1 = OUT (close), paired by position_id.
        """
        await asyncio.sleep(0.5)
        now_ts = int(time.time())
        day_sec = 86400

        mock_deals = []
        symbols = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"]

        for i in range(1, 15):
            pos_id = 1000 + i
            sym = random.choice(symbols)
            vol = random.choice([0.1, 0.1, 0.2, 0.5, 0.1])
            if i == 12:
                vol = 2.5  # inject Rule 1 (oversized position)

            open_time = now_ts - (i * 3 * day_sec)
            close_time = open_time + random.randint(300, 7200)  # 5 min - 2 hr

            mock_deals.append(
                {
                    "ticket": 20000 + (i * 2),
                    "position_id": pos_id,
                    "symbol": sym,
                    "volume": vol,
                    "profit": 0.0,
                    "entry": 0,
                    "time": open_time,
                }
            )

            is_loss = random.choice([True, False])
            profit_amt = random.uniform(-150, 300) if not is_loss else random.uniform(-250, -50)
            if i == 12:
                profit_amt = -450.00  # heavy loss on the oversized trade

            mock_deals.append(
                {
                    "ticket": 20000 + (i * 2) + 1,
                    "position_id": pos_id,
                    "symbol": sym,
                    "volume": vol,
                    "profit": profit_amt,
                    "entry": 1,
                    "time": close_time,
                }
            )

        return mock_deals
