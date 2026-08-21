import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  //读取.env.local等环境文件；GLM_API_KEY不带VITE_前缀，只在Node侧使用，不会打包进前端代码
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [
      vue(),
      vueDevTools(),
    ],
    build: {
      outDir: 'dist/client',
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    server: {
      // 配置代理
      proxy: {
        '/api': {
          target: 'http://159.75.169.224:1235',
          changeOrigin: true,
        },
        //智谱GLM免费模型代理：前端调/llm/*，由开发服务器转发到智谱开放平台并注入密钥
        '/llm': {
          target: 'https://open.bigmodel.cn',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/llm/, ''),
          headers: env.GLM_API_KEY
            ? { Authorization: `Bearer ${env.GLM_API_KEY}` }
            : undefined,
        },
        //LangGraph Agent 服务：前端调/agent/*，转发到本地FastAPI（token头原样透传）
        '/agent': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/agent/, ''),
        },
      },
    }
  }
})
