import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

/* ── Pixel Tyranny: De-componentize Element Icons -> Lucide ── */
import {
  ChevronDown, ChevronUp, Box, MessageCircle, MessageSquare, Check,
  CheckCircle2, XCircle, Clock, X, Coins, Library,
  Link, Copy, Cpu, BarChart2, BarChart3, FileText, PenTool,
  CheckSquare, Info, List, Loader2, Lock, Sparkles, ScrollText, Monitor,
  Moon, Send, Search, Headset, Settings, Share2, Sun,
  Power, TrendingUp, Upload, User, UserCircle2, AlertTriangle, AlertOctagon,
} from 'lucide-vue-next'

import VueECharts from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart, ScatterChart, HeatmapChart, RadarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, ToolboxComponent, VisualMapComponent } from 'echarts/components'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

import '@/styles/variables.css'
import '@/styles/global.css'
import '@/styles/element-dark-overrides.css'
import { initTheme } from '@/composables/useTheme'
import App from './App.vue'
import router from './router/index.js'
import { toast } from '@/components/v2/MessageToast.js'

initTheme('light')

use([CanvasRenderer, LineChart, BarChart, PieChart, ScatterChart, HeatmapChart, RadarChart,
     GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, ToolboxComponent, VisualMapComponent])

const app = createApp(App)

// Disable Element Plus native messages and route them to our custom Dynamic Island Toast
window.$message = ElMessage // Fallback
const customMessage = function(options) {
  if (typeof options === 'string') toast.info(options)
  else if (options.type === 'success') toast.success(options.message)
  else if (options.type === 'error') toast.error(options.message)
  else toast.info(options.message)
}
customMessage.success = (msg) => toast.success(msg)
customMessage.error = (msg) => toast.error(msg)
customMessage.warning = (msg) => toast.error(msg) // map warning to error visually
customMessage.info = (msg) => toast.info(msg)

app.config.globalProperties.$message = customMessage

/* Map Element Plus Icon names to Lucide Icons to prevent breaking existing code */
const icons = {
  ArrowDown: ChevronDown,
  ArrowUp: ChevronUp,
  Box,
  ChatDotRound: MessageCircle,
  ChatLineRound: MessageSquare,
  Check,
  CircleCheckFilled: CheckCircle2,
  CircleCloseFilled: XCircle,
  Clock,
  Close: X,
  Coin: Coins,
  Collection: Library,
  Connection: Link,
  CopyDocument: Copy,
  Cpu,
  BarChart3,
  DataAnalysis: BarChart2,
  Document: FileText,
  EditPen: PenTool,
  Finished: CheckSquare,
  InfoFilled: Info,
  List,
  Loading: Loader2,
  Lock,
  MagicStick: Sparkles, /* AI no longer magic stick, but high-end sparkles */
  Memo: ScrollText,
  Monitor,
  Moon,
  Promotion: Send,
  Search,
  Service: Headset,
  Setting: Settings,
  Share: Share2,
  Sunny: Sun,
  SwitchButton: Power,
  TrendCharts: TrendingUp,
  Upload,
  User,
  UserFilled: UserCircle2,
  Warning: AlertTriangle,
  WarningFilled: AlertOctagon,
}

for (const [key, component] of Object.entries(icons)) {
  // Safely enforce 1.5px stroke width default
  if (!component.props) component.props = {}
  if (typeof component.props === 'object' && !Array.isArray(component.props)) {
    component.props.strokeWidth = { type: [Number, String], default: 1.5 }
  }
  app.component(key, component)
}

app
  .use(createPinia())
  .use(ElementPlus, { locale: zhCn })
  .use(router)
  .component('v-chart', VueECharts)
  .mount('#app')
