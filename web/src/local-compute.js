// 本地 Pyodide 适配器：只加载同源静态资源，不发送算例到任何服务。
let runtimePromise

export function validateLocalIndex(indexURL, location = globalThis.window?.location) {
  if (typeof indexURL !== 'string' || !indexURL.endsWith('/')) throw new Error('未配置本地运行时目录')
  if (location) {
    const base = new URL(indexURL, location.href)
    if (base.origin !== location.origin || !['localhost','127.0.0.1','::1','[::1]'].includes(base.hostname)) throw new Error('运行时必须来自本机同源目录')
    return base.href
  }
  if (!/^(?:\/(?!\/)|[A-Za-z]:[\\/])/.test(indexURL) || indexURL.includes('://')) throw new Error('Node 运行时必须使用本地绝对路径')
  return indexURL
}

export async function createLocalRuntime({ indexURL, readAsset, loadRuntime }) {
  indexURL = validateLocalIndex(indexURL)
  const specifier = typeof window === 'undefined' ? 'pyodide' : new URL('pyodide.mjs', indexURL).href
  const { loadPyodide } = loadRuntime || await import(/* @vite-ignore */ specifier)
  const py = await loadPyodide({ indexURL, packageCacheDir: indexURL })
  // 上游运行时包含默认远程源；在加载任何包之前强制覆盖为本地目录。
  // 该接口随固定版本提供，若未来版本移除则拒绝继续而非回退远程。
  if (typeof py._module?.API?.setCdnUrl !== 'function') throw new Error('本地包源配置不可用')
  py._module.API.setCdnUrl(indexURL)
  await py.loadPackage(['numpy', 'scipy', 'pydantic', 'pyyaml'])
  const source = await readAsset('openresivent.zip')
  py.unpackArchive(source, 'zip', { extractDir: '/orv' })
  await py.runPythonAsync("import sys; sys.path.insert(0, '/orv/src'); from openresivent.browser import calculate_json")
  return {
    calculate(payload) {
      const argument = JSON.stringify(payload)
      if (typeof argument !== 'string') throw new Error('算例不是有效对象')
      const callable = py.globals.get('calculate_json')
      try { return JSON.parse(callable(argument)) } finally { callable.destroy() }
    },
  }
}

export async function localCalculate(payload) {
  if (!runtimePromise) {
    const base = new URL('./pyodide/', window.location.href)
    if (base.origin !== window.location.origin) throw new Error('运行时必须来自当前本机页面')
    runtimePromise = createLocalRuntime({
      indexURL: base.href,
      async readAsset(name) {
        const url = new URL(name, base)
        if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) throw new Error('运行时路径无效')
        const response = await fetch(url)
        if (!response.ok) throw new Error('未找到本地运行时，请先按浏览器版文档构建')
        return new Uint8Array(await response.arrayBuffer())
      },
    }).catch(error => { runtimePromise = undefined; throw error })
  }
  const runtime = await runtimePromise
  return runtime.calculate(payload)
}
