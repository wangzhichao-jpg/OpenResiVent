import { describe, it, expect } from 'vitest'
import YAML from 'yaml'
import shaft from '../../cases/studies/shaft_sweep.yaml?raw'
import makeup from '../../cases/studies/makeup_sweep.yaml?raw'
import { exampleDefinition, baseCase, makeDraft, buildDefinition, encodeDefinition, parseDefinition } from './sweep'

describe('扫描界面定义映射',()=>{
  it.each([['shaft',shaft],['makeup',makeup]])('%s 与研究定义一致',(kind,text)=>{
    const original=YAML.parse(text)
    const result=buildDefinition(exampleDefinition(kind),makeDraft(original),Object.keys(original.metrics),'factorial',42,20)
    expect(result).toEqual(original)
    expect(parseDefinition(encodeDefinition(result))).toEqual({kind,spec:original})
    expect(baseCase(kind).module).toBe(kind==='shaft'?'shaft':'makeup_design')
  })
  it('支持水平选择、连续范围及确定性种子',()=>{
    const spec=exampleDefinition('makeup');const draft=makeDraft(spec)
    draft[0].kind='range';draft[0].text='[0.6, 3]';draft[1].enabled=false
    const result=buildDefinition(spec,draft,['opening_m2'],'lhs',2026,20)
    expect(result.factors.n50_per_h.range).toEqual([0.6,3]);expect(result.factors.hood_m3_h).toBeUndefined()
    expect(result.seed).toBe(2026);expect(result.count).toBe(20)
    expect(()=>buildDefinition(spec,draft,['opening_m2'],'factorial',1,20)).toThrow()
    expect(()=>parseDefinition('method: other')).toThrow()
  })
})
