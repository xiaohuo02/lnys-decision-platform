# 统一 Copilot 系统架构设计 v5.0

> 基于 Datadog Bits AI、Grafana Assistant、ChatGPT Canvas、Gemini Deep Research、
> Claude Artifacts/Projects、DeepSeek Chain-of-Thought、AG-UI Protocol、
> LangChain Skills 等业界最佳实践的深度调研，结合本项目比赛级技术力展示需求。

---

## 一、调研总结：顶级产品核心设计模式

### 1.1 运维/可观测领域 AI 助手

| 产品 | 核心设计 | 值得借鉴的点 |
|------|---------|------------|
| **Datadog Bits AI** | Skills 架构（Dashboard/Notebook/Cost/Alert）；基于 Datadog Role 的权限继承；Web + Mobile + Slack 三端统一；Cmd+I 全局唤起 | **权限继承用户角色**；**Skills 按领域分模块注册**；全局快捷键唤起 |
| **Grafana Assistant** | 上下文感知侧边栏（感知当前页面/数据源/Dashboard）；@ 引用上下文（数据源/标签/Dashboard）；多步调查工作流；自动纠错重试 | **页面上下文注入 system prompt**；**@ 引用机制**；LLM 查询→内嵌可视化 |

### 1.2 通用 AI 助手前端交互

| 产品 | 核心 UX 模式 | 值得借鉴的点 |
|------|-------------|------------|
| **ChatGPT** | Canvas（右侧 Artifacts 面板）；Auto/Fast/Thinking 模式切换；SSE 流式 + █ 光标；Agent Mode 执行任务；Connectors 集成外部数据；Custom Instructions | **Canvas 侧面板**；**模式切换**；**流式 Markdown 渲染** |
| **Gemini** | Deep Research 多步骤计划→搜索→综合；Gems 自定义角色；Memory 跨会话记忆；"Google It" 事实校验按钮；跨设备同步 | **Deep Research 多步可视化**；**Gems 角色模板**；**事实校验按钮** |
| **Claude** | Projects（对话 + 文档的工作区）；Artifacts（代码/HTML/图表独立面板）；Cowork（本地 Agent）；Tone/Length 快速设置；大纲视图（长回答导航） | **Projects 工作区概念**；**Artifacts 面板实时预览**；**大纲跳转** |
| **DeepSeek** | Chain-of-Thought 透明展示（推理过程可见）；DeepThink/Search 开关；推理→工具调用→推理多轮循环 | **思维链可折叠展示**；**DeepThink 开关**；**reasoning_content 流式分离** |

### 1.3 协议与架构模式

| 模式 | 来源 | 核心思想 |
|------|------|---------|
| **AG-UI Protocol** | CopilotKit + LangGraph | 16 种事件类型（Lifecycle/Text/Tool/State/Special）；SSE 流式；INTERRUPT 人工审批；STATE_DELTA 增量更新 |
| **LangChain Skills** | LangChain Docs | Prompt 驱动的技能特化；渐进式披露；动态工具注册；层级技能树 |
| **RBAC for AI Agents** | NeuralTrust | 上下文感知权限（不是 on/off）；动作级控制（控制动词而非名词）；运行时实时校验 |

---

