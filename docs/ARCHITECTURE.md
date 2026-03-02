# unifin 架构设计文档

> **版本**: 0.1.0 | **最后更新**: 2026-02-28

## 1. 项目定位

**unifin** (Unified Intelligent Financial Data Platform) 是一个统一的全球金融数据平台，通过单一 SDK 入口聚合多个数据源（yfinance、eastmoney、tushare、joinquant、fmp 等），对外暴露标准化的 API，让用户（人类或 AI Agent）无需关注底层数据源的差异。

### 核心设计原则

| 原则 | 实践 |
|------|------|
| **统一 Symbol** | ISO 10383 MIC 编码（`000001.XSHE`、`AAPL`），自动转换各 Provider 格式 |
| **严格类型** | 所有参数均为 Pydantic v2 模型 + Enum，拒绝裸字符串 |
| **数据源透明** | SmartRouter 按优先级自动选择最佳 Provider，用户也可显式指定 |
| **统一返回** | 所有 SDK 函数返回 `polars.DataFrame`，结果经 Pydantic 验证 |
| **AI 友好错误** | 结构化错误层级，每个异常包含 `code / received / expected / hint` |
| **可选依赖** | 每个 Provider 为可选包，缺失时不影响其他 Provider |

---

## 2. 分层架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      SDK 层                              │
│  unifin.equity.historical()  unifin.index.historical()  │
│  unifin.equity.search()      unifin.etf.search()        │
│  unifin.equity.profile()     unifin.market.trade_calendar()│
│  unifin.equity.quote()       ...                        │
│  unifin.equity.balance_sheet()                          │
│  unifin.equity.income_statement()                       │
│  unifin.equity.cash_flow()                              │
├─────────────────────────────────────────────────────────┤
│                    Router 层                             │
│  SmartRouter — 自动选择 Provider → TET Pipeline → 验证  │
├──────────────┬──────────────────────────────────────────┤
│  Model 层    │            Registry 层                    │
│  Query/Data  │  ModelRegistry + ProviderRegistry         │
│  (Pydantic)  │  (model, provider, fetcher) 三级注册      │
├──────────────┴──────────────────────────────────────────┤
│                    Core 层                               │
│  Types   Symbol   Fetcher   Errors   Store              │
├─────────────────────────────────────────────────────────┤
│                  Provider 层                             │
│  yfinance (8 fetchers)  │  eastmoney (1 fetcher)        │
│  fmp (planned)          │  tushare (planned)            │
│  joinquant (planned)    │  akshare (planned)            │
└─────────────────────────────────────────────────────────┘
```

### 数据流（一次查询的生命周期）

```
用户调用 unifin.equity.historical("000001.XSHE")
  │
  ▼
SDK 层: 参数类型转换 + 构造 EquityHistoricalQuery (Pydantic)
  │
  ▼
Router 层: SmartRouter.query("equity_historical", query)
  │
  ├─ 1. ModelRegistry.get("equity_historical") → ModelInfo
  ├─ 2. parse_symbol("000001.XSHE") → (code="000001", exchange=XSHE)
  ├─ 3. _resolve_providers() → ["eastmoney", "yfinance"] (按优先级排序)
  │
  ▼
  ├─ 4. 对每个 Provider 执行 TET Pipeline:
  │     ┌──────────────────────────────────────────┐
  │     │  T: transform_query(query)               │ → Provider 专用参数
  │     │  E: extract_data(params, credentials)     │ → 调用 API/SDK
  │     │  T: transform_data(raw_data, query)       │ → 统一 dict 列表
  │     └──────────────────────────────────────────┘
  │
  ├─ 5. 输出验证: result_type.model_validate(row)
  ├─ 6. Symbol 注入: 确保每行结果包含统一 Symbol
  │
  ▼
