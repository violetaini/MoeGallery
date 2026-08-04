import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const e2eDir = path.dirname(fileURLToPath(import.meta.url))
const uploadFixture = path.resolve(e2eDir, '..', 'public', 'favicon.png')

test('public navigation loads gallery without horizontal overflow', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('.home-slideshow')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Anime Gallery' })).toBeVisible()

  const galleryLink = page.getByRole('link', { name: '图片库' })
  await galleryLink.hover()
  await galleryLink.click()
  await expect(page).toHaveURL(/\/gallery$/)
  await expect(page.locator('.masonry .image-card').first()).toBeVisible()

  if (testInfo.project.name === 'mobile-chromium') {
    const viewport = await page.evaluate(() => ({
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth
    }))
    expect(viewport.pageWidth).toBeLessThanOrEqual(viewport.viewportWidth)
  }
})

test('administrator can open settings and submit an image task', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'The authenticated workflow runs once on desktop Chromium.')

  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login\?redirect=\/admin/)
  await page.locator('input[autocomplete="username"]').fill('e2e-admin')
  await page.locator('input[autocomplete="current-password"]').fill('E2E-admin-password-2026')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('menuitem', { name: '后台首页' })).toBeVisible()

  await page.goto('/admin/settings')
  await expect(page.getByText('系统健康', { exact: true })).toBeVisible()

  await page.goto('/admin/images/upload')
  await page.locator('input[type="file"]').first().setInputFiles(uploadFixture)
  await expect(page.getByText('favicon.png', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '开始批量上传' })).toBeEnabled()
  await page.getByRole('button', { name: '开始批量上传' }).click()
  await expect(page.locator('.upload-task-item').filter({ hasText: 'favicon.png' })).toBeVisible()
})