## 二、系统总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vue3)                       │
│  ┌─────────────┐  ┌─────────────┐                       │
│  │ /console/*  │  │ /*          │  Two Layouts           │
│  │ 运维助手     │  │ 运营助手     │  Shared CopilotPanel   │
│  │ (Ops Mode)  │  │ (Biz Mode)  │  Component             │
│  └──────┬──────┘  └──────┬──────┘                       │
│         │                │                               │
│    ┌────┴────────────────┴────┐                          │
│    │   UnifiedCopilotPanel    │  ← 统一交互组件           │
│    │  ┌─────────────────────┐ │                          │
│    │  │ Composer (输入区)    │ │  auto-resize textarea   │
│    │  │ + Context Pills     │ │  @ 引用 + 快捷指令       │
│    │  │ + Mode Switch       │ │  Auto/Think/DeepResearch │
│    │  ├─────────────────────┤ │                          │
│    │  │ Chat Stream (对话流) │ │  SSE 流式 Markdown       │
│    │  │ + Thinking Chain    │ │  可折叠推理链             │
│    │  │ + Tool Call Cards   │ │  工具调用进度卡片         │
│    │  │ + GenUI Components  │ │  动态挂载 Vue 组件        │
│    │  ├─────────────────────┤ │                          │
│    │  │ Artifacts Panel     │ │  右侧滑出面板             │
│    │  │ (表格/图表/代码)     │ │  结构化数据可视化         │
│    │  └─────────────────────┘ │                          │
│    └─────────────┬────────────┘                          │
└──────────────────┼──────────────────────────────────────┘
                   │ SSE Stream (AG-UI 事件协议)
                   ▼
┌─────────────────────────────────────────────────────────┐
│                 Backend (FastAPI)                        │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │           /copilot/stream  (SSE Endpoint)    │       │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────────┐ │       │
│  │  │ Auth +  │→ │ RBAC    │→ │  Copilot     │ │       │
│  │  │ JWT     │  │ Filter  │  │  Engine      │ │       │
│  │  └─────────┘  └─────────┘  └──────┬───────┘ │       │
│  └───────────────────────────────────┼──────────┘       │
│                                      │                  │
│  ┌───────────────────────────────────┼──────────┐       │
│  │          CopilotEngine            │          │       │
│  │  ┌────────────────────────────────┴───────┐  │       │
│  │  │  LLM Intent Router (qwen-plus)        │  │       │
│  │  │  (替代关键词匹配，语义理解意图)          │  │       │
│  │  └────────────────────┬───────────────────┘  │       │
│  │                       │                      │       │
│  │  ┌────────────────────▼───────────────────┐  │       │
│  │  │       Skill Registry (技能注册表)       │  │       │
│  │  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ │  │       │
│  │  │  │ trace   │ │ eval    │ │ prompt   │ │  │       │
│  │  │  │ _skill  │ │ _skill  │ │ _skill   │ │  │       │
│  │  │  ├─────────┤ ├─────────┤ ├──────────┤ │  │       │
│  │  │  │ release │ │sentiment│ │ kb_rag   │ │  │       │
│  │  │  │ _skill  │ │ _skill  │ │ _skill   │ │  │       │
│  │  │  ├─────────┤ ├─────────┤ ├──────────┤ │  │       │
│  │  │  │ system  │ │ review  │ │ ocr      │ │  │       │
│  │  │  │ _skill  │ │ _skill  │ │ _skill   │ │  │       │
│  │  │  └─────────┘ └─────────┘ └──────────┘ │  │       │
│  │  └────────────────────────────────────────┘  │       │
│  │                                              │       │
│  │  ┌────────────────────────────────────────┐  │       │
│  │  │  Context Manager (上下文管理器)         │  │       │
│  │  │  - Thread History (Redis, 最近 N 轮)    │  │       │
│  │  │  - Page Context (当前页面/选中实体)      │  │       │
│  │  │  - User Memory (跨会话偏好)             │  │       │
│  │  └────────────────────────────────────────┘  │       │
│  │                                              │       │
│  │  ┌────────────────────────────────────────┐  │       │
│  │  │  Data Layer (数据访问层)                │  │       │
│  │  │  - ReadRepository (MySQL 只读)          │  │       │
│  │  │  - VectorStore (ChromaDB RAG)           │  │       │
│  │  │  - EmbeddingService (bge-small-zh)      │  │       │
│  │  └────────────────────────────────────────┘  │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## 三、核心设计：双模 Copilot 统一框架

### 3.1 双模切换 —— 一套引擎，两套 Persona

```
CopilotMode = "ops" | "biz"

ops (运维助手 @ /console)：
  - persona: "你是柠优生活平台的运维诊断专家"
  - 技能全集: trace/eval/prompt/release/review/system/kb_rag/sentiment/...
  - 数据权限: 全部只读
  - 允许查看: 内部错误详情、Agent 状态、系统健康指标

biz (运营助手 @ /business)：
  - persona: "你是柠优生活平台的运营分析助手"
  - 技能子集: 由管理控制台配置（默认: 销售/客户/库存/舆情）
  - 数据权限: 仅业务数据，不可查看系统内部状态
  - 允许查看: 业务指标、客户分析、销售趋势
```

### 3.2 RBAC 权限矩阵 —— 借鉴 Datadog Bits AI

**核心原则**: Copilot 继承用户角色权限，不独立鉴权。

```python
# 权限矩阵定义
SKILL_PERMISSIONS = {
    # skill_name: {允许的角色列表}
    "trace_skill":      {"super_admin", "platform_admin", "ops_analyst"},
    "eval_skill":       {"super_admin", "platform_admin", "ops_analyst"},
    "prompt_skill":     {"super_admin", "platform_admin", "business_admin", "ops_analyst"},
    "release_skill":    {"super_admin", "platform_admin", "business_admin"},
    "review_skill":     {"super_admin", "platform_admin", "risk_reviewer"},
    "system_skill":     {"super_admin", "platform_admin"},
    "sentiment_skill":  {"super_admin", "platform_admin", "business_admin", "ops_analyst"},
    "customer_skill":   {"super_admin", "platform_admin", "business_admin"},
    "forecast_skill":   {"super_admin", "platform_admin", "business_admin"},
    "kb_rag_skill":     {"super_admin", "platform_admin", "business_admin", "ops_analyst", "service_agent"},
    "ocr_skill":        {"super_admin", "platform_admin", "business_admin", "ops_analyst"},
}

# 管理控制台可额外配置：
# 对某个用户开放/关闭特定 skill（存 MySQL user_skill_overrides 表）
```

### 3.3 Skill 注册表 —— 借鉴 LangChain Skills + Datadog Skills

每个 Skill 是一个独立模块，遵循统一接口：

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator

class BaseCopilotSkill(ABC):
    """Copilot 技能基类"""

    name: str                    # 唯一标识: "trace_skill"
    display_name: str            # 展示名: "追踪日志查询"
    description: str             # LLM 路由用的描述
    required_roles: set[str]     # 最低权限角色集合
    mode: set[str]               # {"ops"} | {"biz"} | {"ops", "biz"}

    @abstractmethod
    async def execute(
        self,
        question: str,
        context: SkillContext,   # 包含 db, user_role, page_context, thread_history
    ) -> AsyncGenerator[CopilotEvent, None]:
        """流式执行，yield AG-UI 事件"""
        ...

    def get_tool_schema(self) -> dict:
        """返回 OpenAI function calling 格式的 schema，供 LLM 路由选择"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }
```

**技能注册与发现（渐进式披露）：**

```python
class SkillRegistry:
    """全局技能注册表 —— 支持动态注册/卸载"""

    _skills: dict[str, BaseCopilotSkill] = {}

    def register(self, skill: BaseCopilotSkill):
        self._skills[skill.name] = skill

    def get_available_skills(
        self, mode: str, user_role: str, overrides: dict = None
    ) -> list[BaseCopilotSkill]:
        """根据模式 + 角色 + 管理员覆盖配置，返回当前用户可用的技能列表"""
        available = []
        for skill in self._skills.values():
            if mode not in skill.mode:
                continue
            base_allowed = user_role in skill.required_roles
            override = (overrides or {}).get(skill.name)
            if override is True or (base_allowed and override is not False):
                available.append(skill)
        return available

    def get_tool_schemas(self, skills: list) -> list[dict]:
        """生成 LLM function calling 的 tools 列表"""
        return [s.get_tool_schema() for s in skills]
```

---

## 四、SSE 流式协议 —— 借鉴 AG-UI + DeepSeek

### 4.1 事件类型定义

```python
from enum import Enum

class CopilotEventType(str, Enum):
    # ── Lifecycle ──
    RUN_STARTED      = "run_started"       # 开始处理
    STEP_STARTED     = "step_started"      # 某步骤开始
    STEP_FINISHED    = "step_finished"     # 某步骤结束
    RUN_FINISHED     = "run_finished"      # 全部完成
    RUN_ERROR        = "run_error"         # 出错

    # ── Thinking (思维链) ──
    THINKING_START   = "thinking_start"    # 推理开始
    THINKING_DELTA   = "thinking_delta"    # 推理内容增量
    THINKING_END     = "thinking_end"      # 推理结束

    # ── Text (回答) ──
    TEXT_START        = "text_start"       # 回答开始
    TEXT_DELTA        = "text_delta"       # 回答内容增量（Markdown token）
    TEXT_END          = "text_end"         # 回答结束

    # ── Tool Call (工具调用) ──
    TOOL_CALL_START  = "tool_call_start"   # 工具调用开始
    TOOL_CALL_ARGS   = "tool_call_args"    # 参数流式
    TOOL_CALL_END    = "tool_call_end"     # 工具调用结束
    TOOL_RESULT      = "tool_result"       # 工具结果

    # ── Artifacts (结构化数据) ──
    ARTIFACT_START   = "artifact_start"    # Artifact 面板打开
    ARTIFACT_DELTA   = "artifact_delta"    # 数据增量
    ARTIFACT_END     = "artifact_end"      # Artifact 完成

    # ── Suggested Actions ──
    SUGGESTIONS      = "suggestions"       # 建议的后续问题/操作

    # ── Meta ──
    CONTEXT_USED     = "context_used"      # 使用了哪些上下文（透明度）
```

### 4.2 SSE 端点实现

```python
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/copilot", tags=["copilot"])

@router.post("/stream")
async def copilot_stream(body: CopilotStreamRequest, request: Request):
    """统一 Copilot SSE 流式端点"""

    async def event_generator():
        engine = CopilotEngine()
        async for event in engine.run(
            question=body.question,
            mode=body.mode,           # "ops" | "biz"
            user_role=request.state.user_role,
            thread_id=body.thread_id,
            page_context=body.page_context,
            db=request.state.db,
        ):
            yield f"event: {event.type}\ndata: {event.json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # Nginx 不缓冲
        },
    )
```

### 4.3 前端 SSE 消费 —— EventSource + Ring Buffer

```javascript
// composables/useCopilotStream.js
export function useCopilotStream() {
  const messages = ref([])
  const thinking = ref({ visible: false, content: '' })
  const artifact = ref({ visible: false, type: '', data: null })
  const toolCalls = ref([])
  const isStreaming = ref(false)

  async function ask(question, { mode, threadId, pageContext } = {}) {
    isStreaming.value = true
    const currentMsg = reactive({
      role: 'assistant', content: '', streaming: true,
      intent: null, confidence: null, thinking: '',
    })
    messages.value.push(currentMsg)

    const response = await fetch('/admin/copilot/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ question, mode, thread_id: threadId, page_context: pageContext }),
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 事件
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留不完整的最后一行

      for (const line of lines) {
        if (line.startsWith('event: ')) currentEvent = line.slice(7)
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6))
          handleEvent(currentEvent, data, currentMsg)
        }
      }
    }
    currentMsg.streaming = false
    isStreaming.value = false
  }

  function handleEvent(type, data, msg) {
    switch (type) {
      case 'thinking_delta':
        thinking.value.visible = true
        thinking.value.content += data.content
        break
      case 'thinking_end':
        msg.thinking = thinking.value.content
        thinking.value.visible = false
        break
      case 'text_delta':
        msg.content += data.content   // 增量 Markdown
        break
      case 'tool_call_start':
        toolCalls.value.push({ name: data.name, status: 'running', args: '' })
        break
      case 'tool_call_end':
        const tc = toolCalls.value.find(t => t.name === data.name)
        if (tc) tc.status = 'done'
        break
      case 'artifact_start':
        artifact.value = { visible: true, type: data.artifact_type, data: null }
        break
      case 'artifact_delta':
        artifact.value.data = data.content
        break
      case 'suggestions':
        msg.suggestions = data.items
        break
      case 'context_used':
        msg.contextUsed = data.sources
        break
    }
  }

  return { messages, thinking, artifact, toolCalls, isStreaming, ask }
}
```

---

## 五、LLM 意图路由 —— 替代关键词匹配

### 5.1 Function Calling 路由（核心升级）

```python
class CopilotEngine:
    """Copilot 核心引擎"""

    async def run(self, question, mode, user_role, thread_id, page_context, db):
        # 1. 权限过滤可用技能
        skills = self.registry.get_available_skills(mode, user_role)

        # 2. 构建上下文
        context = await self.context_manager.build(
            thread_id=thread_id,
            page_context=page_context,
            user_role=user_role,
            mode=mode,
        )

        # 3. 只读拦截（保留，作为硬编码安全层）
        if self._is_write_action(question):
            yield CopilotEvent(type="text_delta", content="...")
            return

        # 4. LLM Function Calling 路由
        yield CopilotEvent(type="run_started")
        yield CopilotEvent(type="thinking_start")

        tool_schemas = self.registry.get_tool_schemas(skills)
        routing_result = await self._llm_route(question, context, tool_schemas)

        yield CopilotEvent(type="thinking_delta", content=routing_result.reasoning)
        yield CopilotEvent(type="thinking_end")

        # 5. 执行选中的 Skill（可能多个）
        for skill_call in routing_result.skill_calls:
            skill = self.registry.get(skill_call.name)
            yield CopilotEvent(type="tool_call_start", name=skill.display_name)

            async for event in skill.execute(question, context):
                yield event

            yield CopilotEvent(type="tool_call_end", name=skill.display_name)

        # 6. LLM 综合回答（流式）
        async for token in self._llm_synthesize(question, context, results):
            yield CopilotEvent(type="text_delta", content=token)

        yield CopilotEvent(type="run_finished")

    async def _llm_route(self, question, context, tool_schemas):
        """用 qwen-plus function calling 做意图路由"""
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="qwen-plus",
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
        ).bind_tools(tool_schemas)

        messages = [
            SystemMessage(content=self._build_system_prompt(context)),
            *context.thread_history,  # 最近 N 轮历史
            HumanMessage(content=question),
        ]

        response = await llm.ainvoke(messages)
        return self._parse_tool_calls(response)
```

### 5.2 多意图解析（解决之前 MIX 测试全军覆没的问题）

```python
async def _llm_route(self, question, context, tool_schemas):
    """LLM 可以一次返回多个 tool_calls，天然支持多意图"""
    # qwen-plus 的 function calling 支持 parallel_tool_calls
    # "最近有失败的 run 和待审核的任务吗？"
    # → tool_calls: [trace_skill(query="failed_runs"), review_skill(query="pending")]
    # 自动识别多意图并并行执行
    ...
```

---

## 六、上下文管理 —— 借鉴 Grafana + Claude Projects

### 6.1 三层上下文

```python
class ContextManager:
    """三层上下文管理"""

    async def build(self, thread_id, page_context, user_role, mode):
        return SkillContext(
            # Layer 1: 页面上下文（借鉴 Grafana 的页面感知）
            page_context=page_context,
            # e.g. {"page": "/console/traces", "selected_run_id": "run-003"}
            # e.g. {"page": "/sentiment/overview", "time_range": "7d"}

            # Layer 2: 对话历史（Redis，最近 5 轮）
            thread_history=await self._load_thread(thread_id),

            # Layer 3: 用户记忆（借鉴 Gemini Memory）
            user_memory=await self._load_user_memory(user_role),
            # e.g. {"preferred_format": "table", "timezone": "Asia/Shanghai"}
        )
```

### 6.2 @ 引用机制（借鉴 Grafana Assistant）

前端支持在输入框中 `@` 引用上下文实体：

```
用户输入: "@fraud_detection_workflow 最近运行情况怎么样"
         "@sentiment_reviews 知识库里有多少关于物流的差评"

前端解析 @ mention → 传递 context.entities:
  [{ type: "workflow", id: "fraud_detection_workflow" }]
  [{ type: "collection", id: "sentiment_reviews" }]

后端将实体信息注入 skill 的查询上下文
```

---

## 七、前端交互设计 —— 比赛级技术力展示

### 7.1 整体 UI 布局

```
┌─────────────────────────────────────────────────────────┐
│ [Sidebar] │ [Main Content Area]           │ [Artifacts] │
│           │                               │  (滑入)     │
│ 导航菜单   │  ┌───────────────────────────┐│            │
│           │  │  Chat History / Stream     ││ 表格/图表   │
│           │  │  ┌──────────────────────┐  ││ 代码预览    │
│           │  │  │ 🧠 思考中...          │  ││ Trace 瀑布  │
│           │  │  │ > 分析问题意图        │  ││            │
│           │  │  │ > 查询 trace 数据     │  ││            │
│           │  │  │ > 检索知识库          │  ││            │
│           │  │  └──────────────────────┘  ││            │
│           │  │                            ││            │
│           │  │  ┌──────────────────────┐  ││            │
│           │  │  │ ⚡ 调用 trace_skill   │  ││            │
│           │  │  │ ████████████ 100%    │  ││            │
│           │  │  │ ✓ 查询完成 0.3s      │  ││            │
│           │  │  └──────────────────────┘  ││            │
│           │  │                            ││            │
│           │  │  流式 Markdown 回答         ││            │
│           │  │  █ (blinking cursor)       ││            │
│           │  │                            ││            │
│           │  │  [建议问题1] [建议问题2]    ││            │
│           │  └───────────────────────────┘│            │
│           │                               │            │
│           │  ┌───────────────────────────┐│            │
│           │  │ Composer                  ││            │
│           │  │ [@trace] [🧠Think] [🔍]   ││            │
│           │  │ ┌─────────────────────┐   ││            │
│           │  │ │ 请输入问题...        │   ││            │
│           │  │ └─────────────────────┘   ││            │
│           │  └───────────────────────────┘│            │
└─────────────────────────────────────────────────────────┘
```

### 7.2 核心交互组件清单

| 组件 | 借鉴来源 | 技术实现 | 展示亮点 |
|------|---------|---------|---------|
| **Composer** | ChatGPT | auto-resize textarea + context pills + @ mention autocomplete | 自适应高度，弹性动画 |
| **Thinking Chain** | DeepSeek + Claude | 可折叠面板，流式推理文本，脉冲动画 | 推理过程实时可见 |
| **Tool Call Card** | AG-UI + Grafana | 进度条 + 状态指示器 + 耗时标签 | 像 CI/CD pipeline 的步骤卡片 |
| **Stream Markdown** | ChatGPT | AST-based 增量解析，█ blinking cursor，无抖动 | 逐 token 渲染 |
| **Artifacts Panel** | Claude | 右侧滑入面板，支持表格/ECharts 图表/代码高亮/Trace 瀑布图 | 面板内可交互 |
| **Suggestions** | Gemini + Datadog | 底部 pill 按钮，点击自动填入 | 动态生成建议问题 |
| **Mode Switch** | ChatGPT Auto/Think | 顶栏模式切换：Auto / Think(深度推理) / Research(多步调研) | 像 ChatGPT 的模式选择 |
| **AI Transparency** | DeepSeek + 现有实现 | 底部可展开面板：intent / confidence / sources / 耗时 | 不侵入主交互流 |
| **Fact Check** | Gemini "Google It" | 回答末尾的 "查看数据源" 按钮，点击跳转对应管理页面 | 一键跳转验证 |

### 7.3 关键动画与微交互

```
1. Thinking Chain 脉冲动画:
   - 推理开始: 折叠区域滑开（spring 物理动画）
   - 推理中: 文本逐字流入 + 左侧 border 呼吸脉冲（0.8s 周期）
   - 推理结束: 折叠收起（可手动展开查看完整推理链）

2. Tool Call Card 进度:
   - 开始: 卡片从左侧滑入（FLIP 动画）
   - 执行中: 不确定进度条 + shimmer 效果
   - 完成: 进度条填满 + 绿色 ✓ + 耗时标签淡入

3. Artifacts 面板:
   - 触发: 检测到结构化数据时自动滑出（可配置为手动）
   - 动画: 从右侧 translateX(100%) → 0，spring 物理
   - 内容: 表格数据渲染为可排序 DataGrid，图表用 ECharts

4. Markdown 流式渲染:
   - █ blinking cursor (CSS animation, 0.5s)
   - 代码块: 先渲染边框占位，代码流入后自动填充
   - 表格: 完整接收后一次性渲染（避免中间态抖动）
```

---

## 八、知识库集成 —— RAG Skill

### 8.1 双知识库架构

```python
class KBRAGSkill(BaseCopilotSkill):
    """知识库 RAG 查询技能"""

    name = "kb_rag_skill"
    display_name = "知识库检索"
    description = "从舆情知识库或企业知识库中语义检索相关信息"
    mode = {"ops", "biz"}

    async def execute(self, question, context):
        # 1. Embedding 查询向量
        query_vec = embedding_service.embed_query(question)

        # 2. 根据模式选择 collection
        if context.mode == "ops":
            collections = ["sentiment_reviews", "sentiment_entities",
                          "enterprise_documents"]  # 全部可访问
        else:
            # biz 模式只能访问企业知识库
            collections = ["enterprise_documents"]

        # 3. 并行检索 + 合并排序
        results = await asyncio.gather(*[
            self._search_collection(col, query_vec, top_k=5)
            for col in collections
        ])

        # 4. 返回 Artifact（结构化数据）
        yield CopilotEvent(type="artifact_start", artifact_type="search_results")
        yield CopilotEvent(type="artifact_delta", content=merged_results)
        yield CopilotEvent(type="artifact_end")
```

### 8.2 舆情技能（集成已有 SentimentKBService）

```python
class SentimentSkill(BaseCopilotSkill):
    """舆情分析技能"""

    name = "sentiment_skill"
    display_name = "舆情情报查询"
    description = "查询舆情分析结果、情感趋势、实体画像、负面预警"
    mode = {"ops", "biz"}

    async def execute(self, question, context):
        kb = SentimentKBService.get_instance()

        # 语义检索相关评论
        results = await kb.search_similar(question, top_k=10)

        # 按实体检索（如果问题中提到了具体产品/品牌）
        entities = self._extract_entities(question)
        for entity in entities:
            entity_results = await kb.search_by_entity(entity, days=7)
            results["items"].extend(entity_results["items"])

        yield CopilotEvent(type="tool_result", data=results)
```

---

## 九、管理控制台权限配置

### 9.1 数据库表设计

```sql
-- 用户级 Skill 权限覆盖（管理员在控制台配置）
CREATE TABLE copilot_skill_overrides (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(64) NOT NULL,
    skill_name  VARCHAR(64) NOT NULL,
    allowed     BOOLEAN NOT NULL DEFAULT TRUE,  -- true=开放 / false=关闭
    granted_by  VARCHAR(64) NOT NULL,           -- 授权管理员
    granted_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NULL,                  -- 可设过期时间
    UNIQUE KEY uk_user_skill (user_id, skill_name)
);

-- Copilot 对话历史（审计 + 质量改进）
CREATE TABLE copilot_threads (
    id          VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(64) NOT NULL,
    mode        ENUM('ops', 'biz') NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_mode (user_id, mode)
);

CREATE TABLE copilot_messages (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id   VARCHAR(36) NOT NULL,
    role        ENUM('user', 'assistant') NOT NULL,
    content     TEXT NOT NULL,
    intent      VARCHAR(64) NULL,
    skills_used JSON NULL,                      -- ["trace_skill", "kb_rag_skill"]
    confidence  FLOAT NULL,
    feedback    TINYINT NULL,                   -- 1=👍 / -1=👎 / NULL=未评
    elapsed_ms  INT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_thread (thread_id),
    INDEX idx_feedback (feedback)
);
```

### 9.2 管理控制台配置页面

在现有 `ConsoleTeam.vue` 或新增 `ConsoleCopilotConfig.vue` 中：

```
┌──────────────────────────────────────────┐
│  Copilot 权限配置                         │
│                                          │
│  用户: service_agent_01 (客服专员)        │
│  ┌────────────────────────────────────┐  │
│  │ ☑ 知识库检索        默认开放        │  │
│  │ ☑ 舆情情报查询      默认开放        │  │
│  │ ☐ 客户分析          已关闭 ▶ 开放   │  │
│  │ ☐ 销售预测          已关闭          │  │
│  │ ☐ 追踪日志查询      不可配置(角色)  │  │
│  │ ☐ 评测中心查询      不可配置(角色)  │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [保存] [重置]                            │
└──────────────────────────────────────────┘
```

---

## 十、实施路线图（优先级排序）

### Phase 1: 基础架构升级（1-2 周）

| # | 任务 | 产出 |
|---|------|------|
| 1 | SSE 流式端点 `/copilot/stream` | 替代现有 POST `/ops-copilot/ask` |
| 2 | `BaseCopilotSkill` 基类 + `SkillRegistry` | 技能注册框架 |
| 3 | 迁移现有 6 个 handler → 6 个独立 Skill | trace/eval/prompt/release/review/system |
| 4 | LLM function calling 路由替代关键词匹配 | 意图分类准确率 >90% |
| 5 | 错误信息脱敏 + 输入校验 | 修复 P0 安全问题 |
| 6 | 前端 `useCopilotStream` composable | SSE 事件消费框架 |

### Phase 2: 双模 + 权限（1 周）

| # | 任务 | 产出 |
|---|------|------|
| 7 | CopilotMode ops/biz 切换 | 后端 persona + 前端路由感知 |
| 8 | RBAC 权限矩阵 + skill_overrides 表 | 角色级 + 用户级权限 |
| 9 | 管理控制台权限配置 UI | ConsoleCopilotConfig 页面 |
| 10 | 业务空间运营助手路由 + 页面 | BusinessAssistant.vue |

### Phase 3: 高级交互（1-2 周）

| # | 任务 | 产出 |
|---|------|------|
| 11 | Thinking Chain 可折叠面板 | DeepSeek 风格推理链展示 |
| 12 | Tool Call 进度卡片 | AG-UI 风格步骤可视化 |
| 13 | Artifacts 右侧面板 | Claude 风格结构化数据面板 |
| 14 | Stream Markdown 渲染器 | AST 增量解析 + █ cursor |
| 15 | @ 引用 + Context Pills | Grafana 风格上下文引用 |
| 16 | 多轮对话 (thread_id + Redis history) | 解决追问能力缺失 |

### Phase 4: 知识库 + 扩展技能（1-2 周）

| # | 任务 | 产出 |
|---|------|------|
| 17 | kb_rag_skill（双知识库 RAG） | 知识库语义检索技能 |
| 18 | sentiment_skill（舆情分析） | 接入 SentimentKBService |
| 19 | customer_skill / forecast_skill | 业务分析技能 |
| 20 | OCR 小模型技能 | 图片识别分析 |
| 21 | Suggestions 智能建议 | 动态生成后续问题 |
| 22 | 用户反馈机制 👍👎 | 质量数据收集 |

---

## 十一、技术力展示亮点总结

| 维度 | 展示点 | 对标 |
|------|-------|------|
| **架构** | 统一 Skill 注册表 + LLM Function Calling 路由 + AG-UI 流式协议 | LangChain Skills + AG-UI |
| **权限** | 三层 RBAC（角色 → Skill 矩阵 → 用户覆盖） + 运行时动作级校验 | Datadog Bits AI + NeuralTrust |
| **交互** | 思维链透明展示 + 工具调用可视化 + Artifacts 面板 + 流式 Markdown | DeepSeek + Claude + ChatGPT |
| **上下文** | 页面感知注入 + @ 引用 + 多轮历史 + 跨会话记忆 | Grafana Assistant + Gemini Memory |
| **知识** | 双知识库 RAG（舆情 + 企业）+ 向量化语义检索 | 已有 ChromaDB + bge-small-zh |
| **可扩展** | 新功能 = 新 Skill 文件，零修改引擎代码，团队可并行开发 | Plugin 架构最佳实践 |
| **安全** | 错误脱敏 + 只读硬拦截 + 权限运行时校验 + 审计日志 | 企业级安全实践 |
| **工程** | Web Worker AST 解析 + SSE Ring Buffer + FLIP 动画 + 虚拟滚动 | 竞赛级前端工程 |
| **飞书集成** | 长连接事件订阅 + 主动巡检告警 + @mention 智能回复 + 交互式卡片 | 企业级 IM 集成 |
| **记忆** | 三层记忆架构（In-Context → Memory Index → Static Rules）+ 自愈维护 | Claude Code |
| **联动** | 现有 7 大 Service 直接封装为 Skill，GenUI 内嵌交互式 ECharts/表格 | 全链路数据联动 |
| **工作留痕** | 全量对话持久化 + 操作审计 + 历史回溯 + 反馈闭环 | 企业合规最佳实践 |

---

## 十二、现有 Service → Skill 封装方案（数据联动核心）

### 12.1 映射关系

项目已有 7 个成熟的后端 Service，每个 Service 有完整的 Request/Result Pydantic Schema，
**直接复用为 Skill 的数据提供方，零重复开发**：

| 现有 Service | 封装为 Skill | mode | 可视化输出 |
|-------------|-------------|------|-----------|
| `CustomerIntelligenceService` | `customer_intel_skill` | ops + biz | RFM 分群饼图、流失风险 Top-N 表格、CLV 排行柱状图 |
| `SalesForecastService` | `forecast_skill` | ops + biz | 趋势折线图（含置信区间带）、模型对比雷达图 |
| `SentimentIntelligenceService` | `sentiment_skill` | ops + biz | 情感分布环形图、负面主题词云、预警标记 |
| `InventoryOptimizationService` | `inventory_skill` | ops + biz | 紧急补货表格（红色高亮）、EOQ/安全库存对比柱状图 |
| `FraudScoringService` | `fraud_skill` | ops | 风险交易明细表、风险分布热力图 |
| `AssociationMiningService` | `association_skill` | biz | 关联规则网络图（D3.js force-directed）|
| `SentimentKBService` (向量知识库) | `kb_rag_skill` | ops + biz | 检索结果卡片列表 + 相似度评分 |

### 12.2 Skill 封装模式（以 InventorySkill 为例）

```python
# backend/copilot/skills/inventory_skill.py

from backend.copilot.base_skill import BaseCopilotSkill, SkillContext, CopilotEvent
from backend.services.inventory_optimization_service import (
    inventory_optimization_service, InventoryRequest,
)

class InventorySkill(BaseCopilotSkill):
    name = "inventory_skill"
    display_name = "库存优化分析"
    description = "查询库存状态、计算安全库存和EOQ、识别紧急补货SKU、生成补货建议"
    required_roles = {"super_admin", "platform_admin", "business_admin", "ops_analyst"}
    mode = {"ops", "biz"}
    parameters_schema = {
        "type": "object",
        "properties": {
            "store_id": {"type": "string", "description": "门店ID，可选"},
            "action": {
                "type": "string",
                "enum": ["overview", "urgent_only", "specific_sku"],
                "description": "查询类型",
            },
        },
    }

    async def execute(self, question: str, context: SkillContext):
        # 1. 构建请求（LLM 已从 question 提取参数）
        request = InventoryRequest(
            store_id=context.tool_args.get("store_id"),
            lead_time_days=7.0,
        )

        # 2. 调用已有 Service（复用，不重写）
        result = inventory_optimization_service.optimize(request)

        # 3. 输出结构化数据 → 前端渲染为 GenUI
        yield CopilotEvent(
            type="artifact_start",
            artifact_type="inventory_table",
            metadata={
                "title": f"库存优化建议 — {result.total_skus} 支SKU",
                "component": "InventoryArtifact",  # 前端动态挂载的组件名
            }
        )
        yield CopilotEvent(
            type="artifact_delta",
            content={
                "summary": {
                    "total_skus": result.total_skus,
                    "urgent_count": result.urgent_count,
                    "total_reorder_qty": result.total_reorder_qty,
                },
                "recommendations": [r.model_dump() for r in result.recommendations[:20]],
            }
        )
        yield CopilotEvent(type="artifact_end")

        # 4. 如果有紧急 SKU，触发 Action 建议
        if result.urgent_count > 0:
            yield CopilotEvent(
                type="suggestions",
                items=[
                    {
                        "type": "action",
                        "label": f"📢 通知采购群: {result.urgent_count} 支SKU需紧急补货",
                        "action": "feishu_notify",
                        "payload": {
                            "group": "procurement",
                            "message": f"⚠️ 库存预警: {result.urgent_count} 支SKU库存低于安全水位，建议补货量 {result.total_reorder_qty:,}",
                            "data_ref": "inventory_urgent",
                        },
                    },
                    {"type": "question", "label": "哪些SKU预计3天内缺货？"},
                    {"type": "question", "label": "按门店分组查看库存状态"},
                ],
            )

        # 5. yield 工具结果供 LLM 综合回答
        yield CopilotEvent(type="tool_result", data=result.model_dump())
```

### 12.3 前端 GenUI 联动 —— Artifact 动态组件挂载

```vue
<!-- components/copilot/artifacts/InventoryArtifact.vue -->
<template>
  <div class="artifact-inventory">
    <!-- 摘要卡片 -->
    <div class="artifact-summary">
      <div class="stat-item" :class="{ urgent: data.summary.urgent_count > 0 }">
        <span class="stat-value">{{ data.summary.urgent_count }}</span>
        <span class="stat-label">紧急补货</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ data.summary.total_skus }}</span>
        <span class="stat-label">总SKU</span>
      </div>
    </div>

    <!-- ECharts 图表（安全库存 vs 当前库存对比） -->
    <BarChart :data="chartData" />

    <!-- 交互式表格（可排序、筛选） -->
    <DataGrid
      :columns="columns"
      :rows="data.recommendations"
      :highlight-row="row => row.urgent"
    />
  </div>
</template>
```

**GenUI 组件注册表**（前端根据 `artifact_type` 动态挂载对应 Vue 组件）：

```javascript
// copilot/artifact-registry.js
const ARTIFACT_COMPONENTS = {
  inventory_table:    () => import('./artifacts/InventoryArtifact.vue'),
  forecast_chart:     () => import('./artifacts/ForecastArtifact.vue'),
  sentiment_overview: () => import('./artifacts/SentimentArtifact.vue'),
  customer_insight:   () => import('./artifacts/CustomerArtifact.vue'),
  fraud_detail:       () => import('./artifacts/FraudArtifact.vue'),
  association_graph:  () => import('./artifacts/AssociationArtifact.vue'),
  search_results:     () => import('./artifacts/SearchResultsArtifact.vue'),
  generic_table:      () => import('./artifacts/GenericTableArtifact.vue'),
  generic_chart:      () => import('./artifacts/GenericChartArtifact.vue'),
}

export function resolveArtifact(type) {
  return ARTIFACT_COMPONENTS[type] || ARTIFACT_COMPONENTS.generic_table
}
```

---

## 十三、三层记忆系统 —— 借鉴 Claude Code 源码架构

### 13.1 架构总览

```
Claude Code 三层记忆              本系统映射
─────────────────────           ──────────────────────
Layer 1: In-Context             → Redis Thread History（最近 N 轮对话）
  (session scratchpad)            + Page Context（当前页面状态）

Layer 2: memory.md              → copilot_memory 表（DB 持久化）
  (pointer index → domain files)  + 按 domain 分区的记忆条目
  (self-healing, agent writes)    + Agent 可自主 CRUD（工具调用）

Layer 3: CLAUDE.md              → copilot_rules 表 / 静态配置
  (stable project-level context)  + 管理员配置的系统级指令
  (loaded every session)          + 每次会话启动自动加载
```

### 13.2 数据库设计

```sql
-- Layer 2: 动态记忆（Agent 自主维护）
CREATE TABLE copilot_memory (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id      VARCHAR(64) NOT NULL,
    domain       VARCHAR(64) NOT NULL,        -- 'user_preferences' | 'business_context' | 'decisions' | 'patterns'
    title        VARCHAR(256) NOT NULL,
    content      TEXT NOT NULL,               -- Markdown 格式
    importance   FLOAT DEFAULT 0.5,           -- 0~1, 用于检索排序
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active    BOOLEAN DEFAULT TRUE,        -- 软删除
    INDEX idx_user_domain (user_id, domain),
    INDEX idx_importance (importance DESC)
);

-- Layer 3: 静态规则（管理员维护）
CREATE TABLE copilot_rules (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope        ENUM('global', 'ops', 'biz') NOT NULL,  -- 适用范围
    title        VARCHAR(256) NOT NULL,
    content      TEXT NOT NULL,
    priority     INT DEFAULT 0,               -- 高优先级先加载
    created_by   VARCHAR(64) NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_scope (scope, priority DESC)
);
```

### 13.3 记忆工具（Agent 自主维护）

```python
class MemorySkill(BaseCopilotSkill):
    """记忆管理技能 — Agent 用工具调用来读写自己的记忆"""

    name = "memory_skill"
    display_name = "记忆管理"
    description = "保存、检索、更新用户偏好和业务上下文记忆"
    mode = {"ops", "biz"}

    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "update", "search"],
            },
            "domain": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "query": {"type": "string"},   # search 时用
        },
        "required": ["action"],
    }

    async def execute(self, question, context):
        action = context.tool_args["action"]

        if action == "read":
            memories = await self._read_memories(
                context.user_id, context.tool_args.get("domain")
            )
            yield CopilotEvent(type="tool_result", data={"memories": memories})

        elif action == "write":
            await self._write_memory(
                user_id=context.user_id,
                domain=context.tool_args["domain"],
                title=context.tool_args["title"],
                content=context.tool_args["content"],
            )
            yield CopilotEvent(type="tool_result", data={"status": "saved"})

        elif action == "search":
            # 语义检索：embedding 相似度匹配
            results = await self._semantic_search(
                context.user_id, context.tool_args["query"]
            )
            yield CopilotEvent(type="tool_result", data={"results": results})
```

### 13.4 自愈机制

```python
class ContextManager:
    """每次会话启动时的上下文构建"""

    async def build(self, thread_id, page_context, user_id, mode):
        # Layer 3: 静态规则（每次必加载）
        rules = await self._load_rules(mode)     # SELECT * FROM copilot_rules WHERE scope IN ('global', mode)

        # Layer 2: 用户记忆（按 importance 排序，取 top-K）
        memories = await self._load_top_memories(user_id, top_k=10)

        # Layer 1: 对话历史
        history = await self._load_thread(thread_id)  # Redis, 最近 5 轮

        # 注入 system prompt
        system_prompt = self._compose_system_prompt(
            rules=rules,           # Layer 3 → 系统指令部分
            memories=memories,     # Layer 2 → "你记得的关于这个用户的信息"
            page_context=page_context,  # Layer 1 → 当前页面
        )

        return SkillContext(
            system_prompt=system_prompt,
            thread_history=history,
            user_id=user_id,
            mode=mode,
            page_context=page_context,
        )

    async def reconcile(self, user_id):
        """定期调和（借鉴 Claude Code 的 reconciliation step）
        由调度器每周执行一次，清理过时记忆"""
        all_memories = await self._load_all_memories(user_id)
        # LLM 审阅是否有矛盾/过时条目
        prompt = f"以下是用户 {user_id} 的记忆条目，请标记矛盾或过时的:\n{all_memories}"
        result = await llm.ainvoke(prompt)
        # 根据 LLM 建议软删除过时条目
        ...
```

---

## 十四、对话持久化 + 历史功能 + 工作留痕

### 14.1 完整数据模型

```sql
-- 对话线程（已在 V5 定义，此处补充字段）
CREATE TABLE copilot_threads (
    id           VARCHAR(36) PRIMARY KEY,       -- UUID
    user_id      VARCHAR(64) NOT NULL,
    mode         ENUM('ops', 'biz') NOT NULL,
    title        VARCHAR(256) NULL,             -- 第一条消息自动生成标题
    status       ENUM('active', 'archived', 'deleted') DEFAULT 'active',
    summary      TEXT NULL,                     -- LLM 自动生成的对话摘要
    page_origin  VARCHAR(256) NULL,             -- 发起对话时所在页面
    tags         JSON NULL,                     -- 标签 ["库存", "紧急"]
    pinned       BOOLEAN DEFAULT FALSE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_mode (user_id, mode, status),
    INDEX idx_updated (updated_at DESC)
);

-- 对话消息（完整审计）
CREATE TABLE copilot_messages (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id    VARCHAR(36) NOT NULL,
    role         ENUM('user', 'assistant', 'system', 'tool') NOT NULL,
    content      TEXT NOT NULL,
    -- 助手消息元数据
    intent       VARCHAR(64) NULL,
    skills_used  JSON NULL,                     -- ["inventory_skill", "forecast_skill"]
    confidence   FLOAT NULL,
    thinking     TEXT NULL,                     -- 思维链内容（完整保存）
    artifacts    JSON NULL,                     -- [{"type": "inventory_table", "data": {...}}]
    tool_calls   JSON NULL,                     -- 工具调用详情
    suggestions  JSON NULL,                     -- 建议的后续问题
    -- 操作审计
    actions_taken JSON NULL,                    -- [{"type":"feishu_notify","target":"procurement","status":"sent"}]
    -- 反馈
    feedback     TINYINT NULL,                  -- 1=👍 -1=👎
    feedback_text VARCHAR(512) NULL,            -- 用户反馈文本
    -- 性能
    elapsed_ms   INT NULL,
    token_usage  JSON NULL,                     -- {"input": 1200, "output": 800}
    -- 来源标记
    source       ENUM('web', 'feishu', 'api', 'scheduler') DEFAULT 'web',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_thread (thread_id, created_at),
    INDEX idx_feedback (feedback),
    INDEX idx_source (source)
);

-- 操作日志（不可变审计表）
CREATE TABLE copilot_action_log (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id    VARCHAR(36) NOT NULL,
    message_id   BIGINT NOT NULL,
    user_id      VARCHAR(64) NOT NULL,
    action_type  VARCHAR(64) NOT NULL,          -- 'feishu_notify' | 'export_report' | ...
    target       VARCHAR(256) NOT NULL,         -- 目标（群ID/用户ID/文件路径）
    payload      JSON NULL,
    status       ENUM('pending', 'approved', 'executed', 'failed', 'rejected') NOT NULL,
    result       JSON NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_at  DATETIME NULL,
    INDEX idx_thread (thread_id),
    INDEX idx_user (user_id, created_at DESC)
);
```

### 14.2 前端历史面板

```
┌──────────────────────────────────────────┐
│  📋 对话历史                 🔍 搜索     │
│                                          │
│  📌 置顶                                 │
│  ┌─────────────────────────────────────┐ │
│  │ 库存紧急补货分析              2h前   │ │
│  │ inventory_skill · 3条消息           │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  今天                                    │
│  ┌─────────────────────────────────────┐ │
│  │ 舆情负面趋势查询              4h前   │ │
│  │ sentiment_skill · 5条消息           │ │
│  │ [已通知飞书群] [👍]                 │ │
│  └─────────────────────────────────────┘ │
│  ┌─────────────────────────────────────┐ │
│  │ 客户流失风险排查              6h前   │ │
│  │ customer_intel_skill · 8条消息      │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  昨天                                    │
│  ...                                     │
└──────────────────────────────────────────┘
```

### 14.3 持久化时序

```
用户发送消息
  │
  ├→ 1. 立即写入 copilot_messages (role=user)
  ├→ 2. 写入 Redis thread cache (最近 5 轮)
  │
  ├→ CopilotEngine 处理中...
  │   ├→ 思维链内容 → SSE 流给前端
  │   ├→ 工具调用结果 → SSE 流给前端
  │   └→ 回答内容 → SSE 流给前端
  │
  ├→ 3. 流完成后写入 copilot_messages (role=assistant, 含完整元数据)
  │     - thinking, intent, skills_used, artifacts, suggestions, elapsed_ms
  │
  ├→ 4. 如有 Action 执行 → 写入 copilot_action_log
  │
  └→ 5. 异步：首条消息时 LLM 生成 thread title
       第 N 条消息时更新 thread summary
```

---

## 十五、可执行 Action 系统 —— 从只读到可操作

### 15.1 Action 框架

助手不再是只读诊断，而是具备**受控执行能力**。所有 Action 遵循 **Human-in-the-Loop** 原则：

```python
class ActionType(str, Enum):
    FEISHU_NOTIFY      = "feishu_notify"       # 发飞书消息
    FEISHU_CARD        = "feishu_card"         # 发飞书交互式卡片
    EXPORT_REPORT      = "export_report"       # 导出报表
    CREATE_ALERT_RULE  = "create_alert_rule"   # 创建告警规则
    SCHEDULE_TASK      = "schedule_task"       # 创建定时任务

# 风险等级定义
ACTION_RISK_LEVELS = {
    "feishu_notify":     "low",      # 低风险 → 用户确认即可
    "feishu_card":       "low",
    "export_report":     "low",
    "create_alert_rule": "medium",   # 中风险 → 需二次确认
    "schedule_task":     "high",     # 高风险 → 需管理员审批
}
```

### 15.2 SSE 交互式确认流

```
助手: 发现 12 支SKU库存低于安全水位，建议紧急补货。

  ┌──────────────────────────────────────────────┐
  │ 📢 建议操作: 通知采购群                       │
  │                                              │
  │ 目标: 飞书「采购协调群」                       │
  │ 内容: ⚠️ 库存预警: 12支SKU需紧急补货，        │
  │       建议补货总量 3,450 件                    │
  │                                              │
  │ [✅ 发送通知]  [✏️ 编辑内容]  [❌ 取消]        │
  └──────────────────────────────────────────────┘
```

前端收到 `suggestions` 事件中 `type: "action"` 的条目后，渲染为交互式确认卡片。
用户点击确认 → POST `/copilot/action/execute`：

```python
@router.post("/copilot/action/execute")
async def execute_action(body: ActionExecuteRequest, request: Request):
    """用户确认后执行 Action"""
    # 1. 权限校验
    user_role = request.state.user_role
    if not can_execute_action(user_role, body.action_type):
        raise AppError(403, "权限不足")

    # 2. 风险等级校验
    risk = ACTION_RISK_LEVELS[body.action_type]
    if risk == "high" and user_role not in {"super_admin", "platform_admin"}:
        # 高风险操作需要管理员审批
        await create_approval_request(body, request.state.user_id)
        return {"status": "pending_approval"}

    # 3. 执行 Action
    result = await action_executor.execute(body)

    # 4. 记录审计日志
    await log_action(body, result, request.state.user_id)

    return result
```

---

## 十六、飞书集成 —— 长连接 + 主动巡检 + @回复

### 16.1 技术方案

飞书开放平台提供 **WebSocket 长连接模式**，通过 `lark-oapi` Python SDK 与飞书建立全双工通道，
**无需公网 IP、无需内网穿透**，开发接入成本极低。

```
飞书开放平台
    │
    │ WebSocket 长连接 (lark-oapi SDK)
    │
    ▼
┌──────────────────────────────────────┐
│     FeishuBridge (后端常驻服务)       │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ EventDispatcher              │    │
│  │  ├ im.message.receive_v1     │────┼→ @提及消息 → CopilotEngine
│  │  ├ card.action.trigger       │────┼→ 卡片按钮回调 → ActionExecutor
│  │  └ custom events             │    │
│  └──────────────────────────────┘    │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ MessageSender                │    │
│  │  ├ send_text()               │    │  ← CopilotEngine/Scheduler
│  │  ├ send_interactive_card()   │    │  ← 告警/巡检结果
│  │  └ reply_message()           │    │  ← @回复
│  └──────────────────────────────┘    │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ GroupRegistry                │    │  飞书群 ↔ 业务域映射
│  │  procurement_group: "oc_xxx" │    │
│  │  ops_alert_group:   "oc_yyy"│    │
│  │  biz_daily_group:   "oc_zzz"│    │
│  └──────────────────────────────┘    │
└──────────────────────────────────────┘
```

### 16.2 SDK 集成代码

```python
# backend/integrations/feishu/bridge.py

import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    CreateMessageRequest, CreateMessageRequestBody,
)

class FeishuBridge:
    """飞书长连接桥接器 — 在 FastAPI 启动时以 daemon 线程运行"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

        # API Client（用于主动发消息）
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        # 事件分发器
        self.event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._on_message_receive) \
            .build()

    def start(self):
        """启动长连接（daemon 线程，不阻塞主进程）"""
        ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=self.event_handler,
            log_level=lark.LogLevel.INFO,
        )
        thread = threading.Thread(target=ws_client.start, daemon=True)
        thread.start()
        logger.info("[FeishuBridge] WebSocket 长连接已启动")

    def _on_message_receive(self, data: P2ImMessageReceiveV1):
        """收到飞书消息（含 @提及）"""
        event = data.event
        msg_type = event.message.message_type      # "text" / "image" / ...
        chat_id  = event.message.chat_id           # 群聊 ID
        sender   = event.sender.sender_id.user_id  # 发送者

        # 检查是否 @了机器人
        if not self._is_mentioned(event):
            return

        # 提取纯文本（去掉 @mention 标记）
        question = self._extract_text(event.message)

        # 异步调用 CopilotEngine（3 秒内必须返回，否则飞书超时）
        # 先立即回复 "思考中..."，然后异步处理
        self._reply_thinking(event.message.message_id, chat_id)

        # 异步执行引擎
        asyncio.create_task(
            self._process_and_reply(question, chat_id, sender, event.message.message_id)
        )

    async def _process_and_reply(self, question, chat_id, sender, reply_msg_id):
        """异步处理问题并回复"""
        engine = CopilotEngine()
        result_parts = []

        async for event in engine.run(
            question=question,
            mode=self._resolve_mode(chat_id),  # 根据群映射决定 ops/biz
            user_role=self._resolve_role(sender),
            thread_id=f"feishu_{chat_id}",
            page_context={"source": "feishu", "chat_id": chat_id},
        ):
            if event.type == "text_delta":
                result_parts.append(event.content)
            elif event.type == "suggestions":
                # 建议操作 → 飞书交互式卡片按钮
                pass

        # 组装最终回复
        answer = "".join(result_parts)
        self._send_reply(chat_id, reply_msg_id, answer)

    # ── 主动发消息 ──

    def send_to_group(self, chat_id: str, content: str, msg_type: str = "interactive"):
        """主动向飞书群发送消息"""
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            ).build()

        response = self.client.im.v1.message.create(request)
        if not response.success():
            logger.error(f"[FeishuBridge] 发送失败: {response.code} {response.msg}")
        return response

    def send_alert_card(self, chat_id: str, title: str, content: str,
                        severity: str = "warning", actions: list = None):
        """发送告警交互式卡片"""
        card = self._build_alert_card(title, content, severity, actions)
        self.send_to_group(chat_id, card, msg_type="interactive")
```

### 16.3 主动巡检系统

```python
# backend/integrations/feishu/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

class CopilotPatrolScheduler:
    """
    Copilot 主动巡检调度器 —— 每分钟扫描业务指标，异常时主动推送飞书告警。
    运维助手扫描系统健康，运营助手扫描业务指标。
    """

    def __init__(self, feishu: FeishuBridge, engine: CopilotEngine):
        self.feishu = feishu
        self.engine = engine
        self.scheduler = AsyncIOScheduler()

    def start(self):
        # ── 运维巡检（每分钟） ──
        self.scheduler.add_job(
            self._patrol_ops,
            'interval', minutes=1,
            id='ops_patrol', name='运维巡检',
        )
        # ── 运营巡检（每 5 分钟） ──
        self.scheduler.add_job(
            self._patrol_biz,
            'interval', minutes=5,
            id='biz_patrol', name='运营巡检',
        )
        # ── 记忆调和（每周一次） ──
        self.scheduler.add_job(
            self._reconcile_memory,
            'cron', day_of_week='mon', hour=3,
            id='memory_reconcile',
        )
        self.scheduler.start()

    async def _patrol_ops(self):
        """运维巡检: Agent 自动跑错误率、延迟、失败 run 等检查"""
        checks = [
            {"skill": "trace_skill",   "question": "过去5分钟有没有失败的run？"},
            {"skill": "system_skill",  "question": "当前系统健康状态？"},
        ]
        for check in checks:
            try:
                result = await self.engine.run_single_skill(
                    skill_name=check["skill"],
                    question=check["question"],
                    mode="ops",
                    user_role="system_patrol",      # 特殊系统角色
                    source="scheduler",
                )
                if self._is_anomaly(result):
                    # 发送告警到运维群
                    self.feishu.send_alert_card(
                        chat_id=GROUP_REGISTRY["ops_alert"],
                        title="🚨 运维巡检异常",
                        content=result.summary,
                        severity="error",
                        actions=[
                            {"label": "查看详情", "url": f"{WEB_BASE}/console/traces"},
                            {"label": "静默1h", "action": "silence_1h"},
                        ],
                    )
                    # 持久化巡检记录
                    await self._save_patrol_log("ops", check, result)
            except Exception as e:
                logger.error(f"[Patrol] ops check failed: {e}")

    async def _patrol_biz(self):
        """运营巡检: 库存预警、舆情负面飙升、销售异常"""
        checks = [
            {
                "skill": "inventory_skill",
                "question": "有没有SKU库存低于安全水位？",
                "alert_condition": lambda r: r.get("urgent_count", 0) > 0,
                "group": "procurement",
                "title": "📦 库存预警",
            },
            {
                "skill": "sentiment_skill",
                "question": "当前负面舆情占比是否超过30%？",
                "alert_condition": lambda r: r.get("negative_alert", False),
                "group": "biz_daily",
                "title": "📊 舆情预警",
            },
        ]
        for check in checks:
            try:
                result = await self.engine.run_single_skill(
                    skill_name=check["skill"],
                    question=check["question"],
                    mode="biz",
                    user_role="system_patrol",
                    source="scheduler",
                )
                if check["alert_condition"](result):
                    self.feishu.send_alert_card(
                        chat_id=GROUP_REGISTRY[check["group"]],
                        title=check["title"],
                        content=result.summary,
                        severity="warning",
                    )
            except Exception as e:
                logger.error(f"[Patrol] biz check failed: {e}")
```

### 16.4 飞书交互式卡片（按钮回调）

当飞书群内用户点击告警卡片上的按钮时，触发回调：

```python
def _on_card_action(self, data: P2CardActionTrigger):
    """飞书卡片按钮回调"""
    action = data.event.action
    action_value = action.value  # {"action": "silence_1h", "alert_id": "xxx"}

    if action_value["action"] == "silence_1h":
        # 静默该告警 1 小时
        self.scheduler.silence_alert(action_value["alert_id"], hours=1)
        return {"toast": {"type": "info", "content": "已静默 1 小时"}}

    elif action_value["action"] == "view_detail":
        # 返回详情链接
        return {"toast": {"type": "info", "content": "请在浏览器中查看"}}

    elif action_value["action"] == "ask_copilot":
        # 在飞书中追问 Copilot
        question = action_value.get("question", "详细分析这个问题")
        asyncio.create_task(self._process_and_reply(
            question, data.event.context.open_chat_id, ...
        ))
        return {"toast": {"type": "info", "content": "正在分析..."}}
```

### 16.5 飞书群 ↔ 业务域映射配置

```sql
-- 飞书群映射（管理控制台可配置）
CREATE TABLE feishu_group_mapping (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    group_name   VARCHAR(64) NOT NULL,           -- 'procurement' | 'ops_alert' | 'biz_daily'
    chat_id      VARCHAR(128) NOT NULL,          -- 飞书群 chat_id
    mode         ENUM('ops', 'biz') NOT NULL,
    patrol_enabled BOOLEAN DEFAULT TRUE,
    description  VARCHAR(256) NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_group_name (group_name)
);
```

### 16.6 FastAPI 启动集成

```python
# backend/main.py（lifespan 中添加）

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... 现有启动逻辑 ...

    # 启动飞书长连接
    feishu_bridge = FeishuBridge(
        app_id=settings.FEISHU_APP_ID,
        app_secret=settings.FEISHU_APP_SECRET,
    )
    feishu_bridge.start()
    app.state.feishu = feishu_bridge

    # 启动主动巡检调度器
    patrol = CopilotPatrolScheduler(feishu_bridge, copilot_engine)
    patrol.start()
    app.state.patrol = patrol

    yield

    # 关闭
    patrol.scheduler.shutdown()
```

---

## 十七、全景数据流图

```
                        ┌─────────────────────┐
                        │   飞书群聊            │
                        │  @mention / 卡片回调  │
                        └─────────┬───────────┘
                                  │ WebSocket 长连接
                                  ▼
┌──────────────┐    ┌─────────────────────────────┐    ┌──────────────┐
│  前端 Web    │    │      FeishuBridge            │    │  Scheduler   │
│ (SSE Stream) │    │  (EventDispatcher)           │    │  (APScheduler│
│              │    │                              │    │   主动巡检)   │
└──────┬───────┘    └──────────┬──────────────────┘    └──────┬───────┘
       │                       │                              │
       │    POST /copilot/stream (SSE)                        │
       └───────────┬───────────┘                              │
                   ▼                                          │
       ┌───────────────────────────────────────────┐          │
       │            CopilotEngine                  │◄─────────┘
       │                                           │
       │  ┌─────────────────────────────────────┐  │
       │  │         ContextManager               │  │
       │  │  Layer 3: copilot_rules (静态)       │  │
       │  │  Layer 2: copilot_memory (动态)      │  │
       │  │  Layer 1: Redis thread + page ctx    │  │
       │  └─────────────────────────────────────┘  │
       │                                           │
       │  ┌─────────────────────────────────────┐  │
       │  │  LLM Router (qwen-plus)             │  │
       │  │  Function Calling → Skill Selection │  │
       │  └─────────────┬───────────────────────┘  │
       │                │                          │
       │  ┌─────────────▼───────────────────────┐  │
       │  │       SkillRegistry                  │  │
       │  │  ┌──────────┐ ┌──────────┐          │  │
       │  │  │inventory │ │sentiment │ ...       │  │
       │  │  │_skill    │ │_skill    │          │  │
       │  │  └────┬─────┘ └────┬─────┘          │  │
       │  │       │            │                 │  │
       │  │  ┌────▼─────┐ ┌───▼──────┐          │  │
       │  │  │Inventory │ │Sentiment │ ...       │  │ ← 复用现有 Service
       │  │  │Service   │ │Service   │          │  │
       │  │  └──────────┘ └──────────┘          │  │
       │  └─────────────────────────────────────┘  │
       │                                           │
       │  ┌─────────────────────────────────────┐  │
       │  │       ActionExecutor                 │  │
       │  │  feishu_notify → FeishuBridge        │  │
       │  │  export_report → ReportService       │  │
       │  │  create_alert  → AlertService        │  │
       │  └─────────────────────────────────────┘  │
       │                                           │
       └───────────────────────────────────────────┘
                   │
                   ▼
       ┌───────────────────────────────────────────┐
       │         Persistence Layer                  │
       │  copilot_threads + copilot_messages        │ ← 全量持久化
       │  copilot_action_log                        │ ← 操作审计
       │  copilot_memory                            │ ← 记忆
       │  copilot_rules                             │ ← 规则
       │  feishu_group_mapping                      │ ← 群映射
       └───────────────────────────────────────────┘
```

---

## 十八、更新后的实施路线图

### Phase 1: 核心引擎 + Skill 封装（1-2 周）
1. `BaseCopilotSkill` 基类 + `SkillRegistry`
2. 迁移现有 7 个 Service → 7 个 Skill（inventory/sentiment/forecast/customer/fraud/association/kb_rag）
3. SSE 流式端点 `/copilot/stream`
4. LLM Function Calling 路由
5. 前端 `useCopilotStream` composable

### Phase 2: 持久化 + 历史 + 权限（1 周）
6. 建表 `copilot_threads` + `copilot_messages` + `copilot_action_log`
7. 对话持久化中间件（每条消息写 DB + Redis）
8. 前端历史面板 + 对话恢复
9. RBAC 权限矩阵 + `copilot_skill_overrides`
10. 管理控制台权限配置 UI

### Phase 3: 记忆 + GenUI + 交互（1-2 周）
11. 三层记忆系统 (`copilot_memory` + `copilot_rules`)
12. `MemorySkill`（Agent 自主记忆管理）
13. Thinking Chain + Tool Call Cards 前端组件
14. Artifacts Panel + GenUI 组件注册表
15. 7 个 Artifact 组件（每个 Skill 对应一个可视化）

### Phase 4: 飞书 + 主动巡检 + Action（1-2 周）
16. `FeishuBridge` 长连接集成
17. @mention 解析 + 异步回复
18. `CopilotPatrolScheduler` 主动巡检
19. 飞书交互式卡片（告警 + 按钮回调）
20. `ActionExecutor` + 确认流 + 审计日志
21. `feishu_group_mapping` 管理 UI

### Phase 5: 打磨 + 极致体验（1 周）
22. 对话搜索（全文 + 语义）
23. 反馈闭环（👍👎 + 质量看板）
24. 记忆调和定时任务
25. 飞书消息卡片模板美化
26. 端到端集成测试