SDK 层: pl.DataFrame(results) → 缓存到 DuckDB → 返回 DataFrame
```

---

## 3. 各层详细设计

### 3.1 Core 层 — 基础设施

#### 3.1.1 Types (`core/types.py`, 144 行)

平台所有枚举类型的唯一来源：

| 枚举 | 用途 | 成员示例 |
|------|------|---------|
| `Exchange` | ISO 10383 交易所 MIC | `XSHG`, `XSHE`, `XNYS`, `XNAS`, `XHKG` 等 28 个 |
| `Country` | ISO 3166-1 国家代码 | `CN`, `US`, `HK`, `JP` 等 17 个 |
| `Interval` | K 线周期 | `1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1w`, `1M` |
| `Adjust` | 复权类型 | `none`（不复权）, `qfq`（前复权）, `hfq`（后复权） |
| `Period` | 报告周期 | `annual`, `quarter` |
| `Market` | 市场标识 | `cn`, `us`, `hk`, `jp` 等 12 个 |

还提供 `EXCHANGE_COUNTRY` 映射表（Exchange → Country）。

#### 3.1.2 Symbol (`core/symbol.py`, 265 行)

统一 Symbol 编码系统，实现 ISO 10383 MIC ↔ 各 Provider 专有格式的双向转换。

**统一格式规则**:
- A 股: `{6位代码}.{MIC}` → `000001.XSHE`、`600519.XSHG`
- 美股: 纯字母 Ticker → `AAPL`（US 不加后缀）
- 港股: `{4位代码}.XHKG` → `0700.XHKG`
- 指数: `^{代码}` → `^GSPC`、`^HSI`

**核心函数**:

| 函数 | 作用 | 示例 |
|------|------|------|
| `detect_exchange(symbol)` | 从任意格式检测交易所 | `"000001.SZ"` → `XSHE` |
| `parse_symbol(symbol)` | 分离 code + exchange | `"000001.XSHE"` → `("000001", XSHE)` |
| `to_provider_symbol(symbol, provider)` | 统一→Provider | `"000001.XSHE", "yfinance"` → `"000001.SZ"` |
| `to_unified_symbol(symbol, provider)` | Provider→统一 | `"000001.SZ", "yfinance"` → `"000001.XSHE"` |
| `validate_symbol(symbol)` | 格式校验 | `"???"` → 抛出 `SymbolError` |

**Provider 后缀映射表**（6 个 Provider）:

| MIC | yfinance | eastmoney | tushare | joinquant | fmp | akshare |
|-----|----------|-----------|---------|-----------|-----|---------|
| XSHG | `.SS` | `.SH` | `.SH` | `.XSHG` | `.SS` | _(无)_ |
| XSHE | `.SZ` | `.SZ` | `.SZ` | `.XSHE` | `.SZ` | _(无)_ |
| XHKG | `.HK` | `.HK` | — | — | `.HK` | — |
| XNYS | _(无)_ | `.US` | — | — | _(无)_ | — |

**A 股代码自动识别** — 通过前缀模式检测：
- `6xxxxx` → XSHG（上交所主板）
- `0xxxxx` / `3xxxxx` → XSHE（深交所）
- `4xxxxx` / `8xxxxx` → XBSE（北交所）

#### 3.1.3 Fetcher (`core/fetcher.py`, 62 行)

Provider 必须实现的抽象基类，定义 TET 三步管道：

```python
class Fetcher(ABC):
    # ── 声明式元数据（由子类设置）──
    provider_name: ClassVar[str]           # e.g. "yfinance"
    model_name: ClassVar[str]              # e.g. "equity_historical"
    supported_exchanges: ClassVar[list[Exchange]]  # 支持的交易所列表
    requires_credentials: ClassVar[list[str]]      # 需要的凭证环境变量

    # ── 覆盖元数据（推荐填写）──
    supported_fields: ClassVar[list[str]]  # 实际填充的字段名
    data_start_date: ClassVar[str]         # 数据起始日期 "1970-01-01"
    data_delay: ClassVar[str]              # 数据延迟 "15min" / "eod"
    notes: ClassVar[str]                   # 备注（限制、特性）

    # ── TET Pipeline ──
    @abstractmethod
    def transform_query(query) -> dict:    # T: 统一查询 → Provider 参数
    @abstractmethod
    def extract_data(params, creds) -> Any: # E: 调用 API
    @abstractmethod
    def transform_data(raw, query) -> list: # T: 原始数据 → 统一 dict 列表
