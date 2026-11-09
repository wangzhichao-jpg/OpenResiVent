import { describe, expect, it, vi } from 'vitest'
import { createLocalRuntime, validateLocalIndex } from './local-compute'

describe('本地运行时安全边界', () => {
  it('在加载任何依赖包前设置相同的本地运行目录和包目录', async () => {
    const events=[]
    const fake={
      _module:{API:{setCdnUrl:vi.fn(url=>events.push(['packageDir',url]))}},
      loadPackage:vi.fn(async names=>events.push(['packages',names])),
      unpackArchive:vi.fn(()=>events.push(['archive'])),
      runPythonAsync:vi.fn(async()=>events.push(['python'])),
      globals:{get:vi.fn(()=>Object.assign(()=>'{"result":1}',{destroy:vi.fn()}))},
    }
    const loadPyodide=vi.fn(async options=>{events.push(['load',options]);return fake})
    const readAsset=vi.fn(async name=>{events.push(['read',name]);return new Uint8Array([1])})
    const runtime=await createLocalRuntime({indexURL:'/local/runtime/',readAsset,loadRuntime:{loadPyodide}})
    expect(events[0]).toEqual(['load',{indexURL:'/local/runtime/',packageCacheDir:'/local/runtime/'}])
    expect(events[1]).toEqual(['packageDir','/local/runtime/'])
    expect(events[2][0]).toBe('packages')
    expect(readAsset).toHaveBeenCalledWith('openresivent.zip')
    expect(runtime.calculate({})).toEqual({result:1})
  })
  it('拒绝外部地址、协议相对地址和非本机页面', () => {
    expect(() => validateLocalIndex('https://external.test/')).toThrow()
    expect(() => validateLocalIndex('//external.test/')).toThrow()
    const location={href:'http://127.0.0.1:8765/',origin:'http://127.0.0.1:8765'}
    expect(validateLocalIndex('http://127.0.0.1:8765/pyodide/',location)).toBe('http://127.0.0.1:8765/pyodide/')
    expect(() => validateLocalIndex('https://external.test/pyodide/',location)).toThrow()
    const remote={href:'https://example.test/',origin:'https://example.test'}
    expect(() => validateLocalIndex('https://example.test/pyodide/',remote)).toThrow()
  })
})
