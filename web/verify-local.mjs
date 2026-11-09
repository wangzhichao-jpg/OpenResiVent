// 在 Node 的本地 Pyodide 中对照命令行；禁止网络请求。
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import tls from 'node:tls'
import dns from 'node:dns'
import dgram from 'node:dgram'
import http2 from 'node:http2'
import YAML from 'yaml'
import { createLocalRuntime } from './src/local-compute.js'
import { compareResults } from './src/compare-results.js'

const root=resolve(dirname(fileURLToPath(import.meta.url)), '..')
const runtime=resolve(root, 'build/browser-runtime')
const binary=process.env.ORV_CLI || resolve(root, '.venv/bin/resivent')
const inputs=[
  ['co2', 'cases/book/ch02/ex2-01.yaml'],
  ['ventilation', 'cases/book/ch02/ex2-03.yaml'],
  ['dwelling', 'cases/book/ch05/ex5-07.yaml'],
  ['inverse', 'cases/studies/makeup_base.yaml'],
  ['shaft', 'cases/reports/shaft_example.yaml'],
]
const blocked=[]
function deny(name) { return (...args) => {blocked.push(`${name}: ${String(args[0])}`);throw new Error('网络访问在一致性测试中被禁止')} }
globalThis.fetch=deny('fetch')
globalThis.WebSocket=class { constructor(url) { deny('WebSocket')(url) } }
for (const module of [http,https]) for (const method of ['request','get']) module[method]=deny(method)
for (const method of ['connect','createConnection']) net[method]=deny(`net.${method}`)
net.Socket.prototype.connect=deny('Socket.connect')
tls.connect=deny('tls.connect')
dgram.createSocket=deny('dgram.createSocket')
http2.connect=deny('http2.connect')
for (const method of ['lookup','resolve','resolve4','resolve6']) {
  dns[method]=deny(`dns.${method}`)
  if (dns.promises[method]) dns.promises[method]=deny(`dns.promises.${method}`)
}
const engine=await createLocalRuntime({indexURL:runtime+'/',readAsset:async name=>new Uint8Array(readFileSync(join(runtime,name)))})
let count=0, diagnostics=0, strict=0, absoluteRequired=0, maxRelative=0, maxDiagnosticAbsolute=0
for(const [name,file] of inputs){
  let data=YAML.parse(readFileSync(resolve(root,file),'utf8'))
  if(name==='shaft') data={meta:{id:'shaft-model',title:'竖井计算',rules:[]},module:'shaft',input:data.input.shaft,output:{}}
  const temp=mkdtempSync(join(tmpdir(),'orv-wasm-'))
  const path=join(temp,'case.yaml');writeFileSync(path,YAML.stringify(data))
  const run=spawnSync(binary,['run',path,'--out',temp],{cwd:temp,encoding:'utf8'})
  assert.equal(run.status,0,`${name}: ${run.stderr}`)
  const expected=JSON.parse(readFileSync(join(temp,`${data.meta.id}.json`),'utf8'))
  const actual=engine.calculate(data)
  const result=compareResults(expected,actual,name)
  count+=result.numeric;diagnostics+=result.diagnostics;strict+=result.strict;absoluteRequired+=result.absoluteRequired
  maxRelative=Math.max(maxRelative,result.maxRelative)
  maxDiagnosticAbsolute=Math.max(maxDiagnosticAbsolute,result.maxDiagnosticAbsolute)
  console.log(`${name}: 对照通过，数值 ${result.numeric}，残差诊断 ${result.diagnostics}`)
}
assert.deepEqual(blocked,[],'本地计算不应发出网络请求')
console.log(`数值项 ${count}，严格相对误差通过 ${strict}，仅依绝对误差通过 ${absoluteRequired}，残差诊断共 ${diagnostics}，严格项最大相对偏差 ${maxRelative}，残差最大绝对偏差 ${maxDiagnosticAbsolute} kg/s；网络请求 0`)