```

每个 Fetcher 绑定一个 `(provider, model)` 对，这是新增数据源的唯一扩展点。

#### 3.1.4 Registry (`core/registry.py`, 184 行)

平台的"中枢神经系统"，管理两个全局注册表：

**ModelRegistry** — 管理数据模型
```python
@dataclass
class ModelInfo:
    name: str                    # "equity_historical"
    category: str                # "equity.price"
    query_type: type[BaseModel]  # EquityHistoricalQuery
    result_type: type[BaseModel] # EquityHistoricalData
    description: str
    version: str
```

**ProviderRegistry** — 管理 Provider 及其 Fetcher
```python
@dataclass
class ProviderInfo:
    name: str                              # "yfinance"
    description: str
    website: str
    credentials_env: dict[str, str]        # 环境变量名
    coverage: dict[str, list[Exchange]]    # model → 交易所列表
    markets: list[str]                     # ["US", "CN", "HK"]
    data_delay: str                        # "15min"
    notes: str
```

**注册流程**（import 时自动触发）:
1. Model 文件在模块级调用 `model_registry.register(ModelInfo(...))`
2. Provider `__init__.py` 调用 `provider_registry.register_provider(ProviderInfo(...))`
3. Fetcher 文件在模块级调用 `provider_registry.register_fetcher(FetcherClass)`

**查询路由依赖**:
- `get_fetcher(model, provider)` — 获取特定 Fetcher 类
- `get_providers_for_exchange(model, exchange)` — 获取支持某交易所的所有 Provider
- `get_credentials(provider)` — 从环境变量加载凭证

#### 3.1.5 Router (`core/router.py`, 179 行)

SmartRouter 是核心调度引擎，实现自动 Provider 选择和故障转移。

**Provider 优先级**:

| Provider | 优先级 | 说明 |
|----------|--------|------|
| eastmoney | 90 | A 股官方数据，免费 |
| fmp | 85 | 全球覆盖，API Key |
| joinquant | 80 | A 股高质量历史数据 |
| yfinance | 75 | 全球免费，15 分钟延迟 |
| jquants | 70 | 日本市场 |
| akshare | 70 | A 股开源 |
| jugaad | 70 | 印度市场 |
| eodhd | 65 | 全球 EOD 数据 |
| tushare | 60 | A 股经典数据源 |

**选择逻辑**:
1. 用户显式指定 `provider` → 直接使用
2. 从 Symbol 检测交易所 → 筛选支持该交易所的 Provider
3. 按优先级降序排列 → 依次尝试
4. 一个失败 → 自动尝试下一个 → 全部失败抛出 `AllProvidersFailedError`

**输出保障**:
- 每行结果经 `result_type.model_validate(row)` Pydantic 验证
- 自动注入统一 Symbol（若结果中缺失或为 Provider 格式）

#### 3.1.6 Store (`core/store.py`, 114 行)

本地 DuckDB 持久化层，路径 `~/.unifin/data.duckdb`。

| 方法 | 作用 |
|------|------|
| `save(model_name, data, symbol)` | 写入缓存 |
| `load(model_name, symbol, start_date, end_date)` | 读取缓存 |
| `has_data(model_name, symbol)` | 检查数据是否存在 |

缓存失败不影响主流程（non-fatal），连接延迟初始化（lazy）。

#### 3.1.7 Errors (`core/errors.py`, 323 行)

为 AI 调用者设计的结构化错误层级。每个异常携带机器可解析字段：

```python
class UnifinError(Exception):
    code: str          # "INVALID_SYMBOL" — 稳定错误码
    received: Any      # 实际收到的值
    expected: list     # 合法值列表/示例
    hint: str          # 修复建议
    context: dict      # 额外结构化数据
```

**完整错误树**:

```
UnifinError
├── SymbolError (+ ValueError)          # INVALID_SYMBOL
├── ProviderError
│   ├── ProviderNotFoundError           # PROVIDER_NOT_FOUND
│   ├── NoProviderError                 # NO_PROVIDER
│   └── AllProvidersFailedError         # ALL_PROVIDERS_FAILED
├── ModelNotFoundError                  # MODEL_NOT_FOUND (含模糊匹配建议)
├── FetcherNotFoundError                # FETCHER_NOT_FOUND
└── ParamError (+ ValueError)
    ├── InvalidDateRangeError           # INVALID_DATE_RANGE
    ├── InvalidEnumValueError           # INVALID_ENUM_VALUE
    └── InvalidDateFormatError          # INVALID_DATE_FORMAT
