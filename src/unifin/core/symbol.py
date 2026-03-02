"""Symbol resolution: unified ISO 10383 MIC ↔ provider-specific formats.

Unified format: {code}.{MIC}
  - A-share: 000001.XSHE, 600519.XSHG, 430047.XBSE
  - US: AAPL (no suffix for US), or AAPL.XNAS when explicit
  - HK: 0700.XHKG
  - JP: 7203.XJPX

Provider formats:
  - yfinance:  000001.SZ, 600519.SS, AAPL, 0700.HK, 7203.T
  - eastmoney: 000001.SZ, 600519.SH, AAPL.US, 0700.HK
  - joinquant: 000001.XSHE, 600519.XSHG (already MIC)
  - tushare:   000001.SZ, 600519.SH
  - fmp:       000001.SZ, 600519.SS, AAPL
  - akshare:   000001 (plain code, exchange inferred)
"""

from __future__ import annotations

import re

from unifin.core.types import Exchange

# ──────────────────────────────────────────────
# MIC ↔ Provider suffix mappings
# ──────────────────────────────────────────────

_PROVIDER_SUFFIX: dict[str, dict[Exchange, str]] = {
    "yfinance": {
        Exchange.XSHG: ".SS",
        Exchange.XSHE: ".SZ",
        Exchange.XHKG: ".HK",
        Exchange.XJPX: ".T",
        Exchange.XLON: ".L",
        Exchange.XPAR: ".PA",
        Exchange.XAMS: ".AS",
        Exchange.XETR: ".DE",
        Exchange.XSWX: ".SW",
        Exchange.XMIL: ".MI",
        Exchange.XSES: ".SI",
        Exchange.XASX: ".AX",
        Exchange.XKRX: ".KS",
        Exchange.XTAI: ".TW",
        Exchange.XBOM: ".BO",
        Exchange.XNSE: ".NS",
        Exchange.XTSE: ".TO",
        # US exchanges: no suffix
        Exchange.XNYS: "",
        Exchange.XNAS: "",
        Exchange.XASE: "",
        Exchange.ARCX: "",
    },
    "eastmoney": {
        Exchange.XSHG: ".SH",
        Exchange.XSHE: ".SZ",
        Exchange.XHKG: ".HK",
        Exchange.XNYS: ".US",
        Exchange.XNAS: ".US",
    },
    "tushare": {
        Exchange.XSHG: ".SH",
        Exchange.XSHE: ".SZ",
    },
    "joinquant": {
        Exchange.XSHG: ".XSHG",
        Exchange.XSHE: ".XSHE",
        Exchange.XBSE: ".XBSE",
    },
    "fmp": {
        Exchange.XSHG: ".SS",
        Exchange.XSHE: ".SZ",
        Exchange.XHKG: ".HK",
        Exchange.XJPX: ".T",
        Exchange.XLON: ".L",
        # US: no suffix
        Exchange.XNYS: "",
        Exchange.XNAS: "",
    },
    "akshare": {
        # akshare typically uses plain codes
        Exchange.XSHG: "",
        Exchange.XSHE: "",
    },
}

# Reverse map: provider suffix → MIC
_SUFFIX_TO_MIC: dict[str, dict[str, Exchange]] = {}
for provider, mapping in _PROVIDER_SUFFIX.items():
    _SUFFIX_TO_MIC[provider] = {}
    for mic, suffix in mapping.items():
        if suffix:  # skip empty suffixes
            _SUFFIX_TO_MIC[provider][suffix] = mic


# ──────────────────────────────────────────────
# A-share code prefix → exchange detection
# ──────────────────────────────────────────────

_CN_CODE_PATTERNS: list[tuple[re.Pattern, Exchange]] = [
    # Shanghai: 6xxxxx (main), 500xxx/510xxx/512xxx/513xxx/515xxx/518xxx (ETF)
    (re.compile(r"^6\d{5}$"), Exchange.XSHG),
    (re.compile(r"^5[01]\d{4}$"), Exchange.XSHG),
    # Shenzhen: 0xxxxx, 3xxxxx (ChiNext/创业板), 1xxxxx (funds)
    (re.compile(r"^[03]\d{5}$"), Exchange.XSHE),
    (re.compile(r"^1[56]\d{4}$"), Exchange.XSHE),
    # Beijing: 4xxxxx, 8xxxxx
    (re.compile(r"^[48]\d{5}$"), Exchange.XBSE),
    # Shanghai indices: 000xxx
    (re.compile(r"^000\d{3}$"), Exchange.XSHG),
]


def detect_exchange(symbol: str) -> Exchange | None:
    """Detect exchange from a raw symbol string.

    Handles:
    - Already has MIC suffix: 000001.XSHE → XSHE
    - Has provider suffix: 000001.SZ → XSHE, 600519.SS → XSHG
    - Plain A-share code: 000001 → XSHE, 600519 → XSHG
    - US-style ticker (all letters): AAPL → None (ambiguous US)
    """
    symbol = symbol.strip()

    if "." in symbol:
        code, suffix = symbol.rsplit(".", 1)
        suffix_upper = suffix.upper()

        # Check if it's already a MIC
        try:
            return Exchange(suffix_upper)
        except ValueError:
            pass

        # Check known provider suffixes
        for provider, smap in _SUFFIX_TO_MIC.items():
            key = f".{suffix_upper}"
            if key in smap:
                return smap[key]

    # Plain code: try A-share pattern detection
    code = symbol.split(".")[0] if "." in symbol else symbol
    for pattern, exchange in _CN_CODE_PATTERNS:
        if pattern.match(code):
            return exchange

    return None


