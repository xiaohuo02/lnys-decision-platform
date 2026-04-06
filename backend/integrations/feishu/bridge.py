# -*- coding: utf-8 -*-
"""backend/integrations/feishu/bridge.py — 飞书长连接桥接器

通过 lark-oapi SDK WebSocket 长连接与飞书建立全双工通道：
- 接收 @mention 消息 → 转发给 CopilotEngine 处理 → 回复
- 主动向飞书群发送消息/告警卡片
- 处理交互式卡片按钮回调
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, Optional

from loguru import logger

from backend.copilot.agent_logger import feishu_logger

# 飞书 API 超时（秒），防止阻塞事件循环
_FEISHU_TIMEOUT = 10


class FeishuBridge:
    """飞书长连接桥接器

    在 FastAPI 启动时以 daemon 线程运行 WebSocket 长连接。
    无需公网 IP、无需内网穿透。
    """

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._client = None
        self._ws_client = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._group_registry: Dict[str, str] = {}  # group_name → chat_id
        self._started = False

    def start(self, event_loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """启动长连接（daemon 线程，不阻塞主进程）"""
        if not self.app_id or not self.app_secret:
            feishu_logger.warning("[FeishuBridge] APP_ID 或 APP_SECRET 未配置，跳过启动")
            return

        self._event_loop = event_loop or asyncio.get_event_loop()

        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

            # API Client（主动发消息）
            self._client = (
                lark.Client.builder()
                .app_id(self.app_id)
                .app_secret(self.app_secret)
                .log_level(lark.LogLevel.INFO)
                .build()
            )

            # 事件分发器
            event_handler = (
                lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(self._on_message_receive)
                .build()
            )

            # 保存 event_handler 供线程内创建 ws.Client 使用
            self._event_handler = event_handler

            def _run_ws():
                """在独立线程中创建并运行 WebSocket 长连接

                根因：lark_oapi.ws.client 模块在导入时通过
                  loop = asyncio.get_event_loop()
                缓存了主线程 uvicorn 的 uvloop，start() 调用
                loop.run_until_complete() 触发 'already running'。
                修复：在线程内替换模块级 loop 为独立 event loop。
                """
                import asyncio
                from lark_oapi.ws import client as _ws_client_mod

                # 创建线程专属 event loop，替换 SDK 模块级缓存的主线程 loop
                _thread_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_thread_loop)
                _ws_client_mod.loop = _thread_loop

                try:
                    feishu_logger.info("[FeishuBridge] WS 线程启动 (独立 event loop)")
                    ws = lark.ws.Client(
                        self.app_id,
                        self.app_secret,
                        event_handler=self._event_handler,
                        log_level=lark.LogLevel.INFO,
                    )
                    self._ws_client = ws
                    ws.start()  # 阻塞，SDK 内部管理重连
                except Exception as e:
                    feishu_logger.error(f"[FeishuBridge] WS 线程退出: {e}")
                finally:
                    feishu_logger.warning("[FeishuBridge] WS 线程已结束")
                    _thread_loop.close()

            thread = threading.Thread(target=_run_ws, daemon=True, name="feishu-ws")
            thread.start()
            self._started = True
            feishu_logger.info("[FeishuBridge] WebSocket 长连接已启动")

        except ImportError:
            feishu_logger.warning("[FeishuBridge] lark-oapi 未安装，跳过飞书集成。pip install lark-oapi")
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge] 启动失败: {e}")

    def load_group_registry(self, db=None) -> None:
        """从 DB 加载飞书群映射，DB 不可用时从环境变量 fallback"""
        # 1) 尝试从 DB 加载
        if db is not None:
            try:
                from sqlalchemy import text
                rows = db.execute(
                    text("SELECT group_name, chat_id FROM feishu_group_mapping")
                ).fetchall()
                self._group_registry = {r[0]: r[1] for r in rows}
                feishu_logger.info(f"[FeishuBridge] 从 DB 加载 {len(self._group_registry)} 个群映射")
                if self._group_registry:
                    return
            except Exception as e:
                feishu_logger.warning(f"[FeishuBridge] DB 群映射加载失败: {e}")

        # 2) Fallback: 从 FEISHU_GROUP_MAPPING 环境变量加载
        try:
            from backend.config import settings
            if settings.FEISHU_GROUP_MAPPING:
                import json
                self._group_registry = json.loads(settings.FEISHU_GROUP_MAPPING)
                feishu_logger.info(f"[FeishuBridge] 从环境变量加载 {len(self._group_registry)} 个群映射")
        except Exception as e:
            feishu_logger.warning(f"[FeishuBridge] 环境变量群映射解析失败: {e}")

    # ── 接收消息 ──

    def _on_message_receive(self, data) -> None:
        """收到飞书消息（含 @mention）"""
        try:
            event = data.event
            msg = event.message
            chat_id = msg.chat_id
            sender_id = event.sender.sender_id.user_id if event.sender else "unknown"
            msg_type = msg.message_type

            feishu_logger.info(
                f"[FeishuBridge:recv] chat={chat_id} sender={sender_id} type={msg_type}"
            )

            # 检查是否 @了机器人
            mentions = getattr(msg, "mentions", None)
            if not mentions:
                return

            # 提取纯文本
            question = self._extract_text(msg)
            if not question.strip():
                return

            feishu_logger.info(f"[FeishuBridge:mention] question='{question[:60]}'")

            # 立即回复「思考中...」
            self._reply_text(msg.message_id, chat_id, "正在分析中，请稍候...")

            # 异步处理
            if self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._process_and_reply(question, chat_id, sender_id, msg.message_id),
                    self._event_loop,
                )

        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:recv_error] {e}")

    async def _process_and_reply(
        self, question: str, chat_id: str, sender_id: str, reply_msg_id: str
    ) -> None:
        """异步处理并回复"""
        try:
            from backend.copilot.engine import CopilotEngine

            engine = CopilotEngine()
            result_parts = []

            mode = self._resolve_mode(chat_id)
            user_role = self._resolve_role(sender_id)

            async for event in engine.run(
                question=question,
                mode=mode,
                user_id=f"feishu_{sender_id}",
                user_role=user_role,
                thread_id=f"feishu_{chat_id}",
                page_context={"source": "feishu", "chat_id": chat_id},
                source="feishu",
            ):
                if event.type.value == "text_delta" and event.content:
                    result_parts.append(event.content)

            answer = "".join(result_parts) or "抱歉，我暂时无法回答这个问题。"

            # 截断过长回复（飞书消息限制）
            if len(answer) > 3000:
                answer = answer[:3000] + "\n\n...（回复过长已截断，建议在 Web 端查看完整分析）"

            self._reply_text(reply_msg_id, chat_id, answer)
            feishu_logger.info(f"[FeishuBridge:reply] chat={chat_id} len={len(answer)}")

        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:process_error] {e}")
            self._reply_text(reply_msg_id, chat_id, f"处理失败: {type(e).__name__}")

    # ── 主动发消息 ──

    def send_text(self, chat_id: str, text: str) -> bool:
        """向飞书群发送纯文本"""
        if not self._client:
            feishu_logger.warning("[FeishuBridge] client 未初始化")
            return False
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            content = json.dumps({"text": text}, ensure_ascii=False)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                feishu_logger.error(f"[FeishuBridge:send] 失败: {response.code} {response.msg}")
                return False
            return True
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:send] 异常: {e}")
            return False

    async def send_text_async(self, chat_id: str, text: str) -> bool:
        """异步版本：在线程池中执行同步 send_text，带超时保护"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.send_text, chat_id, text),
                timeout=_FEISHU_TIMEOUT,
            )
        except asyncio.TimeoutError:
            feishu_logger.error(f"[FeishuBridge:send_async] 超时 ({_FEISHU_TIMEOUT}s) chat={chat_id}")
            return False
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:send_async] {e}")
            return False

    def send_to_group(self, group_name: str, text: str) -> bool:
        """通过群名发送（从注册表查找 chat_id）"""
        chat_id = self._group_registry.get(group_name)
        if not chat_id:
            feishu_logger.warning(f"[FeishuBridge] 群 '{group_name}' 未注册")
            return False
        return self.send_text(chat_id, text)

    async def send_to_group_async(self, group_name: str, text: str) -> bool:
        """异步版本：通过群名发送"""
        chat_id = self._group_registry.get(group_name)
        if not chat_id:
            feishu_logger.warning(f"[FeishuBridge] 群 '{group_name}' 未注册")
            return False
        return await self.send_text_async(chat_id, text)

    def send_alert_card(
        self,
        chat_id: str,
        title: str,
        content: str,
        severity: str = "warning",
        actions: Optional[list] = None,
    ) -> bool:
        """发送告警交互式卡片"""
        if not self._client:
            return False

        color_map = {"info": "blue", "warning": "orange", "error": "red", "success": "green"}
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color_map.get(severity, "blue"),
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
            ],
        }

        if actions:
            action_elements = []
            for act in actions:
                if "url" in act:
                    action_elements.append({
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": act["label"]},
                        "url": act["url"],
                        "type": "primary",
                    })
                elif "action" in act:
                    action_elements.append({
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": act["label"]},
                        "value": {"action": act["action"]},
                        "type": "default",
                    })
            if action_elements:
                card["elements"].append({"tag": "action", "actions": action_elements})

        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
            card_json = json.dumps(card, ensure_ascii=False)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(card_json)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                feishu_logger.error(f"[FeishuBridge:card] 失败: {response.code} {response.msg}")
                return False
            return True
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:card] 异常: {e}")
            return False

    async def send_alert_card_async(
        self, chat_id: str, title: str, content: str,
        severity: str = "warning", actions: Optional[list] = None,
    ) -> bool:
        """异步版本：发送告警卡片"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.send_alert_card, chat_id, title, content, severity, actions
                ),
                timeout=_FEISHU_TIMEOUT,
            )
        except asyncio.TimeoutError:
            feishu_logger.error(f"[FeishuBridge:card_async] 超时 ({_FEISHU_TIMEOUT}s)")
            return False
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:card_async] {e}")
            return False

    def send_patrol_report_card(
        self,
        chat_id: str,
        title: str,
        items: list,
        mode: str = "ops",
    ) -> bool:
        """发送巡检汇总报告卡片

        Args:
            items: [{"label": "库存预警", "value": "3 支SKU", "status": "warning"}, ...]
        """
        if not self._client:
            return False

        # 构建 Markdown 表格
        md_rows = ["| 检查项 | 结果 | 状态 |", "| --- | --- | --- |"]
        for item in items:
            status_emoji = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(
                item.get("status", "ok"), "ℹ️"
            )
            md_rows.append(f"| {item['label']} | {item.get('value', '-')} | {status_emoji} |")

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "turquoise" if mode == "biz" else "indigo",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(md_rows)},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": f"{'运维' if mode == 'ops' else '运营'}巡检 · 自动生成"}
                    ],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 查看详情"},
                            "url": f"/console/ops-copilot" if mode == "ops" else "/business/copilot",
                            "type": "primary",
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔕 静默 1h"},
                            "value": {"action": "silence_patrol_1h"},
                            "type": "default",
                        },
                    ],
                },
            ],
        }

        return self._send_card(chat_id, card)

    def send_daily_summary_card(
        self,
        chat_id: str,
        summary: dict,
    ) -> bool:
        """发送运营日报卡片

        Args:
            summary: {
                "date": "2025-04-08",
                "sales_total": 12345,
                "sales_change": "+5.2%",
                "orders": 89,
                "sentiment_positive": 78.3,
                "alerts": [{"label": "...", "severity": "warning"}],
                "highlights": ["...", "..."],
            }
        """
        if not self._client:
            return False

        date_str = summary.get("date", "")
        highlights = summary.get("highlights", [])
        alerts = summary.get("alerts", [])

        # 指标行
        metrics_md = (
            f"**销售额** {summary.get('sales_total', 0):,} "
            f"({summary.get('sales_change', '-')})\n"
            f"**订单数** {summary.get('orders', 0)}\n"
            f"**正面评价率** {summary.get('sentiment_positive', 0):.1f}%"
        )

        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": metrics_md}},
        ]

        if highlights:
            hl_md = "\n".join(f"• {h}" for h in highlights[:5])
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**📌 今日要点**\n{hl_md}"},
            })

        if alerts:
            alert_md = "\n".join(
                f"{'⚠️' if a.get('severity') == 'warning' else '❌'} {a['label']}"
                for a in alerts[:5]
            )
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**🚨 告警项**\n{alert_md}"},
            })

        elements.append({"tag": "hr"})
        elements.append({
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": f"运营日报 · {date_str} · 自动生成"}
            ],
        })
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "📊 查看完整报告"},
                    "url": "/business/copilot",
                    "type": "primary",
                },
            ],
        })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"📈 运营日报 — {date_str}"},
                "template": "turquoise",
            },
            "elements": elements,
        }

        return self._send_card(chat_id, card)

    def _send_card(self, chat_id: str, card: dict) -> bool:
        """发送交互式卡片（内部方法）"""
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
            card_json = json.dumps(card, ensure_ascii=False)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(card_json)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                feishu_logger.error(f"[FeishuBridge:card] {response.code} {response.msg}")
                return False
            return True
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:card] {e}")
            return False

    # ── 辅助方法 ──

    def _reply_text(self, reply_msg_id: str, chat_id: str, text: str) -> None:
        """回复指定消息"""
        if not self._client:
            return
        try:
            from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

            content = json.dumps({"text": text}, ensure_ascii=False)
            request = (
                ReplyMessageRequest.builder()
                .message_id(reply_msg_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            self._client.im.v1.message.reply(request)
        except Exception as e:
            feishu_logger.error(f"[FeishuBridge:reply] {e}")
            # 回退到直接发送
            self.send_text(chat_id, text)

    def _extract_text(self, message) -> str:
        """从飞书消息中提取纯文本（去掉 @mention 标记）"""
        try:
            content = json.loads(message.content)
            text = content.get("text", "")
            # 移除 @mention 标记
            import re
            text = re.sub(r"@_user_\d+\s*", "", text).strip()
            return text
        except Exception:
            return ""

    def _resolve_mode(self, chat_id: str) -> str:
        """根据群映射决定 ops/biz 模式"""
        for group_name, cid in self._group_registry.items():
            if cid == chat_id:
                if "ops" in group_name:
                    return "ops"
                return "biz"
        return "biz"

    def _resolve_role(self, sender_id: str) -> str:
        """根据发送者确定角色（默认 biz_operator）"""
        # TODO: 从飞书用户映射表查询实际角色
        return "biz_operator"

    @property
    def is_ready(self) -> bool:
        return self._started