```

`SymbolError` 和 `ParamError` 同时继承 `ValueError`，确保 Pydantic validator 正确传播。

---

### 3.2 Model 层 — 数据模型定义

每个数据模型由 **Query（入参）** + **Data（出参）** 两个 Pydantic v2 模型组成。模型定义是全局唯一的，Provider 不允许定义 ad-hoc 模型。

#### 注册的 10 个模型

| 模型名 | 类别 | Query 关键字段 | Data 关键字段 | 校验器 |
|--------|------|---------------|--------------|--------|
| `equity_historical` | equity.price | symbol, start_date, end_date, interval, adjust | date, OHLCV, amount, vwap, turnover_rate | symbol + date range |
| `equity_search` | equity | query, is_symbol, limit | symbol, name, exchange, asset_type | — |
| `equity_profile` | equity | symbol | symbol, name, sector, industry, employees... (16) | symbol |
| `equity_quote` | equity.price | symbol | symbol, OHLC, bid/ask, year_high/low, market_cap (22) | symbol |
| `balance_sheet` | equity.fundamental | symbol, period, limit | period_ending, 资产/负债/权益 24 个字段 | symbol |
| `income_statement` | equity.fundamental | symbol, period, limit | period_ending, 收入/费用/利润 22 个字段 | symbol |
| `cash_flow` | equity.fundamental | symbol, period, limit | period_ending, 经营/投资/筹资 19 个字段 | symbol |
| `index_historical` | index | symbol, start_date, end_date, interval | date, OHLCV, change, change_percent | symbol + date range |
| `etf_search` | etf | query, limit | symbol, name, fund_type, expense_ratio | — |
| `trade_calendar` | market | market, start_date, end_date | date, is_open, market | date range |

#### 校验机制

- **Symbol 校验**: 所有含 `symbol` 字段的 Query 模型使用 `@field_validator("symbol")` 调用 `validate_symbol()`
- **日期范围校验**: `equity_historical`、`index_historical`、`trade_calendar` 使用 `@model_validator` 确保 `start_date <= end_date`
- **枚举类型**: `interval` → `Interval`, `adjust` → `Adjust`, `period` → `Period`, `market` → `Market`，不接受裸字符串
- **Optional 字段**: 所有 Data 模型的非必填字段均为 `Optional[T] = None`，确保部分 Provider 未覆盖时不报错

---

### 3.3 Provider 层 — 数据源实现

#### 已实现的 Provider

**yfinance** — 8 个 Fetcher

| Fetcher | 支持交易所 | supported_fields | data_start_date | data_delay |
|---------|-----------|-----------------|----------------|------------|
| `equity_historical` | 21 个（全球） | date, open, high, low, close, volume | 1970-01-01 | 15min |
| `equity_search` | 21 个 | symbol, name, exchange, asset_type | — | 15min |
| `equity_profile` | 21 个 | symbol, name, sector, industry... (14) | — | 15min |
| `equity_quote` | 21 个 | symbol, last_price, open... (21) | — | 15min |
| `balance_sheet` | 21 个 | period_ending, fiscal_year... (23) | 2000-01-01 | eod |
| `income_statement` | 21 个 | period_ending, revenue... (22) | 2000-01-01 | eod |
| `cash_flow` | 21 个 | period_ending, net_cash... (18) | 2000-01-01 | eod |
| `index_historical` | 21 个 | date, open, high... (8) | 1970-01-01 | 15min |

**eastmoney** — 1 个 Fetcher

| Fetcher | 支持交易所 | 说明 |
|---------|-----------|------|
| `equity_historical` | XSHG, XSHE, XHKG | 需要 EmQuantAPI 本地客户端 |

#### 计划中的 Provider

| Provider | 优先级 | 覆盖市场 | 主要用途 |
|----------|--------|---------|---------|
| fmp | 85 | 全球 | 全球股票、财务数据 |
| joinquant | 80 | A 股 | 高质量历史数据，支持复权 |
| akshare | 70 | A 股 | 免费开源数据 |
| tushare | 60 | A 股 | 经典财务报表数据 |
| eodhd | 65 | 全球 | 全球 EOD 历史数据 |
| jquants | 70 | 日本 | J-Quants API |
| jugaad | 70 | 印度 | 印度市场数据 |

#### 新增 Provider 的步骤

```
src/unifin/providers/{name}/
├── __init__.py        # register_provider + import fetchers
├── equity_historical.py  # class XxxEquityHistoricalFetcher(Fetcher)
├── equity_search.py      # class XxxEquitySearchFetcher(Fetcher)
└── ...
```

1. 创建 Fetcher 子类，填写 `provider_name`、`model_name`、`supported_exchanges`、`supported_fields` 等元数据
2. 实现 `transform_query()`、`extract_data()`、`transform_data()` 三步管道
3. 在该 Provider 的 `__init__.py` 中注册 `ProviderInfo` 并 import 所有 Fetcher
4. 在 `src/unifin/__init__.py` 中添加 `try: import ... except ImportError: pass`

---

### 3.4 SDK 层 — 用户接口

SDK 暴露 4 个命名空间，每个函数的签名遵循相同模式：

```python
import unifin

