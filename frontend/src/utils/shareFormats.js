import { mediaUrl } from '../api/client'

function absoluteUrl(path) {
  if (typeof window === 'undefined') return path
  return new URL(path, window.location.origin).toString()
}

function imageAlt(image) {
  return String(image?.original_filename || image?.filename || '图片')
    .replaceAll('[', '\\[')
    .replaceAll(']', '\\]')
}

export function sharePageUrl(token) {
  return absoluteUrl(`/s/${encodeURIComponent(token)}`)
}

export function imageDirectUrl(image, shareToken = '') {
  return absoluteUrl(mediaUrl(image, 'original', shareToken))
}

export function imageShareCode(images, format = 'url', shareToken = '') {
  return (images || []).map((image) => {
    const url = imageDirectUrl(image, shareToken)
    if (format === 'markdown') return `![${imageAlt(image)}](${url})`
    if (format === 'bbcode') return `[img]${url}[/img]`
    return url
  }).join('\n')
}
