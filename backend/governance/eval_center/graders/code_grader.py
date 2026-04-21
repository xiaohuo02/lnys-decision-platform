# -*- coding: utf-8 -*-
"""backend/governance/eval_center/graders/code_grader.py — Code-Based 确定性评分器

6 种确定性评分策略，零 LLM 调用：
  - ExactMatchGrader:       精确匹配
  - FieldMatchGrader:       JSON 字段匹配
  - SchemaCheckGrader:      输出 Schema 校验
  - ThresholdGrader:        数值阈值检查
  - KeywordMatchGrader:     关键词命中率
  - KeyInfoRetentionGrader: 关键信息保留率（tool_result 数据是否被引用）
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

from backend.governance.eval_center.graders.base_grader import BaseGrader, GraderResult

_SENTINEL = object()

def _deep_get(obj: Any, path: str, default: Any = _SENTINEL) -> Any:
    """支持嵌套路径取值，如 'scores.0.risk_level' 或 'data_ready'

    路径用 '.' 分隔，纯数字片段当作 list 下标。
    """
    parts = path.split(".")
    cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p, _SENTINEL)
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                cur = _SENTINEL
        else:
            cur = _SENTINEL
        if cur is _SENTINEL:
            return default
    return cur


class ExactMatchGrader(BaseGrader):
    """精确匹配：actual 中指定字段的值 == expected 中对应值"""

    grader_name = "exact_match"

    def __init__(self, field: str = "answer", pass_threshold: float = 1.0, **kwargs):
        super().__init__(pass_threshold=pass_threshold, **kwargs)
        self.field = field

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        field = config.get("field", self.field)

        expected_val = expected_json.get(field)
        actual_val = actual_output.get(field)

        if expected_val is None:
            return self._make_result(1.0, reasoning="expected 无目标字段，视为通过")

        if actual_val is None:
            return self._make_result(0.0, reasoning=f"actual 缺少字段 '{field}'")

        exp_str = str(expected_val).strip().lower()
        act_str = str(actual_val).strip().lower()

        if exp_str == act_str:
            return self._make_result(1.0, reasoning="精确匹配通过")

        # 部分匹配打分：Jaccard 相似度
        exp_set = set(exp_str.split())
        act_set = set(act_str.split())
        if exp_set and act_set:
            jaccard = len(exp_set & act_set) / len(exp_set | act_set)
        else:
            jaccard = 0.0

        return self._make_result(
            jaccard,
            reasoning=f"不完全匹配: expected='{expected_val}', actual='{actual_val}', jaccard={jaccard:.3f}",
        )


class FieldMatchGrader(BaseGrader):
    """JSON 字段匹配：检查 actual 中是否包含 expected 指定的多个字段及值"""

    grader_name = "field_match"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        fields: List[str] = config.get("fields", list(expected_json.keys()))

        if not fields:
            return self._make_result(1.0, reasoning="无需检查的字段")

        matched = 0
        details = []

        for f in fields:
            exp_val = _deep_get(expected_json, f, None)
            act_val = _deep_get(actual_output, f, None)

            if exp_val is None:
                matched += 1
                details.append(f"  {f}: 跳过（expected 无此字段）")
                continue

            if act_val is None:
                details.append(f"  {f}: ✗ actual 缺失")
                continue

            if str(exp_val).strip().lower() == str(act_val).strip().lower():
                matched += 1
                details.append(f"  {f}: ✓")
            else:
                details.append(f"  {f}: ✗ expected='{exp_val}', actual='{act_val}'")

        score = matched / len(fields)
        return self._make_result(
            score,
            reasoning=f"字段匹配 {matched}/{len(fields)}\n" + "\n".join(details),
        )


class SchemaCheckGrader(BaseGrader):
    """Schema 校验：检查 actual 是否包含所有必要字段且类型正确"""

    grader_name = "schema_check"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        required_fields: List[str] = config.get("required_fields", [])

        # 如果 config 没指定，从 expected_json 推断
        if not required_fields and expected_json:
            required_fields = list(expected_json.keys())

        if not required_fields:
            return self._make_result(1.0, reasoning="无 schema 约束")

        present = 0
        missing = []
        for f in required_fields:
            val = _deep_get(actual_output, f, _SENTINEL)
            if val is not _SENTINEL and val is not None:
                present += 1
            else:
                missing.append(f)

        score = present / len(required_fields)
        reasoning = f"必要字段 {present}/{len(required_fields)}"
        if missing:
            reasoning += f", 缺失: {missing}"

        return self._make_result(score, reasoning=reasoning)


class ThresholdGrader(BaseGrader):
    """数值阈值检查：actual 中指定数值字段是否达到/不超过期望阈值"""

    grader_name = "threshold"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        checks: List[Dict] = config.get("checks", [])

        # 从 expected_json 自动推断 checks
        if not checks and expected_json:
            for k, v in expected_json.items():
                if isinstance(v, (int, float)):
                    checks.append({"field": k, "op": "gte", "value": v})

        if not checks:
            return self._make_result(1.0, reasoning="无阈值检查项")

        passed_checks = 0
        details = []

        for chk in checks:
            field = chk.get("field", "")
            op = chk.get("op", "gte")
            threshold = chk.get("value", 0)
            actual_val = actual_output.get(field)

            if actual_val is None:
                details.append(f"  {field}: ✗ 字段缺失")
                continue

            try:
                actual_num = float(actual_val)
            except (ValueError, TypeError):
                details.append(f"  {field}: ✗ 非数值 ({actual_val})")
                continue

            ok = False
            if op == "gte":
                ok = actual_num >= threshold
            elif op == "lte":
                ok = actual_num <= threshold
            elif op == "gt":
                ok = actual_num > threshold
            elif op == "lt":
                ok = actual_num < threshold
            elif op == "eq":
                ok = abs(actual_num - threshold) < 1e-6

            if ok:
                passed_checks += 1
                details.append(f"  {field}: ✓ {actual_num} {op} {threshold}")
            else:
                details.append(f"  {field}: ✗ {actual_num} not {op} {threshold}")

        score = passed_checks / len(checks) if checks else 1.0
        return self._make_result(
            score,
            reasoning=f"阈值检查 {passed_checks}/{len(checks)}\n" + "\n".join(details),
        )


class KeywordMatchGrader(BaseGrader):
    """关键词命中率：actual 文本中是否包含 expected 指定的关键词"""

    grader_name = "keyword_match"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}
        keywords: List[str] = config.get("keywords", [])

        if not keywords:
            keywords = expected_json.get("contains", [])
            if not keywords and isinstance(expected_json.get("keywords"), list):
                keywords = expected_json["keywords"]

        if not keywords:
            return self._make_result(1.0, reasoning="无关键词约束")

        # 从 actual_output 提取所有文本
        text = self._extract_text(actual_output).lower()

        matched = []
        missed = []
        for kw in keywords:
            if kw.lower() in text:
                matched.append(kw)
            else:
                missed.append(kw)

        score = len(matched) / len(keywords)
        reasoning = f"关键词命中 {len(matched)}/{len(keywords)}"
        if missed:
            reasoning += f", 未命中: {missed}"

        return self._make_result(score, reasoning=reasoning)

    @staticmethod
    def _extract_text(output: Dict[str, Any]) -> str:
        """从 actual_output 中提取所有文本内容"""
        parts = []
        for key in ("text", "answer", "content", "summary", "output"):
            val = output.get(key)
            if val and isinstance(val, str):
                parts.append(val)
        if not parts:
            parts.append(json.dumps(output, ensure_ascii=False))
        return " ".join(parts)


class KeyInfoRetentionGrader(BaseGrader):
    """关键信息保留率：tool_result 中的数字/实体是否被正确引用在最终输出中

    用于检测 LLM 幻觉 — tool 返回的数据与最终回答中的数据是否一致。
    """

    grader_name = "key_info_retention"

    async def grade(
        self,
        input_json: Dict[str, Any],
        expected_json: Dict[str, Any],
        actual_output: Dict[str, Any],
        evaluator_config: Dict[str, Any] = None,
    ) -> GraderResult:
        config = evaluator_config or {}

        # 从 expected_json 提取关键信息点
        key_facts: List[str] = config.get("key_facts", [])

        if not key_facts:
            key_facts = self._extract_key_facts(expected_json)

        if not key_facts:
            return self._make_result(1.0, reasoning="无可检查的关键信息")

        text = self._extract_text(actual_output).lower()
        retained = []
        lost = []

        for fact in key_facts:
            fact_lower = str(fact).lower().strip()
            if fact_lower in text:
                retained.append(fact)
            else:
                # 数字可能格式不同（1000 vs 1,000）
                normalized = fact_lower.replace(",", "").replace(" ", "")
                text_normalized = text.replace(",", "").replace(" ", "")
                if normalized in text_normalized:
                    retained.append(fact)
                else:
                    lost.append(fact)

        score = len(retained) / len(key_facts)
        reasoning = f"关键信息保留 {len(retained)}/{len(key_facts)}"
        if lost:
            reasoning += f", 丢失: {lost}"

        return self._make_result(score, reasoning=reasoning)

    @staticmethod
    def _extract_key_facts(expected: Dict[str, Any]) -> List[str]:
        """从 expected_json 中提取数字和关键实体作为事实检查点"""
        facts = []
        for k, v in expected.items():
            if isinstance(v, (int, float)):
                facts.append(str(v))
            elif isinstance(v, str):
                # 提取数字
                numbers = re.findall(r'\d+\.?\d*', v)
                facts.extend(numbers)
                # 提取中文实体（2字以上连续中文）
                entities = re.findall(r'[\u4e00-\u9fff]{2,}', v)
                facts.extend(entities)
            elif isinstance(v, list):
                facts.extend(str(item) for item in v)
        return facts[:20]  # 上限 20 个检查点

    @staticmethod
    def _extract_text(output: Dict[str, Any]) -> str:
        parts = []
        for key in ("text", "answer", "content", "summary", "output"):
            val = output.get(key)
            if val and isinstance(val, str):
                parts.append(val)
        if not parts:
            parts.append(json.dumps(output, ensure_ascii=False))
        return " ".join(parts)
