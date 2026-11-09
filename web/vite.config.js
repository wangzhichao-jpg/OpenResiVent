import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { cpSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const webDir = fileURLToPath(new URL('.', import.meta.url))
const localRuntime = {
  name: 'local-runtime',
  closeBundle() {
    const source = resolve(webDir, '../build/browser-runtime')
    if (existsSync(source)) cpSync(source, resolve(webDir, '../build/web/pyodide'), { recursive: true })
  },
}
export default defineConfig({ plugins: [vue(), localRuntime], build: { outDir: '../build/web', emptyOutDir: true } })
