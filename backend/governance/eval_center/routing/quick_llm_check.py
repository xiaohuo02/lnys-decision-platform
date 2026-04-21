# -*- coding: utf-8 -*-
"""LLM 配置自检工具：测试当前 .env / config.py 配置能否调通 Qwen 系列模型。

用法（项目根）：
    python -m backend.governance.eval_center.routing.quick_llm_check

输出每个候选模型的：是否可调通 / 单条调用延时 / 模型回复内容。
保留为运维诊断脚本，跟 routing eval 配套，用于：
  - 切换模型时确认新模型可用性与延时
  - LLM 兜底超时/降级排查时定位是 key / 网络 / 模型版本问题
  - 升级 langchain-openai 后回归验证

历史发现（2026/05/02）：项目原配置 `qwen3.5-plus-2026-02-15` 单条 6.74s，
比标准 `qwen-plus`（0.89s）慢 7 倍，导致 supervisor_agent.aroute() 的
asyncio.timeout(15s) 全部触发。本工具就是定位这个问题用的。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# ── 路径准备 ──
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main():
    from openai import OpenAI
    from backend.config import settings

    print("=" * 60)
    print("LLM 配置自检")
    print("=" * 60)
    print(f"BASE_URL    : {settings.LLM_BASE_URL}")
    print(f"CONFIGURED  : {settings.LLM_MODEL_NAME}")
    print(f"KEY_LENGTH  : {len(settings.LLM_API_KEY)}")
    print(f"KEY_PREFIX  : sk-..." if settings.LLM_API_KEY.startswith("sk-") else "KEY_PREFIX  : (非 sk- 开头)")
    print()

    if not settings.LLM_API_KEY:
        print("❌ LLM_API_KEY 为空，停止测试")
        sys.exit(1)

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=10.0,
    )

    # 候选模型名（按 Qwen 官方文档常见命名）
    candidates = [
        settings.LLM_MODEL_NAME,   # 配置里的（可能错）
        "qwen-plus",               # 标准命名
        "qwen-turbo",
        "qwen-max",
        "qwen3-plus",              # 新版
    ]
    # 去重
    seen = set()
    candidates = [m for m in candidates if not (m in seen or seen.add(m))]

    print(f"将依次测试 {len(candidates)} 个模型名")
    print("-" * 60)

    results = []
    for model in candidates:
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "回 OK 即可"}],
                max_tokens=10,
            )
            latency = time.time() - t0
            content = (resp.choices[0].message.content or "").strip()[:30]
            print(f"  ✅ [{model:30s}]  {latency:.2f}s  reply={content!r}")
            results.append((model, True, latency, None))
        except Exception as e:
            latency = time.time() - t0
            err_type = type(e).__name__
            err_msg = str(e)[:120]
            print(f"  ❌ [{model:30s}]  {latency:.2f}s  {err_type}: {err_msg}")
            results.append((model, False, latency, f"{err_type}: {err_msg}"))

    print("-" * 60)
    ok = [r for r in results if r[1]]
    if ok:
        print(f"\n✅ 可用模型：{[r[0] for r in ok]}")
        print(f"   推荐改 settings.LLM_MODEL_NAME = {ok[0][0]!r}")
    else:
        print("\n❌ 所有候选模型都不可用，请检查 .env 中的 LLM_API_KEY 或 LLM_BASE_URL")


if __name__ == "__main__":
    main()
