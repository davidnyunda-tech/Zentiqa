"""
Zentiqa — multi-tenant database models.

Decouples trading history from any single MT5 terminal/memory state, so
the analytics engine can run against data pulled from any user's account
at any time, not just a live local connection.
"""

import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from crypto import decrypt_credential, encrypt_credential

Base = declarative_base()


class FirmOrUser(Base):
    __tablename__ = "users_firms"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), default="retail")  # 'retail', 'prop_admin', 'prop_trader'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    accounts = relationship("TradingAccount", back_populates="owner")


class TradingAccount(Base):
    __tablename__ = "trading_accounts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users_firms.id"), nullable=False)
    account_login = Column(String(50), nullable=False)
    # Always encrypted at rest. Only ever populate this with an MT5
    # INVESTOR (read-only) password — never the trade password. Use
    # set_credential()/get_credential() below rather than touching this
    # column directly, so plaintext never accidentally gets assigned to it.
    encrypted_credential = Column(String(255), nullable=False)
    broker_server = Column(String(100), nullable=False)
    broker_company = Column(String(100))
    base_currency = Column(String(10), default="USD")
    current_balance = Column(Float, default=0.0)
    current_equity = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    owner = relationship("FirmOrUser", back_populates="accounts")
    deals = relationship("HistoricalDeal", back_populates="account")

    def set_credential(self, plaintext_investor_password: str) -> None:
        """Encrypt and store the investor password. Never assign to
        encrypted_credential directly."""
        self.encrypted_credential = encrypt_credential(plaintext_investor_password)

    def get_credential(self) -> str:
        """Decrypt the stored investor password for use against the broker
        gateway. The returned value is plaintext in memory only — never
        log it, print it, or store it anywhere else."""
        return decrypt_credential(self.encrypted_credential)


class HistoricalDeal(Base):
    __tablename__ = "historical_deals"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("trading_accounts.id"), nullable=False)
    ticket = Column(Integer, unique=True, nullable=False)
    position_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(30), nullable=False)
    volume = Column(Float, nullable=False)
    profit = Column(Float, nullable=False)
    entry_type = Column(Integer, nullable=False)  # 0 = IN (open), 1 = OUT (close)
    execution_time = Column(DateTime, nullable=False)  # stored as UTC

    account = relationship("TradingAccount", back_populates="deals")


def get_engine(db_url: str = "sqlite:///zentiqa.db"):
    """Create the SQLAlchemy engine. Swap db_url for Postgres in production,
    e.g. postgresql://user:pass@host:5432/zentiqa
    """
    from sqlalchemy import create_engine

    return create_engine(db_url)


def init_db(engine):
    Base.metadata.create_all(engine)
