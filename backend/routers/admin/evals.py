# -*- coding: utf-8 -*-
"""backend/routers/admin/evals.py

管理后台：Eval Center API
GET  /admin/evals/datasets             → 数据集列表
POST /admin/evals/datasets             → 创建数据集
GET  /admin/evals/evaluators           → Evaluator 列表
POST /admin/evals/evaluators           → 创建 Evaluator
POST /admin/evals/experiments          → 创建评测实验
GET  /admin/evals/experiments/{id}     → 实验详情 + 结果
POST /admin/evals/experiments/{id}/run → 触发实验（stub）
POST /admin/evals/online-samples/import → 线上抽样导入
"""
import json
import uuid
from typing import Any, Dict, List, Optional

import sqlalchemy
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db, SessionLocal
from backend.core.exceptions import AppError
from backend.middleware.auth import admin_user, CurrentUser
from backend.governance.trace_center.audit import async_write_audit_log

router = APIRouter(tags=["admin-evals"])


class DatasetBody(BaseModel):
    name:        str
    description: Optional[str] = None
    task_type:   str


class EvaluatorBody(BaseModel):
    name:          str
    description:   Optional[str] = None
    task_type:     str
    scoring_rules: Dict[str, Any]


class ExperimentBody(BaseModel):
    name:           str
    dataset_id:     str
    evaluator_id:   str
    target_type:    Optional[str] = None
    target_id:      Optional[str] = None
    target_version: Optional[str] = None


class OnlineSampleBody(BaseModel):
    import_batch:   str
    samples:        List[Dict[str, Any]]
    source_note:    Optional[str] = None


# ── 数据集 ─────────────────────────────────────────────────────────

@router.get("/evals/datasets")
async def admin_list_datasets(limit: int = 50, offset: int = 0, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT dataset_id, name, task_type, item_count, created_by, created_at "
        "FROM eval_datasets ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), {"l": limit, "o": offset})
    rows = result.fetchall()
    total_r = await db.execute(sqlalchemy.text("SELECT COUNT(*) FROM eval_datasets"))
    total = total_r.scalar() or 0
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/evals/datasets/{dataset_id}")
async def admin_get_dataset(dataset_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM eval_datasets WHERE dataset_id = :id"
    ), {"id": dataset_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"dataset_id={dataset_id} 不存在")
    ds = dict(row._mapping)
    result2 = await db.execute(sqlalchemy.text(
        "SELECT case_id, input_json, expected_json, tags, created_at "
        "FROM eval_cases WHERE dataset_id = :id ORDER BY created_at LIMIT 50"
    ), {"id": dataset_id})
    ds["cases"] = [dict(r._mapping) for r in result2.fetchall()]
    return ds


@router.post("/evals/datasets")
async def admin_create_dataset(body: DatasetBody, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    did = str(uuid.uuid4())
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO eval_datasets (dataset_id, name, description, task_type, created_by)
            VALUES (:did, :name, :desc, :task_type, :created_by)
        """), {"did": did, "name": body.name, "desc": body.description,
               "task_type": body.task_type, "created_by": user.username})
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, f"数据集名称 '{body.name}' 已存在")
    await async_write_audit_log(
        db, operator=user.username, action="create_dataset",
        target_type="eval_dataset", target_id=did,
        after={"name": body.name, "task_type": body.task_type},
    )
    return {"dataset_id": did, "status": "created"}


# ── Evaluator ─────────────────────────────────────────────────────

@router.get("/evals/evaluators")
async def admin_list_evaluators(limit: int = 50, offset: int = 0, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT evaluator_id, name, task_type, scoring_rules, version, created_by, created_at "
        "FROM evaluators ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), {"l": limit, "o": offset})
    rows = result.fetchall()
    total_r = await db.execute(sqlalchemy.text("SELECT COUNT(*) FROM evaluators"))
    total = total_r.scalar() or 0
    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.get("/evals/evaluators/{evaluator_id}")
async def admin_get_evaluator(evaluator_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM evaluators WHERE evaluator_id = :id"
    ), {"id": evaluator_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"evaluator_id={evaluator_id} 不存在")
    return dict(row._mapping)


@router.post("/evals/evaluators")
async def admin_create_evaluator(body: EvaluatorBody, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    eid = str(uuid.uuid4())
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO evaluators (evaluator_id, name, description, task_type, scoring_rules, created_by)
            VALUES (:eid, :name, :desc, :task_type, :rules, :created_by)
        """), {"eid": eid, "name": body.name, "desc": body.description,
               "task_type": body.task_type,
               "rules": json.dumps(body.scoring_rules, ensure_ascii=False),
               "created_by": user.username})
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, f"评测器名称 '{body.name}' 已存在")
    await async_write_audit_log(
        db, operator=user.username, action="create_evaluator",
        target_type="evaluator", target_id=eid,
        after={"name": body.name, "task_type": body.task_type},
    )
    return {"evaluator_id": eid, "status": "created"}


