import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const e2eDir = path.dirname(fileURLToPath(import.meta.url))
const uploadFixture = path.resolve(e2eDir, '..', 'public', 'favicon.png')
const uploadFixtureBytes = readFileSync(uploadFixture)

async function loginAsAdmin(page) {
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login\?redirect=\/admin/)
  await page.locator('input[autocomplete="username"]').fill('e2e-admin')
  await page.locator('input[autocomplete="current-password"]').fill('E2E-admin-password-2026')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('menuitem', { name: '后台首页' })).toBeVisible()
}

async function swipeImageDetail(page, fromRatio, toRatio) {
  const panel = page.locator('.image-detail-overlay__panel')
  const box = await panel.boundingBox()
  if (!box) throw new Error('Image detail panel is not visible')
  const y = box.y + Math.min(220, box.height * 0.35)
  await page.mouse.move(box.x + box.width * fromRatio, y)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * toRatio, y, { steps: 8 })
  await page.mouse.up()
}

function captureRuntimeErrors(page) {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource:')) {
      errors.push(message.text())
    }
  })
  page.on('response', (response) => {
    if (response.status() < 400) return
    const url = new URL(response.url())
    const expectedAnonymousProbe = response.status() === 401 && url.pathname === '/api/auth/me'
    if (!expectedAnonymousProbe) errors.push(`${response.status()} ${url.pathname}`)
  })
  return errors
}

test('public navigation loads gallery without horizontal overflow', async ({ page }, testInfo) => {
  const runtimeErrors = captureRuntimeErrors(page)
  const previewRequestIds = new Set()
  page.on('request', (request) => {
    const match = request.url().match(/\/media\/(\d+)\/preview\//)
    if (match) previewRequestIds.add(match[1])
  })
  await page.goto('/')
  await expect(page.locator('.home-slideshow')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Anime Gallery' })).toBeVisible()

  const galleryLink = page.getByRole('link', { name: '图片库' })
  await galleryLink.hover()
  await galleryLink.click()
  await expect(page).toHaveURL(/\/gallery$/)
  await expect(page.locator('.masonry .image-card').first()).toBeVisible()

  await page.locator('.masonry .image-card').first().click()
  await expect(page.locator('.image-detail-overlay')).toBeVisible()
  await expect(page).toHaveURL(/\?image=\d+$/)
  await expect(page.locator('.image-detail-overlay__panel')).toBeVisible()
  await expect(page.locator('.image-detail-view .detail-image')).toBeVisible()
  const imagePanelBox = await page.locator('.image-detail-view > .detail-panel').first().boundingBox()
  const metadataPanelBox = await page.locator('.image-detail-meta').boundingBox()
  const detailImageBox = await page.locator('.image-detail-view .detail-image').boundingBox()
  expect(imagePanelBox).not.toBeNull()
  expect(metadataPanelBox).not.toBeNull()
  expect(detailImageBox).not.toBeNull()
  if (testInfo.project.name === 'desktop-chromium') {
    expect(Math.abs(imagePanelBox.height - metadataPanelBox.height)).toBeLessThanOrEqual(1)
  }
  await expect.poll(() => previewRequestIds.size).toBeGreaterThan(1)
  const nextButton = page.getByRole('button', { name: '下一张' })
  const firstImageUrl = page.url()
  if (testInfo.project.name === 'mobile-chromium') {
    await expect(nextButton).toBeHidden()
    await swipeImageDetail(page, 0.76, 0.24)
  } else {
    const nextButtonBeforeHover = await nextButton.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    })
    expect(nextButtonBeforeHover.width).toBe(nextButtonBeforeHover.height)
    await nextButton.hover()
    const nextButtonAfterHover = await nextButton.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { x: rect.x, y: rect.y }
    })
    expect(nextButtonAfterHover).toEqual({ x: nextButtonBeforeHover.x, y: nextButtonBeforeHover.y })
    await nextButton.click()
  }
  await expect(page).toHaveURL(/\/gallery\?image=\d+$/)
  await expect.poll(() => page.url()).not.toBe(firstImageUrl)
  await expect(page.locator('.image-detail-overlay')).toBeVisible()
  if (testInfo.project.name === 'mobile-chromium') {
    await swipeImageDetail(page, 0.24, 0.76)
  } else {
    await expect(page.getByRole('button', { name: '上一张' })).toBeVisible()
    await page.getByRole('button', { name: '上一张' }).click()
  }
  await expect.poll(() => page.url()).toBe(firstImageUrl)
  await expect(page.locator('.image-detail-overlay')).toBeVisible()
  if (testInfo.project.name === 'desktop-chromium') {
    const viewport = page.viewportSize()
    await page.mouse.click(viewport.width / 2, 8)
    await expect(page.locator('.image-detail-overlay')).toBeVisible()
    await page.mouse.click(4, viewport.height / 2)
    await expect(page.locator('.image-detail-overlay')).toBeHidden()
  } else {
    await page.getByRole('button', { name: '关闭' }).click()
    await expect(page.locator('.image-detail-overlay')).toBeHidden()
  }

  if (testInfo.project.name === 'mobile-chromium') {
    const viewport = await page.evaluate(() => ({
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth
    }))
    expect(viewport.pageWidth).toBeLessThanOrEqual(viewport.viewportWidth)
  }
  expect(runtimeErrors).toEqual([])
})

