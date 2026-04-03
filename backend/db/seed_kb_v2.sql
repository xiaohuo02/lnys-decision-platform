SET NAMES utf8mb4;
-- seed_kb_v2.sql — 知识库中台 v2 演示数据
-- 覆盖 3 个知识库 + 12 篇文档 + 每篇 2-3 个分块
-- 使用 INSERT IGNORE 防止重复，幂等执行

-- ════════════════════════════════════════════════════════════════════
--  建表（IF NOT EXISTS，幂等）
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS kb_libraries (
    kb_id            CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    name             VARCHAR(200)  NOT NULL UNIQUE COMMENT '唯一标识名',
    display_name     VARCHAR(200)  NOT NULL COMMENT '显示名称',
    description      TEXT          DEFAULT NULL,
    domain           VARCHAR(50)   NOT NULL DEFAULT 'enterprise' COMMENT '业务域',
    collection_name  VARCHAR(100)  NOT NULL UNIQUE COMMENT 'ChromaDB collection',
    embedding_model  VARCHAR(200)  NOT NULL DEFAULT 'bge-small-zh-v1.5',
    chunk_strategy   VARCHAR(50)   NOT NULL DEFAULT 'recursive' COMMENT 'recursive/fixed/none',
    chunk_config     JSON          DEFAULT NULL COMMENT '分块参数',
    doc_count        INT           NOT NULL DEFAULT 0 COMMENT '文档总数(冗余)',
    chunk_count      INT           NOT NULL DEFAULT 0 COMMENT '分块总数(冗余)',
    is_active        TINYINT(1)    NOT NULL DEFAULT 1,
    created_by       VARCHAR(100)  NOT NULL,
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_kb_lib_domain  (domain),
    INDEX idx_kb_lib_active  (is_active)
) ENGINE=InnoDB COMMENT='知识库实例表';