# ── 实验 ───────────────────────────────────────────────────────────

@router.get("/evals/experiments")
async def admin_list_experiments(
    status:     Optional[str] = None,
    agent_name: Optional[str] = None,
    limit:      int = 50,
    offset:     int = 0,
    user:       CurrentUser = Depends(admin_user),
    db:         AsyncSession = Depends(get_async_db),
):
    conditions = ["1=1"]
    params: Dict[str, Any] = {"l": limit, "o": offset}
    if status:
        conditions.append("status = :status"); params["status"] = status
    if agent_name:
        conditions.append("target_id = :agent_name"); params["agent_name"] = agent_name
    where = " AND ".join(conditions)
    result = await db.execute(sqlalchemy.text(
        f"SELECT experiment_id, name, COALESCE(agent_name, target_id) AS agent_name, dataset_id, evaluator_id, "
        f"status, total_cases, pass_rate, created_by, created_at "
        f"FROM eval_experiments WHERE {where} ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), params)
    rows = result.fetchall()
    total_result = await db.execute(sqlalchemy.text(
        f"SELECT COUNT(*) FROM eval_experiments WHERE {where}"
    ), {k: v for k, v in params.items() if k not in ("l", "o")})
    total_row = total_result.fetchone()
    return {"items": [dict(r._mapping) for r in rows], "total": int(total_row[0] or 0)}


@router.post("/evals/experiments")
async def admin_create_experiment(body: ExperimentBody, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT 1 FROM eval_datasets WHERE dataset_id = :id"
    ), {"id": body.dataset_id})
    if result.fetchone() is None:
        raise AppError(404, f"dataset_id='{body.dataset_id}' 不存在")

    result2 = await db.execute(sqlalchemy.text(
        "SELECT 1 FROM evaluators WHERE evaluator_id = :id"
    ), {"id": body.evaluator_id})
    if result2.fetchone() is None:
        raise AppError(404, f"evaluator_id='{body.evaluator_id}' 不存在")

    exp_id = str(uuid.uuid4())
    try:
        await db.execute(sqlalchemy.text("""
            INSERT INTO eval_experiments
                (experiment_id, name, dataset_id, evaluator_id,
                 target_type, target_id, target_version, status, created_by)
            VALUES
                (:eid, :name, :did, :vid, :ttype, :tid, :tver, 'pending', :created_by)
        """), {"eid": exp_id, "name": body.name, "did": body.dataset_id,
               "vid": body.evaluator_id, "ttype": body.target_type,
               "tid": body.target_id, "tver": body.target_version,
               "created_by": user.username})
        await db.commit()
    except sqlalchemy.exc.IntegrityError:
        await db.rollback()
        raise AppError(409, "创建实验失败：数据完整性冲突，请检查参数")
    await async_write_audit_log(
        db, operator=user.username, action="create_experiment",
        target_type="eval_experiment", target_id=exp_id,
        after={"name": body.name, "dataset_id": body.dataset_id, "evaluator_id": body.evaluator_id},
    )
    return {"experiment_id": exp_id, "status": "pending"}


@router.get("/evals/experiments/{experiment_id}")
async def admin_get_experiment(experiment_id: str, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM eval_experiments WHERE experiment_id = :id"
    ), {"id": experiment_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"experiment_id={experiment_id} 不存在")
    exp = dict(row._mapping)
    result2 = await db.execute(sqlalchemy.text(
        "SELECT id, case_id, score, passed, detail_json, created_at FROM eval_results "
        "WHERE experiment_id = :id ORDER BY id LIMIT 100"
    ), {"id": experiment_id})
    exp["results"] = [dict(r._mapping) for r in result2.fetchall()]
    exp["result_count"] = len(exp["results"])
    return exp


@router.post("/evals/experiments/{experiment_id}/run")
async def admin_run_experiment(experiment_id: str, request: Request, user: CurrentUser = Depends(admin_user)):
    """触发评测实验 — 调用 eval_service 真实执行评测"""
    from backend.governance.eval_center.eval_service import run_experiment
    app_state = request.app.state if hasattr(request, "app") else None
    try:
        sync_db = SessionLocal()
        try:
            result = await run_in_threadpool(run_experiment, experiment_id, sync_db, app_state)
        finally:
            sync_db.close()
        return result
    except ValueError as e:
        raise AppError(400, str(e))


# ── 线上抽样 ───────────────────────────────────────────────────────

@router.post("/evals/online-samples/import")
async def admin_import_online_samples(body: OnlineSampleBody, user: CurrentUser = Depends(admin_user), db: AsyncSession = Depends(get_async_db)):
    count = 0
    for sample in body.samples:
        await db.execute(sqlalchemy.text("""
            INSERT INTO eval_online_samples (import_batch, input_json, source_note)
            VALUES (:batch, :input_json, :note)
        """), {"batch": body.import_batch,
               "input_json": json.dumps(sample, ensure_ascii=False),
               "note": body.source_note})
        count += 1
    await db.commit()
    await async_write_audit_log(
        db, operator=user.username, action="import_online_samples",
        target_type="eval_online_samples", target_id=body.import_batch,
        after={"imported_count": count, "source_note": body.source_note},
    )
    return {"import_batch": body.import_batch, "imported_count": count}


# ══════════════════════════════════════════════════════════════════
# 自进化 / 爬山法 / 轨迹记忆 — 评测中心 V2 端点
# ══════════════════════════════════════════════════════════════════


class KarpathyLoopBody(BaseModel):
    agent_name:     str
    dataset_id:     str
    evaluator_id:   str
    metric_name:    str = "score"
    max_iterations: int = 5
    time_budget_s:  int = 600


class EvolutionBody(BaseModel):
    skill_name:   str
    dataset_id:   str
    max_retry:    int = 3


class TipQueryBody(BaseModel):
    task_description: str
    top_k:            int = 5
    method:           str = "cosine"  # cosine | llm | keyword


# ── Karpathy Loop（范式一：ML Agent 爬山法） ──────────────────

@router.post("/evals/karpathy-loop")
async def admin_start_karpathy_loop(
    body:    KarpathyLoopBody,
    request: Request,
    user:    CurrentUser = Depends(admin_user),
    db:      AsyncSession = Depends(get_async_db),
):
    """启动 Karpathy Loop 爬山法循环"""
    from backend.governance.eval_center.evolution.karpathy_loop import KarpathyLoop
    from backend.governance.eval_center.runners.ml_agent_runner import MLAgentRunner
    from backend.governance.eval_center.eval_service import build_graders

    # 读取 evaluator + 数据集
    evaluator_row = await db.execute(sqlalchemy.text(
        "SELECT scoring_rules FROM evaluators WHERE evaluator_id = :id"
    ), {"id": body.evaluator_id})
    evaluator = evaluator_row.fetchone()
    if evaluator is None:
        raise AppError(404, f"evaluator_id='{body.evaluator_id}' 不存在")

    scoring_rules = evaluator._mapping["scoring_rules"]
    if isinstance(scoring_rules, str):
        scoring_rules = json.loads(scoring_rules)
    graders = build_graders(scoring_rules)

    cases_rows = await db.execute(sqlalchemy.text(
        "SELECT case_id, input_json, expected_json FROM eval_cases "
        "WHERE dataset_id = :did ORDER BY created_at"
    ), {"did": body.dataset_id})
    golden_cases = []
    for r in cases_rows.fetchall():
        c = dict(r._mapping)
        inp = c["input_json"]
        exp = c["expected_json"]
        golden_cases.append({
            "case_id": c["case_id"],
            "input_json": json.loads(inp) if isinstance(inp, str) else inp,
            "expected_json": json.loads(exp) if isinstance(exp, str) else exp,
        })

    if not golden_cases:
        raise AppError(400, f"数据集 {body.dataset_id} 无用例")

    app_state = request.app.state if hasattr(request, "app") else None
    agent = getattr(app_state, body.agent_name, None) if app_state else None

    loop = KarpathyLoop(
        agent=agent,
        agent_name=body.agent_name,
        golden_cases=golden_cases,
        graders=graders,
        metric_name=body.metric_name,
        max_iterations=body.max_iterations,
        time_budget_s=body.time_budget_s,
    )

    result = await loop.run()
    return result.model_dump()


# ── Prompt Evolution（范式二：Skill 自进化） ──────────────────

@router.post("/evals/evolution")
async def admin_start_evolution(
    body: EvolutionBody,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """启动 Copilot Skill Prompt 自进化循环"""
    from backend.governance.eval_center.evolution.prompt_evolver import PromptEvolver
    from backend.copilot.registry import SkillRegistry

    skill = SkillRegistry.instance().get(body.skill_name)
    if skill is None:
        raise AppError(404, f"Skill '{body.skill_name}' 未找到")

    initial_prompt = getattr(skill, "system_prompt", "") or getattr(skill, "description", "")
    if not initial_prompt:
        raise AppError(400, f"Skill '{body.skill_name}' 无可用 prompt")

    cases_rows = await db.execute(sqlalchemy.text(
        "SELECT case_id, input_json, expected_json FROM eval_cases "
        "WHERE dataset_id = :did ORDER BY created_at"
    ), {"did": body.dataset_id})
    golden_cases = []
    for r in cases_rows.fetchall():
        c = dict(r._mapping)
        inp = c["input_json"]
        exp = c["expected_json"]
        golden_cases.append({
            "case_id": c["case_id"],
            "input_json": json.loads(inp) if isinstance(inp, str) else inp,
            "expected_json": json.loads(exp) if isinstance(exp, str) else exp,
        })

    if not golden_cases:
        raise AppError(400, f"数据集 {body.dataset_id} 无用例")

    # 构建 grader：优先用确定性 grader，避免依赖 LLM/Embedding 环境
    # 注意：不使用 KeyInfoRetentionGrader — 它在结构化 Skill 输出上无法有效评分
    from backend.governance.eval_center.graders.code_grader import (
        SchemaCheckGrader, KeywordMatchGrader, FieldMatchGrader,
    )
    evo_graders = [
        SchemaCheckGrader(pass_threshold=0.8),
        FieldMatchGrader(pass_threshold=0.6),
        KeywordMatchGrader(pass_threshold=0.5),
    ]

    evolver = PromptEvolver(
        skill_name=body.skill_name,
        initial_prompt=initial_prompt,
        golden_cases=golden_cases,
        graders=evo_graders,
        max_retry=body.max_retry,
    )

    result = await evolver.evolve()
    return result.model_dump()


# ── Prompt 版本管理 ───────────────────────────────────────────

@router.get("/evals/prompt-versions/{skill_name}")
async def admin_get_prompt_versions(
    skill_name: str,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """获取某 Skill 的 prompt 版本历史"""
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM eval_prompt_versions "
        "WHERE skill_name = :name ORDER BY version DESC LIMIT 50"
    ), {"name": skill_name})
    rows = result.fetchall()
    return {"items": [dict(r._mapping) for r in rows], "total": len(rows)}


@router.post("/evals/prompt-versions/{version_id}/approve")
async def admin_approve_prompt_version(
    version_id: str,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """审批通过某 prompt 版本"""
    from datetime import datetime
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM eval_prompt_versions WHERE id = :id"
    ), {"id": version_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"version_id='{version_id}' 不存在")

    await db.execute(sqlalchemy.text(
        "UPDATE eval_prompt_versions SET status='approved', "
        "approved_by=:user, approved_at=:now WHERE id=:id"
    ), {"user": user.username, "now": datetime.utcnow(), "id": version_id})
    await db.commit()

    await async_write_audit_log(
        db, operator=user.username, action="approve_prompt_version",
        target_type="eval_prompt_version", target_id=version_id,
        after={"status": "approved"},
    )
    return {"id": version_id, "status": "approved"}


@router.post("/evals/prompt-versions/{version_id}/rollback")
async def admin_rollback_prompt_version(
    version_id: str,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """回滚某 prompt 版本"""
    result = await db.execute(sqlalchemy.text(
        "SELECT skill_name, version FROM eval_prompt_versions WHERE id = :id"
    ), {"id": version_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"version_id='{version_id}' 不存在")

    r = dict(row._mapping)
    await db.execute(sqlalchemy.text(
        "UPDATE eval_prompt_versions SET status='rolled_back' WHERE id=:id"
    ), {"id": version_id})

    # 将上一个 approved 版本设为 active
    await db.execute(sqlalchemy.text(
        "UPDATE eval_prompt_versions SET status='active' "
        "WHERE skill_name=:name AND version < :ver AND status='approved' "
        "ORDER BY version DESC LIMIT 1"
    ), {"name": r["skill_name"], "ver": r["version"]})
    await db.commit()

    await async_write_audit_log(
        db, operator=user.username, action="rollback_prompt_version",
        target_type="eval_prompt_version", target_id=version_id,
        after={"status": "rolled_back"},
    )
    return {"id": version_id, "status": "rolled_back"}


# ── 轨迹记忆 Tips（范式三） ───────────────────────────────────

@router.get("/evals/tips")
async def admin_list_tips(
    tip_type:   Optional[str] = None,
    is_active:  Optional[int] = None,
    limit:      int = 50,
    offset:     int = 0,
    user:       CurrentUser = Depends(admin_user),
    db:         AsyncSession = Depends(get_async_db),
):
    """获取 Tips 列表"""
    conditions = ["1=1"]
    params: Dict[str, Any] = {"l": limit, "o": offset}
    if tip_type:
        conditions.append("tip_type = :tip_type")
        params["tip_type"] = tip_type
    if is_active is not None:
        conditions.append("is_active = :is_active")
        params["is_active"] = is_active
    where = " AND ".join(conditions)

    result = await db.execute(sqlalchemy.text(
        f"SELECT * FROM eval_agent_tips WHERE {where} "
        f"ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), params)
    rows = result.fetchall()

    total_r = await db.execute(sqlalchemy.text(
        f"SELECT COUNT(*) FROM eval_agent_tips WHERE {where}"
    ), {k: v for k, v in params.items() if k not in ("l", "o")})
    total = total_r.scalar() or 0

    return {"items": [dict(r._mapping) for r in rows], "total": total}


@router.post("/evals/tips/retrieve")
async def admin_retrieve_tips(
    body: TipQueryBody,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """根据任务描述检索相关 Tips"""
    from backend.governance.eval_center.memory.tip_retriever import TipRetriever

    retriever = TipRetriever(
        top_k=body.top_k,
        use_llm=(body.method == "llm"),
    )
    tips = await retriever.retrieve(
        task_description=body.task_description,
        db=db,
    )
    return {"tips": tips, "count": len(tips)}


@router.patch("/evals/tips/{tip_id}/toggle")
async def admin_toggle_tip(
    tip_id:    str,
    user:      CurrentUser = Depends(admin_user),
    db:        AsyncSession = Depends(get_async_db),
):
    """启用/禁用某条 Tip"""
    result = await db.execute(sqlalchemy.text(
        "SELECT is_active FROM eval_agent_tips WHERE tip_id = :id"
    ), {"id": tip_id})
    row = result.fetchone()
    if row is None:
        raise AppError(404, f"tip_id='{tip_id}' 不存在")

    new_val = 0 if row._mapping["is_active"] else 1
    await db.execute(sqlalchemy.text(
        "UPDATE eval_agent_tips SET is_active=:val WHERE tip_id=:id"
    ), {"val": new_val, "id": tip_id})
    await db.commit()
    return {"tip_id": tip_id, "is_active": bool(new_val)}


# ── Karpathy Loop 日志 ────────────────────────────────────────

@router.get("/evals/loop-log/{experiment_id}")
async def admin_get_loop_log(
    experiment_id: str,
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """获取 Karpathy Loop 某实验的迭代日志"""
    result = await db.execute(sqlalchemy.text(
        "SELECT * FROM eval_loop_log WHERE experiment_id = :eid ORDER BY iteration"
    ), {"eid": experiment_id})
    rows = result.fetchall()
    return {"items": [dict(r._mapping) for r in rows], "total": len(rows)}


# ── Tips 统计 ─────────────────────────────────────────────────

@router.get("/evals/tips/stats")
async def admin_tips_stats(
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """Tips 统计（按类型、活跃状态）"""
    result = await db.execute(sqlalchemy.text("""
        SELECT
            tip_type,
            COUNT(*) AS total,
            SUM(is_active) AS active,
            AVG(confidence) AS avg_confidence,
            SUM(reference_count) AS total_references
        FROM eval_agent_tips
        GROUP BY tip_type
    """))
    rows = result.fetchall()
    return {"stats": [dict(r._mapping) for r in rows]}


# ══════════════════════════════════════════════════════════════════
# Benchmark 综合面板 — 聚合评测指标供前端展示
# ══════════════════════════════════════════════════════════════════

@router.get("/evals/benchmark/summary")
async def admin_benchmark_summary(
    user: CurrentUser = Depends(admin_user),
    db:   AsyncSession = Depends(get_async_db),
):
    """Benchmark 综合面板:
    - 实验总览 (总数/运行中/通过/失败)
    - 按 agent_name 聚合 pass_rate
    - 最近 10 次实验趋势
    - 评测引擎 + Grader 使用分布
    """
    # 实验总览
    overview_result = await db.execute(sqlalchemy.text("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
            AVG(CASE WHEN pass_rate IS NOT NULL THEN pass_rate END) AS avg_pass_rate,
            SUM(total_cases) AS total_cases
        FROM eval_experiments
    """))
    overview = dict(overview_result.fetchone()._mapping)

    # 按 agent 聚合
    agent_result = await db.execute(sqlalchemy.text("""
        SELECT
            COALESCE(agent_name, target_id, 'unknown') AS agent,
            COUNT(*) AS experiments,
            AVG(CASE WHEN pass_rate IS NOT NULL THEN pass_rate END) AS avg_pass_rate,
            MAX(CASE WHEN pass_rate IS NOT NULL THEN pass_rate END) AS best_pass_rate,
            SUM(total_cases) AS total_cases
        FROM eval_experiments
        WHERE status = 'completed'
        GROUP BY COALESCE(agent_name, target_id, 'unknown')
        ORDER BY avg_pass_rate DESC
    """))
    agents = [dict(r._mapping) for r in agent_result.fetchall()]

    # 最近实验趋势
    trend_result = await db.execute(sqlalchemy.text("""
        SELECT experiment_id, name,
               COALESCE(agent_name, target_id) AS agent,
               pass_rate, total_cases, status, created_at
        FROM eval_experiments
        WHERE status IN ('completed', 'failed')
        ORDER BY created_at DESC
        LIMIT 20
    """))
    trend = [dict(r._mapping) for r in trend_result.fetchall()]

    # Grader / Evaluator 使用分布
    evaluator_result = await db.execute(sqlalchemy.text("""
        SELECT e.name, e.task_type, COUNT(x.experiment_id) AS usage_count
        FROM evaluators e
        LEFT JOIN eval_experiments x ON x.evaluator_id = e.evaluator_id
        GROUP BY e.evaluator_id, e.name, e.task_type
        ORDER BY usage_count DESC
        LIMIT 20
    """))
    evaluators = [dict(r._mapping) for r in evaluator_result.fetchall()]

    # Dataset 统计
    dataset_result = await db.execute(sqlalchemy.text("""
        SELECT d.name, d.task_type, d.item_count,
               COUNT(x.experiment_id) AS experiment_count
        FROM eval_datasets d
        LEFT JOIN eval_experiments x ON x.dataset_id = d.dataset_id
        GROUP BY d.dataset_id, d.name, d.task_type, d.item_count
        ORDER BY experiment_count DESC
        LIMIT 20
    """))
    datasets = [dict(r._mapping) for r in dataset_result.fetchall()]

    # Telemetry 交叉数据
    telemetry_data = {}
    try:
        from backend.core.telemetry import telemetry as tm
        s = tm.summary()
        telemetry_data = {
            "total_model_calls": s.model_calls,
            "total_skill_executions": s.skill_calls,
            "total_tokens": s.model_tokens_in + s.model_tokens_out,
        }
    except Exception:
        pass

    return {
        "ok": True,
        "data": {
            "overview": overview,
            "agents": agents,
            "trend": trend,
            "evaluators": evaluators,
            "datasets": datasets,
            "telemetry": telemetry_data,
        },
    }
