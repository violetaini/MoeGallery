const VIEW_KEY = 'agms-viewed-image-at'
const VIEW_INTERVAL = 24 * 60 * 60 * 1000

function readMap() {
  try {
    const parsed = JSON.parse(localStorage.getItem(VIEW_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeMap(value) {
  localStorage.setItem(VIEW_KEY, JSON.stringify(value))
}

export function shouldTrackImageView(imageId, now = Date.now()) {
  const id = String(imageId)
  const viewedAt = Number(readMap()[id] || 0)
  return !viewedAt || now - viewedAt > VIEW_INTERVAL
}

export function markImageViewed(imageId, now = Date.now()) {
  const map = readMap()
  map[String(imageId)] = now
  writeMap(map)
}
