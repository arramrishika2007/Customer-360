// Same behaviour as the old dashboard: pass { body } to POST JSON, otherwise GET.
export async function api(path, opts) {
  const res = await fetch(
    `/api${path}`,
    opts && opts.body
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(opts.body),
        }
      : undefined
  )
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(
      typeof json.detail === 'string'
        ? json.detail
        : JSON.stringify(json.detail || res.statusText)
    )
  }
  return json
}