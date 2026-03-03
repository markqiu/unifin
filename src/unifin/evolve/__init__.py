"""unifin self-evolution module — auto-discover data sources and generate code.

Workflow:
1. User describes a data need in natural language (via chat/REST).
2. Orchestrator → Analyzer → LLM understands the need → DataNeed.
3. Discoverer searches known provider APIs for matching functions.
4. Generator produces model + fetcher + test code.
5. User confirms the plan.
6. Loader hot-registers everything → immediately available in SDK/REST/NL.
"""
