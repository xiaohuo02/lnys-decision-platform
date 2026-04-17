# -*- coding: utf-8 -*-
"""backend/copilot/registry.py — Skill 注册表

单例模式管理所有已注册 Skill。
支持自动发现 skills/ 目录下的 Skill 类并注册。
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from backend.copilot.base_skill import BaseCopilotSkill


class SkillRegistry:
    """Copilot Skill 注册表"""

    _instance: Optional["SkillRegistry"] = None

    def __init__(self):
        self._skills: Dict[str, BaseCopilotSkill] = {}

    @classmethod
    def instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, skill: BaseCopilotSkill) -> None:
        """注册一个 Skill 实例"""
        if not skill.name:
            raise ValueError(f"Skill {skill.__class__.__name__} 缺少 name 属性")
        if skill.name in self._skills:
            logger.warning(f"[SkillRegistry] Skill '{skill.name}' 已存在，将被覆盖")
        self._skills[skill.name] = skill
        logger.info(f"[SkillRegistry] ✅ 注册: {skill.name} ({skill.display_name})")

    def get(self, name: str) -> Optional[BaseCopilotSkill]:
        return self._skills.get(name)

    def get_available_skills(
        self, mode: str, user_role: str, allowed_set: Optional[Set[str]] = None
    ) -> List[BaseCopilotSkill]:
        """获取在指定模式和角色下可用的 Skill 列表"""
        result = []
        for skill in self._skills.values():
            if not skill.is_available(mode, user_role):
                continue
            if allowed_set is not None and skill.name not in allowed_set:
                continue
            result.append(skill)
        return result

    def get_function_schemas(
        self, mode: str, user_role: str, allowed_set: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """获取可用 Skill 的 Function Calling schema 列表"""
        skills = self.get_available_skills(mode, user_role, allowed_set)
        return [s.to_function_schema() for s in skills]

    def all_skills(self) -> Dict[str, BaseCopilotSkill]:
        return dict(self._skills)

    @property
    def count(self) -> int:
        return len(self._skills)

    def auto_discover(self) -> int:
        """自动发现并注册 backend/copilot/skills/ 目录下所有 Skill

        Returns:
            本次新发现并注册的 Skill 数量（不含已注册的）
        """
        skills_dir = Path(__file__).parent / "skills"
        if not skills_dir.exists():
            logger.warning(f"[SkillRegistry] skills 目录不存在: {skills_dir}")
            return 0

        package_name = "backend.copilot.skills"
        discovered = 0

        for importer, modname, ispkg in pkgutil.iter_modules([str(skills_dir)]):
            if modname.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"{package_name}.{modname}")
                # 查找模块中所有 BaseCopilotSkill 子类的实例
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, BaseCopilotSkill)
                        and attr.name
                        and attr.name not in self._skills
                    ):
                        self.register(attr)
                        discovered += 1
            except Exception as e:
                logger.warning(f"[SkillRegistry] 加载 {modname} 失败: {e}")

        logger.info(f"[SkillRegistry] 自动发现完成: {discovered} 个新 Skill，总计 {self.count} 个")
        return discovered
