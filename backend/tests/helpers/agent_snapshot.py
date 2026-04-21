# -*- coding: utf-8 -*-
"""backend/tests/helpers/agent_snapshot.py — Agent/Skill 行为快照工具 (R6-3-pre)

设计目标:
  - 把 Agent/Skill 的结构化输出序列化为稳定 JSON（按 key 排序）
  - 写入 golden file，供后续重构时做行为回归对比
  - 环境变量 UPDATE_SNAPSHOTS=1 强制更新 golden，不触发 assert

用法:
    # 首次运行: UPDATE_SNAPSHOTS=1 pytest tests/test_something.py
    # 后续运行: 自动对比
    from backend.tests.helpers.agent_snapshot import assert_matches_snapshot

    def test_my_agent():
        output = my_agent.answer(input)
        assert_matches_snapshot(
            actual=output.model_dump(),
            snapshot_name="my_agent_happy_path",
        )

规范:
  - snapshot 文件存放: backend/tests/fixtures/snapshots/<snapshot_name>.json
  - 序列化稳定性: sort_keys=True + ensure_ascii=False + 缩进 2
  - 非 JSON 可序列化字段 (datetime/UUID/set) 用 default=str fallback
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

SNAPSHOT_DIR = Path(__file__).parent.parent / "fixtures" / "snapshots"
UPDATE_ENV = "UPDATE_SNAPSHOTS"


def _snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / f"{name}.json"


def _serialize(data: Any) -> str:
    """稳定序列化: 排序 key + 非 JSON 类型降级为 str。"""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2, default=str)


def save_snapshot(name: str, data: Any) -> Path:
    """显式保存一个 snapshot（用于手动维护 golden file）。"""
    path = _snapshot_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize(data), encoding="utf-8")
    return path


def load_snapshot(name: str) -> Optional[Any]:
    """加载 snapshot。不存在时返回 None（首次运行）。"""
    path = _snapshot_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def assert_matches_snapshot(
    actual: Any,
    snapshot_name: str,
    update: Optional[bool] = None,
) -> None:
    """把 actual 和 golden snapshot 对比。

    Args:
        actual:        当前 Agent/Skill 输出（dict / list / 标量）
        snapshot_name: golden file 逻辑名（自动拼 fixtures/snapshots/<name>.json）
        update:        True 则强制重写 golden；None 则读环境变量 UPDATE_SNAPSHOTS

    Raises:
        AssertionError: 输出与 golden 不一致且非 update 模式
    """
    if update is None:
        update = os.environ.get(UPDATE_ENV, "").lower() in ("1", "true", "yes")

    path = _snapshot_path(snapshot_name)

    if update or not path.exists():
        save_snapshot(snapshot_name, actual)
        return

    expected_text = path.read_text(encoding="utf-8")
    actual_text = _serialize(actual)

    if expected_text != actual_text:
        # 生成简要 diff 摘要，避免刷屏
        import difflib
        diff_lines = list(difflib.unified_diff(
            expected_text.splitlines(keepends=True),
            actual_text.splitlines(keepends=True),
            fromfile=f"{snapshot_name}.golden",
            tofile=f"{snapshot_name}.actual",
            n=3,
        ))
        diff_preview = "".join(diff_lines[:60])  # 限制长度
        raise AssertionError(
            f"Snapshot mismatch for '{snapshot_name}' at {path}\n\n"
            f"Diff (first 60 lines):\n{diff_preview}\n\n"
            f"提示: 设置 {UPDATE_ENV}=1 可以强制更新 golden file"
        )
