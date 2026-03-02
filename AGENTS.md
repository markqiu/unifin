# AGENTS.md — unifin

unifin 是一个统一的全球金融数据平台，通过单一 SDK 入口聚合多个数据源（yfinance、eastmoney、tushare、joinquant、fmp 等），对外提供标准化的 Python API。所有 SDK 函数返回 `polars.DataFrame`。

## 环境设置

- Python **3.11+**（当前开发环境为 3.14.2）
- 包管理：使用 uv 或 pip
- 虚拟环境路径：`.venv/`
- 安装命令（开发模式）：

```bash
pip install -e ".[dev,all]"
```

## 构建、测试、Lint 命令

```bash
# 运行全部测试（115 个，约 5 秒）
pytest

# 运行单个测试文件
pytest tests/test_equity_historical.py -xvs

# 运行单个测试
pytest tests/test_m2_models.py::TestModelsRegistered::test_all_models_registered -xvs

# Lint 检查
ruff check src/ tests/

# 格式化检查
ruff format --check src/ tests/

# 自动修复
ruff check --fix src/ tests/
ruff format src/ tests/
```

- 每次修改代码后 **必须** 运行 `pytest` 确保全部 115 个测试通过。
- 每次修改代码后 **必须** 运行 `ruff check src/ tests/` 确保无 lint 错误。
- 测试不依赖网络，可离线运行。需要真实 API 调用的测试标记了 E2E。

## 项目结构

```
src/unifin/
├── __init__.py          # 入口：先注册 10 个 Model → 再注册 Provider → 暴露 SDK
├── core/
│   ├── types.py         # 所有枚举: Exchange(28 MIC), Country, Interval, Adjust, Period, Market
│   ├── symbol.py        # ISO 10383 MIC ↔ Provider symbol 双向转换 + 校验
│   ├── fetcher.py       # Fetcher 抽象基类 (TET pipeline)
│   ├── registry.py      # ModelRegistry + ProviderRegistry 全局单例
│   ├── router.py        # SmartRouter: 自动选 Provider、优先级排序、故障转移
│   ├── store.py         # DuckDB 本地缓存 (~/.unifin/data.duckdb)
│   └── errors.py        # 结构化错误层级 (UnifinError 树)
├── models/              # 10 个数据模型 (每个文件含 Query + Data Pydantic 模型)
├── providers/
│   ├── yfinance/        # 8 个 Fetcher (全球覆盖)
│   └── eastmoney/       # 1 个 Fetcher (A 股)
├── sdk/                 # 4 个命名空间模块 (equity, index, etf, market)
tests/
├── test_equity_historical.py   # 25 tests: Symbol + Registry + Router + E2E
├── test_m2_models.py           # 57 tests: 全模型 + Fetcher + 类型 + 输出验证
└── test_error_messages.py      # 33 tests: 错误结构 + 友好性 + 继承链
```

## 架构规则

### 1. 分层依赖方向（严格单向）

```
SDK → Router → Registry → Model → Core (types, symbol, fetcher, errors)
                                     ↑
Provider → Fetcher(ABC) ─────────────┘
```

- **禁止** 上层模块 import 下层具体实现（如 core 不能 import sdk 或 providers）。
- **禁止** Provider 之间相互 import。
- Provider 只能依赖 `core/*` 和 `models/*`。

### 2. 初始化顺序（`__init__.py` 中的 import 顺序不可改）

1. **先注册所有 Model**（10 个 `from unifin.models import ...`）
2. **再注册所有 Provider**（`try-except ImportError` 包裹，缺失可选依赖不报错）
3. **最后暴露 SDK 命名空间**

违反此顺序会导致 Registry 查找失败。

### 3. Model 定义规范

每个模型文件 **必须** 包含：

- 一个 `*Query(BaseModel)` — 查询入参
- 一个 `*Data(BaseModel)` — 返回结果
- 模块级 `model_registry.register(ModelInfo(...))` 调用

格式规范：
- 日期字段使用 `import datetime as dt` 然后 `dt.date` / `dt.datetime`（**绝对不能** `from datetime import date`，Python 3.14 + Pydantic 会冲突）。
- 所有 Data 模型的非必填字段 **必须** 为 `Optional[T] = None`。
- 含 `symbol` 字段的 Query **必须** 添加 `@field_validator("symbol")` 调用 `validate_symbol()`。
- 含日期范围的 Query **必须** 添加 `@model_validator(mode="after")` 验证 `start_date <= end_date`。
- 枚举参数 **必须** 使用 `Interval` / `Adjust` / `Period` / `Market` 枚举类型，**禁止** 裸字符串。

### 4. Fetcher 实现规范

每个 Fetcher **必须**：

- 继承 `unifin.core.fetcher.Fetcher`
- 设置 `ClassVar`: `provider_name`, `model_name`, `supported_exchanges`
- **强烈建议** 设置: `supported_fields`, `data_start_date`, `data_delay`, `notes`
- 实现三个 `@staticmethod @abstractmethod` 方法:
  - `transform_query(query) → dict` — 统一查询 → Provider 参数
  - `extract_data(params, credentials) → Any` — 调用 API
  - `transform_data(raw_data, query) → list[dict]` — 原始数据 → 统一 dict 列表
- 在模块级调用 `provider_registry.register_fetcher(XxxFetcher)` 完成自注册

### 5. Provider 注册规范

每个 Provider 包的 `__init__.py` **必须**：

1. 先调用 `provider_registry.register_provider(ProviderInfo(...))` 注册元信息
2. 再 import 各 Fetcher 模块以触发 `register_fetcher`
3. 在项目根 `__init__.py` 中用 `try/except ImportError` 包裹 import

### 6. Symbol 编码规则

