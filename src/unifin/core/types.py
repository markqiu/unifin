"""Common types and enums for unifin."""

from enum import Enum


class Exchange(str, Enum):
    """ISO 10383 Market Identifier Codes (MIC) for major exchanges."""

    # China
    XSHG = "XSHG"  # Shanghai Stock Exchange
    XSHE = "XSHE"  # Shenzhen Stock Exchange
    XBSE = "XBSE"  # Beijing Stock Exchange

    # United States
    XNYS = "XNYS"  # New York Stock Exchange
    XNAS = "XNAS"  # NASDAQ
    XASE = "XASE"  # NYSE American (AMEX)
    ARCX = "ARCX"  # NYSE Arca

    # Hong Kong
    XHKG = "XHKG"  # Hong Kong Exchanges

    # Japan
    XJPX = "XJPX"  # Japan Exchange Group (TSE)

    # United Kingdom
    XLON = "XLON"  # London Stock Exchange

    # Europe
    XPAR = "XPAR"  # Euronext Paris
    XAMS = "XAMS"  # Euronext Amsterdam
    XBRU = "XBRU"  # Euronext Brussels
    XLIS = "XLIS"  # Euronext Lisbon
    XETR = "XETR"  # XETRA (Deutsche Börse)
    XSWX = "XSWX"  # SIX Swiss Exchange
    XMIL = "XMIL"  # Borsa Italiana

    # Asia Pacific
    XSES = "XSES"  # Singapore Exchange
    XASX = "XASX"  # Australian Securities Exchange
    XKRX = "XKRX"  # Korea Exchange
    XTAI = "XTAI"  # Taiwan Stock Exchange
    XBOM = "XBOM"  # BSE India (Bombay)
    XNSE = "XNSE"  # National Stock Exchange India

    # Canada
    XTSE = "XTSE"  # Toronto Stock Exchange

    # Other
    XXXX = "XXXX"  # Unknown / not applicable


class Country(str, Enum):
    """ISO 3166-1 alpha-2 country codes for markets."""

    CN = "CN"  # China
    US = "US"  # United States
    HK = "HK"  # Hong Kong
    JP = "JP"  # Japan
    GB = "GB"  # United Kingdom
    DE = "DE"  # Germany
    FR = "FR"  # France
    NL = "NL"  # Netherlands
    CH = "CH"  # Switzerland
    IT = "IT"  # Italy
    SG = "SG"  # Singapore
    AU = "AU"  # Australia
    KR = "KR"  # South Korea
    TW = "TW"  # Taiwan
    IN = "IN"  # India
    CA = "CA"  # Canada
    BR = "BR"  # Brazil


# Exchange → Country mapping
EXCHANGE_COUNTRY: dict[Exchange, Country] = {
    Exchange.XSHG: Country.CN,
    Exchange.XSHE: Country.CN,
    Exchange.XBSE: Country.CN,
    Exchange.XNYS: Country.US,
    Exchange.XNAS: Country.US,
    Exchange.XASE: Country.US,
    Exchange.ARCX: Country.US,
    Exchange.XHKG: Country.HK,
    Exchange.XJPX: Country.JP,
    Exchange.XLON: Country.GB,
    Exchange.XPAR: Country.FR,
    Exchange.XAMS: Country.NL,
    Exchange.XETR: Country.DE,
    Exchange.XSWX: Country.CH,
    Exchange.XMIL: Country.IT,
    Exchange.XSES: Country.SG,
    Exchange.XASX: Country.AU,
    Exchange.XKRX: Country.KR,
    Exchange.XTAI: Country.TW,
    Exchange.XBOM: Country.IN,
    Exchange.XNSE: Country.IN,
    Exchange.XTSE: Country.CA,
}


class Interval(str, Enum):
    """Price bar interval / frequency."""

    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    THIRTY_MIN = "30m"
    ONE_HOUR = "1h"
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1M"


class Adjust(str, Enum):
    """Price adjustment type."""

    NONE = "none"       # 不复权
    FORWARD = "qfq"     # 前复权 (forward adjust)
    BACKWARD = "hfq"    # 后复权 (backward adjust)


class Period(str, Enum):
    """Financial statement reporting period."""

    ANNUAL = "annual"
    QUARTER = "quarter"


class Market(str, Enum):
    """Market identifier for calendars and market-level queries."""

    CN = "cn"    # China A-share
    US = "us"    # United States
    HK = "hk"    # Hong Kong
    JP = "jp"    # Japan
    GB = "gb"    # United Kingdom
    DE = "de"    # Germany
    SG = "sg"    # Singapore
    AU = "au"    # Australia
    KR = "kr"    # South Korea
    TW = "tw"    # Taiwan
    IN = "in"    # India
    CA = "ca"    # Canada
