-- ═══════════════════════════════════════════════════════════════
-- R5-1: copilot_memory 表扩展访问统计字段
-- ═══════════════════════════════════════════════════════════════
-- 目的:
--   让 FreshnessEngine 的 frequency 维度真实可用：
--   每次 MemorySkill 读取/搜索记忆时，对应条目 access_count += 1，
--   记忆调和（reconcile）按新鲜度综合分（recency + importance + frequency）
--   做衰减/归档决策，避免只基于时间的粗粒度决策。
--
-- 兼容:
--   - access_count 带 NOT NULL DEFAULT 0，既有行自动初始化为 0
--   - last_accessed_at 可空（NULL）表示未访问过
--   - 索引 idx_access_count 加速"按访问频次排序"的后台分析查询
--
-- 回滚:
--   ALTER TABLE copilot_memory DROP COLUMN access_count, DROP COLUMN last_accessed_at;
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE copilot_memory
    ADD COLUMN access_count INT NOT NULL DEFAULT 0
        COMMENT '访问次数（FreshnessEngine frequency 输入）' AFTER importance,
    ADD COLUMN last_accessed_at DATETIME NULL
        COMMENT '最后一次访问时间' AFTER access_count,
    ADD INDEX idx_memory_access (access_count),
    ADD INDEX idx_memory_last_accessed (last_accessed_at);
