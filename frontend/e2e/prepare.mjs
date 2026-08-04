import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const projectDir = path.resolve(frontendDir, '..', '..')
const workspace = path.resolve(process.env.AGMS_E2E_ROOT || path.join(frontendDir, '..', '.e2e'))
const python = process.env.AGMS_E2E_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python.exe' : 'python3')
const preparationScript = path.join(projectDir, 'scripts', 'prepare_e2e.py')

const result = spawnSync(python, [preparationScript, '--workspace', workspace], {
  cwd: projectDir,
  env: process.env,
  stdio: 'inherit'
})

if (result.error) {
  throw result.error
}
if (result.status !== 0) {
  process.exit(result.status || 1)
}
