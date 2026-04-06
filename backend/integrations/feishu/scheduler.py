# -*- coding: utf-8 -*-
"""backend/integrations/feishu/scheduler.py — 主动巡检调度器

Copilot 主动巡检：
- 运维巡检（每30分钟）：扫描失败 Run、系统异常
- 运营巡检（每2小时）：库存预警、舆情负面飙升
- 记忆调和（每周一次）：清理过时记忆
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import sqlalchemy
from loguru import logger

from backend.copilot.agent_logger import patrol_logger


class CopilotPatrolScheduler:
    """Copilot 主动巡检调度器"""

    def __init__(self, feishu_bridge=None, engine=None):
        self._feishu = feishu_bridge
        self._engine = engine
        self._scheduler = None
        self._silenced_alerts: Dict[str, float] = {}  # alert_id → silence_until timestamp

    def start(self) -> None:
        """启动 APScheduler 调度"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler()

            # 运维巡检 — 每30分钟
            self._scheduler.add_job(
                self._patrol_ops,
                "interval", minutes=30,
                id="ops_patrol", name="运维巡检",
                max_instances=1,
            )

            # 运营巡检 — 每2小时
            self._scheduler.add_job(
                self._patrol_biz,
                "interval", hours=2,
                id="biz_patrol", name="运营巡检",
                max_instances=1,
            )

            # 记忆调和 — 每周一凌晨3点
            self._scheduler.add_job(
                self._reconcile_memory,
                "cron", day_of_week="mon", hour=3,
                id="memory_reconcile", name="记忆调和",
            )

            self._scheduler.start()
            patrol_logger.info("[PatrolScheduler] 巡检调度器已启动")

            # 启动确认：向 ops_alert 群发一条通知
            self._send_startup_notification()

        except ImportError:
            patrol_logger.warning(
                "[PatrolScheduler] apscheduler 未安装，跳过巡检。pip install apscheduler"
            )
        except Exception as e:
            patrol_logger.error(f"[PatrolScheduler] 启动失败: {e}")

    def _send_startup_notification(self) -> None:
        """启动时发一条确认消息，验证飞书推送通路"""
        if not self._feishu or not self._feishu.is_ready:
            patrol_logger.warning("[PatrolScheduler] 飞书未就绪，跳过启动通知")
            return
        chat_id = self._feishu._group_registry.get("ops_alert")
        if not chat_id:
            patrol_logger.warning("[PatrolScheduler] ops_alert 群未映射，跳过启动通知")
            return
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sent = self._feishu.send_text(
            chat_id,
            f"[Copilot] 巡检调度器已启动 ({now})\n"
            f"- 运维巡检: 每30分钟\n"
            f"- 运营巡检: 每2小时\n"
            f"- 记忆调和: 每周一 03:00"
        )
        if sent:
            patrol_logger.info("[PatrolScheduler] 启动通知已发送到 ops_alert 群")
        else:
            patrol_logger.error("[PatrolScheduler] 启动通知发送失败")

    def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            patrol_logger.info("[PatrolScheduler] 已关闭")

    # ── DB 写入辅助（fire-and-forget，失败不阻塞）─────────────────

    def _write_patrol_run(
        self, run_id: str, wf_name: str, status: str,
        input_summary: str, output_summary: str = "",
        error_message: str = "", latency_ms: int = 0,
    ) -> None:
        try:
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                db.execute(sqlalchemy.text("""
                    INSERT INTO runs
                        (run_id, thread_id, request_id, entrypoint, workflow_name,
                         status, triggered_by, input_summary, output_summary,
                         error_message, started_at, ended_at, latency_ms)
                    VALUES
                        (:rid, :tid, :rid, 'scheduler', :wf,
                         :st, 'scheduler', :inp, :out,
                         :err, NOW(), NOW(), :lat)
                    ON DUPLICATE KEY UPDATE
                        status=VALUES(status), output_summary=VALUES(output_summary),
                        error_message=VALUES(error_message), ended_at=VALUES(ended_at),
                        latency_ms=VALUES(latency_ms)
                """), {
                    "rid": run_id, "tid": f"patrol_{wf_name}",
                    "wf": wf_name, "st": status,
                    "inp": (input_summary or "")[:200],
                    "out": (output_summary or "")[:200],
                    "err": (error_message or "")[:500],
                    "lat": latency_ms,
                })
                db.commit()
            finally:
                db.close()
        except Exception as e:
            patrol_logger.warning(f"[patrol:db] write run failed (non-fatal): {e}")

    def _write_patrol_step(
        self, run_id: str, step_name: str, agent_name: str,
        status: str, input_summary: str, output_summary: str = "",
        error_message: str = "", latency_ms: int = 0,
    ) -> None:
        try:
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                db.execute(sqlalchemy.text("""
                    INSERT INTO run_steps
                        (step_id, run_id, step_type, step_name, agent_name,
                         status, input_summary, output_summary, error_message,
                         started_at, ended_at)
                    VALUES
                        (:sid, :rid, 'agent_call', :sn, :an,
                         :st, :inp, :out, :err, NOW(), NOW())
                """), {
                    "sid": str(uuid.uuid4()), "rid": run_id,
                    "sn": step_name, "an": agent_name,
                    "st": status,
                    "inp": (input_summary or "")[:200],
                    "out": (output_summary or "")[:200],
                    "err": (error_message or "")[:500],
                })
                db.commit()
            finally:
                db.close()
        except Exception as e:
            patrol_logger.warning(f"[patrol:db] write step failed (non-fatal): {e}")

    # ── 运维巡检 ──

    async def _patrol_ops(self) -> None:
        """运维巡检：检查系统健康"""
        patrol_logger.info("[patrol:ops] 开始运维巡检")
        run_id = str(uuid.uuid4())
        t0 = time.time()

        # 先写父记录，确保 run_steps FK 不会失败
        self._write_patrol_run(
            run_id, "patrol_ops",
            status="running",
            input_summary="运维巡检: system_skill",
        )

        checks = [
            {
                "skill": "system_skill",
                "question": "当前系统健康状态？",
                "alert_id": "ops_system_health",
                "is_anomaly": lambda r: r.get("status") != "healthy",
                "group": "ops_alert",
                "title": "系统健康异常",
            },
        ]

        has_anomaly = False
        anomaly_msgs = []
        for check in checks:
            result = await self._run_check("ops", check, run_id)
            if result and result.get("is_anomaly"):
                has_anomaly = True
                anomaly_msgs.append(result.get("message", ""))

        lat = int((time.time() - t0) * 1000)
        self._write_patrol_run(
            run_id, "patrol_ops",
            status="failed" if has_anomaly else "completed",
            input_summary="运维巡检: system_skill",
            output_summary="; ".join(anomaly_msgs) if anomaly_msgs else "正常",
            latency_ms=lat,
        )
        patrol_logger.info("[patrol:ops] 运维巡检完成")

    # ── 运营巡检 ──

    async def _patrol_biz(self) -> None:
        """运营巡检：库存预警、舆情负面飙升"""
        patrol_logger.info("[patrol:biz] 开始运营巡检")
        run_id = str(uuid.uuid4())
        t0 = time.time()

        # 先写父记录，确保 run_steps FK 不会失败
        self._write_patrol_run(
            run_id, "patrol_biz",
            status="running",
            input_summary="运营巡检: inventory_skill, sentiment_skill",
        )

        checks = [
            {
                "skill": "inventory_skill",
                "question": "有没有SKU库存低于安全水位？",
                "alert_id": "biz_inventory_urgent",
                "is_anomaly": lambda r: r.get("urgent_count", 0) > 0,
                "group": "procurement",
                "title": "库存预警",
                "format_msg": lambda r: (
                    f"库存预警: {r.get('urgent_count', 0)} 支SKU库存低于安全水位，"
                    f"建议补货总量 {r.get('total_reorder_qty', 0):,}"
                ),
            },
            {
                "skill": "sentiment_skill",
                "question": "当前负面舆情占比是否超过30%？",
                "alert_id": "biz_sentiment_negative",
                "is_anomaly": lambda r: r.get("negative_alert", False),
                "group": "biz_daily",
                "title": "舆情预警",
                "format_msg": lambda r: (
                    f"舆情负面占比 {r.get('negative_ratio', 0):.1%}，"
                    f"共 {r.get('total_reviews', 0)} 条评价"
                ),
            },
        ]

        has_anomaly = False
        anomaly_msgs = []
        for check in checks:
            result = await self._run_check("biz", check, run_id)
            if result and result.get("is_anomaly"):
                has_anomaly = True
                anomaly_msgs.append(result.get("message", ""))

        lat = int((time.time() - t0) * 1000)
        self._write_patrol_run(
            run_id, "patrol_biz",
            status="failed" if has_anomaly else "completed",
            input_summary="运营巡检: inventory_skill, sentiment_skill",
            output_summary="; ".join(anomaly_msgs) if anomaly_msgs else "正常",
            latency_ms=lat,
        )
        patrol_logger.info("[patrol:biz] 运营巡检完成")

    # ── 通用巡检执行器 ──

    async def _run_check(self, mode: str, check: Dict[str, Any], run_id: str = "") -> Optional[Dict[str, Any]]:
        """执行单个巡检项，返回 {is_anomaly, message} 或 None"""
        alert_id = check["alert_id"]
        t0 = time.time()

        # 检查是否被静默
        if self._is_silenced(alert_id):
            patrol_logger.debug(f"[patrol] {alert_id} 已静默，跳过")
            return None

        if self._engine is None:
            return None

        check_result: Optional[Dict[str, Any]] = None
        try:
            result = await self._engine.run_single_skill(
                skill_name=check["skill"],
                question=check["question"],
                mode=mode,
                user_role="system_patrol",
                source="scheduler",
            )

            is_anomaly_fn = check.get("is_anomaly", lambda r: False)
            is_anomaly = is_anomaly_fn(result)

            lat = int((time.time() - t0) * 1000)

            # 写 step
            if run_id:
                out_summary = json.dumps(result, ensure_ascii=False, default=str)[:200] if result else ""
                self._write_patrol_step(
                    run_id, step_name=alert_id, agent_name=check["skill"],
                    status="completed" if not is_anomaly else "failed",
                    input_summary=check["question"],
                    output_summary=out_summary,
                    latency_ms=lat,
                )

            if is_anomaly:
                group = check.get("group", "ops_alert")
                title = check.get("title", "巡检异常")

                # 格式化消息
                format_fn = check.get("format_msg")
                if format_fn:
                    message = format_fn(result)
                else:
                    message = f"{title}: {result}"

                patrol_logger.warning(f"[patrol:anomaly] {alert_id}: {message}")
                check_result = {"is_anomaly": True, "message": message}

                # 发飞书告警
                if self._feishu and self._feishu.is_ready:
                    chat_id = self._feishu._group_registry.get(group)
                    if chat_id:
                        self._feishu.send_alert_card(
                            chat_id=chat_id,
                            title=f"[巡检] {title}",
                            content=message,
                            severity="warning" if mode == "biz" else "error",
                            actions=[
                                {"label": "查看详情", "url": f"/console/ops-copilot"},
                                {"label": "静默1h", "action": f"silence_{alert_id}"},
                            ],
                        )
                else:
                    patrol_logger.debug(f"[patrol] 飞书未就绪，跳过告警发送: {alert_id}")
            else:
                check_result = {"is_anomaly": False}

        except Exception as e:
            patrol_logger.error(f"[patrol:error] {alert_id}: {e}")
            if run_id:
                self._write_patrol_step(
                    run_id, step_name=alert_id, agent_name=check.get("skill", ""),
                    status="failed", input_summary=check.get("question", ""),
                    error_message=str(e)[:500],
                )
            check_result = {"is_anomaly": True, "message": f"{alert_id} error: {e}"}

        return check_result

    # ── 记忆调和 ──

    async def _reconcile_memory(self) -> None:
        """定期清理过时/低重要度记忆 — 每周一凌晨"""
        patrol_logger.info("[patrol:memory] 开始记忆调和")
        run_id = str(uuid.uuid4())
        t0 = time.time()

        # 先写父记录
        self._write_patrol_run(
            run_id, "patrol_memory",
            status="running",
            input_summary="记忆调和",
        )

        error_msg = ""
        output_summary = ""
        try:
            from backend.copilot.context import ContextManager
            from backend.database import SessionLocal

            db = SessionLocal()
            try:
                ctx_mgr = ContextManager(db=db)

                user_ids = await ctx_mgr.get_all_active_user_ids()
                patrol_logger.info(f"[patrol:memory] 需调和用户数: {len(user_ids)}")

                total_stats = {"reviewed": 0, "decayed": 0, "deleted": 0}
                for uid in user_ids:
                    result = await ctx_mgr.reconcile(uid)
                    if result.get("status") == "ok":
                        total_stats["reviewed"] += result.get("reviewed", 0)
                        total_stats["decayed"] += result.get("decayed", 0)
                        total_stats["deleted"] += result.get("deleted", 0)

                output_summary = (
                    f"users={len(user_ids)} reviewed={total_stats['reviewed']} "
                    f"decayed={total_stats['decayed']} deleted={total_stats['deleted']}"
                )
                patrol_logger.info(f"[patrol:memory] 记忆调和完成: {output_summary}")
            finally:
                db.close()
        except Exception as e:
            error_msg = str(e)
            patrol_logger.error(f"[patrol:memory] 调和失败: {e}")

        lat = int((time.time() - t0) * 1000)
        self._write_patrol_run(
            run_id, "patrol_memory",
            status="failed" if error_msg else "completed",
            input_summary="记忆调和",
            output_summary=output_summary,
            error_message=error_msg,
            latency_ms=lat,
        )

    # ── 静默管理 ──

    def _is_silenced(self, alert_id: str) -> bool:
        import time
        until = self._silenced_alerts.get(alert_id, 0)
        return time.time() < until

    def silence_alert(self, alert_id: str, hours: int = 1) -> None:
        import time
        self._silenced_alerts[alert_id] = time.time() + hours * 3600
        patrol_logger.info(f"[patrol] {alert_id} 已静默 {hours} 小时")
