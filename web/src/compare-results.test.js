import { describe, expect, it } from 'vitest'
import { compareResults } from './compare-results'

describe('跨平台结果比较', () => {
  it('仅精确命名的质量残差使用绝对误差并校验收敛', () => {
    const summary=compareResults({mass_residual_kg_s:1e-14,flow:0.1},{mass_residual_kg_s:2e-14,flow:0.1},'dwelling')
    expect(summary.numeric).toBe(2)
    expect(summary.diagnostics).toBe(1)
    expect(summary.strict).toBe(1)
    expect(summary.absoluteRequired).toBe(1)
    expect(summary.maxDiagnosticAbsolute).toBeCloseTo(1e-14,20)
    expect(() => compareResults({mass_residual_kg_s:1e-14},{mass_residual_kg_s:2e-13},'dwelling')).toThrow()
    expect(() => compareResults({mass_residual_kg_s:1e-11},{mass_residual_kg_s:1e-11},'dwelling')).toThrow()
    expect(() => compareResults({mass_residual_kg_s_extra:1e-14},{mass_residual_kg_s_extra:2e-14},'dwelling')).toThrow()
    expect(() => compareResults({mass_residual_kg_s:1e-14},{mass_residual_kg_s:2e-14},'other')).toThrow()
  })
  it('普通结果始终使用相对误差，零值须精确', () => {
    expect(() => compareResults({flow:1},{flow:1+2e-12},'shaft')).toThrow()
    expect(() => compareResults({flow:0},{flow:1e-16},'shaft')).toThrow()
    expect(compareResults({flow:1},{flow:1+1e-13},'shaft').maxRelative).toBeLessThan(1e-12)
  })
})