def parse_symbol(symbol: str) -> tuple[str, Exchange | None]:
    """Parse a symbol into (code, exchange).

    Returns:
        (code, exchange) — exchange may be None for ambiguous US tickers.

    Examples:
        "000001.XSHE"  → ("000001", Exchange.XSHE)
        "AAPL"         → ("AAPL", None)
        "AAPL.XNAS"    → ("AAPL", Exchange.XNAS)
        "600519.SS"     → ("600519", Exchange.XSHG)
        "000001"        → ("000001", Exchange.XSHE)
    """
    symbol = symbol.strip()
    exchange = detect_exchange(symbol)

    # Extract the code part (strip any suffix)
    code = symbol.split(".")[0] if "." in symbol else symbol

    return code, exchange


def to_provider_symbol(symbol: str, provider: str) -> str:
    """Convert a unified symbol to provider-specific format.

    Examples:
        to_provider_symbol("000001.XSHE", "yfinance")  → "000001.SZ"
        to_provider_symbol("AAPL", "yfinance")          → "AAPL"
        to_provider_symbol("0700.XHKG", "yfinance")    → "0700.HK"
        to_provider_symbol("000001.XSHE", "eastmoney") → "000001.SZ"
    """
    code, exchange = parse_symbol(symbol)

    if exchange is None:
        # Ambiguous (likely US ticker), return as-is
        return code

    suffix_map = _PROVIDER_SUFFIX.get(provider, {})
    suffix = suffix_map.get(exchange, "")

    return f"{code}{suffix}"


def to_unified_symbol(symbol: str, provider: str | None = None) -> str:
    """Convert a provider-specific symbol back to unified format.

    Examples:
        to_unified_symbol("000001.SZ", "yfinance")    → "000001.XSHE"
        to_unified_symbol("600519.SS")                 → "600519.XSHG"
        to_unified_symbol("AAPL")                      → "AAPL"
        to_unified_symbol("000001.XSHE")               → "000001.XSHE"
    """
    code, exchange = parse_symbol(symbol)

    if exchange is None:
        return code  # US ticker, no suffix needed

    return f"{code}.{exchange.value}"


# ──────────────────────────────────────────────
# Symbol format validation (for Query models)
# ──────────────────────────────────────────────

# Valid symbol patterns:
#   - US ticker: 1-5 uppercase letters, optionally with dots (BRK.B)
#   - Code.MIC:  digits or letters + "." + MIC code  (000001.XSHE)
#   - Code.suffix: digits + "." + provider suffix (000001.SZ, 600519.SS)
#   - Plain A-share: 6 digits (000001, 600519)
#   - Index with caret: ^GSPC, ^HSI
_VALID_SYMBOL_RE = re.compile(
    r"^("
    r"\^[A-Z0-9]{2,10}"  # ^GSPC, ^HSI, ^N225
    r"|[A-Z]{1,5}(\.[A-Z]{1,2})?"  # AAPL, BRK.B
    r"|[A-Z]{1,5}\.[A-Z]{3,4}"  # AAPL.XNAS (ticker + MIC)
    r"|\d{4,6}\.[A-Z]{2,4}"  # 000001.XSHE, 0700.XHKG, 600519.SS
    r"|\d{4,6}"  # 000001, 600519 (plain code)
    r")$"
)


def validate_symbol(symbol: str) -> str:
    """Validate and normalize a symbol string.

    Raises SymbolError (subclass of ValueError) if the symbol format is
    clearly invalid.  The error message is designed to help AI callers
    self-correct by listing valid formats and examples.

    Accepts:
      - US tickers: AAPL, MSFT, BRK.B
      - MIC format: 000001.XSHE, 0700.XHKG
      - Provider format: 000001.SZ, 600519.SS
      - Plain A-share codes: 000001, 600519
      - Index symbols: ^GSPC, ^HSI
    """
    from unifin.core.errors import SymbolError

    symbol = symbol.strip()
    if not symbol:
        raise SymbolError(
            "Symbol must not be empty.",
            received="''",
            hint="Provide a non-empty stock symbol, e.g. 'AAPL' or '000001.XSHE'.",
        )
    if not _VALID_SYMBOL_RE.match(symbol):
        raise SymbolError(
            f"Invalid symbol format: '{symbol}'.",
            received=symbol,
            hint=(
                "A valid symbol is a US ticker (1-5 letters, e.g. 'AAPL', 'BRK.B'), "
                "a code with MIC suffix (e.g. '000001.XSHE', '0700.XHKG'), "
                "a plain 4-6 digit A-share code (e.g. '000001'), "
                "or an index with caret (e.g. '^GSPC'). "
                "Check for typos, extra spaces, or invalid characters."
            ),
        )
    return symbol