test('public archive routes render works, characters, ratings, and search results', async ({ page }) => {
  const runtimeErrors = captureRuntimeErrors(page)

  await page.goto('/works')
  const workCard = page.locator('.entity-card--work').filter({ hasText: 'E2E 作品' }).first()
  await expect(workCard).toBeVisible()
  await workCard.click()
  await expect(page.getByRole('heading', { name: 'E2E 作品', level: 1 })).toBeVisible()
  await expect(page.locator('.work-character-grid .entity-card--character').filter({ hasText: 'E2E 角色' })).toBeVisible()
  await expect(page.locator('.masonry .image-card')).toHaveCount(2)

  await page.goto('/characters')
  const characterCard = page.locator('.entity-card--character').filter({ hasText: 'E2E 角色' }).first()
  await expect(characterCard).toBeVisible()
  await characterCard.click()
  await expect(page.getByRole('heading', { name: 'E2E 角色', level: 1 })).toBeVisible()
  await expect(page.locator('.masonry .image-card')).toHaveCount(1)

  await page.goto('/tags')
  await expect(page.getByRole('heading', { name: '分级', level: 1 })).toBeVisible()
  await expect(page.locator('.rating-toolbar-copy').getByRole('heading', { name: '安全', level: 2 })).toBeVisible()
  await expect(page.locator('.rating-gallery-meta')).toHaveCount(0)
  const ratingAlignment = await page.evaluate(() => {
    const eyebrow = document.querySelector('.listing-hero--rating .hero-eyebrow')
    const toolbarTitle = document.querySelector('.rating-toolbar-copy h2')
    if (!eyebrow || !toolbarTitle) return null
    const eyebrowRect = eyebrow.getBoundingClientRect()
    const toolbarRect = toolbarTitle.getBoundingClientRect()
    return {
      eyebrowLineX: eyebrowRect.x + Number.parseFloat(getComputedStyle(eyebrow).paddingLeft),
      toolbarTitleX: toolbarRect.x
    }
  })
  expect(ratingAlignment).not.toBeNull()
  expect(ratingAlignment.toolbarTitleX).toBe(ratingAlignment.eyebrowLineX)
  await expect(page.locator('.masonry .image-card[aria-label^="e2e-"]')).toHaveCount(2)

  await page.goto('/search?q=E2E')
  await expect(page.locator('.entity-card--work').filter({ hasText: 'E2E 作品' })).toBeVisible()
  await expect(page.locator('.entity-card--character').filter({ hasText: 'E2E 角色' })).toBeVisible()
  await expect(page.locator('.masonry .image-card')).toHaveCount(2)

  expect(runtimeErrors).toEqual([])
})

