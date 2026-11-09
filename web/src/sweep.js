import YAML from 'yaml'
import shaftDefinition from '../../cases/studies/shaft_sweep.yaml?raw'
import shaftBase from '../../cases/studies/shaft_base.yaml?raw'
import makeupDefinition from '../../cases/studies/makeup_sweep.yaml?raw'
import makeupBase from '../../cases/studies/makeup_base.yaml?raw'

const definitions={shaft:YAML.parse(shaftDefinition),makeup:YAML.parse(makeupDefinition)}
const bases={shaft:YAML.parse(shaftBase),makeup:YAML.parse(makeupBase)}
export const moduleLabels={shaft:'高层竖井',makeup:'户内补风'}
export function exampleDefinition(kind) { return structuredClone(definitions[kind]) }
export function baseCase(kind) { return structuredClone(bases[kind]) }
export function parseDefinition(text) {
  const spec=YAML.parse(text)
  if(!spec || typeof spec!=='object' || !spec.factors || !spec.metrics || !['factorial','lhs'].includes(spec.method)) throw new Error('扫描定义缺少因子、指标或抽样方式')
  const kind=Object.keys(definitions).find(k=>definitions[k].base_case===spec.base_case)
  if(!kind) throw new Error('仅支持竖井和户内补风示例基准算例')
  if(Object.values(spec.criteria || {}).some(x=>x.rule)) throw new Error('当前界面仅支持数值阈值判据，规则包判据请通过命令行使用')
  return {kind,spec}
}
export function encodeDefinition(spec) { return YAML.stringify(spec) }
export function makeDraft(spec) {
  return Object.entries(spec.factors).map(([name,value])=>({name,enabled:true,kind:value.range?'range':'values',text:JSON.stringify(value.range || value.values)}))
}
export function buildDefinition(original,draft,metrics,method,seed,count) {
  const spec=structuredClone(original)
  spec.method=method
  if(method==='lhs') { spec.seed=Number(seed); spec.count=Number(count) } else { delete spec.seed; delete spec.count }
  spec.factors={}
  for(const row of draft.filter(x=>x.enabled)) {
    if(method==='factorial' && row.kind==='range') throw new Error(`${row.name} 全因子扫描须使用离散水平`)
    let values
    try { values=YAML.parse(row.text) } catch { throw new Error(`${row.name} 的水平或范围格式有误`) }
    if(!Array.isArray(values) || !values.length || (row.kind==='range' && (values.length!==2 || !values.every(Number.isFinite) || values[0]>=values[1]))) throw new Error(`${row.name} 的水平或范围无效`)
    spec.factors[row.name]={[row.kind]:values}
  }
  if(!Object.keys(spec.factors).length) throw new Error('请至少选择一个因子')
  if(!metrics.length) throw new Error('请至少选择一个指标')
  spec.metrics=Object.fromEntries(Object.entries(original.metrics).filter(([key])=>metrics.includes(key)))
  if(original.criteria) spec.criteria=Object.fromEntries(Object.entries(original.criteria).filter(([key])=>metrics.includes(key)))
  if(method==='lhs' && (!Number.isInteger(spec.seed) || !Number.isInteger(spec.count) || spec.count<2)) throw new Error('种子须为整数，样本数不少于2')
  return spec
}
