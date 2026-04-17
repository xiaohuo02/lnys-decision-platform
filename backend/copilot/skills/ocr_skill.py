# -*- coding: utf-8 -*-
"""backend/copilot/skills/ocr_skill.py — OCR 图片识别技能

骨架实现 — 等 OCR 模型部署后可直接接入。
当前状态: 返回友好提示告知用户 OCR 功能尚未部署。

接入方式:
  1. 在 backend/services/ 下创建 ocr_service.py，提供 OcrService.recognize(image_bytes) -> OcrResult
  2. 取消下方 _call_ocr_service 的占位逻辑，替换为真实调用
  3. 无需修改 registry 或 engine — auto_discover 会自动注册本 Skill
"""
from __future__ import annotations

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext
from backend.copilot.events import (
    CopilotEvent, EventType,
    text_delta_event,
)


class OcrSkill(BaseCopilotSkill):
    name = "ocr_skill"
    display_name = "OCR 图片识别"
    description = (
        "识别用户上传图片中的文字内容，"
        "支持票据、截图、表格照片等场景的文字提取和结构化。"
    )
    required_roles = {
        # DB 真实角色
        "platform_admin", "ops_analyst", "customer_service_manager",
        # legacy 兼容
        "super_admin", "business_admin",
    }
    mode = {"ops", "biz"}

    parameters_schema = {
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "图片 URL 或 base64 data URI",
            },
            "output_format": {
                "type": "string",
                "enum": ["text", "table", "json"],
                "description": "输出格式：纯文本/表格/结构化 JSON",
                "default": "text",
            },
        },
        "required": ["image_url"],
    }

    async def execute(self, question: str, context: SkillContext):
        image_url = context.tool_args.get("image_url", "")
        output_format = context.tool_args.get("output_format", "text")

        if not image_url:
            yield text_delta_event("请提供需要识别的图片（URL 或 base64 格式）。")
            return

        # ── 检查 OCR 服务是否可用 ──
        ocr_available = await self._check_ocr_available()

        if not ocr_available:
            yield text_delta_event(
                "**OCR 服务尚未部署**\n\n"
                "图片识别功能需要 OCR 模型支持，当前尚未部署。\n"
                "部署完成后，本功能将自动激活，支持以下场景：\n"
                "- 票据/发票文字提取\n"
                "- 截图内容识别\n"
                "- 表格照片 → 结构化数据\n"
                "- 手写文字识别\n\n"
                "*请联系管理员部署 OCR 服务。*"
            )
            return

        # ── 调用 OCR 服务 ──
        result = await self._call_ocr_service(image_url, output_format)

        # 输出结构化结果
        yield CopilotEvent(
            type=EventType.ARTIFACT_START,
            artifact_type="generic_table" if output_format == "table" else "generic_table",
            metadata={"title": "OCR 识别结果", "component": "GenericTableArtifact"},
        )
        yield CopilotEvent(
            type=EventType.ARTIFACT_DELTA,
            content=result,
        )
        yield CopilotEvent(type=EventType.ARTIFACT_END)

        yield CopilotEvent(
            type=EventType.TOOL_RESULT,
            data=result,
        )

    async def _check_ocr_available(self) -> bool:
        """检查 OCR 服务是否已部署并可用"""
        try:
            # 尝试导入 OCR 服务模块
            # 取消注释以下行以接入真实 OCR 服务:
            # from backend.services.ocr_service import ocr_service
            # return ocr_service.is_available()
            return False  # 当前未部署
        except ImportError:
            return False

    async def _call_ocr_service(self, image_url: str, output_format: str) -> dict:
        """调用 OCR 服务进行图片识别

        接入指南:
          from backend.services.ocr_service import ocr_service, OcrRequest
          request = OcrRequest(image_url=image_url, output_format=output_format)
          result = await ocr_service.recognize(request)
          return result.model_dump()
        """
        # 占位实现 — 部署后替换
        return {
            "status": "not_deployed",
            "message": "OCR 服务尚未部署",
            "recognized_text": "",
            "confidence": 0.0,
            "format": output_format,
        }


ocr_skill = OcrSkill()
