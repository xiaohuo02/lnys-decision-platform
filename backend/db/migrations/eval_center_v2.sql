-- ══════════════════════════════════════════════════════════════════
-- 评测中心 V2 迁移 — 新增 Prompt 版本、轨迹记忆 Tips、实验循环日志
-- ══════════════════════════════════════════════════════════════════

-- ── 1. Prompt 版本历史 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_prompt_versions (
    id             CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    skill_name     VARCHAR(64)  NOT NULL    COMMENT 'Skill 名称',
    version        INT          NOT NULL    COMMENT '版本号（递增）',
    prompt_text    TEXT         NOT NULL    COMMENT 'prompt 全文',
    model_name     VARCHAR(64)  DEFAULT NULL COMMENT '模型名',
    eval_id        CHAR(36)     DEFAULT NULL COMMENT '关联实验 ID',
    avg_score      DECIMAL(5,4) DEFAULT NULL COMMENT '该版本平均分',
    grader_scores  JSON         DEFAULT NULL COMMENT '各 grader 分数快照',
    status         ENUM('draft','testing','approved','active','rolled_back')
                   NOT NULL DEFAULT 'draft',
    approved_by    VARCHAR(64)  DEFAULT NULL COMMENT '审批人',
    approved_at    DATETIME(3)  DEFAULT NULL COMMENT '审批时间',
    metadata       JSON         DEFAULT NULL,
    created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_epv_skill_version (skill_name, version),
    INDEX idx_epv_status (status)
) ENGINE=InnoDB COMMENT='Copilot Skill prompt 版本历史';

-- ── 2. 轨迹记忆 Tips ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_agent_tips (
    tip_id             CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    tip_type           ENUM('strategy','recovery','optimization') NOT NULL,
    content            TEXT         NOT NULL    COMMENT 'Tip 正文',
    trigger_desc       TEXT         DEFAULT NULL COMMENT '触发条件描述',
    steps              JSON         DEFAULT NULL COMMENT '具体步骤',
    source_trace_id    CHAR(36)     DEFAULT NULL COMMENT '来源 trace run_id',
    source_task_type   VARCHAR(64)  DEFAULT NULL COMMENT '来源任务类型',
    generalized_desc   TEXT         DEFAULT NULL COMMENT '泛化描述（用于聚类）',
    cluster_id         VARCHAR(36)  DEFAULT NULL COMMENT '所属聚类 ID',
    confidence         DECIMAL(3,2) NOT NULL DEFAULT 0.50,
    reference_count    INT          NOT NULL DEFAULT 0 COMMENT '被引用次数',
    is_active          TINYINT(1)   NOT NULL DEFAULT 1,
    created_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_eat_type (tip_type),
    INDEX idx_eat_cluster (cluster_id),
    INDEX idx_eat_active (is_active),
    INDEX idx_eat_task_type (source_task_type)
) ENGINE=InnoDB COMMENT='轨迹记忆 Tips（IBM Trajectory Memory）';

-- ── 3. 实验循环日志（Karpathy Loop） ───────────────────────────
CREATE TABLE IF NOT EXISTS eval_loop_log (
    id              CHAR(36)     PRIMARY KEY COMMENT 'UUID',
    experiment_id   CHAR(36)     NOT NULL,
    iteration       INT          NOT NULL    COMMENT '轮次',
    change_desc     TEXT         DEFAULT NULL COMMENT '本轮变更描述',
    params_snapshot JSON         DEFAULT NULL COMMENT '参数快照',
    metric_name     VARCHAR(64)  DEFAULT NULL COMMENT '指标名',
    metric_before   DECIMAL(10,6) DEFAULT NULL COMMENT '变更前指标',
    metric_after    DECIMAL(10,6) DEFAULT NULL COMMENT '变更后指标',
    decision        ENUM('keep','discard','crash') NOT NULL,
    duration_ms     INT          DEFAULT NULL COMMENT '本轮耗时 ms',
    created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_ell_exp_iter (experiment_id, iteration),
    FOREIGN KEY (experiment_id) REFERENCES eval_experiments(experiment_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='实验循环日志（Karpathy Loop 爬山法）';

-- ── 4. eval_results 扩展字段（兼容 ALTER） ─────────────────────
-- 如果列不存在则添加
-- MySQL 不支持 IF NOT EXISTS 在 ALTER TABLE，用存储过程处理
DELIMITER //
CREATE PROCEDURE eval_v2_add_columns()
BEGIN
    -- eval_results.grader_scores
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_results' AND COLUMN_NAME = 'grader_scores'
    ) THEN
        ALTER TABLE eval_results ADD COLUMN grader_scores JSON DEFAULT NULL COMMENT '各 grader 独立分数';
    END IF;

    -- eval_results.grader_reasoning
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_results' AND COLUMN_NAME = 'grader_reasoning'
    ) THEN
        ALTER TABLE eval_results ADD COLUMN grader_reasoning JSON DEFAULT NULL COMMENT '各 grader 推理过程';
    END IF;

    -- eval_results.actual_output（设计 §4.2 要求）
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_results' AND COLUMN_NAME = 'actual_output'
    ) THEN
        ALTER TABLE eval_results ADD COLUMN actual_output JSON DEFAULT NULL COMMENT 'Agent/Skill 的实际输出';
    END IF;

    -- eval_cases.target_type（设计 §4.2 要求）
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_cases' AND COLUMN_NAME = 'target_type'
    ) THEN
        ALTER TABLE eval_cases ADD COLUMN target_type VARCHAR(32) DEFAULT NULL COMMENT '"ml_agent"|"copilot_skill"|"workflow"|"supervisor"';
    END IF;

    -- eval_cases.target_id（设计 §4.2 要求）
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_cases' AND COLUMN_NAME = 'target_id'
    ) THEN
        ALTER TABLE eval_cases ADD COLUMN target_id VARCHAR(64) DEFAULT NULL COMMENT '被测对象标识，如 fraud_agent / fraud_skill';
    END IF;

    -- eval_experiments.target_version（设计 §4.2 要求）
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_experiments' AND COLUMN_NAME = 'target_version'
    ) THEN
        ALTER TABLE eval_experiments ADD COLUMN target_version VARCHAR(64) DEFAULT NULL COMMENT '被测对象版本标识';
    END IF;

    -- eval_experiments.baseline_experiment_id
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'eval_experiments' AND COLUMN_NAME = 'baseline_experiment_id'
    ) THEN
        ALTER TABLE eval_experiments ADD COLUMN baseline_experiment_id CHAR(36) DEFAULT NULL COMMENT '对比基线实验 ID';
    END IF;
END //
DELIMITER ;

CALL eval_v2_add_columns();
DROP PROCEDURE IF EXISTS eval_v2_add_columns;
