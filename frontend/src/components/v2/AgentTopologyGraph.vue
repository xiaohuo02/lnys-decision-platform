<template>
  <div class="topo" ref="containerRef">
    <svg :width="svgW" :height="svgH" class="topo__svg">
      <defs>
        <marker id="topo-arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6" fill="none" stroke="var(--v2-text-4)" stroke-width="1"/>
        </marker>
        <marker id="topo-arrow-active" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6" fill="none" stroke="var(--v2-text-1)" stroke-width="1.2"/>
        </marker>
      </defs>

      <!-- Edges -->
      <g class="topo__edges">
        <path
          v-for="(edge, i) in renderedEdges" :key="'e' + i"
          :d="edge.d"
          class="topo__edge"
          :class="{
            'topo__edge--active': edge.active,
            'topo__edge--done': edge.done,
          }"
          :marker-end="edge.active || edge.done ? 'url(#topo-arrow-active)' : 'url(#topo-arrow)'"
        />
        <!-- Animated pulse along active edges -->
        <circle
          v-for="(edge, i) in renderedEdges.filter(e => e.active)" :key="'pulse' + i"
          r="3" class="topo__edge-pulse"
        >
          <animateMotion :dur="edge.dur || '1.2s'" repeatCount="indefinite" :path="edge.d" />
        </circle>
      </g>

      <!-- Nodes -->
      <g v-for="node in renderedNodes" :key="node.id"
         class="topo__node"
         :class="'topo__node--' + node.status"
         :transform="`translate(${node.x}, ${node.y})`"
         @click="$emit('node-click', node)"
         style="cursor: pointer;"
      >
        <!-- Node body -->
        <rect
          :x="-nodeW / 2" :y="-nodeH / 2"
          :width="nodeW" :height="nodeH"
          :rx="8"
          class="topo__node-bg"
        />
        <!-- Status indicator dot -->
        <circle :cx="-nodeW / 2 + 14" cy="0" r="4" class="topo__node-dot" />
        <!-- Label -->
        <text :x="0" :y="1" class="topo__node-label" text-anchor="middle" dominant-baseline="central">
          {{ node.shortLabel }}
        </text>
        <!-- Latency badge -->
        <text v-if="node.latency" :x="nodeW / 2 - 8" :y="nodeH / 2 + 14" class="topo__node-meta" text-anchor="end">
          {{ node.latency }}
        </text>
        <!-- Spinner ring for running -->
        <circle v-if="node.status === 'running'" cx="0" cy="0" :r="nodeH / 2 + 6"
          class="topo__node-spinner" fill="none" stroke-width="2"
        />
      </g>
    </svg>

    <!-- Legend -->
    <div class="topo__legend">
      <span class="topo__legend-item"><span class="topo__legend-dot topo__legend-dot--pending"></span>等待</span>
      <span class="topo__legend-item"><span class="topo__legend-dot topo__legend-dot--running"></span>运行中</span>
      <span class="topo__legend-item"><span class="topo__legend-dot topo__legend-dot--completed"></span>完成</span>
      <span class="topo__legend-item"><span class="topo__legend-dot topo__legend-dot--error"></span>失败</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  /** Array of { name, status, latency_ms } */
  steps: { type: Array, default: () => [] },
  /** Workflow type to determine DAG layout */
  workflowType: { type: String, default: 'business_overview' },
})

defineEmits(['node-click'])

const containerRef = ref(null)
const nodeW = 120
const nodeH = 40
const gapX = 180
const gapY = 70

// ── 步骤名显示映射 ──
const STEP_LABELS = {
  data_preparation: '数据准备',
  customer_intel: '客户洞察',
  sales_forecast: '销售预测',
  sentiment_intel: '舆情分析',
  fraud_scoring: '欺诈风控',
  inventory: '库存优化',
  insight_composer: '智能报告',
}
function stepLabel(name) { return STEP_LABELS[name] || name }

// ── Map step names to DAG node positions ──
// Auto-detect parallel layout from step.parallel flag
const dagLayout = computed(() => {
  if (!props.steps.length) return { nodes: [], edges: [] }

  // Group steps into layers: sequential steps get own layer, parallel steps share a layer
  const layers = []
  let parallelBatch = []
  props.steps.forEach(s => {
    if (s.parallel) {
      parallelBatch.push(s)
    } else {
      if (parallelBatch.length) {
        layers.push(parallelBatch)
        parallelBatch = []
      }
      layers.push([s])
    }
  })
  if (parallelBatch.length) layers.push(parallelBatch)

  return buildFromLayers(layers)
})

function buildFromLayers(layers) {
  const nodes = []
  const edges = []

  layers.forEach((layer, layerIdx) => {
    const layerWidth = layer.length * gapX
    const startX = -layerWidth / 2 + gapX / 2

    layer.forEach((step, nodeIdx) => {
      const label = stepLabel(step.name)
      nodes.push({
        id: step.name,
        name: step.name,
        label,
        shortLabel: label.length > 6 ? label.slice(0, 5) + '…' : label,
        layerIdx,
        isParallel: !!step.parallel,
        x: startX + nodeIdx * gapX,
        y: layerIdx * gapY,
        status: step.status || 'pending',
        latency: step.latency_ms != null ? (step.latency_ms / 1000).toFixed(1) + 's' : null,
        latency_ms: step.latency_ms,
      })
    })

    // Edges: every node in current layer → every node in next layer
    if (layerIdx < layers.length - 1) {
      const nextLayer = layers[layerIdx + 1]
      layer.forEach(src => {
        nextLayer.forEach(tgt => {
          const srcNode = nodes.find(n => n.id === src.name)
          const tgtNode = nodes.find(n => n.id === tgt.name)
          if (!srcNode || !tgtNode) return
          edges.push({
            from: src.name, to: tgt.name,
            active: srcNode.status === 'completed' && tgtNode.status === 'running',
            done: srcNode.status === 'completed' && (tgtNode.status === 'completed' || tgtNode.status === 'running'),
          })
        })
      })
    }
  })

  return { nodes, edges }
}