# unifin.{namespace}.{function}(params...) → polars.DataFrame
df = unifin.equity.historical("AAPL", start_date="2024-01-01")
```

#### 命名空间

| 命名空间 | 函数 | 作用 |
|---------|------|------|
| `unifin.equity` | `historical()` | 历史行情（OHLCV） |
| | `search()` | 搜索股票 |
| | `profile()` | 公司资料 |
| | `quote()` | 实时/延迟报价 |
| | `balance_sheet()` | 资产负债表 |
| | `income_statement()` | 利润表 |
| | `cash_flow()` | 现金流量表 |
| `unifin.index` | `historical()` | 指数历史行情 |
| `unifin.etf` | `search()` | 搜索 ETF |
| `unifin.market` | `trade_calendar()` | 交易日历 |

#### SDK 层职责

1. **参数类型转换**: 字符串日期 → `datetime.date`，字符串枚举 → `Enum`
2. **友好错误**: 转换失败时抛出 `InvalidDateFormatError` / `InvalidEnumValueError`
3. **构造 Query**: 用转换后的参数构造 Pydantic Query 模型
4. **路由**: 调用 `router.query(model_name, query, provider)`
5. **缓存**: 查询前检查 DuckDB 缓存，查询后写入缓存（non-fatal）
6. **返回**: `polars.DataFrame`

---

## 4. 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | ≥ 3.11 |
| 类型系统 | Pydantic | v2 |
| 数据帧 | Polars | ≥ 1.0 |
| 本地缓存 | DuckDB | ≥ 1.0 |
| HTTP 客户端 | httpx | ≥ 0.27 |
| 构建工具 | Hatchling | — |
| 代码格式 | Ruff | ≥ 0.5 |
| 测试 | pytest | ≥ 8.0 |

---

## 5. 目录结构

```
unifin/
├── pyproject.toml                           # 项目配置
├── src/unifin/
│   ├── __init__.py                          # 入口：注册模型→Provider→暴露 SDK
│   ├── core/
│   │   ├── types.py        (144 行)        # 枚举: Exchange, Country, Interval, Adjust, Period, Market
│   │   ├── symbol.py       (265 行)        # Symbol 编解码 + 校验
│   │   ├── fetcher.py       (62 行)        # Fetcher 抽象基类
│   │   ├── registry.py     (184 行)        # ModelRegistry + ProviderRegistry
│   │   ├── router.py       (179 行)        # SmartRouter
│   │   ├── store.py        (114 行)        # DuckDB 缓存
│   │   └── errors.py       (323 行)        # 结构化错误层级
│   ├── models/                              # 10 个数据模型（Query + Data）
│   │   ├── equity_historical.py  (79 行)
│   │   ├── equity_search.py      (50 行)
│   │   ├── equity_profile.py     (58 行)
│   │   ├── equity_quote.py       (64 行)
│   │   ├── balance_sheet.py      (90 行)
│   │   ├── income_statement.py   (88 行)
│   │   ├── cash_flow.py          (84 行)
│   │   ├── index_historical.py   (73 行)
│   │   ├── etf_search.py         (48 行)
│   │   └── trade_calendar.py     (56 行)
│   ├── providers/
│   │   ├── yfinance/              (8 fetchers, 全球覆盖)
│   │   └── eastmoney/             (1 fetcher, A 股)
│   └── sdk/                                 # 4 个命名空间
│       ├── equity.py        (288 行)        # 7 个函数
│       ├── index.py          (69 行)        # 1 个函数
│       ├── etf.py            (41 行)        # 1 个函数
│       └── market.py         (65 行)        # 1 个函数
└── tests/                                   # 115 个测试
    ├── test_equity_historical.py  (317 行)  # Symbol + Registry + Router + E2E
    ├── test_m2_models.py          (591 行)  # 全模型 + Fetcher + 严格类型 + 输出验证
    └── test_error_messages.py     (424 行)  # 错误结构 + 友好性 + 继承链
