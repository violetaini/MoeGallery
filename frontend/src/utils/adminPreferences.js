export const imageManageViewModes = [
  { value: 'classic', label: '经典' },
  { value: 'waterfall', label: '瀑布' }
]

const imageManageViewModeKey = 'anime-gallery.admin.imageManageViewMode'

export function normalizeImageManageViewMode(value) {
  return imageManageViewModes.some((mode) => mode.value === value) ? value : 'classic'
}

export function getImageManageViewMode() {
  if (typeof window === 'undefined') {
    return 'classic'
  }
  const value = window.localStorage.getItem(imageManageViewModeKey)
  return normalizeImageManageViewMode(value)
}

export function setImageManageViewMode(value) {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(imageManageViewModeKey, normalizeImageManageViewMode(value))
}
