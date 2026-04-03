SET NAMES utf8mb4;

INSERT IGNORE INTO memory_records (memory_id, customer_id, memory_kind, source_type, content_summary, risk_level, pii_flag, is_active, expires_at) VALUES
('mem-001', 'C10001', 'semantic', 'chat', '用户偏好水果类产品，尤其是柑橘系列', 'low', 0, 1, NULL),
('mem-002', 'C10001', 'episodic', 'order', '2025-12 连续3次购买柠檬相关产品，复购周期约14天', 'low', 0, 1, '2026-06-30 00:00:00'),
('mem-003', 'C10002', 'semantic', 'chat', '用户反馈对配送速度不满意，曾投诉2次', 'medium', 0, 1, NULL),
('mem-004', 'C10002', 'episodic', 'service', '用户要求退款并提供了身份证号码用于核验', 'high', 1, 1, '2026-03-01 00:00:00'),
('mem-005', 'C10003', 'semantic', 'recommendation', '用户对促销敏感，历史优惠券使用率85%', 'low', 0, 1, NULL),
('mem-006', 'C10003', 'episodic', 'fraud_check', '异常登录IP检测：同一账号24小时内从3个不同城市登录', 'high', 0, 1, NULL),
('mem-007', 'C10004', 'semantic', 'chat', '用户明确表示不希望接收短信营销推送', 'medium', 1, 1, NULL),
('mem-008', 'C10004', 'episodic', 'order', '大额订单：单笔消费2680元，超出该用户月均消费3倍', 'high', 0, 1, NULL),
('mem-009', 'C10005', 'semantic', 'recommendation', '用户偏好有机食品，客单价较高', 'low', 0, 1, NULL),
('mem-010', 'C10005', 'episodic', 'chat', '用户咨询会员积分兑换规则，表示考虑升级VIP', 'low', 0, 0, NULL),
('mem-011', 'C10001', 'episodic', 'service', '客服工单：用户要求修改收货地址含详细门牌号', 'medium', 1, 1, '2026-12-31 00:00:00'),
('mem-012', 'C10006', 'semantic', 'chat', '用户是素食主义者，需过滤肉类推荐', 'low', 0, 1, NULL);

INSERT IGNORE INTO memory_feedback (memory_id, feedback_type, reason, operated_by) VALUES
('mem-001', 'human_review', '已确认用户偏好准确', 'admin'),
('mem-004', 'flag_pii', '包含身份证号，已标记PII', 'admin'),
('mem-007', 'human_review', '已确认营销偏好', 'admin');
