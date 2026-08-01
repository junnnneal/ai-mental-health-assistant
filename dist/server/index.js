const BACKEND_ORIGIN = 'http://159.75.169.224:1235'

function wantsHtml(request) {
  return request.method === 'GET' && (request.headers.get('accept') || '').includes('text/html')
}

async function proxyApi(request) {
  const incomingUrl = new URL(request.url)
  const targetUrl = new URL(incomingUrl.pathname, BACKEND_ORIGIN)
  targetUrl.search = incomingUrl.search

  const headers = new Headers(request.headers)
  for (const header of [
    'host',
    'origin',
    'referer',
    'cookie',
    'cf-connecting-ip',
    'cf-ipcountry',
    'cf-ray',
    'cf-visitor',
    'oai-authenticated-user-email',
    'oai-authenticated-user-full-name',
    'oai-authenticated-user-full-name-encoding',
    'oai-authenticated-user-id',
    'x-dispatched-app',
    'x-forwarded-proto',
    'x-real-ip',
  ]) {
    headers.delete(header)
  }

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
