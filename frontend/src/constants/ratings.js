export const ratingOptions = [
  {
    value: 'safe',
    label: '安全',
    description: '普通公开图片'
  },
  {
    value: 'sensitive',
    label: '敏感',
    description: '需要谨慎浏览的图片'
  },
  {
    value: 'hidden',
    label: '隐藏',
    description: '后台隐藏或非公开图片'
  }
]

export function ratingLabel(value) {
  return ratingOptions.find((item) => item.value === value)?.label || value
}

export function ratingTagType(value) {
  if (value === 'safe') return 'success'
  if (value === 'sensitive') return 'warning'
  return 'info'
}
