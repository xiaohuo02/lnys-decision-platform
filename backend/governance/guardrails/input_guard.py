# -*- coding: utf-8 -*-
"""backend/governance/guardrails/input_guard.py — 输入安全防护

设计来源: Claude Code 分层 Guardrails + 本项目 v4.0 安全架构

检查项:
  1. PII 检测: 手机号/身份证/银行卡/邮箱 → 脱敏或拦截
  2. 注入攻击: 提示词注入/角色伪装/指令覆写 → 拦截
  3. 长度限制: 超长文本 → 截断
  4. 敏感词: 内部规则名/风控阈值/系统提示词泄露 → 拦截

原则:
  - 检查失败不抛异常，返回 GuardResult
  - 可脱敏的尽量脱敏后放行，不可容忍的才拦截
  - 所有拦截记录 guardrail_hits (供 Trace 使用)
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel


# ── 检查结果结构 ──────────────────────────────────────────────────

class GuardHit(BaseModel):
    """单条命中记录"""
    rule: str
    severity: str       # info | warning | block
    message: str
    original: str = ""  # 命中的原始文本片段


class GuardResult(BaseModel):
    """InputGuard 的返回结构"""
    passed: bool                          # 是否放行
    sanitized_text: Optional[str] = None  # 脱敏/截断后的文本 (passed=True 时有值)
    blocked_reason: Optional[str] = None  # 拦截原因 (passed=False 时有值)
    hits: List[GuardHit] = []             # 所有命中的规则


# ── 正则模式 ──────────────────────────────────────────────────────

# 中国手机号: 1 开头 11 位
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# 身份证号: 18 位 (最后一位可能是 X)
_RE_ID_CARD = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")

# 银行卡号候选: 16-19 位纯数字（两阶段过滤：Luhn 校验 + 上下文关键词）
_RE_BANK_CARD_CANDIDATE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

# 银行卡上下文关键词（小写匹配）：仅当文本中出现这些词才对 16-19 位数字做银行卡脱敏
_BANK_CARD_CONTEXT_WORDS = (
    "银行卡", "卡号", "信用卡", "储蓄卡", "借记卡", "银行账号", "开户行",
    "bank card", "credit card", "debit card", "bankcard", "card number",
)


def _luhn_check(digits_str: str) -> bool:
    """Luhn 算法校验银行卡号（ISO/IEC 7812-1）。

    Luhn 能过滤随机数字串（10% 通过率），结合上下文关键词能把银行卡误报
    从~100% 降到约 1%（双重过滤）。
    """
    try:
        digits = [int(c) for c in digits_str]
    except ValueError:
        return False
    if len(digits) < 13:
        return False
    checksum = 0
    # 从右往左，偶数位（从 1 开始计数）翻倍再取数位和
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0

# 邮箱
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# 注入攻击关键词（运行前会先做 NFKC 归一化 + 移除零宽字符）
_INJECTION_PATTERNS = [
    # 中文 "忽略/无视/跳过/抛开/不要管" + 指令/规则/提示/约束/上下文
    r"(忽略|无视|跳过|抛开|丢掉|不要管|不用理).{0,10}(指令|规则|提示|约束|上面|之前|前面)",
    r"(忽略|无视).{0,5}以上",
    # 繁体等价词
    r"(忽略|無視|跳過|拋開|丟掉).{0,10}(指令|規則|提示|約束|上面|之前|前面)",
    # 自我赋予管理员身份
    r"你(现在|已经)?是.{0,5}(管理员|超级用户|超级管理员|root|admin|developer)",
    r"(扮演|假装|充当|演).{0,5}(是|为)?.{0,10}(管理员|超级用户|root|admin|developer|system)",
    r"act\s+as\s+(?:a|an)?\s*(admin|root|developer|system|superuser)",
    # 直接注入 system 消息
    r"system\s*:",
    r"<\s*system\s*>",
    r"\[\s*system\s*\]",
    # 试图读内部提示
    r"你的(系统|内部).{0,5}(提示|指令|规则)",
    r"(输出|显示|回显|告诉我|告知|泄露|展示).{0,15}(系统提示|system\s*prompt|内部指令|prompt\s*模板|原始提示)",
    r"(show|reveal|dump|leak|print)\s+(me\s+)?(your\s+|the\s+)?(system\s*prompt|prompt\s*template|full\s*instruction)",
    # Override 系列
    r"override\s*(all|previous|system)",
    # 越狱关键词
    r"jailbreak",
    r"DAN\s*(mode|do\s*anything\s*now)",
    r"developer\s*mode",
    # 英文忽略指令
    r"ignore\s+(all\s+)?(previous\s+|above\s+)?(instructions?|rules?|prompts?|constraints?)",
    r"disregard\s+(all\s+)?(previous\s+|above\s+)?(instructions?|rules?)",
    # 角色扮演指令
    r"pretend\s*(you|to)\s*(are|be)\s*(a|an)?",
    r"roleplay\s+as",
]
_RE_INJECTION = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

_RE_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060\u180e]")

# 内部敏感词 (不应在用户输入中出现的内部术语)
_SENSITIVE_TERMS = [
    "风控阈值", "fraud_threshold", "score_cutoff",
    "policy_engine", "guardrail_config",
    "internal_api_key", "secret_key", "api_key", "api key",
    "action_ledger", "audit_bypass",
    "数据库密码", "db password", "db_password",
    "密钥", "密码是什么", "token是什么",
    "system prompt", "系统提示词",
]


# ── InputGuard 实现 ───────────────────────────────────────────────

class InputGuard:
    """
    输入安全防护。

    用法:
        guard = InputGuard()
        result = guard.check("帮我查一下订单")
        if result.passed:
            safe_text = result.sanitized_text
        else:
            return f"请求被拦截: {result.blocked_reason}"
    """

    def __init__(
        self,
        max_length: int = 4000,
        pii_action: str = "mask",      # mask | block
        enable_injection_check: bool = True,
        enable_sensitive_check: bool = True,
    ):
        self.max_length = max_length
        self.pii_action = pii_action
        self.enable_injection_check = enable_injection_check
        self.enable_sensitive_check = enable_sensitive_check

    def check(self, text: str) -> GuardResult:
        """执行全部检查，返回 GuardResult"""
        if not text or not text.strip():
            return GuardResult(passed=True, sanitized_text="", hits=[])

        hits: List[GuardHit] = []
        current_text = text

        # ── 1. 长度检查 ──────────────────────────────────────────
        if len(current_text) > self.max_length:
            hits.append(GuardHit(
                rule="length_limit",
                severity="warning",
                message=f"输入过长 ({len(current_text)} > {self.max_length})，已截断",
                original=f"len={len(current_text)}",
            ))
            current_text = current_text[:self.max_length]

        # ── 1.5. Unicode 归一化 (NFKC) + 零宽字符移除 ──────────
        normalized = unicodedata.normalize("NFKC", current_text)
        normalized = _RE_ZERO_WIDTH.sub("", normalized)

        # ── 2. 注入攻击检测 ──────────────────────────────────────
        if self.enable_injection_check:
            for pattern in _RE_INJECTION:
                match = pattern.search(normalized)
                if match:
                    hits.append(GuardHit(
                        rule="injection_attack",
                        severity="block",
                        message=f"检测到可能的提示词注入攻击",
                        original=match.group()[:50],
                    ))
                    logger.warning(
                        f"[InputGuard] injection detected: pattern={pattern.pattern} "
                        f"match='{match.group()[:50]}'"
                    )
                    return GuardResult(
                        passed=False,
                        blocked_reason="检测到不安全的输入内容，请修改后重试",
                        hits=hits,
                    )

        # ── 3. 敏感词检测 ────────────────────────────────────────
        if self.enable_sensitive_check:
            text_lower = normalized.lower()
            for term in _SENSITIVE_TERMS:
                if term.lower() in text_lower:
                    hits.append(GuardHit(
                        rule="sensitive_term",
                        severity="block",
                        message=f"输入包含内部敏感术语",
                        original=term,
                    ))
                    logger.warning(f"[InputGuard] sensitive term detected: {term}")
                    return GuardResult(
                        passed=False,
                        blocked_reason="输入包含受限内容，请修改后重试",
                        hits=hits,
                    )

        # ── 4. PII 检测与脱敏 ────────────────────────────────────
        current_text, pii_hits = self._handle_pii(current_text)
        hits.extend(pii_hits)

        # 如果 PII 策略是 block 且发现了 PII
        if self.pii_action == "block" and pii_hits:
            return GuardResult(
                passed=False,
                blocked_reason="输入包含个人敏感信息，请去除后重试",
                hits=hits,
            )

        return GuardResult(
            passed=True,
            sanitized_text=current_text,
            hits=hits,
        )

    def _handle_pii(self, text: str) -> tuple[str, List[GuardHit]]:
        """检测并脱敏 PII 信息"""
        hits: List[GuardHit] = []
        result = text

        # 手机号 → 138****1234
        for match in _RE_PHONE.finditer(result):
            phone = match.group()
            hits.append(GuardHit(
                rule="pii_phone",
                severity="info",
                message="检测到手机号，已脱敏",
                original=phone[:3] + "****" + phone[-4:],
            ))
        result = _RE_PHONE.sub(lambda m: m.group()[:3] + "****" + m.group()[-4:], result)

        # 身份证 → 110101****1234
        for match in _RE_ID_CARD.finditer(result):
            card = match.group()
            hits.append(GuardHit(
                rule="pii_id_card",
                severity="warning",
                message="检测到身份证号，已脱敏",
                original=card[:6] + "****" + card[-4:],
            ))
        result = _RE_ID_CARD.sub(lambda m: m.group()[:6] + "****" + m.group()[-4:], result)

        # 银行卡两阶段过滤：
        #   1. 文本里必须含上下文关键词（银行卡/卡号/bank card 等）
        #   2. 候选数字串必须通过 Luhn 校验
        # 任一条件不满足则保留原文，避免误伤订单号/流水号/序列号等正常业务数字
        text_lower = result.lower()
        has_bank_ctx = any(kw in text_lower for kw in _BANK_CARD_CONTEXT_WORDS)

        if has_bank_ctx:
            def _mask_if_bank(m: "re.Match[str]") -> str:
                card = m.group()
                if not _luhn_check(card):
                    return card
                hits.append(GuardHit(
                    rule="pii_bank_card",
                    severity="warning",
                    message="检测到银行卡号，已脱敏",
                    original=card[:4] + "****" + card[-4:],
                ))
                return card[:4] + "****" + card[-4:]

            result = _RE_BANK_CARD_CANDIDATE.sub(_mask_if_bank, result)

        # 邮箱 → u***@example.com
        for match in _RE_EMAIL.finditer(result):
            email = match.group()
            at_pos = email.index("@")
            masked = email[0] + "***" + email[at_pos:]
            hits.append(GuardHit(
                rule="pii_email",
                severity="info",
                message="检测到邮箱，已脱敏",
                original=masked,
            ))
        result = _RE_EMAIL.sub(
            lambda m: m.group()[0] + "***" + m.group()[m.group().index("@"):],
            result,
        )

        return result, hits


# ── 全局单例 ──────────────────────────────────────────────────────

input_guard = InputGuard()
