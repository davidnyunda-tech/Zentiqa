"""
Zentiqa — stateless behavioral analytics engine.

Pure computation over a flat list of deal dicts (no platform dependency,
no DB session needed). Runs all 10 behavioral rules and returns a
discipline score plus the detail behind every flag raised.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta


class ZentiqaEngine:
    def __init__(self, deals_payload: list, account_balance: float):
        self.deals = deals_payload
        self.balance = account_balance

        # Closed trades only (entry == 1 means OUT/close)
        self.trades = [d for d in self.deals if d.get("entry") == 1]
        self.trades.sort(key=lambda t: t["time"])

        self.deals_by_position = defaultdict(list)
        for d in self.deals:
            self.deals_by_position[d["position_id"]].append(d)

    def analyze_all_rules(self) -> dict:
        if not self.trades:
            return {"discipline_score": 100, "rules_triggered": [], "flags": {}, "metrics": {}}

        triggered = []
        flags = {}

        volumes = [t["volume"] for t in self.trades]
        avg_volume = sum(volumes) / len(volumes) if volumes else 0

        trades_by_day = defaultdict(list)
        for t in self.trades:
            day = datetime.fromtimestamp(t["time"]).strftime("%Y-%m-%d")
            trades_by_day[day].append(t)

        # Rule 1: Oversized positions (>= 2x average volume)
        size_flags = [t for t in self.trades if t["volume"] >= avg_volume * 2.0]
        flags["oversized_positions"] = size_flags
        if size_flags:
            triggered.append("Rule 1: Oversized Positions")

        # Rule 2: Revenge trading (new trade within 5 min of a loss)
        revenge_flags = []
        for i in range(1, len(self.trades)):
            prev, curr = self.trades[i - 1], self.trades[i]
            if prev["profit"] < 0:
                gap_min = (curr["time"] - prev["time"]) / 60
                if 0 <= gap_min <= 5:
                    revenge_flags.append({"current": curr, "previous": prev, "gap_minutes": gap_min})
        flags["revenge_trades"] = revenge_flags
        if revenge_flags:
            triggered.append("Rule 2: Revenge Trading")

        # Rule 3: Overtrading (day with >= 2x average trade count, min 3)
        counts = [len(v) for v in trades_by_day.values()]
        avg_daily_trades = sum(counts) / len(counts) if counts else 0
        overtrade_flags = [
            (day, len(dt)) for day, dt in trades_by_day.items()
            if len(dt) >= avg_daily_trades * 2.0 and len(dt) >= 3
        ]
        flags["overtrading_days"] = overtrade_flags
        if overtrade_flags:
            triggered.append("Rule 3: Overtrading")

        # Rule 4: Hope-holding (losers held >= 2x as long as winners)
        winner_times, loser_times = [], []
        for t in self.trades:
            entry_deal = next((d for d in self.deals_by_position[t["position_id"]] if d["entry"] == 0), None)
            if not entry_deal:
                continue
            hold_min = (t["time"] - entry_deal["time"]) / 60
            (winner_times if t["profit"] >= 0 else loser_times).append(hold_min)

        avg_win_hold = sum(winner_times) / len(winner_times) if winner_times else 0
        avg_loss_hold = sum(loser_times) / len(loser_times) if loser_times else 0
        hope_pattern = avg_win_hold > 0 and avg_loss_hold >= (avg_win_hold * 2.0)
        flags["hope_holding"] = {
            "detected": hope_pattern,
            "avg_win_min": avg_win_hold,
            "avg_loss_min": avg_loss_hold,
        }
        if hope_pattern:
            triggered.append("Rule 4: Hope-Holding")

        # Rule 5: Daily loss limit breach (3% of balance), trading on after
        loss_limit_amount = self.balance * 0.03
        loss_limit_flags = []
        for day, day_trades in trades_by_day.items():
            sorted_dt = sorted(day_trades, key=lambda x: x["time"])
            running_pnl, breached, post_breach_count = 0, False, 0
            for t in sorted_dt:
                running_pnl += t["profit"]
                if not breached and running_pnl <= -loss_limit_amount:
                    breached = True
                elif breached:
                    post_breach_count += 1
            if breached and post_breach_count > 0:
                loss_limit_flags.append({"day": day, "extra_trades": post_breach_count, "final_pnl": running_pnl})
        flags["loss_limit_breaches"] = loss_limit_flags
        if loss_limit_flags:
            triggered.append("Rule 5: Daily Loss Limit Breach")

        # Rule 6: Correlation overexposure (overlapping correlated pairs)
        corr_groups = [{"EURUSD", "GBPUSD"}, {"XAUUSD", "XAGUSD"}, {"USDJPY", "USDCHF"}, {"BTCUSD", "ETHUSD"}]
        windows = []
        for t in self.trades:
            entry_d = next((d for d in self.deals_by_position[t["position_id"]] if d["entry"] == 0), None)
            if entry_d:
                windows.append({"symbol": t["symbol"], "open": entry_d["time"], "close": t["time"], "ticket": t["ticket"]})

        correlation_flags = []
        for i, w1 in enumerate(windows):
            for j, w2 in enumerate(windows):
                if i >= j or w1["symbol"] == w2["symbol"]:
                    continue
                matched_group = next((g for g in corr_groups if w1["symbol"] in g and w2["symbol"] in g), None)
                if matched_group and w1["open"] < w2["close"] and w2["open"] < w1["close"]:
                    correlation_flags.append((w1, w2))
        flags["correlation_events"] = correlation_flags
        if correlation_flags:
            triggered.append("Rule 6: Correlation Risk")

        # Rule 7: Trading outside usual hours (hour used <= 5% of the time)
        hour_counts = defaultdict(int)
        for t in self.trades:
            hour_counts[datetime.fromtimestamp(t["time"]).hour] += 1
        unusual_hour_flags = []
        if len(self.trades) >= 5:
            for t in self.trades:
                h = datetime.fromtimestamp(t["time"]).hour
                pct = (hour_counts[h] / len(self.trades)) * 100
                if pct <= 5.0:
                    unusual_hour_flags.append(t)
        flags["unusual_hours"] = unusual_hour_flags
        if unusual_hour_flags:
            triggered.append("Rule 7: Trading Outside Usual Hours")

        # Rule 8: Inconsistent sizing (coefficient of variation >= 0.5)
        inconsistent_sizing, cv = False, 0.0
        if len(volumes) >= 5 and avg_volume > 0:
            variance = sum((v - avg_volume) ** 2 for v in volumes) / len(volumes)
            std_dev = math.sqrt(variance)
            cv = std_dev / avg_volume
            inconsistent_sizing = cv >= 0.5
        flags["inconsistent_sizing"] = {"detected": inconsistent_sizing, "coefficient_of_variation": cv}
        if inconsistent_sizing:
            triggered.append("Rule 8: Inconsistent Sizing")

        # Rule 9: Weekend exposure (position open spans a Sat/Sun)
        weekend_flags = []
        for w in windows:
            odt, cdt = datetime.fromtimestamp(w["open"]), datetime.fromtimestamp(w["close"])
            chk = odt.date()
            while chk <= cdt.date():
                if chk.weekday() in (5, 6):
                    weekend_flags.append(w)
                    break
                chk += timedelta(days=1)
        flags["weekend_exposure"] = weekend_flags
        if weekend_flags:
            triggered.append("Rule 9: Weekend Exposure")

        # Rule 10: Consecutive losses (3+ in a row = tilt risk)
        streak_flags, curr_streak = [], []
        for t in self.trades:
            if t["profit"] < 0:
                curr_streak.append(t)
            else:
                if len(curr_streak) >= 3:
                    streak_flags.append(curr_streak)
                curr_streak = []
        if len(curr_streak) >= 3:
            streak_flags.append(curr_streak)
        flags["losing_streaks"] = streak_flags
        if streak_flags:
            triggered.append("Rule 10: Consecutive Losses")

        deductions = len(triggered) * 10
        discipline_score = max(0, 100 - deductions)

        return {
            "discipline_score": discipline_score,
            "rules_triggered": triggered,
            "flags": flags,
            "metrics": {"avg_volume": avg_volume, "total_trades": len(self.trades)},
        }
