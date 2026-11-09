import { cloneCase, exampleNoise } from './cases'

export function newHousehold() {
  return {title:'典型三居室示例',ventilation:cloneCase('ventilation'),dwelling:cloneCase('dwelling'),sources:{}}
}
export function classifiedHousehold(data) {
  const value=structuredClone(data), baseline=newHousehold()
  function visit(current,reference,path) {
    if(Array.isArray(current)) return current.forEach((x,i)=>visit(x,Array.isArray(reference)?reference[i]:undefined,`${path}[${i+1}]`))
    if(current && typeof current==='object') return Object.entries(current).forEach(([key,x])=>{if(!['source','assumption','assumptions'].includes(key))visit(x,reference?.[key],path?`${path}.${key}`:key)})
    if(JSON.stringify(current)!==JSON.stringify(reference)) value.sources[path]='用户输入'
    else if(!value.sources[path]) value.sources[path]='假设，需用户确认'
  }
  for(const name of ['ventilation','dwelling']) visit(value[name].input,baseline[name].input,value[name].module)
  return value
}
export function exportHousehold(data) { return JSON.stringify(data,null,2) }
export function importHousehold(text) {
  const value=JSON.parse(text)
  if (!value || typeof value.title!=='string' || value.ventilation?.module!=='ventrate' || value.dwelling?.module!=='dwelling_pressure' || !value.ventilation.input || !value.dwelling.input || !value.sources || typeof value.sources!=='object') throw new Error('一户算例格式无效')
  return structuredClone(value)
}
export function invalidate(flags, step) { return flags.map((value,index)=>index>=step?false:value) }
export function setNoise(data, enabled) { if(enabled) data.ventilation.input.noise=exampleNoise(); else delete data.ventilation.input.noise }
