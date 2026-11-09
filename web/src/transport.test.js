import { describe, it, expect, vi } from 'vitest'
import { runCalculation } from './transport'
import { cloneCase, makeupCase } from './cases'

describe('本地和服务计算模式', () => {
  it('浏览器模式不请求本机服务', async () => {
    const payload=cloneCase('dwelling')
    const local=vi.fn(async data=>({result:data.module}))
    const fetcher=vi.fn(()=>{throw new Error('不应请求')})
    expect(await runCalculation(payload,'browser',{local,fetcher})).toEqual({result:'dwelling_pressure'})
    expect(local).toHaveBeenCalledWith(payload)
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('服务模式发送相同算例且传播错误', async () => {
    const payload=makeupCase(cloneCase('dwelling').input,0.6)
    const fetcher=vi.fn(async()=>({ok:true,json:async()=>({value:2})}))
    expect(await runCalculation(payload,'service',{fetcher})).toEqual({value:2})
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(payload)
    expect(payload.module).toBe('makeup_design')
    expect(payload.input.n50_per_h).toBe(0.6)
    await expect(runCalculation(payload,'unknown')).rejects.toThrow('计算模式无效')
  })
})
