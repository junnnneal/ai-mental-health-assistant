import { copyFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(new URL('../package.json', import.meta.url)))
const distDir = join(root, 'dist')
const serverDir = join(distDir, 'server')
const openaiDir = join(distDir, '.openai')

mkdirSync(serverDir, { recursive: true })
mkdirSync(openaiDir, { recursive: true })

copyFileSync(join(root, '.openai', 'hosting.json'), join(openaiDir, 'hosting.json'))

writeFileSync(
  join(serverDir, 'index.js'),
  `const BACKEND_ORIGIN = 'http://159.75.169.224:1235'

function wantsHtml(request) {
  return request.method === 'GET' && (request.headers.get('accept') || '').includes('text/html')
}

async function proxyApi(request) {
  const incomingUrl = new URL(request.url)
  const targetUrl = new URL(incomingUrl.pathname.replace(/^\\/api/, '') || '/', BACKEND_ORIGIN)
  targetUrl.search = incomingUrl.search

  const headers = new Headers(request.headers)
  headers.set('host', targetUrl.host)

  return fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
    redirect: 'manual',
  })
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
      return proxyApi(request)
    }

    const assetResponse = await env.ASSETS.fetch(request)
    if (assetResponse.status !== 404 || !wantsHtml(request)) {
      return assetResponse
    }

    return env.ASSETS.fetch(new Request(new URL('/index.html', url), request))
  },
}
`,
)
