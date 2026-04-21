# -*- coding: utf-8 -*-
"""backend/services/report_rendering_service.py

ReportRenderingService — 报告渲染服务

╔══════════════════════════════════════════════════════════════════╗
║  Agent 契약                                                       ║
╠══════════════════════════════════════════════════════════════════╣
║  输入   : ReportRenderRequest（artifact_refs + 报告类型）         ║
║  输出   : ReportRenderResult（Markdown 正文 + artifact_uri）      ║
║  可调用 : ArtifactRef 读取、字符串模板拼接                        ║
║  禁止   : 重新调用 ML 服务、直接写 DB、调用 LLM                   ║
║  降级   : 缺少某个 artifact 时跳过该节，标记 partial=True          ║
║  HITL   : 不需要                                                   ║
║  依赖   : InsightComposerAgent 的输出 executive_summary          ║
║           各 Service 的 artifact refs                            ║
║  Trace  : step_name="report_rendering"                           ║
║           output_summary=报告字数 + section 数量                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.schemas.artifact import ArtifactRef, ArtifactType


_STORE_ROOT = settings.ARTIFACT_STORE_ROOT / "reports"


class ReportSection(BaseModel):
    title:   str
    content: str
    skipped: bool = False


class ReportRenderRequest(BaseModel):
    run_id:           Optional[str] = None
    report_type:      str = "business_overview"   # business_overview / risk_review / custom
    requested_format: str = "markdown"
    executive_summary: Optional[str] = None
    risk_highlights:   Optional[str] = None
    action_plan:       Optional[str] = None
    # artifact refs from each service (optional)
    customer_summary:  Optional[str] = None
    forecast_summary:  Optional[str] = None
    sentiment_summary: Optional[str] = None
    fraud_summary:     Optional[str] = None
    inventory_summary: Optional[str] = None
    association_summary: Optional[str] = None
    # 报告元数据
    title:             str = "经营分析报告"
    generated_by:      str = "InsightComposerAgent"


class ReportRenderResult(BaseModel):
    run_id:           Optional[str]
    data_ready:       bool
    partial:          bool = False           # 部分 section 被跳过

    report_markdown:  str = ""
    report_html:      str = ""
    sections:         List[ReportSection] = Field(default_factory=list)
    word_count:       int = 0
    artifact_uri:     Optional[str] = None   # 保存到磁盘后的路径
    artifact_uris:    Dict[str, str] = Field(default_factory=dict)

    artifact:         Optional[ArtifactRef] = None
    error_message:    Optional[str] = None
    rendered_at:      datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportRenderingService:
    """
    将各 service/agent 产出的摘要文本拼装成结构化 Markdown 报告。
    不调用 LLM，纯模板渲染。
    """

    def render(self, request: ReportRenderRequest) -> ReportRenderResult:
        sections: List[ReportSection] = []
        skipped = 0

        # ── 封面 ──────────────────────────────────────────────────
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections.append(ReportSection(
            title="封面",
            content=(
                f"# {request.title}\n\n"
                f"> 生成时间：{now}  \n"
                f"> 分析模块：`{request.report_type}`  \n"
                f"> 生成方：{request.generated_by}  \n"
                f"> 导出格式：{request.requested_format}\n"
            ),
        ))

        # ── 管理层摘要 ────────────────────────────────────────────
        if request.executive_summary:
            sections.append(ReportSection(
                title="管理层摘要",
                content=f"## 管理层摘要\n\n{request.executive_summary}\n",
            ))
        else:
            sections.append(ReportSection(
                title="管理层摘要", content="", skipped=True,
            ))
            skipped += 1

        # ── 风险提示 ──────────────────────────────────────────────
        if request.risk_highlights:
            sections.append(ReportSection(
                title="风险提示",
                content=f"## 风险提示\n\n{request.risk_highlights}\n",
            ))
        else:
            sections.append(ReportSection(
                title="风险提示", content="", skipped=True,
            ))
            skipped += 1

        # ── 各模块明细 ────────────────────────────────────────────
        module_sections = [
            ("客户分析",   request.customer_summary),
            ("销售预测",   request.forecast_summary),
            ("舆情分析",   request.sentiment_summary),
            ("欺诈风控",   request.fraud_summary),
            ("库存优化",   request.inventory_summary),
            ("关联分析",   request.association_summary),
        ]
        covered_modules = [name for name, content in module_sections if content]
        skipped_modules = [name for name, content in module_sections if not content]
        coverage_lines = [f"- 已纳入模块：{', '.join(covered_modules) if covered_modules else '无'}"]
        if skipped_modules:
            coverage_lines.append(f"- 缺失模块：{', '.join(skipped_modules)}")
            coverage_lines.append("- 说明：缺失模块不会阻断报告生成，但相关结论需要结合业务数据补充判断。")
        else:
            coverage_lines.append("- 说明：本次报告已覆盖全部核心经营模块，可直接用于答辩或管理层汇报。")
        sections.append(ReportSection(
            title="数据覆盖",
            content="## 数据覆盖\n\n" + "\n".join(coverage_lines) + "\n",
        ))

        for name, content in module_sections:
            if content:
                sections.append(ReportSection(
                    title=name,
                    content=f"## {name}\n\n{content}\n",
                ))
            else:
                sections.append(ReportSection(title=name, content="", skipped=True))
                skipped += 1

        # ── 行动建议 ──────────────────────────────────────────────
        if request.action_plan:
            sections.append(ReportSection(
                title="行动建议",
                content=f"## 行动建议\n\n{request.action_plan}\n",
            ))
            checklist = self._build_checklist(request.action_plan)
            if checklist:
                sections.append(ReportSection(
                    title="执行清单",
                    content=f"## 执行清单\n\n{checklist}\n",
                ))

        # ── 拼装 Markdown ─────────────────────────────────────────
        full_md = "\n\n---\n\n".join(
            s.content for s in sections if not s.skipped and s.content
        )
        full_html = self._render_html_document(request.title, sections)
        word_count = len(full_md)

        # ── 持久化到磁盘（artifact_store/reports/）────────────────
        artifact_uri: Optional[str] = None
        artifact_uris: Dict[str, str] = {}
        try:
            _STORE_ROOT.mkdir(parents=True, exist_ok=True)
            base_name = f"{request.run_id or uuid.uuid4().hex[:8]}_{request.report_type}"
            md_path = _STORE_ROOT / f"{base_name}.md"
            html_path = _STORE_ROOT / f"{base_name}.html"
            md_path.write_text(full_md, encoding="utf-8")
            html_path.write_text(full_html, encoding="utf-8")
            artifact_uris = {
                "markdown": str(md_path),
                "html": str(html_path),
            }
            artifact_uri = artifact_uris.get(request.requested_format) or artifact_uris["markdown"]
        except Exception as e:
            logger.warning(f"[ReportService] 报告写入磁盘失败（非致命）: {e}")

        artifact = ArtifactRef(
            artifact_type=ArtifactType.REPORT,
            summary=f"报告: {request.title}, {word_count} 字, {len(sections)-skipped} 节",
        ) if word_count > 0 else None

        result = ReportRenderResult(
            run_id=request.run_id,
            data_ready=word_count > 0,
            partial=skipped > 0,
            report_markdown=full_md,
            report_html=full_html,
            sections=sections,
            word_count=word_count,
            artifact_uri=artifact_uri,
            artifact_uris=artifact_uris,
            artifact=artifact,
        )
        logger.info(
            f"[ReportService] type={request.report_type} "
            f"sections={len(sections)-skipped}/{len(sections)} "
            f"words={word_count} formats={list(artifact_uris.keys())} uri={artifact_uri}"
        )
        return result

    @staticmethod
    def _build_checklist(action_plan: str) -> str:
        items: List[str] = []
        for raw_line in action_plan.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^\d+\.\s*", "", line)
            line = re.sub(r"^-\s*", "", line)
            if line:
                items.append(f"- [ ] {line}")
        return "\n".join(items[:5])

    def _render_html_document(self, title: str, sections: List[ReportSection]) -> str:
        body = "\n".join(
            self._section_to_html(section)
            for section in sections
            if not section.skipped and section.content
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ee;
      --card: #fffdf8;
      --line: #ded5c6;
      --text: #1f2933;
      --muted: #6b7280;
      --accent: #9a3412;
      --accent-soft: rgba(154, 52, 18, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(154, 52, 18, 0.08), transparent 32%),
        linear-gradient(180deg, #fbf7f1 0%, var(--bg) 100%);
      color: var(--text);
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 24px;
      margin-bottom: 18px;
      box-shadow: 0 10px 30px rgba(31, 41, 51, 0.06);
    }}
    h1, h2 {{ margin: 0 0 16px; line-height: 1.25; }}
    h1 {{ font-size: 32px; }}
    h2 {{
      font-size: 20px;
      color: var(--accent);
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }}
    p, li {{ line-height: 1.75; font-size: 15px; }}
    p {{ margin: 0 0 12px; }}
    ul, ol {{ margin: 0 0 12px 20px; padding: 0; }}
    code {{
      background: var(--accent-soft);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 8px;
      font-size: 13px;
    }}
    .report-meta {{
      color: var(--muted);
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <main>
{body}
  </main>
</body>
</html>"""

    def _section_to_html(self, section: ReportSection) -> str:
        parts = self._render_text_blocks(section.content)
        return "    <section>\n" + "\n".join(parts) + "\n    </section>"

    def _render_text_blocks(self, text: str) -> List[str]:
        lines = text.splitlines()
        blocks: List[str] = []
        paragraph: List[str] = []
        list_tag: Optional[str] = None
        list_items: List[str] = []

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                blocks.append(f"      <p>{'<br />'.join(paragraph)}</p>")
                paragraph = []

        def flush_list() -> None:
            nonlocal list_tag, list_items
            if list_tag and list_items:
                blocks.append(f"      <{list_tag}>")
                for item in list_items:
                    blocks.append(f"        <li>{item}</li>")
                blocks.append(f"      </{list_tag}>")
            list_tag = None
            list_items = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                flush_paragraph()
                flush_list()
                continue
            if line.startswith("# "):
                flush_paragraph()
                flush_list()
                blocks.append(f"      <h1>{html.escape(line[2:].strip())}</h1>")
                continue
            if line.startswith("## "):
                flush_paragraph()
                flush_list()
                blocks.append(f"      <h2>{html.escape(line[3:].strip())}</h2>")
                continue
            if line.startswith("> "):
                flush_paragraph()
                flush_list()
                blocks.append(f"      <p class=\"report-meta\">{self._inline_markup(line[2:].strip())}</p>")
                continue
            ordered = re.match(r"^(\d+)\.\s+(.*)$", line)
            if ordered:
                flush_paragraph()
                if list_tag not in (None, "ol"):
                    flush_list()
                list_tag = "ol"
                list_items.append(self._inline_markup(ordered.group(2).strip()))
                continue
            if line.startswith("- "):
                flush_paragraph()
                if list_tag not in (None, "ul"):
                    flush_list()
                list_tag = "ul"
                list_items.append(self._inline_markup(line[2:].strip()))
                continue
            flush_list()
            paragraph.append(self._inline_markup(line))

        flush_paragraph()
        flush_list()
        return blocks

    @staticmethod
    def _inline_markup(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        return escaped


report_rendering_service = ReportRenderingService()
