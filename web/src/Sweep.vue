<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { exampleDefinition, baseCase, parseDefinition, encodeDefinition, makeDraft, buildDefinition } from './sweep'

const kind=ref('shaft'), original=ref(), draft=ref([]), metrics=ref([]), method=ref('factorial'), seed=ref(42), count=ref(20)
const criteria=ref({}), state=ref(null), result=ref(null), error=ref(''), chartEl=ref(null)
let timer, chart
const factorNames={floors:'层数',width:'竖井宽度（m）',depth:'竖井深度（m）',fraction:'同时使用率',fan_kind:'风机类型',valve_class:'止回阀等级',n50_per_h:'气密性（次/h）',hood_m3_h:'油烟机风量（m³/h）',bedrooms:'卧室数'}
const metricNames={bottom_m3_s:'底层排风量（m³/s）',worst_m3_s:'最不利运行层排风量（m³/s）',backflow_m3_s:'最大倒灌量（m³/s）',mechanical_m3_s:'最小机械补风（m³/s）',opening_m2:'最小自然补风面积（m²）'}
function useSpec(k,spec) {
  kind.value=k; original.value=structuredClone(spec);draft.value=makeDraft(spec);metrics.value=Object.keys(spec.metrics)
  method.value=spec.method;seed.value=spec.seed ?? 42;count.value=spec.count ?? 20
  criteria.value=Object.fromEntries(Object.keys(spec.metrics).map(m=>[m,{enabled:!!spec.criteria?.[m],op:spec.criteria?.[m]?.op ?? 'min',limit:spec.criteria?.[m]?.limit ?? 0}]))
  error.value=''
}
function selectKind(k){if(state.value?.status==='running')return;useSpec(k,exampleDefinition(k));result.value=null;state.value=null;clearInterval(timer);sessionStorage.removeItem('orv-sweep-job')}
useSpec('shaft',exampleDefinition('shaft'))
const metricOptions=computed(()=>Object.keys(original.value?.metrics ?? {}))
function definition() {
  const spec=buildDefinition(original.value,draft.value,metrics.value,method.value,seed.value,count.value)
  spec.criteria={}
  for(const key of metrics.value) if(criteria.value[key]?.enabled) spec.criteria[key]={op:criteria.value[key].op,limit:Number(criteria.value[key].limit)}
  if(!Object.keys(spec.criteria).length) delete spec.criteria
  return spec
}
function saveBlob(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
function exportDefinition(){try{saveBlob(new Blob([encodeDefinition(definition())],{type:'text/yaml'}),'扫描定义.yaml')}catch(e){error.value=e.message}}
async function importDefinition(event){try{if(state.value?.status==='running')throw new Error('扫描运行中不能切换定义');const parsed=parseDefinition(await event.target.files[0].text());useSpec(parsed.kind,parsed.spec);result.value=null;state.value=null;clearInterval(timer);sessionStorage.removeItem('orv-sweep-job')}catch(e){error.value=e.message}}
async function poll(job) {
  try {
    const response=await fetch(`/sweep/${job}`);if(!response.ok)throw new Error('无法读取扫描进度')
    state.value=await response.json()
    if(state.value.status==='completed') {
      clearInterval(timer); const r=await fetch(`/sweep/${job}/results`);if(!r.ok)throw new Error('无法读取扫描统计')
      result.value=await r.json();await nextTick();renderChart()
    } else if(state.value.status==='failed') { clearInterval(timer);error.value=state.value.error || '扫描失败' }
  } catch(e) {clearInterval(timer);error.value=e.message}
}
async function run(){
  try {
    error.value='';result.value=null;clearInterval(timer)
    const spec=definition();const response=await fetch('/sweep',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({spec,case:baseCase(kind.value),workers:2})})
    const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))
    state.value=body;sessionStorage.setItem('orv-sweep-job',JSON.stringify({id:body.job_id,kind:kind.value}));timer=setInterval(()=>poll(body.job_id),1000);await poll(body.job_id)
  } catch(e){error.value=e.message}
}
function renderChart(){
  if(!chartEl.value || !result.value)return
  const rows=result.value.sensitivity;chart?.dispose();chart=echarts.init(chartEl.value)
  chart.setOption({title:{text:'敏感性（主效应极差或标准化秩回归系数）'},tooltip:{},grid:{left:150,right:30},xAxis:{type:'value'},yAxis:{type:'category',data:rows.map(x=>`${metricNames[x.metric]||x.metric} / ${factorNames[x.factor]||x.factor}`)},series:[{type:'bar',data:rows.map(x=>x.value)}]})
}
async function download(name){try{const response=await fetch(`/sweep/${state.value.job_id}/files/${name}`);if(!response.ok)throw new Error('下载失败');saveBlob(await response.blob(),name)}catch(e){error.value=e.message}}
onMounted(()=>{try{const saved=JSON.parse(sessionStorage.getItem('orv-sweep-job') || 'null');if(saved?.id && saved?.kind){useSpec(saved.kind,exampleDefinition(saved.kind));timer=setInterval(()=>poll(saved.id),1000);poll(saved.id)}}catch{sessionStorage.removeItem('orv-sweep-job')}})
onBeforeUnmount(()=>{clearInterval(timer);chart?.dispose()})
</script>
<template>
<el-card><template #header>参数扫描</template>
<p>选择示例模型及因子；取值和模型条件均须核实。扫描结果仅反映指定假设，不代表现场检测或总体概率。</p>
<el-alert v-if="error" type="error" :title="error" :closable="false" show-icon/>
<label>计算模块 <el-select :model-value="kind" :disabled="state?.status==='running'" @update:model-value="selectKind"><el-option label="高层竖井" value="shaft"/><el-option label="户内补风" value="makeup"/></el-select></label>
<h3>因子设置</h3><p>水平或范围使用列表格式，例如 [6, 18, 33]；连续范围输入 [下限, 上限]。文本水平须与示例算例定义一致。</p>
<div v-for="row in draft" :key="row.name" class="factor"><el-checkbox v-model="row.enabled">{{factorNames[row.name]||row.name}}</el-checkbox><el-select v-model="row.kind" class="factor-kind"><el-option label="离散水平" value="values"/><el-option label="连续范围" value="range" :disabled="method==='factorial'"/></el-select><el-input v-model="row.text" class="factor-values"/></div>
<label>抽样方式 <el-select v-model="method"><el-option label="全因子" value="factorial"/><el-option label="拉丁超立方" value="lhs"/></el-select></label>
<template v-if="method==='lhs'"><label> 随机种子 <el-input-number v-model="seed" :min="0"/></label><label> 样本数 <el-input-number v-model="count" :min="2" :max="100000"/></label><p>文本类别按所列顺序编码，敏感性系数依赖该顺序。</p></template>
<h3>指标与判据</h3><div v-for="key in metricOptions" :key="key" class="factor"><el-checkbox-group v-model="metrics"><el-checkbox :value="key">{{metricNames[key]||key}}</el-checkbox></el-checkbox-group><el-checkbox v-model="criteria[key].enabled" :disabled="!metrics.includes(key)">启用阈值</el-checkbox><el-select v-model="criteria[key].op" class="factor-kind"><el-option label="不小于" value="min"/><el-option label="不大于" value="max"/></el-select><el-input-number v-model="criteria[key].limit" :step="0.01"/></div>
<div class="actions"><el-button type="primary" :disabled="state?.status==='running'" @click="run">开始扫描</el-button><el-button @click="exportDefinition">导出定义 YAML</el-button><label class="file">导入定义 YAML<input type="file" accept=".yaml,.yml" @change="importDefinition"></label></div>
<p v-if="state">状态：{{state.status==='running'?'运行中':state.status==='completed'?'完成':'失败'}}；进度 {{state.completed}} / {{state.total}}</p>
</el-card>
<el-card v-if="result"><template #header>扫描结果</template><p>百分位采用线性插值；分组达标率按扫描组合等权计算。</p>
<el-table :data="Object.entries(result.metrics).map(([name,v])=>({name:metricNames[name]||name,...v}))"><el-table-column prop="name" label="指标"/><el-table-column v-for="x in ['min','p10','p50','p90','max']" :key="x" :prop="x" :label="{min:'最小',p10:'P10',p50:'中位数',p90:'P90',max:'最大'}[x]"/></el-table>
<h3>分组及达标率</h3><el-table :data="result.groups"><el-table-column prop="metric" label="指标"/><el-table-column prop="factor" label="因子"/><el-table-column prop="level" label="水平"/><el-table-column prop="count" label="样本数"/><el-table-column prop="mean" label="均值"/><el-table-column label="达标率"><template #default="s">{{s.row.pass_rate===null?'未设置判据':(s.row.pass_rate*100).toFixed(1)+'%'}}</template></el-table-column></el-table>
<div ref="chartEl" class="sweep-chart"></div><p>不同指标量纲可能不同，请分别理解图中数值。</p><el-button @click="download('samples.csv')">下载 CSV</el-button><el-button @click="download('results.xlsx')">下载 XLSX</el-button><el-button @click="download('summary.docx')">下载 DOCX</el-button>
</el-card>
</template>
<style scoped>.factor{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:8px 0}.factor-kind{width:140px}.factor-values{width:300px}.sweep-chart{height:520px;min-width:320px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}</style>
