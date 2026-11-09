// 跨平台数值对照：仅精确列出的收敛诊断字段使用绝对误差。
import assert from 'node:assert/strict'

const RESIDUAL_LIMITS = Object.freeze({ mass_residual_kg_s: 1e-13 })
const SOLVER_TOLERANCES = Object.freeze({ dwelling: 1e-11, inverse: 1e-11, shaft: 1e-10 })

export function compareResults(native, wasm, example) {
  const summary = { numeric: 0, diagnostics: 0, strict: 0, absoluteRequired: 0, maxRelative: 0, maxDiagnosticAbsolute: 0 }
  function compare(a,b,path,field) {
    if (typeof a==='number' && typeof b==='number') {
      assert.ok(Number.isFinite(a) && Number.isFinite(b), `${path}: 非有限数`)
      const difference=Math.abs(a-b)
      summary.numeric++
      if (Object.hasOwn(RESIDUAL_LIMITS, field)) {
        const tolerance=SOLVER_TOLERANCES[example]
        assert.ok(tolerance !== undefined, `${path}: 未定义收敛判据`)
        assert.ok(a >= 0 && b >= 0 && a < tolerance && b < tolerance, `${path}: 未满足求解器收敛判据`)
        assert.ok(difference <= RESIDUAL_LIMITS[field], `${path}: 残差绝对偏差 ${difference}`)
        summary.diagnostics++
        const relative=difference/Math.max(Math.abs(a),Math.abs(b),1e-300)
        if (relative < 1e-12 || difference === 0) {
          summary.strict++
          summary.maxRelative=Math.max(summary.maxRelative,relative)
        } else summary.absoluteRequired++
        summary.maxDiagnosticAbsolute=Math.max(summary.maxDiagnosticAbsolute,difference)
      } else {
        const relative=difference/Math.max(Math.abs(a),Math.abs(b),1e-300)
        summary.maxRelative=Math.max(summary.maxRelative,relative)
        summary.strict++
        assert.ok(relative < 1e-12 || difference === 0, `${path}: 命令行 ${a}，本地 ${b}，相对偏差 ${relative}`)
      }
    } else if (Array.isArray(a)) {
      assert.ok(Array.isArray(b),path);assert.equal(a.length,b.length,path)
      a.forEach((value,i)=>compare(value,b[i],`${path}[${i}]`,null))
    } else if (a && typeof a==='object') {
      assert.ok(b && typeof b==='object' && !Array.isArray(b),path)
      const keys=Object.keys(a).filter(k=>k!=='provenance').sort()
      assert.deepEqual(keys,Object.keys(b).filter(k=>k!=='provenance').sort(),path)
      for (const key of keys) compare(a[key],b[key],`${path}.${key}`,key)
    } else assert.deepEqual(a,b,path)
  }
  compare(native,wasm,example,null)
  return summary
}
