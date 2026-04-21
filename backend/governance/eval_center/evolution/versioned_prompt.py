# -*- coding: utf-8 -*-
"""backend/governance/eval_center/evolution/versioned_prompt.py — Prompt 版本管理

参考 OpenAI Cookbook Self-Evolving Agents 的 VersionedPrompt 设计：
  - 每个版本带版本号 + 时间戳 + eval_id + 分数
  - 支持 update / current / revert / select_best
  - 持久化到 eval_prompt_versions 表
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from loguru import logger


class PromptVersionEntry(BaseModel):
    """单个 prompt 版本"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str
    version: int = Field(ge=0)
    prompt_text: str = Field(min_length=1)
    model_name: str = "qwen3.5-plus-2026-02-15"
    eval_id: Optional[str] = None
    avg_score: Optional[float] = None
    grader_scores: Optional[Dict[str, float]] = None
    status: str = "draft"  # draft/testing/approved/active/rolled_back
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VersionedPrompt:
    """Prompt 版本管理器

    管理某个 Skill 的 prompt 版本历史，支持：
      - update(): 创建新版本
      - current(): 获取当前版本
      - revert_to(): 回滚到指定版本
      - select_best(): 选择历史最高分版本
      - save() / load(): 持久化到 DB
    """

    def __init__(
        self,
        skill_name: str,
        initial_prompt: str,
        model_name: str = "qwen3.5-plus-2026-02-15",
    ):
        self.skill_name = skill_name
        self._versions: List[PromptVersionEntry] = []

        first = PromptVersionEntry(
            skill_name=skill_name,
            version=0,
            prompt_text=initial_prompt,
            model_name=model_name,
            status="active",
        )
        self._versions.append(first)

    def current(self) -> PromptVersionEntry:
        """获取当前（最新）版本"""
        return self._versions[-1]

    def update(
        self,
        new_prompt: str,
        model_name: Optional[str] = None,
        eval_id: Optional[str] = None,
        avg_score: Optional[float] = None,
        grader_scores: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptVersionEntry:
        """创建新版本"""
        new_version = self.current().version + 1
        entry = PromptVersionEntry(
            skill_name=self.skill_name,
            version=new_version,
            prompt_text=new_prompt,
            model_name=model_name or self.current().model_name,
            eval_id=eval_id,
            avg_score=avg_score,
            grader_scores=grader_scores,
            status="testing",
            metadata=metadata,
        )
        self._versions.append(entry)
        logger.info(f"[VersionedPrompt] {self.skill_name}: v{new_version} 已创建 (score={avg_score})")
        return entry

    def revert_to(self, version: int) -> PromptVersionEntry:
        """回滚到指定版本"""
        target = None
        for v in self._versions:
            if v.version == version:
                target = v
                break

        if target is None:
            raise ValueError(f"版本 {version} 不存在")

        # 将当前版本标记为 rolled_back
        self.current().status = "rolled_back"

        # 基于目标版本创建新版本
        new_entry = self.update(
            new_prompt=target.prompt_text,
            model_name=target.model_name,
            metadata={"reverted_from": self.current().version, "reverted_to": version},
        )
        new_entry.status = "active"
        logger.info(f"[VersionedPrompt] {self.skill_name}: 回滚到 v{version}, 新版本 v{new_entry.version}")
        return new_entry

    def select_best(self) -> PromptVersionEntry:
        """选择历史最高分版本"""
        scored = [v for v in self._versions if v.avg_score is not None]
        if not scored:
            return self.current()
        return max(scored, key=lambda v: (v.avg_score, v.version))

    def history(self) -> List[PromptVersionEntry]:
        """获取所有版本（按版本号排序）"""
        return sorted(self._versions, key=lambda v: v.version)

    @property
    def version_count(self) -> int:
        return len(self._versions)

    def save_to_db(self, db) -> None:
        """持久化所有未保存的版本到 eval_prompt_versions 表"""
        import sqlalchemy

        for entry in self._versions:
            db.execute(sqlalchemy.text("""
                INSERT IGNORE INTO eval_prompt_versions
                    (id, skill_name, version, prompt_text, model_name,
                     eval_id, avg_score, grader_scores, status, metadata, created_at)
                VALUES
                    (:id, :skill, :ver, :prompt, :model,
                     :eval_id, :score, :grader_scores, :status, :meta, :created)
            """), {
                "id": entry.id,
                "skill": entry.skill_name,
                "ver": entry.version,
                "prompt": entry.prompt_text,
                "model": entry.model_name,
                "eval_id": entry.eval_id,
                "score": entry.avg_score,
                "grader_scores": json.dumps(entry.grader_scores, ensure_ascii=False) if entry.grader_scores else None,
                "status": entry.status,
                "meta": json.dumps(entry.metadata, ensure_ascii=False) if entry.metadata else None,
                "created": entry.created_at,
            })
        db.commit()
        logger.info(f"[VersionedPrompt] {self.skill_name}: {len(self._versions)} 个版本已保存")

    @classmethod
    def load_from_db(cls, skill_name: str, db) -> Optional["VersionedPrompt"]:
        """从 DB 加载已有版本历史"""
        import sqlalchemy

        rows = db.execute(sqlalchemy.text(
            "SELECT * FROM eval_prompt_versions WHERE skill_name = :name ORDER BY version"
        ), {"name": skill_name}).fetchall()

        if not rows:
            return None

        rows = [dict(r._mapping) for r in rows]
        first = rows[0]

        vp = cls.__new__(cls)
        vp.skill_name = skill_name
        vp._versions = []

        for r in rows:
            grader_scores = r.get("grader_scores")
            if isinstance(grader_scores, str):
                grader_scores = json.loads(grader_scores)

            metadata = r.get("metadata")
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            entry = PromptVersionEntry(
                id=r["id"],
                skill_name=r["skill_name"],
                version=r["version"],
                prompt_text=r["prompt_text"],
                model_name=r.get("model_name", ""),
                eval_id=r.get("eval_id"),
                avg_score=float(r["avg_score"]) if r.get("avg_score") is not None else None,
                grader_scores=grader_scores,
                status=r.get("status", "draft"),
                approved_by=r.get("approved_by"),
                approved_at=r.get("approved_at"),
                metadata=metadata,
                created_at=r.get("created_at", datetime.utcnow()),
            )
            vp._versions.append(entry)

        return vp
