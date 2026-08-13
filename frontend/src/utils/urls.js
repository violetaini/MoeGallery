export function safeExternalUrl(value) {
  const text = String(value || '').trim()
  if (!text || text.includes('\\')) return ''
  try {
    const parsed = new URL(text)
    if (!['http:', 'https:'].includes(parsed.protocol)) return ''
    if (!parsed.hostname || parsed.username || parsed.password) return ''
    return text
  } catch (error) {
    return ''
  }
}