统一使用 ISO 10383 MIC 格式：
- A 股: `{6位代码}.XSHE` 或 `.XSHG`（如 `000001.XSHE`）
- 美股: 纯 Ticker（如 `AAPL`、`BRK.B`），**不加后缀**
- 港股: `{代码}.XHKG`（如 `0700.XHKG`）
- 指数: `^{代码}`（如 `^GSPC`）

Router 自动将统一 Symbol 转换为 Provider 格式（如 yfinance 的 `.SZ`），Fetcher 内部 **不需要** 自行转换。

### 7. 错误处理规范

- 所有自定义异常 **必须** 继承 `UnifinError`。
- 每个错误 **必须** 设置 `code`（机器可读）、`received`、`expected`（合法值列表）、`hint`（修复建议）。
- 需要被 Pydantic validator 抛出的错误，**必须** 同时继承 `ValueError`（如 `SymbolError(UnifinError, ValueError)`）。
- **禁止** 抛出裸 `Exception` 或 `ValueError`，始终使用 `errors.py` 中的具体错误类。

错误层级：
```
UnifinError
├── SymbolError (+ValueError)
├── ProviderError → ProviderNotFoundError / NoProviderError / AllProvidersFailedError
├── ModelNotFoundError (含模糊匹配建议)
├── FetcherNotFoundError
└── ParamError (+ValueError) → InvalidDateRangeError / InvalidEnumValueError / InvalidDateFormatError
```

### 8. SDK 函数规范

- 每个 SDK 函数 **必须** 返回 `polars.DataFrame`。
- 字符串参数在 SDK 层做类型转换：日期字符串 → `datetime.date`，枚举字符串 → `Enum`。
- 转换失败时抛出 `InvalidDateFormatError` 或 `InvalidEnumValueError`，**不抛裸 ValueError**。
- SDK 函数 **不能** 直接调用 Provider 代码，**必须** 通过 `router.query()` 路由。

### 9. SmartRouter 行为

- Provider 优先级: eastmoney(90) > fmp(85) > joinquant(80) > yfinance(75) > akshare(70) > tushare(60)
- 路由流程: 从 symbol 检测 exchange → 筛选支持该 exchange 的 Provider → 按优先级排序 → 依次尝试（首个成功即返回）
- Router 负责: symbol 转换（unified → provider）、Pydantic 输出验证、symbol 注入（确保结果含统一 symbol）
- 缓存失败 **不能** 影响主流程（non-fatal）。

### 10. 测试规范

- 测试文件放在 `tests/` 目录下，命名 `test_*.py`。
- 使用 `pytest`，**不** 使用 `unittest.TestCase`。
- 新增 Model 或 Fetcher **必须** 同时添加测试，覆盖：注册、字段验证、类型检查。
- 错误路径和边界条件 **必须** 有对应测试。
- E2E 测试（需要实际 API 调用）使用 `@pytest.mark.skipif` 条件跳过。

## 新增功能的操作清单

### 新增一个 Model

1. 在 `src/unifin/models/` 创建 `{model_name}.py`
2. 定义 `Query(BaseModel)` + `Data(BaseModel)` + `model_registry.register()`
3. 在 `src/unifin/__init__.py` 中添加 `from unifin.models import {model_name}` （在 Provider import **之前**）
4. 在 `tests/` 中添加测试（注册、字段验证）
5. 运行 `pytest` 和 `ruff check`

### 新增一个 Fetcher

1. 在 `src/unifin/providers/{provider}/` 创建 `{model_name}.py`
2. 实现 Fetcher 子类，设置全部 ClassVar + TET 三步方法
3. 在该 Provider 的 `__init__.py` 中 import 新 Fetcher
4. 在 `tests/` 中添加测试（注册、数据转换）
5. 运行 `pytest` 和 `ruff check`

### 新增一个 Provider

1. 创建 `src/unifin/providers/{name}/__init__.py`
2. 调用 `provider_registry.register_provider(ProviderInfo(...))`
3. 实现各 Fetcher 并在 `__init__.py` 中 import
4. 在 `src/unifin/__init__.py` 中添加 `try: import ... except ImportError: pass`
5. 在 `pyproject.toml` 的 `[project.optional-dependencies]` 中添加对应依赖
6. 更新 `[project.optional-dependencies] all = [...]` 列表
7. 运行 `pytest` 和 `ruff check`

## 代码风格

- Ruff 配置: `target-version = "py311"`, `line-length = 100`
- 启用规则: `E`(pycodestyle), `F`(pyflakes), `I`(isort), `N`(pep8-naming), `W`(warnings), `UP`(pyupgrade)
- 所有 import 顶部分组排列（标准库 → 第三方 → 本地），由 ruff isort 管理。
- 类型注解使用 `from __future__ import annotations`（core 模块中使用）。
- 模块级 docstring **必须** 包含模块用途的单行描述。

## 不要做的事情

- **不要** 修改 `core/types.py` 中现有枚举成员的值（会破坏已有 symbol 映射）。
- **不要** 在 Provider 代码中硬编码 symbol 后缀映射，使用 `core/symbol.py` 的函数。
- **不要** 在 Fetcher 中直接返回 `polars.DataFrame`，始终返回 `list[dict]`。
- **不要** 跳过 Pydantic 输出验证（不要绕过 Router 的 `model_validate`）。
- **不要** 在错误中暴露 API Key 或凭证信息。
- **不要** 在生产代码中使用 `print()`，使用结构化错误或日志。

## 参考文档

- 完整架构设计: `docs/ARCHITECTURE.md`
- pyproject.toml: 依赖和构建配置
- `src/unifin/core/errors.py`: 完整错误层级定义
- `src/unifin/core/types.py`: 所有枚举类型定义
