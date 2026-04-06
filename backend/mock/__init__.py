# -*- coding: utf-8 -*-
"""backend/mock — 集中管理 Mock / 降级数据

当 ENABLE_MOCK_DATA=true 且真实数据源（Agent/DB/CSV）均不可用时，
Service 层从此包获取固定示例数据，避免 Mock 数据散落在各 Service 文件中。
"""
