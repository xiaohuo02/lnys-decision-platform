-- ═══════════════════════════════════════════════════════════════
-- R6-5: eval_verdict + policy_change_log 持久化表
-- ═══════════════════════════════════════════════════════════════
-- 目的:
--   PeriodicEvaluator 产出的 EvalVerdict 和 PolicyAdjuster 产生的
--   PolicyChange 默认放在内存环形缓冲里（单 worker 丢失风险 + 重启清零）。
--   本 migration 为它们提供持久化，让 admin 面板可以跨 worker / 跨重启
--   查询历史闭环数据（telemetry 产生的建议 + policy 变更 + 回滚）。
--
-- 兼容:
--   - 表不存在时, Evaluator/Adjuster 仍只写内存（best-effort 写表）
--   - 索引覆盖最常见的 admin 查询: 按 metric / status / 时间范围
--
-- 回滚:
--   DROP TABLE IF EXISTS eval_verdict;
--   DROP TABLE IF EXISTS policy_change_log;
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS eval_verdict (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    metric             VARCHAR(64)  NOT NULL COMMENT '指标名，如 model_latency_p95_5m',
    subject            VARCHAR(128) NOT NULL COMMENT '主体，如 model name / skill name / global',
    `value`            DOUBLE       NOT NULL COMMENT '实测值',
    threshold_warning  DOUBLE       NOT NULL DEFAULT 0 COMMENT '警告阈值',
    threshold_critical DOUBLE       NOT NULL DEFAULT 0 COMMENT '严重阈值',
    status             VARCHAR(16)  NOT NULL COMMENT 'normal / warning / critical / insufficient',
    sample_size        INT          NOT NULL DEFAULT 0,
    window_seconds     INT          NOT NULL DEFAULT 300,
    recommendation     VARCHAR(128) NOT NULL DEFAULT '' COMMENT '给 PolicyAdjuster 的建议 key',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_metric_created  (metric, created_at),
    KEY idx_status_created  (status, created_at),
    KEY idx_subject_created (subject, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='R6-5 周期评测产出的 verdict';


CREATE TABLE IF NOT EXISTS policy_change_log (
    change_id       VARCHAR(36)   NOT NULL COMMENT 'uuid, 同 PolicyChange.change_id',
    policy_key      VARCHAR(64)   NOT NULL COMMENT '如 model.default_name',
    new_value       TEXT              NULL COMMENT '建议的新值（JSON 或字符串）',
    old_value       TEXT              NULL COMMENT '被替换的旧值',
    source_verdict  JSON              NULL COMMENT '触发此变更的 verdict 快照',
    mode            VARCHAR(16)   NOT NULL DEFAULT 'shadow' COMMENT 'shadow / enforce',
    applied         TINYINT(1)    NOT NULL DEFAULT 0,
    applied_at      DATETIME          NULL,
    rolled_back     TINYINT(1)    NOT NULL DEFAULT 0,
    rolled_back_at  DATETIME          NULL,
    reason          TEXT              NULL,
    suggested_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME      NOT NULL,
    PRIMARY KEY (change_id),
    KEY idx_policy_key_time (policy_key, suggested_at),
    KEY idx_applied_at      (applied, applied_at),
    KEY idx_suggested_at    (suggested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='R6-5 PolicyAdjuster 产生的变更记录';
