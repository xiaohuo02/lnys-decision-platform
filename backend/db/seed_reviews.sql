SET NAMES utf8mb4;
-- seed_reviews.sql  — HITL 审核队列演示数据
-- 使用 NOW() 相对时间，保证数据始终在合理时间范围内

INSERT INTO review_cases
  (case_id, run_id, review_type, priority, status, subject, context_json, created_by, created_at)
VALUES
  -- 3 条 pending（待审核）
  ('rc-seed-001', 'run_20260402_003', 'fraud_transaction', 'critical', 'pending',
   '高风险交易：订单 ORD-88412 金额 ¥38,500 触发欺诈规则',
   '{"thread_id":"thread_003","order_id":"ORD-88412","amount":38500,"fraud_score":0.96,"rule_hits":["amount_spike","new_device","geo_mismatch"]}',
   'system', NOW() - INTERVAL 25 MINUTE),

  ('rc-seed-002', 'run_20260402_003', 'agent_output', 'high', 'pending',
   'Agent 输出审核：舆情分析报告含敏感结论需人工确认',
   '{"thread_id":"thread_003","agent":"SentimentAgent","confidence":0.72,"flagged_topics":["物流延误","品质争议"]}',
   'system', NOW() - INTERVAL 18 MINUTE),

  ('rc-seed-003', 'run_20260402_002', 'policy_violation', 'high', 'pending',
   '策略违规：库存推荐超出安全库存阈值 200%',
   '{"thread_id":"thread_002","sku":"SKU-7734","recommended_qty":5000,"safety_stock":1600,"ratio":3.125}',
   'system', NOW() - INTERVAL 12 MINUTE),

  -- 1 条 approved（已通过）
  ('rc-seed-004', 'run_20260402_001', 'fraud_transaction', 'medium', 'approved',
   '中风险交易：订单 ORD-77201 金额 ¥12,800 模型评分 0.78',
   '{"thread_id":"thread_001","order_id":"ORD-77201","amount":12800,"fraud_score":0.78}',
   'system', NOW() - INTERVAL 2 HOUR),

  -- 1 条 rejected（已拒绝）
  ('rc-seed-005', 'run_20260402_001', 'agent_output', 'low', 'rejected',
   'Agent 输出异常：预测模型置信度过低(0.31)，建议重跑',
   '{"thread_id":"thread_001","agent":"ForecastAgent","confidence":0.31,"mape":42.5}',
   'system', NOW() - INTERVAL 3 HOUR)

ON DUPLICATE KEY UPDATE subject = VALUES(subject);

-- 为已审批/已拒绝的案例插入对应动作记录
INSERT INTO review_actions
  (action_id, case_id, action_type, decision_by, decision_note, created_at)
VALUES
  ('ra-seed-001', 'rc-seed-004', 'approve', 'admin',
   '经核实为正常大额采购，客户为 VIP 企业用户',
   NOW() - INTERVAL 90 MINUTE),

  ('ra-seed-002', 'rc-seed-005', 'reject', 'admin',
   '模型置信度不足，已通知数据团队重新训练',
   NOW() - INTERVAL 150 MINUTE)

ON DUPLICATE KEY UPDATE decision_note = VALUES(decision_note);