test('search keeps the newest result when an older request finishes last', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'The request race only needs one browser pass.')
  let markOldRequestStarted
  let releaseOldRequest
  const oldRequestStarted = new Promise((resolve) => { markOldRequestStarted = resolve })
  const oldRequestRelease = new Promise((resolve) => { releaseOldRequest = resolve })
  await page.route('**/api/search?*', async (route) => {
    const query = new URL(route.request().url()).searchParams.get('q') || ''
    if (query === '旧查询') {
      markOldRequestStarted()
      await oldRequestRelease
    }
    await route.fulfill({
      json: {
        images: [],
        characters: [],
        tags: [],
        works: [{ id: query === '旧查询' ? 9101 : 9102, name: `${query}结果` }]
      }
    })
  })

  const navigation = page.goto('/search?q=%E6%97%A7%E6%9F%A5%E8%AF%A2')
  await oldRequestStarted
  await navigation
  const input = page.getByPlaceholder('关键词')
  await input.fill('新查询')
  await input.press('Enter')
  await expect(page.locator('.entity-card--work').filter({ hasText: '新查询结果' })).toBeVisible()
  releaseOldRequest()
  await expect(page.locator('.entity-card--work').filter({ hasText: '旧查询结果' })).toHaveCount(0)
})

test('work list pagination requests the selected page', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Pagination behavior only needs one browser pass.')
  const requestedPages = []
  await page.route('**/api/works?*', async (route) => {
    const requestUrl = new URL(route.request().url())
    const requestedPage = Number(requestUrl.searchParams.get('page') || 1)
    requestedPages.push(requestedPage)
    const firstIndex = (requestedPage - 1) * 48
    const itemCount = requestedPage === 1 ? 48 : 1
    const items = Array.from({ length: itemCount }, (_value, index) => {
      const id = firstIndex + index + 1
      return {
        id,
        name: `分页作品 ${id}`,
        original_name: `Paged Work ${id}`,
        sort_order: id,
        created_at: '2026-08-11T00:00:00',
        updated_at: '2026-08-11T00:00:00'
      }
    })
    await route.fulfill({ json: { items, total: 49, page: requestedPage, page_size: 48 } })
  })

  await page.goto('/works')
  await expect(page.locator('.entity-card--work')).toHaveCount(48)
  await page.locator('.el-pagination .btn-next').click()
  await expect(page.locator('.entity-card--work').filter({ hasText: '分页作品 49' })).toBeVisible()
  expect(requestedPages).toContain(2)
})

test('administrator work and character tables can reach records after the first page', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Admin pagination only needs one browser pass.')
  await loginAsAdmin(page)

  await page.route('**/api/works?*', async (route) => {
    const url = new URL(route.request().url())
    const requestedPage = Number(url.searchParams.get('page') || 1)
    const pageSize = Number(url.searchParams.get('page_size') || 24)
    const total = pageSize === 50 ? 51 : 1
    const count = pageSize === 50 ? (requestedPage === 1 ? 50 : 1) : 1
    const start = pageSize === 50 ? (requestedPage - 1) * 50 : 0
    const items = Array.from({ length: count }, (_value, index) => ({
      id: start + index + 1,
      name: pageSize === 50 ? `管理作品 ${start + index + 1}` : '筛选作品',
      sort_order: start + index + 1
    }))
    await route.fulfill({ json: { items, total, page: requestedPage, page_size: pageSize } })
  })

  await page.goto('/admin/works')
  await expect(page.getByText('管理作品 1', { exact: true })).toBeVisible()
  await page.locator('.pagination-bar .btn-next').click()
  await expect(page.getByText('管理作品 51', { exact: true })).toBeVisible()

  await page.route('**/api/characters?*', async (route) => {
    const url = new URL(route.request().url())
    const requestedPage = Number(url.searchParams.get('page') || 1)
    const pageSize = Number(url.searchParams.get('page_size') || 24)
    const start = (requestedPage - 1) * pageSize
    const count = requestedPage === 1 ? 50 : 1
    const items = Array.from({ length: count }, (_value, index) => ({
      id: start + index + 1,
      work_id: 1,
      name: `管理角色 ${start + index + 1}`,
      work: { id: 1, name: '筛选作品' }
    }))
    await route.fulfill({ json: { items, total: 51, page: requestedPage, page_size: pageSize } })
  })

  await page.goto('/admin/characters')
  await expect(page.getByText('管理角色 1', { exact: true })).toBeVisible()
  await page.locator('.pagination-bar .btn-next').click()
  await expect(page.getByText('管理角色 51', { exact: true })).toBeVisible()
})

