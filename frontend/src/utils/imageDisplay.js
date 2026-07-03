const HDR_BROWSER_MIME_TYPES = new Set([
  'image/avif'
])

export function canUseHdrOriginal(image) {
  return Boolean(
    image &&
    image.dynamic_range === 'hdr' &&
    image.file_path &&
    HDR_BROWSER_MIME_TYPES.has(String(image.mime_type || '').toLowerCase())
  )
}
