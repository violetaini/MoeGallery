export function mergeSelectedOptions(currentOptions, selectedIds, nextOptions) {
  const selected = new Set((selectedIds || []).filter((value) => value !== null && value !== undefined))
  const incoming = Array.isArray(nextOptions) ? nextOptions : []
  const incomingIds = new Set(incoming.map((item) => item.id))
  const retained = (currentOptions || []).filter((item) => selected.has(item.id) && !incomingIds.has(item.id))
  return [...retained, ...incoming]
}
