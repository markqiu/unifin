"""End-to-end verification script for the unifin full pipeline."""

import httpx
import json

base = "http://127.0.0.1:8000"

# 1. Health check
print("=== 1. Health Check ===")
r = httpx.get(f"{base}/api/health")
print(r.json())
print()

# 2. List models
print("=== 2. List Models ===")
r = httpx.get(f"{base}/api/models")
for m in r.json():
    name = m["name"]
    cat = m["category"]
    desc = m["description"][:50]
    print(f"  {name:25s}  {cat:15s}  {desc}")
print()

# 3. List providers
print("=== 3. List Providers ===")
r = httpx.get(f"{base}/api/providers")
for p in r.json():
    name = p["name"]
    models = p["models"]
    print(f"  {name:12s}  models: {models}")
print()

# 4. POST equity_historical (US — more reliable than akshare)
print("=== 4. POST equity_historical (美股 AAPL) ===")
r = httpx.post(
    f"{base}/api/equity/price/equity_historical",
    json={
        "symbol": "AAPL",
        "start_date": "2025-06-01",
        "end_date": "2025-06-30",
    },
    timeout=30,
)
data = r.json()
assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"
print(f"  返回 {len(data)} 行数据")
if data:
    first = data[0]
    print(f"  第一行: date={first['date']}, close={first['close']}")
    print(f"  最后行: date={data[-1]['date']}, close={data[-1]['close']}")
print()

# 5. POST equity_search
print("=== 5. POST equity_search (搜索 AAPL) ===")
r = httpx.post(
    f"{base}/api/equity/equity_search",
    json={"query": "AAPL"},
    timeout=30,
)
data = r.json()
assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"
print(f"  返回 {len(data)} 条结果")
if data:
    print(f"  第一条: {data[0]}")
print()

# 6. NL tools schema
print("=== 6. NL Tools Schema ===")
r = httpx.get(f"{base}/api/nl/tools")
tools = r.json()
print(f"  生成 {len(tools)} 个工具定义")
for t in tools:
    print(f"  - {t['function']['name']}")
print()

print("=== 全流程验证通过! ===")
