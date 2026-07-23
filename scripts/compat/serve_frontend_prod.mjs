/**
 * Serve nc-gui production output on port 6100 (fast open path).
 * Falls back message if .output is missing — run `pnpm --filter=nc-gui run build` first.
 *
 * Env:
 *   NITRO_PORT / PORT  (default 6100)
 *   NITRO_HOST         (default 0.0.0.0)
 *   NUXT_PUBLIC_NC_BACKEND_URL (default http://localhost:6080)
 */
import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const guiRoot = join(__dirname, '../../packages/nc-gui')
const entry = join(guiRoot, '.output/server/index.mjs')

if (!existsSync(entry)) {
  console.error(
    '[start:frontend] Missing production build at packages/nc-gui/.output\n' +
      'Run once: pnpm --filter=nc-gui run build\n' +
      'For HMR/dev instead: pnpm start:frontend:dev (port 6110)',
  )
  process.exit(1)
}

process.env.NITRO_HOST = process.env.NITRO_HOST || '0.0.0.0'
process.env.NITRO_PORT = process.env.NITRO_PORT || process.env.PORT || '6100'
process.env.PORT = process.env.NITRO_PORT
process.env.NUXT_PUBLIC_NC_BACKEND_URL =
  process.env.NUXT_PUBLIC_NC_BACKEND_URL || 'http://localhost:6080'
process.env.NUXT_PAGE_TRANSITION_DISABLE =
  process.env.NUXT_PAGE_TRANSITION_DISABLE || 'true'

console.log(
  `[start:frontend] serving production UI on http://${process.env.NITRO_HOST}:${process.env.NITRO_PORT}/ (backend ${process.env.NUXT_PUBLIC_NC_BACKEND_URL})`,
)

const child = spawn(process.execPath, [entry], {
  cwd: guiRoot,
  stdio: 'inherit',
  env: process.env,
})

child.on('exit', (code) => process.exit(code ?? 0))
