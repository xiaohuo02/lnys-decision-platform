-- ═══════════════════════════════════════════════════════════════
-- §3.4 反馈闭环 · kb_feedback 表
-- ═══════════════════════════════════════════════════════════════
-- 目的:
--   线上一旦运行，不断涌现新的 bad case（错误回答、幻觉、该拒没拒）。
--   本表负责记录用户对 KB 搜索 / RAG 答案的显式反馈（👍/👎），
--   后续 Phase γ 接入 self-monitor 自动打标 + 周报生成。
--
-- 与既有 copilot_messages.feedback 的关系:
--   - copilot_messages.feedback 仅覆盖 Copilot 对话场景（biz/ops mode）
--   - kb_feedback 覆盖业务前台直搜、admin 端 KB 预览、RAG 答案卡片等
--     非 Copilot 路径，避免对 copilot_messages 表过度耦合。
--
-- 索引:
--   - idx_rating_time:    按评分/时间检索 bad case
--   - idx_kb_time:        按知识库聚合（哪个库被吐槽最多）
--   - idx_user_trace_uniq:同一用户对同一 trace 24h 内幂等（业务层 upsert）
--   - idx_source:         区分来源场景（biz_kb / admin_kb / copilot_biz_rag）
--
-- 回滚:
--   DROP TABLE IF EXISTS kb_feedback;
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS kb_feedback (
    feedback_id   BIGINT       AUTO_INCREMENT PRIMARY KEY,
    trace_id      VARCHAR(64)  DEFAULT NULL COMMENT '关联到原 answer/search 的 trace_id',
    user_id       VARCHAR(100) NOT NULL     COMMENT '反馈用户 username',
    kb_id         CHAR(36)     DEFAULT NULL COMMENT '命中的主 kb_id（取 hits[0].kb_id）',
    query         TEXT         NOT NULL     COMMENT '原始 query',
    answer        TEXT         DEFAULT NULL COMMENT 'RAG 答案文本（仅 RAG 场景填）',
    citations     JSON         DEFAULT NULL COMMENT 'hits 引用 [{document_id,chunk_id,kb_id,title,score}]',
    rating        TINYINT      NOT NULL     COMMENT '1=👍  -1=👎  0=中性',
    rating_reason VARCHAR(50)  DEFAULT NULL COMMENT 'inaccurate/irrelevant/outdated/incomplete/other',
    free_text     VARCHAR(1000) DEFAULT NULL COMMENT '用户自由文本',
    source        VARCHAR(20)  NOT NULL DEFAULT 'biz_kb'
                                        COMMENT 'biz_kb / admin_kb / copilot_biz_rag / api_external',
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    INDEX idx_rating_time (rating, created_at),
    INDEX idx_kb_time     (kb_id, created_at),
    INDEX idx_user_trace  (user_id, trace_id),
    INDEX idx_source      (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='§3.4 KB 用户反馈表（显式 + 后续 self-monitor 自动）';

-- 修复历史 (v2.5 -> v2.6)：旧版 r7 创建时表级 utf8mb4_unicode_ci，
-- 与 kb_libraries（server 默认 utf8mb4_0900_ai_ci）JOIN 报
-- "Illegal mix of collations"。本 ALTER 幂等地把表对齐到一致的 server 默认。
ALTER TABLE kb_feedback
    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
