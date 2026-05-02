---
trigger: glob
globs: frontend/src/**/*.vue
---

# Frontend Vue3 约束 (改 .vue 时自动生效)

## axios 必须用三套封装客户端 (核心)

`frontend/src/api/request.js` 已经封装好 3 套, 组件 / store / composable **绝不**自己 `new axios` 或裸 `fetch`:

| 后端路径前缀 | 用什么 | 响应行为 |
|---|---|---|
| `/api/*`    | `requestBusiness` | 自动解包 `{code,data,message}`, 带 L1 缓存 + SWR + 请求去重, 30s timeout |
| `/admin/*`  | `requestAdmin`    | 裸对象响应, 15s timeout |
| `/api/v1/*` | `requestWorkflow` | workflow 接口, 60s timeout |

封装新接口时在 `frontend/src/api/admin/<module>.js` 或 `frontend/src/api/business/<module>.js` 加, 组件只 import 模块, 不直接调 axios.

## UI 状态完整性 (不写半成品)

所有数据驱动视图必须显式处理 **4 种状态**, 不要只写 happy path:

- **loading** - 骨架屏 / spinner / 占位文案
- **empty**   - 空数据友好提示 (不要白屏)
- **error**   - 错误回退 + 重试按钮 (不要只 ElMessage 完事)
- **success** - 正常渲染

列表 / 表单 / 弹窗 / 详情页 / Dashboard 卡片都适用.

## 组件约束

- 优先 `<script setup>`; `props` / `emits` 显式声明; 不要靠隐式 `$attrs`
- 复杂业务逻辑下沉到 `frontend/src/composables/` 或 Pinia store (`frontend/src/stores/`); **不要全塞模板**
- 单 SFC > 500 行主动拆 (拆子组件 / 拆 composable)
- 全局状态统一 Pinia, 不要 provide/inject 串到处都是

## 路由与权限

- admin 角色登录后跳 `/console/dashboard`; 业务角色跳业务前台首页 (具体在 `frontend/src/router/`)
- 401 由 `request.js::handleNetworkError` 统一处理 (清 token + replace 到 `/login`); 组件**不要**自己判断 401

## 禁止

- 硬编码 baseURL (已在 `request.js` 配好)
- 直接读 `localStorage.token` 拼请求头 (拦截器 `injectAuth` 已处理)
- 生产环境留 `console.log` (开发调试日志请走 `import.meta.env.DEV` 判断)
- `requestBusiness` 用在 `/admin/*` 路径上, 或反过来 (响应解包格式不一样, 一定踩坑)
- `npm install` / 改 `package.json` 不和用户确认

## 强烈建议

- 表单优先 Element Plus + `el-form-item` 自带的 rules, 不要自造校验
- 图标统一 lucide-vue-next; 不要混用多套图标库
- 颜色 / 间距走项目已有的 design token / Tailwind 类, 不要随手写魔法值
