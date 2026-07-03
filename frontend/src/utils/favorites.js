const FAVORITE_KEY = 'agms-favorite-image-ids'

function readIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAVORITE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed.map((id) => Number(id)).filter(Number.isFinite) : []
  } catch {
    return []
  }
}

function writeIds(ids) {
  localStorage.setItem(FAVORITE_KEY, JSON.stringify([...new Set(ids)]))
}

export function isImageFavorited(imageId) {
  return readIds().includes(Number(imageId))
}

export function setImageFavorited(imageId, favorited) {
  const id = Number(imageId)
  if (!Number.isFinite(id)) return
  const ids = new Set(readIds())
  if (favorited) {
    ids.add(id)
  } else {
    ids.delete(id)
  }
  writeIds([...ids])
}
