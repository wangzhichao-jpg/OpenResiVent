import { localCalculate } from './local-compute'

// 浏览器模式绝不调用服务端；依赖注入供无浏览器自动测试。
export async function runCalculation(payload, mode, options={}) {
  if (mode === 'browser') return (options.local || localCalculate)(payload)
  if (mode !== 'service') throw new Error('计算模式无效')
  const request = options.fetcher || fetch
  const response = await request('/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
  const result = await response.json()
  if (!response.ok) throw new Error(JSON.stringify(result.detail || result.errors || result))
  return result
}
