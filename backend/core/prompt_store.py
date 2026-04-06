# -*- coding: utf-8 -*-
"""backend/core/prompt_store.py — 统一 Prompt 注册中心 (R6-4)

设计目标:
  1. 所有 prompt（Agent / Skill / Workflow）统一放入 PromptStore 管理
  2. 支持版本化: 同一 key 可以有 v1/v2/v3 多版本
  3. 支持灰度: 按 user_id hash 路由到指定版本（v1 占 70% / v2 占 30%）
  4. 支持审计: 每次 render 发 PROMPT_USED 遥测事件, 可在 /admin 查询
  5. 加载源:
     - copilot_rules 表（DB）
     - backend/governance/prompt_center/ 目录 YAML
     - Skill.summarization_hint 属性

不做的事（留给后续迭代）:
  - 编译时模板校验（Jinja2 语法检查）
  - 热更新（现阶段重启 app 才能生效）
  - 分布式一致性（所有 worker 独立加载）

YAML 格式示例:
    # backend/governance/prompt_center/agent/openclaw/respond.v1.yaml
    key: agent.openclaw.respond
    version: v1
    variables: [user_question, tool_result]
    content: |
      你是 OpenClaw 客服助手...
      用户问题: {user_question}
      工具结果: {tool_result}
    metadata:
      description: OpenClaw Agent 回答模板
      tags: [agent, openclaw]

API:
    ps = PromptStore()
    ps.load_from_yaml_dir(Path("backend/governance/prompt_center"))
    ps.load_from_db(sync_db_session)
    ps.load_from_skill_registry(registry)

    # 渲染（按 user_id 灰度，自动选版本）
    rendered = ps.render(
        key="agent.openclaw.respond",
        variables={"user_question": "...", "tool_result": "..."},
        user_id="u123",
    )

    # 强制指定版本
    rendered = ps.render(key="...", version="v2", variables={...})
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── 数据结构 ────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptTemplate:
    """单个 prompt 版本的不可变描述。"""
    key: str
    version: str
    content: str
    variables: List[str] = field(default_factory=list)
    source: str = "unknown"      # yaml / db / skill / inline
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GrayscaleRule:
    """灰度规则: 按 user_id hash % 100 < percent 则走目标版本。

    多规则按顺序评估，首次命中即返回。
    """
    key: str            # prompt key
    target_version: str
    percent: int = 100  # 0..100
    description: str = ""


# ── PromptStore ────────────────────────────────────────────────

class PromptStore:
    """prompt 统一注册中心。

    线程安全:
      - register / load_from_* 应在启动阶段完成（lifespan 内），之后视为只读
      - render 是只读操作，线程安全
    """

    def __init__(self):
        # key → version → PromptTemplate
        self._templates: Dict[str, Dict[str, PromptTemplate]] = {}
        # key → 默认版本（通常是最新注册的）
        self._default_version: Dict[str, str] = {}
        # 灰度规则列表
        self._gray_rules: List[GrayscaleRule] = []

    # ── 注册 ──────────────────────────────────────────────

    def register(self, template: PromptTemplate, set_as_default: bool = True) -> None:
        """注册一个 prompt 模板（按 key + version 唯一）。"""
        if not template.key or not template.version:
            raise ValueError("PromptTemplate 需要非空 key 和 version")
        versions = self._templates.setdefault(template.key, {})
        if template.version in versions:
            logger.warning(
                f"[PromptStore] overwriting {template.key}@{template.version} "
                f"(old source={versions[template.version].source})"
            )
        versions[template.version] = template
        if set_as_default:
            self._default_version[template.key] = template.version

    def add_gray_rule(self, rule: GrayscaleRule) -> None:
        if not 0 <= rule.percent <= 100:
            raise ValueError(f"percent must be in [0,100], got {rule.percent}")
        self._gray_rules.append(rule)

    # ── 查询 ──────────────────────────────────────────────

    def get(self, key: str, version: Optional[str] = None) -> Optional[PromptTemplate]:
        """按 key + version 查找模板。version=None 时用默认版本。"""
        versions = self._templates.get(key)
        if not versions:
            return None
        if version is None:
            version = self._default_version.get(key)
            if version is None:
                # 兜底：取字典中任一版本（稳定顺序）
                version = sorted(versions.keys())[0]
        return versions.get(version)

    def list_keys(self) -> List[str]:
        return sorted(self._templates.keys())

    def list_versions(self, key: str) -> List[str]:
        return sorted(self._templates.get(key, {}).keys())

    def resolve_version(
        self, key: str, user_id: Optional[str] = None
    ) -> Optional[str]:
        """按灰度规则决定给 user_id 返回哪个版本。

        算法:
          1. 遍历 key 匹配的 gray rule
          2. 计算 user_id 的稳定 hash % 100
          3. 落入 [0, percent) 区间 → 命中该规则的 target_version
          4. 未命中任何规则 → 返回默认版本
        """
        if not user_id:
            return self._default_version.get(key)

        hash_bucket = int(hashlib.md5(user_id.encode("utf-8")).hexdigest()[:8], 16) % 100

        for rule in self._gray_rules:
            if rule.key != key:
                continue
            if hash_bucket < rule.percent:
                return rule.target_version

        return self._default_version.get(key)

    # ── 渲染 ──────────────────────────────────────────────

    def render(
        self,
        key: str,
        variables: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """渲染 prompt 并发 PROMPT_USED 遥测。

        Args:
            key:       prompt key
            variables: {var_name: value} 字典；简单 str.replace("{name}", str(value))
            version:   强制指定版本；None 则走灰度路由
            user_id:   用于灰度分桶

        Returns:
            渲染后的字符串

        Raises:
            KeyError: key / version 不存在
        """
        if version is None:
            version = self.resolve_version(key, user_id=user_id)

        template = self.get(key, version=version)
        if template is None:
            raise KeyError(
                f"Prompt not found: key='{key}' version='{version}' "
                f"(available keys: {self.list_keys()[:20]})"
            )

        rendered = template.content
        for k, v in (variables or {}).items():
            rendered = rendered.replace("{" + k + "}", str(v))

        # Telemetry（best-effort）
        try:
            from backend.core.telemetry import telemetry, TelemetryEventType
            telemetry.emit(TelemetryEventType.PROMPT_USED, {
                "key": key,
                "version": template.version,
                "source": template.source,
                "user_id": user_id or "",
                "variables": list((variables or {}).keys()),
            }, component="PromptStore")
        except Exception as e:
            logger.debug(f"[PromptStore] telemetry emit failed: {e}")

        return rendered

    # ── 加载器 ────────────────────────────────────────────

    def load_from_yaml_dir(self, directory: Path) -> int:
        """递归扫描目录加载所有 .yaml / .yml 文件。

        Returns:
            本次加载成功的模板数量
        """
        try:
            import yaml  # type: ignore
        except ImportError:
            logger.warning("[PromptStore] PyYAML not installed, skipping YAML load")
            return 0

        if not directory.exists():
            logger.info(f"[PromptStore] YAML dir does not exist, skipping: {directory}")
            return 0

        count = 0
        for yaml_file in directory.rglob("*.y*ml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    logger.warning(f"[PromptStore] {yaml_file}: not a dict, skipping")
                    continue
                template = PromptTemplate(
                    key=data["key"],
                    version=str(data["version"]),
                    content=data["content"],
                    variables=list(data.get("variables") or []),
                    source=f"yaml:{yaml_file.name}",
                    metadata=dict(data.get("metadata") or {}),
                )
                self.register(template, set_as_default=True)
                count += 1
            except KeyError as ke:
                logger.warning(f"[PromptStore] {yaml_file}: missing field {ke}, skipping")
            except Exception as e:
                logger.warning(f"[PromptStore] {yaml_file}: load failed ({e}), skipping")

        logger.info(f"[PromptStore] loaded {count} templates from {directory}")
        return count

    def load_from_db(self, db: "Session") -> int:
        """从 copilot_rules 表加载静态规则作为 prompt。

        映射关系:
          - key = f"rule.{scope}.{normalized_title}"
          - version = "db-{id}" (允许同一 title 有历史版本)
          - source = "db"
        """
        try:
            from backend.models.copilot import CopilotRule
        except Exception as e:
            logger.warning(f"[PromptStore] CopilotRule import failed: {e}")
            return 0

        count = 0
        try:
            rows = db.query(CopilotRule).filter(CopilotRule.is_active.is_(True)).all()
        except Exception as e:
            logger.warning(f"[PromptStore] query copilot_rules failed: {e}")
            return 0

        for row in rows:
            try:
                normalized = (row.title or "").strip().lower().replace(" ", "_")[:64]
                template = PromptTemplate(
                    key=f"rule.{row.scope}.{normalized}",
                    version=f"db-{row.id}",
                    content=row.content or "",
                    source="db",
                    metadata={
                        "title": row.title,
                        "scope": row.scope,
                        "priority": row.priority,
                        "created_by": row.created_by,
                    },
                )
                self.register(template, set_as_default=True)
                count += 1
            except Exception as e:
                logger.warning(f"[PromptStore] rule id={row.id} register failed: {e}")

        logger.info(f"[PromptStore] loaded {count} templates from copilot_rules")
        return count

    def load_from_skill_registry(self, registry: Any) -> int:
        """从 SkillRegistry 的每个 skill 读取 summarization_hint 注册为 prompt。

        映射:
          - key = f"skill.{skill.name}.summarization_hint"
          - version = "v1"
          - source = "skill"
        """
        count = 0
        try:
            skills = registry.all_skills() if hasattr(registry, "all_skills") else {}
        except Exception:
            skills = {}

        for name, skill in skills.items():
            hint = getattr(skill, "summarization_hint", "") or ""
            if not hint:
                continue
            try:
                template = PromptTemplate(
                    key=f"skill.{name}.summarization_hint",
                    version="v1",
                    content=hint,
                    source="skill",
                    metadata={"display_name": getattr(skill, "display_name", "")},
                )
                self.register(template, set_as_default=True)
                count += 1
            except Exception as e:
                logger.warning(f"[PromptStore] skill={name} hint register failed: {e}")

        logger.info(f"[PromptStore] loaded {count} summarization_hints from SkillRegistry")
        return count

    # ── 调试 / 观测 ────────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """返回 store 当前状态摘要（供 /admin/prompt-store 路由使用）。"""
        total_templates = sum(len(vs) for vs in self._templates.values())
        by_source: Dict[str, int] = {}
        for versions in self._templates.values():
            for tpl in versions.values():
                src = tpl.source.split(":", 1)[0]
                by_source[src] = by_source.get(src, 0) + 1
        return {
            "total_keys": len(self._templates),
            "total_templates": total_templates,
            "by_source": by_source,
            "gray_rules": len(self._gray_rules),
        }


# ── 默认单例 ──────────────────────────────────────────────
prompt_store = PromptStore()