```

**总代码量**: ~2,500 行（core + models + sdk），~1,330 行（tests），~5,070 行（总计）。

---

## 6. 关键机制详解

### 6.1 模块初始化顺序

`import unifin` 触发 `__init__.py` 中的初始化链：

```
1. 注册 10 个 Model（模型级 model_registry.register）
2. 注册 Provider（yfinance, eastmoney）
   → 每个 Provider 的 __init__.py 先注册 ProviderInfo
   → 再 import 各 Fetcher 模块 → 自动 register_fetcher
3. 暴露 SDK 命名空间（equity, index, etf, market）
```

Provider 注册使用 `try/except ImportError`，确保缺失可选依赖不影响启动。

### 6.2 TET Pipeline

每个 Fetcher 的核心职责是实现 Transform → Extract → Transform 三步管道：

```
               统一 Query
                  │
    ┌─────────────┼──────── Router 自动转换 symbol ────┐
    │             ▼                                     │
    │   transform_query(query) → params                 │
    │             │                                     │
    │   extract_data(params, creds) → raw_data          │
    │             │                                     │
    │   transform_data(raw_data, query) → [{...}, ...]  │
    │             │                                     │
    │   ┌─────────▼─────────── Router ──────────────┐   │
    │   │ model_validate() + symbol 注入             │   │
    │   └───────────────────────────────────────────┘   │
    └──────────────────────────────────────────────────┘
```

Router 在调用 `transform_query` 前自动将 Symbol 从统一格式转换为 Provider 格式。在 `transform_data` 后自动做 Pydantic 验证 + Symbol 回转。

### 6.3 错误消息设计（AI 友好）

设计目标：AI Agent 在收到错误后，**无需查阅任何文档**即可自动修正参数并重试。

**示例**:

```python
# 输入一个无效的 Symbol
unifin.equity.historical("apple inc")

# 抛出的 SymbolError:
# Invalid symbol format: 'apple inc'.
#   Received: 'apple inc'
#   Valid values: ['AAPL', '000001.XSHE', '0700.XHKG', '600519', '^GSPC', 'BRK.B']
#   Hint: A valid symbol is a US ticker (1-5 letters, e.g. 'AAPL', 'BRK.B'), ...

# 输入一个无效的周期
unifin.equity.historical("AAPL", interval="2h")

# 抛出的 InvalidEnumValueError:
# Invalid value for parameter 'interval'.
#   Received: '2h'
#   Valid values: ['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M']
#   Hint: Use one of: ['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M']

# 请求一个不存在的模型
model_registry.get("equity_hist")

