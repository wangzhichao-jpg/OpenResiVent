import { describe, it, expect } from 'vitest'
import YAML from 'yaml'
import { cloneCase, parseCase, encodeCase, shaftRun, parameterSources, exampleNoise } from './cases'
import vent from '../../cases/book/ch02/ex2-03.yaml?raw'
import home from '../../cases/book/ch05/ex5-07.yaml?raw'
import shaft from '../../cases/reports/shaft_example.yaml?raw'
import single from '../../cases/book/ch02/ex2-01.yaml?raw'

describe('表单算例映射', () => {
  it.each([['ventilation',vent],['dwelling',home],['shaft',shaft]])('%s 与样例一致', (name,text) => {
    expect(cloneCase(name)).toEqual(YAML.parse(text))
  })
  it('二氧化碳法示例与原始输入一致并用可读标准编号显示', () => {
    const expected=YAML.parse(single); expected.meta.rules=['JGJ/T 440-2018']
    expect(cloneCase('single')).toEqual(expected)
  })
  it('编辑、导入与导出保持数据', () => {
    const x=cloneCase('ventilation'); x.input.occupants=4
    expect(parseCase(encodeCase(x,'yaml'))).toEqual(x)
    expect(parseCase(encodeCase(x,'json'))).toEqual(x)
    expect(() => parseCase('input: {}')).toThrow()
    expect(cloneCase('ventilation').input.occupants).not.toBe(4)
  })
  it('逐项参数来源按默认与修改区分', () => {
    const x=cloneCase('ventilation'); x.input.area_m2=80
    const rows=parameterSources('ventilation',x)
    expect(rows.find(r=>r.parameter==='面积').source).toBe('用户输入')
    expect(rows.find(r=>r.parameter==='净高').source).toBe('假设，需作者确认')
    expect(rows.find(r=>r.parameter==='计算方法及规则包').source).toBe('通用参数')
    expect(parameterSources('shaft',cloneCase('shaft')).find(r=>r.parameter==='竖井.竖井宽度').source).toContain('通用参数')
  })
  it('噪声默认参数不冒称用户输入', () => {
    const x=cloneCase('ventilation');x.input.noise=exampleNoise()
    const before=parameterSources('ventilation',x)
    expect(before.filter(r=>r.source==='用户输入')).toHaveLength(0)
    x.input.noise.fan_power_db[0]=99
    expect(parameterSources('ventilation',x).filter(r=>r.source==='用户输入')).toHaveLength(1)
  })
  it('竖井报告的输入映射到计算模块', () => {
    const x=cloneCase('shaft'); const y=shaftRun(x)
    expect(y.module).toBe('shaft'); expect(y.input).toEqual(x.input.shaft)
  })
})
