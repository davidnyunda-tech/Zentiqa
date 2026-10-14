"""
Zentiqa — Cloud Portal (Streamlit UI)

Reads from the CloudBrokerGateway (currently mock data — swap in a real
MT5 bridge in broker.py when ready) and runs it through ZentiqaEngine.
"""

import asyncio

import streamlit as st

from broker import CloudBrokerGateway
from engine import ZentiqaEngine

st.set_page_config(page_title="Zentiqa Cloud Portal", page_icon="📊", layout="wide")

st.title("📊 Zentiqa — Risk Architecture Hub")
st.caption("Multi-tenant, read-only behavioral analytics for your MT5 account.")

# --- Sidebar: connect account ---
st.sidebar.header("🔑 Connect Account")
broker_server = st.sidebar.text_input("Broker Server", "FTMO-Server")
account_login = st.sidebar.text_input("MT5 Account Login", "5540219")
access_token = st.sidebar.text_input(
    "MT5 Investor Password",
    type="password",
    value="mock_secure_token",
    help=(
        "Use your INVESTOR (read-only) password, never your trade password. "
        "This value is used in memory for this scan only and is never "
        "written to disk in plaintext — see crypto.py / models.py for how "
        "it's encrypted when an account is saved for repeat scans."
    ),
)

run_scan = st.sidebar.button("Run Discipline Scan")

if run_scan:
    with st.spinner("Fetching account data and running behavioral analysis..."):
        gateway = CloudBrokerGateway(account_login, broker_server, access_token)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        account_info = loop.run_until_complete(gateway.get_account_info())
        raw_deals = loop.run_until_complete(gateway.fetch_deal_history())
        loop.close()

        engine = ZentiqaEngine(raw_deals, account_info["balance"])
        report = engine.analyze_all_rules()

    # --- Account header ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Account", account_info["login"])
    c2.metric("Balance", f"{account_info['balance']:.2f} {account_info['currency']}")
    c3.metric("Broker", account_info["company"])

    st.markdown("---")

    # --- Discipline score ---
    score = report["discipline_score"]
    if score >= 80:
        st.success(f"### 🛡️ Discipline Score: **{score}%** — Strong risk control.")
    elif score >= 50:
        st.warning(f"### ⚠️ Discipline Score: **{score}%** — Some risky patterns detected.")
    else:
        st.error(f"### 🚨 Discipline Score: **{score}%** — High tilt/overexposure risk.")

    # --- Flag summary grid ---
    st.subheader("💡 Flag Summary")
    flags = report["flags"]
    fc = st.columns(5)
    fc[0].metric("Oversized Positions", len(flags["oversized_positions"]))
    fc[1].metric("Revenge Trades", len(flags["revenge_trades"]))
    fc[2].metric("Overtrading Days", len(flags["overtrading_days"]))
    fc[3].metric("Loss Limit Breaches", len(flags["loss_limit_breaches"]))
    fc[4].metric("Losing Streaks (3+)", len(flags["losing_streaks"]))

    st.markdown("---")
    st.subheader("🔍 Rule Detail")

    if flags["oversized_positions"]:
        with st.expander("🔴 Rule 1 — Oversized Positions"):
            for t in flags["oversized_positions"]:
                st.warning(f"Ticket #{t['ticket']} — Volume: {t['volume']} lots — P/L: {t['profit']:.2f}")

    if flags["revenge_trades"]:
        with st.expander("🔴 Rule 2 — Revenge Trading"):
            for rf in flags["revenge_trades"]:
                st.warning(
                    f"Opened {rf['gap_minutes']:.1f} min after a loss on ticket #{rf['previous']['ticket']}"
                )

    if flags["overtrading_days"]:
        with st.expander("🔴 Rule 3 — Overtrading"):
            for day, count in flags["overtrading_days"]:
                st.warning(f"{day}: {count} trades (well above average)")

    if flags["hope_holding"]["detected"]:
        with st.expander("🔴 Rule 4 — Hope-Holding"):
            st.error(
                f"Average losing trade held **{flags['hope_holding']['avg_loss_min']:.1f} min**, "
                f"vs. winners cut at **{flags['hope_holding']['avg_win_min']:.1f} min**."
            )

    if flags["loss_limit_breaches"]:
        with st.expander("🔴 Rule 5 — Daily Loss Limit Breach"):
            for b in flags["loss_limit_breaches"]:
                st.error(f"{b['day']}: {b['extra_trades']} trades placed after hitting the 3% daily loss limit.")

    if flags["correlation_events"]:
        with st.expander("🔴 Rule 6 — Correlation Overexposure"):
            for w1, w2 in flags["correlation_events"]:
                st.warning(f"{w1['symbol']} (#{w1['ticket']}) overlapped with {w2['symbol']} (#{w2['ticket']})")

    if flags["unusual_hours"]:
        with st.expander("🟡 Rule 7 — Trading Outside Usual Hours"):
            for t in flags["unusual_hours"]:
                st.info(f"Ticket #{t['ticket']} traded at an unusual hour")

    if flags["inconsistent_sizing"]["detected"]:
        with st.expander("🟡 Rule 8 — Inconsistent Position Sizing"):
            st.info(f"Coefficient of variation: {flags['inconsistent_sizing']['coefficient_of_variation']:.2f}")

    if flags["weekend_exposure"]:
        with st.expander("🟡 Rule 9 — Weekend Exposure"):
            for w in flags["weekend_exposure"]:
                st.info(f"{w['symbol']} (#{w['ticket']}) held open over a weekend")

    if flags["losing_streaks"]:
        with st.expander("🔴 Rule 10 — Consecutive Losses"):
            for streak in flags["losing_streaks"]:
                tickets = ", ".join(str(t["ticket"]) for t in streak)
                st.error(f"{len(streak)} losses in a row — tickets: {tickets}")

    if not report["rules_triggered"]:
        st.success("No behavioral flags triggered on this scan. 🎉")

else:
    st.info("Enter account credentials in the sidebar and click **Run Discipline Scan** to begin.")
