import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const projectDir = path.resolve(frontendDir, '..')
const backendDir = path.join(projectDir, 'backend')
const workspace = path.resolve(process.env.AGMS_E2E_ROOT || path.join(frontendDir, '.e2e'))
const port = Number(process.env.AGMS_E2E_PORT || 8123)
const baseURL = `http://127.0.0.1:${port}`
const databasePath = path.join(workspace, 'moegallery-e2e.db').replaceAll('\\', '/')
const storagePath = path.join(workspace, 'storage')
const python = process.env.AGMS_E2E_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python.exe' : 'python3')
const pythonCommand = python.includes(' ') ? `"${python}"` : python

const serverEnv = {
  ...process.env,
  AGMS_DATABASE_URL: `sqlite:///${databasePath}`,
  AGMS_STORAGE_PATH: storagePath,
  AGMS_AUTH_SECRET: 'e2e-auth-secret-with-at-least-thirty-two-characters-20260804',
  AGMS_API_KEYS: 'e2e:agms_e2e_api_key_with_at_least_thirty_two_characters_20260804',
  AGMS_LISTEN_HOST: '127.0.0.1'
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
    },
    {
      name: 'mobile-chromium',
      use: { ...devices['iPhone 13'], browserName: 'chromium' }
    }
  ],
  webServer: {
    command: `${pythonCommand} -m uvicorn app.main:app --host 127.0.0.1 --port ${port}`,
    cwd: backendDir,
    env: serverEnv,
    url: `${baseURL}/api/health`,
    timeout: 60_000,
    reuseExistingServer: process.env.AGMS_E2E_REUSE_SERVER === '1'
  }
})
