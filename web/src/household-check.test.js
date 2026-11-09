import { describe, it, expect } from 'vitest'
import {newHousehold, classifiedHousehold, exportHousehold, importHousehold, invalidate, setNoise} from './household-check'

describe('一户校核算例与状态', () => {
  it('导出导入完整复原，包括可选噪声', () => {
    const x=newHousehold(); setNoise(x,true); x.sources['ventrate.area_m2']='用户输入'
    expect(importHousehold(exportHousehold(x))).toEqual(x)
    expect(()=>importHousehold('{}')).toThrow()
  })
  it('按输入与示例逐项标识来源', () => {
    const x=newHousehold();x.ventilation.input.bedrooms[0].area_m2=20
    const y=classifiedHousehold(x)
    expect(y.sources['ventrate.bedrooms[1].area_m2']).toBe('用户输入')
    expect(y.sources['ventrate.area_m2']).toContain('假设')
  })
  it('修改上游标记下游失效', () => {
    expect(invalidate([true,true,true,true,true,true],2)).toEqual([true,true,false,false,false,false])
  })
})