test('administrator dashboard requests two responsive rows of recent uploads', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Responsive dashboard sizing only needs one browser pass.')
  const requestedPageSizes = []
  await page.route('**/api/images?*', async (route) => {
    const requestUrl = new URL(route.request().url())
    const pageSize = Number(requestUrl.searchParams.get('page_size') || 0)
    requestedPageSizes.push(pageSize)
    await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: pageSize } })
  })

  await loginAsAdmin(page)
  await expect.poll(() => requestedPageSizes.at(-1) || 0).toBeGreaterThan(12)
  const widePageSize = requestedPageSizes.at(-1)
  expect(widePageSize % 2).toBe(0)

  await page.setViewportSize({ width: 1000, height: 900 })
  await expect.poll(() => requestedPageSizes.at(-1)).toBeLessThan(widePageSize)
  const compactPageSize = requestedPageSizes.at(-1)
  expect(compactPageSize % 2).toBe(0)

  await page.setViewportSize({ width: 1600, height: 900 })
  await expect.poll(() => requestedPageSizes.at(-1)).toBeGreaterThan(compactPageSize)
})

test('upload preview requests use the bounded client queue', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'Preview concurrency only needs one browser pass.')
  await loginAsAdmin(page)
  let activeRequests = 0
  let peakRequests = 0
  await page.route('**/api/images/preview', async (route) => {
    activeRequests += 1
    peakRequests = Math.max(peakRequests, activeRequests)
    await new Promise((resolve) => setTimeout(resolve, 120))
    await route.fulfill({ status: 200, contentType: 'image/png', body: uploadFixtureBytes })
    activeRequests -= 1
  })

  await page.goto('/admin/images/upload')
  const files = Array.from({ length: 8 }, (_value, index) => ({
    name: `preview-${index + 1}.png`,
    mimeType: 'image/png',
    buffer: uploadFixtureBytes
  }))
  await page.locator('input[type="file"]').first().setInputFiles(files)
  await expect(page.locator('.upload-preview-card img')).toHaveCount(8)
  expect(peakRequests).toBeGreaterThan(1)
  expect(peakRequests).toBeLessThanOrEqual(6)
})

test('administrator can open settings and submit an image task', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'The authenticated workflow runs once on desktop Chromium.')
  const runtimeErrors = captureRuntimeErrors(page)

  await loginAsAdmin(page)
  await expect(page.getByRole('menuitem', { name: '后台首页' })).toBeVisible()

  await page.getByRole('button', { name: '修改账号、昵称或密码' }).click()
  await expect(page).toHaveURL(/\/admin\/settings\?account=1/)
  await expect(page.locator('.admin-account-panel')).toBeVisible()
  await expect(page.getByText('系统健康', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '轮换登录密钥' }).click()
  const confirmation = page.locator('.el-message-box')
  await expect(confirmation).toBeVisible()
  await confirmation.getByRole('button', { name: '取消' }).click()
  await expect(confirmation).toBeHidden()

  await page.goto('/admin/images/upload')
  await page.locator('input[type="file"]').first().setInputFiles(uploadFixture)
  await expect(page.getByText('favicon.png', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '开始批量上传' })).toBeEnabled()
  await page.getByRole('button', { name: '开始批量上传' }).click()
  await expect(page.locator('.upload-task-item').filter({ hasText: 'favicon.png' })).toBeVisible()
  expect(runtimeErrors).toEqual([])
})