function buildLinearDag(steps) {
  const nodes = steps.map((s, i) => {
    const label = stepLabel(s.name)
    return {
      id: s.name,
      name: s.name,
      label,
      shortLabel: label.length > 6 ? label.slice(0, 5) + '…' : label,
      layerIdx: i,
      isParallel: false,
      x: 0,
      y: i * gapY,
      status: s.status || 'pending',
      latency: s.latency_ms != null ? (s.latency_ms / 1000).toFixed(1) + 's' : null,
      latency_ms: s.latency_ms,
    }
  })

  const edges = []
  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      from: nodes[i].id,
      to: nodes[i + 1].id,
      active: nodes[i].status === 'completed' && nodes[i + 1].status === 'running',
      done: nodes[i].status === 'completed',
    })
  }
  return { nodes, edges }
}

// ── SVG dimensions ──
const svgW = computed(() => {
  const nodes = dagLayout.value.nodes
  if (!nodes.length) return 400
  const xs = nodes.map(n => n.x)
  return Math.max(400, Math.max(...xs) - Math.min(...xs) + nodeW + 80)
})

const svgH = computed(() => {
  const nodes = dagLayout.value.nodes
  if (!nodes.length) return 200
  const ys = nodes.map(n => n.y)
  return Math.max(200, Math.max(...ys) - Math.min(...ys) + nodeH + 80)
})

// ── Center offset ──
const offsetX = computed(() => svgW.value / 2)
const offsetY = computed(() => 40)

// ── Rendered nodes with offset ──
const renderedNodes = computed(() =>
  dagLayout.value.nodes.map(n => ({
    ...n,
    x: n.x + offsetX.value,
    y: n.y + offsetY.value,
  }))
)

// ── Rendered edges as SVG paths ──
const renderedEdges = computed(() => {
  const nodeMap = new Map(renderedNodes.value.map(n => [n.id, n]))
  return dagLayout.value.edges.map(e => {
    const src = nodeMap.get(e.from)
    const tgt = nodeMap.get(e.to)
    if (!src || !tgt) return null
    const x1 = src.x, y1 = src.y + nodeH / 2
    const x2 = tgt.x, y2 = tgt.y - nodeH / 2
    const cy1 = y1 + (y2 - y1) * 0.4
    const cy2 = y1 + (y2 - y1) * 0.6
    return {
      ...e,
      d: `M${x1},${y1} C${x1},${cy1} ${x2},${cy2} ${x2},${y2}`,
      dur: '1s',
    }
  }).filter(Boolean)
})
</script>

<style scoped>
.topo { position: relative; overflow: auto; }
.topo__svg { display: block; margin: 0 auto; }

/* ── Edges ── */
.topo__edge { fill: none; stroke: var(--v2-border-2); stroke-width: 1.5; transition: stroke 0.3s, stroke-width 0.3s; }
.topo__edge--active { stroke: var(--v2-text-1); stroke-width: 2; stroke-dasharray: 6 4; animation: topo-dash 0.8s linear infinite; }
.topo__edge--done { stroke: var(--v2-text-3); stroke-width: 1.5; }
@keyframes topo-dash { to { stroke-dashoffset: -10; } }

.topo__edge-pulse { fill: var(--v2-text-1); opacity: 0.7; }

/* ── Nodes ── */
.topo__node { transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.topo__node-bg { fill: var(--v2-bg-card); stroke: var(--v2-border-1); stroke-width: 1; transition: all 0.3s; }
.topo__node:hover .topo__node-bg { stroke: var(--v2-text-1); stroke-width: 1.5; }

.topo__node-dot { transition: fill 0.3s; }
.topo__node--pending .topo__node-dot { fill: var(--v2-text-4); }
.topo__node--running .topo__node-dot { fill: var(--v2-text-1); }
.topo__node--completed .topo__node-dot { fill: var(--v2-success); }
.topo__node--error .topo__node-dot { fill: var(--v2-error); }
.topo__node--failed .topo__node-dot { fill: var(--v2-error); }
.topo__node--hitl_pending .topo__node-dot { fill: var(--v2-warning, #f59e0b); }

.topo__node--running .topo__node-bg { stroke: var(--v2-text-1); stroke-width: 1.5; }
.topo__node--completed .topo__node-bg { stroke: var(--v2-success); }
.topo__node--error .topo__node-bg, .topo__node--failed .topo__node-bg { stroke: var(--v2-error); }

.topo__node-label { font-size: 12px; font-weight: 500; fill: var(--v2-text-1); font-family: var(--v2-font-sans); pointer-events: none; }
.topo__node-meta { font-size: 10px; fill: var(--v2-text-3); font-family: var(--v2-font-mono); pointer-events: none; }

/* Spinner for running node */
.topo__node-spinner {
  stroke: var(--v2-text-1);
  stroke-dasharray: 40 120;
  stroke-linecap: round;
  animation: topo-spin 1.2s linear infinite;
  transform-origin: center;
}
@keyframes topo-spin { to { transform: rotate(360deg); } }

/* ── Legend ── */
.topo__legend { display: flex; gap: 16px; justify-content: center; padding: 8px 0; }
.topo__legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--v2-text-3); }
.topo__legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.topo__legend-dot--pending { background: var(--v2-text-4); }
.topo__legend-dot--running { background: var(--v2-text-1); }
.topo__legend-dot--completed { background: var(--v2-success); }
.topo__legend-dot--error { background: var(--v2-error); }
</style>
