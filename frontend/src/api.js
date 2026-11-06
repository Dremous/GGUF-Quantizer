// 与 FastAPI 后端通信的轻量客户端

async function request(path, options = {}) {
  const res = await fetch(path, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = data.detail || `请求失败 (${res.status})`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export function health() {
  return request('/api/health')
}

export function quantTypes() {
  return request('/api/quant-types')
}

export async function upload(file) {
  const fd = new FormData()
  fd.append('file', file)
  return request('/api/upload', { method: 'POST', body: fd })
}

export function quantize(payload) {
  return request('/api/quantize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function job(id, offset = 0) {
  return request(`/api/jobs/${id}?offset=${offset}`)
}

export function cancel(id) {
  return request(`/api/jobs/${id}/cancel`, { method: 'POST' })
}

export function deleteJob(id) {
  return request(`/api/jobs/${id}/delete`, { method: 'POST' })
}

export function downloadUrl(id) {
  return `/api/jobs/${id}/download`
}
