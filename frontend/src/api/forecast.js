// 桥接文件：重新导出 api/business/forecast，避免旧引用静默返回空对象
export { forecastApi as default, forecastApi } from './business/forecast'

