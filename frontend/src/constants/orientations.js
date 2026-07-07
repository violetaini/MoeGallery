export const orientationOptions = [
  { value: 'landscape', label: '横图' },
  { value: 'portrait', label: '竖图' },
  { value: 'square', label: '方图' }
]

export function orientationLabel(value) {
  return orientationOptions.find((item) => item.value === value)?.label || value || '未知'
}
