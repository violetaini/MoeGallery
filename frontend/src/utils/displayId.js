export function displayId(index, page = 1, pageSize = 0) {
  const rowIndex = Number(index)
  if (!Number.isFinite(rowIndex) || rowIndex < 0) {
    return ''
  }

  const currentPage = Math.max(Number(page) || 1, 1)
  const currentPageSize = Math.max(Number(pageSize) || 0, 0)
  return currentPageSize ? (currentPage - 1) * currentPageSize + rowIndex + 1 : rowIndex + 1
}