CREATE TABLE IF NOT EXISTS kb_documents (
    document_id      CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    kb_id            CHAR(36)      NOT NULL,
    title            VARCHAR(500)  NOT NULL,
    source_type      VARCHAR(50)   NOT NULL DEFAULT 'faq_manual' COMMENT 'faq_manual/file_upload/agent_auto/api_import',
    source_uri       VARCHAR(500)  DEFAULT NULL COMMENT '文件路径/URL',
    file_name        VARCHAR(300)  DEFAULT NULL,
    file_type        VARCHAR(50)   DEFAULT NULL COMMENT 'pdf/docx/xlsx/csv/txt/image',
    file_size        BIGINT        DEFAULT NULL COMMENT '字节数',
    file_hash        VARCHAR(64)   DEFAULT NULL COMMENT 'SHA-256',
    content_raw      LONGTEXT      DEFAULT NULL COMMENT '原始提取文本',
    content_clean    LONGTEXT      DEFAULT NULL COMMENT '清洗后文本',
    status           VARCHAR(30)   NOT NULL DEFAULT 'pending' COMMENT 'pending/processing/ready/failed/disabled',
    version          INT           NOT NULL DEFAULT 1,
    quality_score    FLOAT         DEFAULT NULL COMMENT '0~1',
    chunk_count      INT           NOT NULL DEFAULT 0,
    error_msg        TEXT          DEFAULT NULL,
    created_by       VARCHAR(100)  NOT NULL DEFAULT 'system',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    INDEX idx_kb_doc_kb     (kb_id),
    INDEX idx_kb_doc_status (status),
    INDEX idx_kb_doc_hash   (file_hash),
    INDEX idx_kb_doc_source (source_type),
    FOREIGN KEY (kb_id) REFERENCES kb_libraries(kb_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库文档表';

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id         CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    document_id      CHAR(36)      NOT NULL,
    kb_id            CHAR(36)      NOT NULL COMMENT '冗余FK加速查询',
    chunk_index      INT           NOT NULL COMMENT '块序号',
    content          LONGTEXT      NOT NULL,
    token_count      INT           DEFAULT NULL,
    char_count       INT           DEFAULT NULL,
    heading_path     VARCHAR(500)  DEFAULT NULL COMMENT '标题层级路径',
    chunk_type       VARCHAR(30)   NOT NULL DEFAULT 'paragraph' COMMENT 'paragraph/table/list/code/ocr',
    metadata_extra   JSON          DEFAULT NULL,
    chromadb_id      VARCHAR(200)  DEFAULT NULL COMMENT 'ChromaDB 向量 ID',
    embedding_status VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending/done/failed',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_kb_chunk_doc   (document_id),
    INDEX idx_kb_chunk_kb    (kb_id),
    INDEX idx_kb_chunk_embed (embedding_status),
    FOREIGN KEY (document_id) REFERENCES kb_documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (kb_id) REFERENCES kb_libraries(kb_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库分块表';

CREATE TABLE IF NOT EXISTS kb_document_versions (
    version_id       CHAR(36)      PRIMARY KEY COMMENT 'UUID',
    document_id      CHAR(36)      NOT NULL,
    version          INT           NOT NULL COMMENT '版本号',
    content_raw      LONGTEXT      DEFAULT NULL,
    content_clean    LONGTEXT      DEFAULT NULL,
    quality_score    FLOAT         DEFAULT NULL,
    chunk_count      INT           NOT NULL DEFAULT 0,
    created_by       VARCHAR(100)  NOT NULL DEFAULT 'system',
    created_at       DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_kb_ver_doc (document_id, version),
    FOREIGN KEY (document_id) REFERENCES kb_documents(document_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='知识库文档版本快照表';

-- ════════════════════════════════════════════════════════════════════
--  知识库实例
-- ════════════════════════════════════════════════════════════════════

INSERT IGNORE INTO kb_libraries
  (kb_id, name, display_name, description, domain, collection_name, embedding_model, chunk_strategy, chunk_config, doc_count, chunk_count, is_active, created_by, created_at, updated_at)
VALUES
  ('kb-seed-0001-0001-0001-000000000001', 'enterprise_faq',
   '企业客服FAQ', '柠优生活电商平台客服常见问答知识库，覆盖订单、退款、物流、账户等高频问题',
   'enterprise', 'kb_enterprise_faq', 'bge-small-zh-v1.5', 'recursive',
   '{"max_tokens":512,"overlap":64}', 5, 12, 1, 'admin', NOW() - INTERVAL 30 DAY, NOW()),

  ('kb-seed-0002-0002-0002-000000000002', 'sentiment_reviews',
   '舆情评论库', '从电商平台和社交媒体采集的用户评论语料，供舆情分析Agent检索参考',
   'sentiment', 'kb_sentiment_reviews', 'bge-small-zh-v1.5', 'recursive',
   '{"max_tokens":256,"overlap":32}', 4, 10, 1, 'admin', NOW() - INTERVAL 25 DAY, NOW()),

  ('kb-seed-0003-0003-0003-000000000003', 'ops_runbook',
   '运维手册', '平台运维操作手册，包含数据库维护、缓存清理、服务重启、告警处理等标准操作流程',
   'ops', 'kb_ops_runbook', 'bge-small-zh-v1.5', 'recursive',
   '{"max_tokens":512,"overlap":64}', 3, 8, 1, 'admin', NOW() - INTERVAL 20 DAY, NOW());


-- ════════════════════════════════════════════════════════════════════
--  企业客服FAQ 文档（5篇）
-- ════════════════════════════════════════════════════════════════════

INSERT IGNORE INTO kb_documents
  (document_id, kb_id, title, source_type, content_raw, content_clean, status, version, quality_score, chunk_count, created_by, created_at, updated_at)
VALUES
-- 文档 1: 退款政策
('doc-seed-e001-0000-0000-000000000001', 'kb-seed-0001-0001-0001-000000000001',
 '退款政策完整说明', 'faq_manual',
 '退款政策完整说明\n\n一、退款条件\n1. 商品签收后7天内，未使用、未拆封的商品支持无理由退货退款\n2. 商品存在质量问题，签收后30天内可申请退款\n3. 发货超时（超过承诺发货时间48小时），可直接申请退款\n\n二、退款流程\n1. 进入"我的订单"→选择需要退款的订单→点击"申请售后"\n2. 选择退款原因并上传相关凭证（质量问题需拍照）\n3. 商家在1-2个工作日内审核\n4. 审核通过后，根据商家要求寄回商品（质量问题由平台承担运费）\n5. 商家确认收货后1-3个工作日内退款到账\n\n三、退款到账时间\n- 微信支付：1-3个工作日\n- 支付宝：1-3个工作日\n- 银行卡：3-7个工作日\n- 余额支付：即时退回\n\n四、特殊说明\n- 生鲜食品、个人护理用品拆封后不支持无理由退货\n- 定制商品不支持退货退款\n- 优惠券购买的商品退款时，优惠券将退回账户（需在有效期内）',
 '退款政策完整说明\n\n一、退款条件\n1. 商品签收后7天内，未使用、未拆封的商品支持无理由退货退款\n2. 商品存在质量问题，签收后30天内可申请退款\n3. 发货超时超过承诺发货时间48小时可直接申请退款\n\n二、退款流程\n1. 进入我的订单选择需要退款的订单点击申请售后\n2. 选择退款原因并上传相关凭证\n3. 商家在1-2个工作日内审核\n4. 审核通过后根据商家要求寄回商品\n5. 商家确认收货后1-3个工作日内退款到账\n\n三、退款到账时间\n微信支付1-3个工作日\n支付宝1-3个工作日\n银行卡3-7个工作日\n余额支付即时退回\n\n四、特殊说明\n生鲜食品个人护理用品拆封后不支持无理由退货\n定制商品不支持退货退款\n优惠券购买的商品退款时优惠券将退回账户',
 'ready', 1, 0.82, 3, 'admin', NOW() - INTERVAL 28 DAY, NOW()),

-- 文档 2: 会员等级制度
('doc-seed-e002-0000-0000-000000000002', 'kb-seed-0001-0001-0001-000000000001',
 '会员等级制度与权益', 'faq_manual',
 '会员等级制度与权益\n\n一、等级划分\n柠优生活会员体系分为四个等级：\n1. 普通会员（注册即享）\n2. 银卡会员（年消费满2000元）\n3. 金卡会员（年消费满8000元）\n4. 钻石会员（年消费满20000元）\n\n二、等级权益\n普通会员：\n- 基础购物功能\n- 每月1张5元无门槛优惠券\n\n银卡会员：\n- 全场95折\n- 每月2张10元优惠券\n- 优先客服通道\n\n金卡会员：\n- 全场9折\n- 每月3张20元优惠券\n- 专属客服\n- 免费退换货运费\n\n钻石会员：\n- 全场85折\n- 每月5张30元优惠券\n- 一对一VIP客服\n- 免费退换货运费\n- 新品优先购买权\n- 生日双倍积分\n\n三、积分规则\n- 每消费1元 = 1积分\n- 100积分 = 1元抵扣\n- 积分有效期为获得后12个月',
 '会员等级制度与权益\n\n一、等级划分\n柠优生活会员体系分为四个等级\n1. 普通会员注册即享\n2. 银卡会员年消费满2000元\n3. 金卡会员年消费满8000元\n4. 钻石会员年消费满20000元\n\n二、等级权益\n普通会员基础购物功能每月1张5元无门槛优惠券\n银卡会员全场95折每月2张10元优惠券优先客服通道\n金卡会员全场9折每月3张20元优惠券专属客服免费退换货运费\n钻石会员全场85折每月5张30元优惠券一对一VIP客服免费退换货运费新品优先购买权生日双倍积分\n\n三、积分规则\n每消费1元等于1积分\n100积分等于1元抵扣\n积分有效期为获得后12个月',
 'ready', 1, 0.78, 3, 'admin', NOW() - INTERVAL 26 DAY, NOW()),

-- 文档 3: 配送服务说明
('doc-seed-e003-0000-0000-000000000003', 'kb-seed-0001-0001-0001-000000000001',
 '配送服务说明', 'faq_manual',
 '配送服务说明\n\n一、配送范围\n柠优生活目前覆盖全国300+城市，包括：\n- 一二线城市：全区域覆盖\n- 三四线城市：主城区覆盖\n- 乡镇地区：部分覆盖（以下单时系统提示为准）\n\n二、配送时效\n1. 标准配送：下单后48小时内发货，3-5天送达\n2. 次日达：一二线城市部分商品支持，下午14:00前下单次日送达\n3. 当日达：仅限同城仓商品，上午10:00前下单当日送达\n4. 预售商品：按商品页面标注的预计发货时间\n\n三、运费规则\n- 订单满49元免运费\n- 未满49元收取基础运费8元\n- 偏远地区（新疆、西藏、青海等）需额外加收5-15元\n- 大件商品运费单独计算，以页面标注为准\n\n四、验货说明\n- 建议当面验货签收\n- 外包装破损请拒收并联系客服\n- 签收后发现问题请在24小时内反馈',
 '配送服务说明\n\n一、配送范围\n柠优生活目前覆盖全国300+城市\n一二线城市全区域覆盖\n三四线城市主城区覆盖\n乡镇地区部分覆盖\n\n二、配送时效\n标准配送下单后48小时内发货3-5天送达\n次日达一二线城市部分商品支持下午14点前下单次日送达\n当日达仅限同城仓商品上午10点前下单当日送达\n预售商品按商品页面标注的预计发货时间\n\n三、运费规则\n订单满49元免运费\n未满49元收取基础运费8元\n偏远地区需额外加收5-15元\n大件商品运费单独计算\n\n四、验货说明\n建议当面验货签收\n外包装破损请拒收并联系客服\n签收后发现问题请在24小时内反馈',
 'ready', 1, 0.85, 2, 'admin', NOW() - INTERVAL 24 DAY, NOW()),

-- 文档 4: 优惠券使用规则
('doc-seed-e004-0000-0000-000000000004', 'kb-seed-0001-0001-0001-000000000001',
 '优惠券使用规则', 'faq_manual',
 '优惠券使用规则\n\n一、优惠券类型\n1. 无门槛券：无最低消费限制\n2. 满减券：满足最低消费金额后可使用（如满100减20）\n3. 品类券：限指定品类商品使用\n4. 店铺券：限指定店铺商品使用\n\n二、使用规则\n- 每笔订单限使用一张优惠券\n- 优惠券不可与其他优惠叠加使用（特殊活动除外）\n- 优惠券有有效期，过期自动失效\n- 使用优惠券后取消订单，优惠券将退回（若在有效期内）\n\n三、获取方式\n1. 新用户注册礼包：价值200元优惠券组合\n2. 领券中心：每日限量发放\n3. 会员月度发放：根据等级自动发放\n4. 活动专区：大促期间专属优惠券\n5. 分享有礼：邀请好友注册可获得奖励券',
 '优惠券使用规则\n\n一、优惠券类型\n无门槛券无最低消费限制\n满减券满足最低消费金额后可使用\n品类券限指定品类商品使用\n店铺券限指定店铺商品使用\n\n二、使用规则\n每笔订单限使用一张优惠券\n优惠券不可与其他优惠叠加使用\n优惠券有有效期过期自动失效\n使用优惠券后取消订单优惠券将退回\n\n三、获取方式\n新用户注册礼包价值200元优惠券组合\n领券中心每日限量发放\n会员月度发放根据等级自动发放\n活动专区大促期间专属优惠券\n分享有礼邀请好友注册可获得奖励券',
 'ready', 1, 0.75, 2, 'admin', NOW() - INTERVAL 22 DAY, NOW()),

-- 文档 5: 数据安全与隐私保护
('doc-seed-e005-0000-0000-000000000005', 'kb-seed-0001-0001-0001-000000000001',
 '数据安全与隐私保护政策', 'faq_manual',
 '数据安全与隐私保护政策\n\n一、数据收集范围\n我们收集的用户数据包括：\n1. 注册信息：手机号、昵称、头像\n2. 交易信息：订单记录、支付信息（不存储完整银行卡号）\n3. 行为信息：浏览记录、搜索记录、点击偏好\n4. 设备信息：设备型号、操作系统版本\n\n二、数据使用目的\n- 提供基础购物服务\n- 个性化商品推荐\n- 风控反欺诈检测\n- 客服服务质量提升\n- 平台运营数据分析（脱敏聚合后使用）\n\n三、数据保护措施\n1. 传输加密：全站HTTPS + TLS 1.3\n2. 存储加密：敏感字段AES-256加密存储\n3. 访问控制：RBAC权限管理 + 操作审计日志\n4. 数据脱敏：展示层自动脱敏（手机号、身份证等）\n5. 定期审计：每季度第三方安全审计\n\n四、用户权利\n- 查看个人数据：设置→隐私→数据导出\n- 删除个人数据：联系客服申请注销（30天内处理）\n- 撤回授权：设置→隐私→权限管理',
 '数据安全与隐私保护政策\n\n一、数据收集范围\n注册信息手机号昵称头像\n交易信息订单记录支付信息\n行为信息浏览记录搜索记录点击偏好\n设备信息设备型号操作系统版本\n\n二、数据使用目的\n提供基础购物服务\n个性化商品推荐\n风控反欺诈检测\n客服服务质量提升\n平台运营数据分析\n\n三、数据保护措施\n传输加密全站HTTPS加TLS1.3\n存储加密敏感字段AES-256加密存储\n访问控制RBAC权限管理加操作审计日志\n数据脱敏展示层自动脱敏\n定期审计每季度第三方安全审计\n\n四、用户权利\n查看个人数据\n删除个人数据\n撤回授权',
 'ready', 1, 0.88, 2, 'admin', NOW() - INTERVAL 18 DAY, NOW());


-- ════════════════════════════════════════════════════════════════════
--  舆情评论库 文档（4篇）
-- ════════════════════════════════════════════════════════════════════

INSERT IGNORE INTO kb_documents
  (document_id, kb_id, title, source_type, content_raw, content_clean, status, version, quality_score, chunk_count, created_by, created_at, updated_at)
VALUES
-- 文档 6: 正面评论合集
('doc-seed-s001-0000-0000-000000000001', 'kb-seed-0002-0002-0002-000000000002',
 '2024年Q4正面评论合集', 'api_import',
 '用户好评合集 - 2024年Q4\n\n1. "柠优生活的水果真的很新鲜，每次买的橙子都特别甜，包装也很用心，防撞泡沫包得很好。"\n\n2. "第一次用这个平台，下单到收货只用了一天，太快了！而且价格比超市便宜不少。"\n\n3. "客服小柠太好用了，我问了退货流程，秒回还帮我直接提交了退货申请，比人工客服还靠谱。"\n\n4. "会员制度很划算，金卡9折真的香，每个月还送优惠券，已经推荐给身边的朋友了。"\n\n5. "双十一活动力度很大，叠加优惠券省了快200块，物流也没有爆仓延迟，好评！"\n\n6. "生鲜区的三文鱼品质超好，冷链配送全程有温控记录，吃着放心。"',
 '用户好评合集2024年Q4\n\n柠优生活的水果真的很新鲜每次买的橙子都特别甜包装也很用心防撞泡沫包得很好\n\n第一次用这个平台下单到收货只用了一天太快了而且价格比超市便宜不少\n\n客服小柠太好用了我问了退货流程秒回还帮我直接提交了退货申请比人工客服还靠谱\n\n会员制度很划算金卡9折真的香每个月还送优惠券已经推荐给身边的朋友了\n\n双十一活动力度很大叠加优惠券省了快200块物流也没有爆仓延迟好评\n\n生鲜区的三文鱼品质超好冷链配送全程有温控记录吃着放心',
 'ready', 1, 0.72, 2, 'admin', NOW() - INTERVAL 20 DAY, NOW()),

-- 文档 7: 负面评论合集
('doc-seed-s002-0000-0000-000000000002', 'kb-seed-0002-0002-0002-000000000002',
 '2024年Q4负面评论合集', 'api_import',
 '用户差评合集 - 2024年Q4\n\n1. "买的衣服色差太大了，图片上是深蓝色，收到的明显是紫色，申请退货还要我自己出运费。"\n\n2. "物流太慢了，显示48小时发货，结果等了5天才发出来，催了客服也没用。"\n\n3. "APP经常闪退，尤其是抢购的时候，好几次都因为闪退没抢到，体验很差。"\n\n4. "优惠券限制太多了，说是满100减20，结果一堆商品不参加活动，凑单凑半天。"\n\n5. "收到的鸡蛋碎了三个，虽然客服给补偿了5元优惠券，但总感觉包装需要改进。"',
 '用户差评合集2024年Q4\n\n买的衣服色差太大了图片上是深蓝色收到的明显是紫色申请退货还要自己出运费\n\n物流太慢了显示48小时发货结果等了5天才发出来催了客服也没用\n\nAPP经常闪退尤其是抢购的时候好几次都因为闪退没抢到体验很差\n\n优惠券限制太多了说是满100减20结果一堆商品不参加活动凑单凑半天\n\n收到的鸡蛋碎了三个虽然客服给补偿了5元优惠券但总感觉包装需要改进',
 'ready', 1, 0.70, 2, 'admin', NOW() - INTERVAL 18 DAY, NOW()),

-- 文档 8: 竞品对比评论
('doc-seed-s003-0000-0000-000000000003', 'kb-seed-0002-0002-0002-000000000002',
 '竞品对比用户声音', 'api_import',
 '竞品对比用户反馈\n\n1. "之前一直用XX买菜，换到柠优生活后发现水果品质好很多，就是蔬菜品类少了点。"\n\n2. "跟YY到家比，柠优生活的配送范围大不少，我们小区YY不送，柠优可以。价格差不多。"\n\n3. "柠优的AI客服比其他平台强，能理解我说的模糊问题，不像有些平台的机器人只会固定回复。"\n\n4. "退货体验比ZZ商城好多了，ZZ要等三四天审核，柠优当天就通过了。"',
 '竞品对比用户反馈\n\n之前一直用其他平台买菜换到柠优生活后发现水果品质好很多就是蔬菜品类少了点\n\n跟其他到家平台比柠优生活的配送范围大不少价格差不多\n\n柠优的AI客服比其他平台强能理解模糊问题不像有些平台的机器人只会固定回复\n\n退货体验比其他商城好多了其他要等三四天审核柠优当天就通过了',
 'ready', 1, 0.68, 3, 'admin', NOW() - INTERVAL 15 DAY, NOW()),

-- 文档 9: 社交媒体舆情摘要
('doc-seed-s004-0000-0000-000000000004', 'kb-seed-0002-0002-0002-000000000002',
 '2024年12月微博舆情摘要', 'api_import',
 '2024年12月微博舆情监测摘要\n\n热门话题：#柠优生活年终大促#\n- 提及量：12,580次\n- 正面占比：67.3%\n- 负面占比：15.2%\n- 中性占比：17.5%\n\n正面关键词：划算、品质好、配送快、客服好、推荐\n负面关键词：色差、延迟发货、闪退、限制多、碎了\n\n典型正面微博：\n"柠优年终大促真的太香了，囤了一堆零食和日用品，算下来比双十一还便宜 #柠优生活#"\n\n典型负面微博：\n"@柠优生活官方 你们的APP能不能优化一下，抢购高峰期根本打不开，年终大促变年终烦恼 #吐槽#"\n\n舆情建议：\n1. APP性能优化为当务之急，抢购场景需扩容\n2. 物流时效承诺需更保守，减少用户预期落差\n3. 增加色差问题的商品图片审核标准',
 '2024年12月微博舆情监测摘要\n\n热门话题柠优生活年终大促\n提及量12580次\n正面占比67.3%\n负面占比15.2%\n中性占比17.5%\n\n正面关键词划算品质好配送快客服好推荐\n负面关键词色差延迟发货闪退限制多碎了\n\n舆情建议\nAPP性能优化为当务之急抢购场景需扩容\n物流时效承诺需更保守减少用户预期落差\n增加色差问题的商品图片审核标准',
 'ready', 1, 0.80, 3, 'admin', NOW() - INTERVAL 10 DAY, NOW());


-- ════════════════════════════════════════════════════════════════════
--  运维手册 文档（3篇）
-- ════════════════════════════════════════════════════════════════════

INSERT IGNORE INTO kb_documents
  (document_id, kb_id, title, source_type, content_raw, content_clean, status, version, quality_score, chunk_count, created_by, created_at, updated_at)
VALUES
-- 文档 10: MySQL 日常运维
('doc-seed-o001-0000-0000-000000000001', 'kb-seed-0003-0003-0003-000000000003',
 'MySQL数据库日常运维手册', 'faq_manual',
 'MySQL数据库日常运维手册\n\n一、健康检查\n每日必查项目：\n1. 连接数监控：SHOW STATUS LIKE ''Threads_connected''; 正常值 < 200\n2. 慢查询日志：检查 slow_query_log 中超过 2s 的查询\n3. 磁盘空间：数据目录使用率不超过 80%\n4. 主从延迟：Seconds_Behind_Master 正常值 < 5\n\n二、备份策略\n1. 全量备份：每日凌晨 3:00 执行 mysqldump 全库备份\n2. 增量备份：binlog 实时同步到备份服务器\n3. 备份保留：本地保留 7 天，远程保留 30 天\n4. 恢复演练：每月第一个周日进行备份恢复验证\n\n三、常见故障处理\n问题：连接数暴涨\n原因：应用连接池泄漏或慢查询堆积\n处理：\n1. SHOW PROCESSLIST 定位异常连接\n2. KILL 长时间 Sleep 状态的连接\n3. 排查应用层连接池配置\n\n问题：磁盘空间不足\n处理：\n1. 清理过期 binlog：PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY\n2. 优化大表：ALTER TABLE ... ENGINE=InnoDB（触发空间回收）\n3. 归档历史数据到冷存储',
 'MySQL数据库日常运维手册\n\n一、健康检查\n每日必查项目\n连接数监控正常值小于200\n慢查询日志检查超过2s的查询\n磁盘空间数据目录使用率不超过80%\n主从延迟正常值小于5\n\n二、备份策略\n全量备份每日凌晨3点执行mysqldump全库备份\n增量备份binlog实时同步到备份服务器\n备份保留本地保留7天远程保留30天\n恢复演练每月第一个周日进行备份恢复验证\n\n三、常见故障处理\n连接数暴涨处理方案\n磁盘空间不足处理方案',
 'ready', 1, 0.90, 3, 'admin', NOW() - INTERVAL 15 DAY, NOW()),

-- 文档 11: Redis 运维
('doc-seed-o002-0000-0000-000000000002', 'kb-seed-0003-0003-0003-000000000003',
 'Redis缓存运维手册', 'faq_manual',
 'Redis缓存运维手册\n\n一、监控指标\n1. 内存使用率：INFO memory → used_memory / maxmemory，阈值 85%\n2. 命中率：INFO stats → keyspace_hits / (keyspace_hits + keyspace_misses)，正常 > 90%\n3. 连接数：INFO clients → connected_clients，正常 < 500\n4. 慢日志：SLOWLOG GET 10，关注超过 10ms 的命令\n\n二、缓存清理策略\n当前配置：maxmemory-policy allkeys-lru\n手动清理场景：\n1. 发布新版本后清理旧格式缓存：redis-cli KEYS "cache:v1:*" | xargs redis-cli DEL\n2. 知识库更新后清理检索缓存：redis-cli DEL kb:bm25:*\n3. 全量清理（谨慎）：FLUSHDB\n\n三、持久化配置\n- RDB：save 900 1, save 300 10, save 60 10000\n- AOF：appendonly yes, appendfsync everysec\n- 混合持久化：aof-use-rdb-preamble yes\n\n四、故障恢复\n1. Redis 宕机：systemctl restart redis，检查 AOF 文件完整性\n2. 内存 OOM：临时调大 maxmemory，排查大 key（redis-cli --bigkeys）\n3. 主从断开：检查网络连通性，SLAVEOF NO ONE 后重新建立同步',
 'Redis缓存运维手册\n\n一、监控指标\n内存使用率阈值85%\n命中率正常大于90%\n连接数正常小于500\n慢日志关注超过10ms的命令\n\n二、缓存清理策略\n当前配置allkeys-lru\n发布新版本后清理旧格式缓存\n知识库更新后清理检索缓存\n\n三、持久化配置\n四、故障恢复方案',
 'ready', 1, 0.86, 3, 'admin', NOW() - INTERVAL 12 DAY, NOW()),

-- 文档 12: 告警处理流程
('doc-seed-o003-0000-0000-000000000003', 'kb-seed-0003-0003-0003-000000000003',
 '平台告警处理SOP', 'faq_manual',
 '平台告警处理标准操作流程（SOP）\n\n一、告警级别定义\nP0 - 致命：核心服务完全不可用（如支付失败、全站502）\n  响应时间：5分钟内\n  处理时限：30分钟内恢复\n  通知方式：电话 + 飞书群 + 短信\n\nP1 - 严重：核心功能降级（如搜索超时、部分接口报错率 > 10%）\n  响应时间：15分钟内\n  处理时限：2小时内恢复\n  通知方式：飞书群 + 短信\n\nP2 - 警告：非核心功能异常（如推荐系统降级、日志采集延迟）\n  响应时间：30分钟内\n  处理时限：下一个工作日\n  通知方式：飞书群\n\nP3 - 提示：性能指标接近阈值\n  响应时间：1个工作日\n  处理时限：本周内\n  通知方式：日报邮件\n\n二、处理流程\n1. 确认告警：判断是否为误报（检查监控面板和日志）\n2. 初步定位：根据告警类型缩小范围（网络/应用/数据库/外部依赖）\n3. 应急处理：优先恢复服务（重启/回滚/切流量/降级）\n4. 根因分析：服务恢复后进行根因定位\n5. 修复上线：修复代码并走正常发布流程\n6. 复盘总结：产出故障报告，更新运维手册\n\n三、常用应急命令\n服务重启：docker compose restart backend\n回滚版本：docker compose up -d --build（切回上一个 tag）\n流量降级：修改 .env 中 ENABLE_MOCK_DATA=true 开启降级',
 '平台告警处理标准操作流程SOP\n\n一、告警级别定义\nP0致命核心服务完全不可用响应5分钟内30分钟内恢复\nP1严重核心功能降级响应15分钟内2小时内恢复\nP2警告非核心功能异常响应30分钟内下一个工作日\nP3提示性能指标接近阈值\n\n二、处理流程\n确认告警初步定位应急处理根因分析修复上线复盘总结\n\n三、常用应急命令',
 'ready', 1, 0.92, 2, 'admin', NOW() - INTERVAL 8 DAY, NOW());


-- ════════════════════════════════════════════════════════════════════
--  分块数据（每篇文档 2-3 个 chunk）
-- ════════════════════════════════════════════════════════════════════

INSERT IGNORE INTO kb_chunks
  (chunk_id, document_id, kb_id, chunk_index, content, token_count, char_count, heading_path, chunk_type, embedding_status, created_at)
VALUES
-- == 文档1: 退款政策 (3 chunks) ==
('chk-seed-e001-001', 'doc-seed-e001-0000-0000-000000000001', 'kb-seed-0001-0001-0001-000000000001',
 0, '退款政策完整说明\n\n一、退款条件\n1. 商品签收后7天内，未使用、未拆封的商品支持无理由退货退款\n2. 商品存在质量问题，签收后30天内可申请退款\n3. 发货超时超过承诺发货时间48小时可直接申请退款', 82, 120, '退款政策 > 退款条件', 'paragraph', 'pending', NOW()),

('chk-seed-e001-002', 'doc-seed-e001-0000-0000-000000000001', 'kb-seed-0001-0001-0001-000000000001',
 1, '二、退款流程\n1. 进入我的订单选择需要退款的订单点击申请售后\n2. 选择退款原因并上传相关凭证\n3. 商家在1-2个工作日内审核\n4. 审核通过后根据商家要求寄回商品\n5. 商家确认收货后1-3个工作日内退款到账', 88, 128, '退款政策 > 退款流程', 'paragraph', 'pending', NOW()),

('chk-seed-e001-003', 'doc-seed-e001-0000-0000-000000000001', 'kb-seed-0001-0001-0001-000000000001',
 2, '三、退款到账时间\n微信支付1-3个工作日\n支付宝1-3个工作日\n银行卡3-7个工作日\n余额支付即时退回\n\n四、特殊说明\n生鲜食品个人护理用品拆封后不支持无理由退货\n定制商品不支持退货退款\n优惠券购买的商品退款时优惠券将退回账户', 90, 135, '退款政策 > 到账时间与特殊说明', 'paragraph', 'pending', NOW()),

-- == 文档2: 会员等级 (3 chunks) ==
('chk-seed-e002-001', 'doc-seed-e002-0000-0000-000000000002', 'kb-seed-0001-0001-0001-000000000001',
 0, '会员等级制度与权益\n\n一、等级划分\n柠优生活会员体系分为四个等级\n1. 普通会员注册即享\n2. 银卡会员年消费满2000元\n3. 金卡会员年消费满8000元\n4. 钻石会员年消费满20000元', 75, 110, '会员制度 > 等级划分', 'paragraph', 'pending', NOW()),

('chk-seed-e002-002', 'doc-seed-e002-0000-0000-000000000002', 'kb-seed-0001-0001-0001-000000000001',
 1, '二、等级权益\n普通会员基础购物功能每月1张5元无门槛优惠券\n银卡会员全场95折每月2张10元优惠券优先客服通道\n金卡会员全场9折每月3张20元优惠券专属客服免费退换货运费\n钻石会员全场85折每月5张30元优惠券一对一VIP客服免费退换货运费新品优先购买权生日双倍积分', 110, 165, '会员制度 > 等级权益', 'paragraph', 'pending', NOW()),

('chk-seed-e002-003', 'doc-seed-e002-0000-0000-000000000002', 'kb-seed-0001-0001-0001-000000000001',
 2, '三、积分规则\n每消费1元等于1积分\n100积分等于1元抵扣\n积分有效期为获得后12个月', 38, 50, '会员制度 > 积分规则', 'paragraph', 'pending', NOW()),

-- == 文档3: 配送服务 (2 chunks) ==
('chk-seed-e003-001', 'doc-seed-e003-0000-0000-000000000003', 'kb-seed-0001-0001-0001-000000000001',
 0, '配送服务说明\n\n一、配送范围\n柠优生活目前覆盖全国300+城市\n一二线城市全区域覆盖\n三四线城市主城区覆盖\n\n二、配送时效\n标准配送下单后48小时内发货3-5天送达\n次日达一二线城市部分商品支持\n当日达仅限同城仓商品上午10点前下单当日送达', 95, 140, '配送服务 > 范围与时效', 'paragraph', 'pending', NOW()),

('chk-seed-e003-002', 'doc-seed-e003-0000-0000-000000000003', 'kb-seed-0001-0001-0001-000000000001',
 1, '三、运费规则\n订单满49元免运费\n未满49元收取基础运费8元\n偏远地区需额外加收5-15元\n\n四、验货说明\n建议当面验货签收\n外包装破损请拒收并联系客服\n签收后发现问题请在24小时内反馈', 75, 105, '配送服务 > 运费与验货', 'paragraph', 'pending', NOW()),

-- == 文档4: 优惠券 (2 chunks) ==
('chk-seed-e004-001', 'doc-seed-e004-0000-0000-000000000004', 'kb-seed-0001-0001-0001-000000000001',
 0, '优惠券使用规则\n\n一、优惠券类型\n无门槛券无最低消费限制\n满减券满足最低消费金额后可使用\n品类券限指定品类商品使用\n店铺券限指定店铺商品使用', 62, 88, '优惠券 > 类型', 'paragraph', 'pending', NOW()),

('chk-seed-e004-002', 'doc-seed-e004-0000-0000-000000000004', 'kb-seed-0001-0001-0001-000000000001',
 1, '二、使用规则\n每笔订单限使用一张优惠券\n优惠券不可与其他优惠叠加使用\n优惠券有有效期过期自动失效\n\n三、获取方式\n新用户注册礼包价值200元优惠券组合\n领券中心每日限量发放\n会员月度发放根据等级自动发放\n分享有礼邀请好友注册可获得奖励券', 85, 125, '优惠券 > 使用规则与获取', 'paragraph', 'pending', NOW()),

-- == 文档5: 数据安全 (2 chunks) ==
('chk-seed-e005-001', 'doc-seed-e005-0000-0000-000000000005', 'kb-seed-0001-0001-0001-000000000001',
 0, '数据安全与隐私保护政策\n\n一、数据收集范围\n注册信息手机号昵称头像\n交易信息订单记录支付信息\n行为信息浏览记录搜索记录点击偏好\n\n二、数据使用目的\n提供基础购物服务\n个性化商品推荐\n风控反欺诈检测', 80, 115, '数据安全 > 收集与使用', 'paragraph', 'pending', NOW()),

('chk-seed-e005-002', 'doc-seed-e005-0000-0000-000000000005', 'kb-seed-0001-0001-0001-000000000001',
 1, '三、数据保护措施\n传输加密全站HTTPS加TLS1.3\n存储加密敏感字段AES-256加密存储\n访问控制RBAC权限管理加操作审计日志\n数据脱敏展示层自动脱敏\n\n四、用户权利\n查看个人数据\n删除个人数据\n撤回授权', 72, 108, '数据安全 > 保护措施与用户权利', 'paragraph', 'pending', NOW()),

-- == 文档6: 正面评论 (2 chunks) ==
('chk-seed-s001-001', 'doc-seed-s001-0000-0000-000000000001', 'kb-seed-0002-0002-0002-000000000002',
 0, '用户好评合集2024年Q4\n\n柠优生活的水果真的很新鲜每次买的橙子都特别甜包装也很用心防撞泡沫包得很好\n\n第一次用这个平台下单到收货只用了一天太快了而且价格比超市便宜不少\n\n客服小柠太好用了我问了退货流程秒回还帮我直接提交了退货申请比人工客服还靠谱', 95, 140, '好评 > 品质与服务', 'paragraph', 'pending', NOW()),

('chk-seed-s001-002', 'doc-seed-s001-0000-0000-000000000001', 'kb-seed-0002-0002-0002-000000000002',
 1, '会员制度很划算金卡9折真的香每个月还送优惠券已经推荐给身边的朋友了\n\n双十一活动力度很大叠加优惠券省了快200块物流也没有爆仓延迟好评\n\n生鲜区的三文鱼品质超好冷链配送全程有温控记录吃着放心', 82, 120, '好评 > 活动与生鲜', 'paragraph', 'pending', NOW()),

-- == 文档7: 负面评论 (2 chunks) ==
('chk-seed-s002-001', 'doc-seed-s002-0000-0000-000000000002', 'kb-seed-0002-0002-0002-000000000002',
 0, '用户差评合集2024年Q4\n\n买的衣服色差太大了图片上是深蓝色收到的明显是紫色申请退货还要自己出运费\n\n物流太慢了显示48小时发货结果等了5天才发出来催了客服也没用', 72, 105, '差评 > 质量与物流', 'paragraph', 'pending', NOW()),

('chk-seed-s002-002', 'doc-seed-s002-0000-0000-000000000002', 'kb-seed-0002-0002-0002-000000000002',
 1, 'APP经常闪退尤其是抢购的时候好几次都因为闪退没抢到体验很差\n\n优惠券限制太多了说是满100减20结果一堆商品不参加活动凑单凑半天\n\n收到的鸡蛋碎了三个虽然客服给补偿了5元优惠券但总感觉包装需要改进', 80, 118, '差评 > APP与促销', 'paragraph', 'pending', NOW()),

-- == 文档8: 竞品对比 (3 chunks) ==
('chk-seed-s003-001', 'doc-seed-s003-0000-0000-000000000003', 'kb-seed-0002-0002-0002-000000000002',
 0, '竞品对比用户反馈\n\n之前一直用其他平台买菜换到柠优生活后发现水果品质好很多就是蔬菜品类少了点', 45, 60, '竞品 > 品质对比', 'paragraph', 'pending', NOW()),

('chk-seed-s003-002', 'doc-seed-s003-0000-0000-000000000003', 'kb-seed-0002-0002-0002-000000000002',
 1, '跟其他到家平台比柠优生活的配送范围大不少价格差不多\n\n柠优的AI客服比其他平台强能理解模糊问题不像有些平台的机器人只会固定回复', 68, 95, '竞品 > 配送与客服', 'paragraph', 'pending', NOW()),

('chk-seed-s003-003', 'doc-seed-s003-0000-0000-000000000003', 'kb-seed-0002-0002-0002-000000000002',
 2, '退货体验比其他商城好多了其他要等三四天审核柠优当天就通过了', 32, 42, '竞品 > 售后', 'paragraph', 'pending', NOW()),

-- == 文档9: 微博舆情 (3 chunks) ==
('chk-seed-s004-001', 'doc-seed-s004-0000-0000-000000000004', 'kb-seed-0002-0002-0002-000000000002',
 0, '2024年12月微博舆情监测摘要\n\n热门话题柠优生活年终大促\n提及量12580次\n正面占比67.3%\n负面占比15.2%\n中性占比17.5%', 52, 75, '舆情 > 数据概览', 'paragraph', 'pending', NOW()),

('chk-seed-s004-002', 'doc-seed-s004-0000-0000-000000000004', 'kb-seed-0002-0002-0002-000000000002',
 1, '正面关键词划算品质好配送快客服好推荐\n负面关键词色差延迟发货闪退限制多碎了', 40, 55, '舆情 > 关键词', 'paragraph', 'pending', NOW()),

('chk-seed-s004-003', 'doc-seed-s004-0000-0000-000000000004', 'kb-seed-0002-0002-0002-000000000002',
 2, '舆情建议\nAPP性能优化为当务之急抢购场景需扩容\n物流时效承诺需更保守减少用户预期落差\n增加色差问题的商品图片审核标准', 48, 68, '舆情 > 改进建议', 'paragraph', 'pending', NOW()),

-- == 文档10: MySQL运维 (3 chunks) ==
('chk-seed-o001-001', 'doc-seed-o001-0000-0000-000000000001', 'kb-seed-0003-0003-0003-000000000003',
 0, 'MySQL数据库日常运维手册\n\n一、健康检查\n每日必查项目\n连接数监控正常值小于200\n慢查询日志检查超过2s的查询\n磁盘空间数据目录使用率不超过80%\n主从延迟正常值小于5', 70, 100, 'MySQL > 健康检查', 'paragraph', 'pending', NOW()),

('chk-seed-o001-002', 'doc-seed-o001-0000-0000-000000000001', 'kb-seed-0003-0003-0003-000000000003',
 1, '二、备份策略\n全量备份每日凌晨3点执行mysqldump全库备份\n增量备份binlog实时同步到备份服务器\n备份保留本地保留7天远程保留30天\n恢复演练每月第一个周日进行备份恢复验证', 68, 98, 'MySQL > 备份策略', 'paragraph', 'pending', NOW()),

('chk-seed-o001-003', 'doc-seed-o001-0000-0000-000000000001', 'kb-seed-0003-0003-0003-000000000003',
 2, '三、常见故障处理\n连接数暴涨处理方案\n1. SHOW PROCESSLIST定位异常连接\n2. KILL长时间Sleep状态的连接\n3. 排查应用层连接池配置\n\n磁盘空间不足处理方案\n1. 清理过期binlog\n2. 优化大表触发空间回收\n3. 归档历史数据到冷存储', 82, 120, 'MySQL > 故障处理', 'paragraph', 'pending', NOW()),

-- == 文档11: Redis运维 (3 chunks) ==
('chk-seed-o002-001', 'doc-seed-o002-0000-0000-000000000002', 'kb-seed-0003-0003-0003-000000000003',
 0, 'Redis缓存运维手册\n\n一、监控指标\n内存使用率阈值85%\n命中率正常大于90%\n连接数正常小于500\n慢日志关注超过10ms的命令', 55, 78, 'Redis > 监控指标', 'paragraph', 'pending', NOW()),

('chk-seed-o002-002', 'doc-seed-o002-0000-0000-000000000002', 'kb-seed-0003-0003-0003-000000000003',
 1, '二、缓存清理策略\n当前配置allkeys-lru\n发布新版本后清理旧格式缓存\n知识库更新后清理检索缓存', 42, 58, 'Redis > 缓存清理', 'paragraph', 'pending', NOW()),

('chk-seed-o002-003', 'doc-seed-o002-0000-0000-000000000002', 'kb-seed-0003-0003-0003-000000000003',
 2, '三、持久化配置\nRDB和AOF混合持久化\n\n四、故障恢复方案\nRedis宕机重启检查AOF文件完整性\n内存OOM临时调大maxmemory排查大key\n主从断开检查网络连通性重新建立同步', 65, 92, 'Redis > 持久化与故障恢复', 'paragraph', 'pending', NOW()),

-- == 文档12: 告警SOP (2 chunks) ==
('chk-seed-o003-001', 'doc-seed-o003-0000-0000-000000000003', 'kb-seed-0003-0003-0003-000000000003',
 0, '平台告警处理标准操作流程SOP\n\n一、告警级别定义\nP0致命核心服务完全不可用响应5分钟内30分钟内恢复\nP1严重核心功能降级响应15分钟内2小时内恢复\nP2警告非核心功能异常响应30分钟内下一个工作日\nP3提示性能指标接近阈值', 90, 130, '告警SOP > 级别定义', 'paragraph', 'pending', NOW()),

('chk-seed-o003-002', 'doc-seed-o003-0000-0000-000000000003', 'kb-seed-0003-0003-0003-000000000003',
 1, '二、处理流程\n确认告警初步定位应急处理根因分析修复上线复盘总结\n\n三、常用应急命令\n服务重启docker compose restart backend\n回滚版本docker compose up -d --build\n流量降级修改ENABLE_MOCK_DATA开启降级', 72, 105, '告警SOP > 处理流程与命令', 'paragraph', 'pending', NOW());