# 抛出的 ModelNotFoundError:
# Model 'equity_hist' is not registered.
#   Received: 'equity_hist'
#   Valid values: ['balance_sheet', 'cash_flow', 'equity_historical', ...]
#   Hint: Did you mean one of: ['equity_historical', 'equity_search', ...]?
```

**核心字段作用**:

| 字段 | AI Agent 用途 |
|------|-------------|
| `code` | 程序化判断错误类别，选择修复策略 |
| `received` | 明确知道什么值触发了错误 |
| `expected` | 直接从中选择合法值重试 |
| `hint` | 当 expected 列表不够时提供修复方向 |
| `context` | 额外上下文（model_name、exchange 等） |

### 6.4 本地缓存策略

- **写入时机**: 成功获取数据后写入 DuckDB（仅 `equity_historical` 开启缓存）
- **读取时机**: SDK 调用前先查询本地缓存
- **缓存粒度**: 按 model + symbol + date range 查询
- **故障处理**: 缓存读写失败静默跳过（non-fatal）
- **存储位置**: `~/.unifin/data.duckdb`

---

## 7. 测试体系

| 测试文件 | 测试数量 | 覆盖范围 |
|---------|---------|---------|
| `test_equity_historical.py` | 25 | Symbol 解析 ×14、Registry ×3、Router ×2、Model ×3、E2E ×3 |
| `test_m2_models.py` | 57 | 模型注册 ×2、Fetcher 注册 ×3、模型校验 ×12、SDK ×4、E2E yfinance ×8、严格类型 ×8、输出验证 ×2、Provider 元数据 ×4、Symbol 校验 ×12 |
| `test_error_messages.py` | 33 | 错误类结构 ×11、Symbol 错误 ×3、Registry 错误 ×3、Router 错误 ×1、SDK 转换错误 ×8、模型验证 ×3、继承链 ×4 |
| **合计** | **115** | 全部通过（4.60s） |

---

## 8. 覆盖矩阵

### Model × Provider 实现状态

| 模型 | yfinance | eastmoney | fmp | joinquant | akshare | tushare |
|------|----------|-----------|-----|-----------|---------|---------|
| `equity_historical` | ✅ | ✅ | ⬜ | ⬜ | ⬜ | ⬜ |
| `equity_search` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `equity_profile` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `equity_quote` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `balance_sheet` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `income_statement` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `cash_flow` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `index_historical` | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `etf_search` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| `trade_calendar` | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

**当前覆盖**: yfinance 8/10、eastmoney 1/10

---

## 9. 使用示例

```python
import unifin

# ─── 基本查询 ─────────────────────

# 获取 A 股历史行情（自动选择 Provider）
df = unifin.equity.historical("000001.XSHE", start_date="2024-01-01")

# 获取美股历史行情
df = unifin.equity.historical("AAPL", start_date="2024-01-01")

# 指定 Provider
df = unifin.equity.historical("AAPL", provider="yfinance")

# 搜索股票
df = unifin.equity.search("Apple")

# 公司资料
df = unifin.equity.profile("AAPL")

# 实时报价
df = unifin.equity.quote("AAPL")

# ─── 财务报表 ─────────────────────

df = unifin.equity.balance_sheet("AAPL", period="quarter", limit=8)
df = unifin.equity.income_statement("AAPL")
df = unifin.equity.cash_flow("AAPL")

# ─── 指数 / ETF / 市场 ───────────

df = unifin.index.historical("^GSPC", start_date="2024-01-01")
df = unifin.etf.search("S&P 500")
df = unifin.market.trade_calendar(market="cn")

# ─── 错误处理 ─────────────────────

from unifin.core.errors import UnifinError, SymbolError, NoProviderError

try:
    df = unifin.equity.historical("???")
except SymbolError as e:
    print(f"[{e.code}] {e.hint}")
    # AI Agent 可以从 e.expected 中选择合法值重试

try:
    df = unifin.equity.historical("AAPL", interval="2h")
except UnifinError as e:
    print(f"Error {e.code}: expected {e.expected}")
```

---

## 10. 路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 | 核心框架 + equity_historical + yfinance/eastmoney | ✅ 完成 |
| M2 | 10 个模型 + 8 个 yfinance fetcher + 4 个 SDK 命名空间 | ✅ 完成 |
| 质量审计 | Period/Market 枚举、日期校验、输出验证、Symbol 注入、Provider 元数据 | ✅ 完成 |
| 错误友好 | 结构化错误层级、AI 友好消息、SDK 转换错误 | ✅ 完成 |
| M3 | fmp / joinquant Provider 实现 | ⬜ 计划 |
| M4 | etf_search / trade_calendar fetcher 实现 | ⬜ 计划 |
| M5 | akshare / tushare Provider 实现 | ⬜ 计划 |
| M6 | 增量同步、更智能的缓存策略 | ⬜ 计划 |
