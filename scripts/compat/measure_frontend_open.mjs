/**
 * Measure SPA open time for http://localhost:6100/ via Chrome CDP.
 * Pass criteria: interactive (login/app shell visible) within 3000ms.
 *
 * Usage:
 *   node scripts/compat/measure_frontend_open.mjs
 *   node scripts/compat/measure_frontend_open.mjs --url http://127.0.0.1:6100/ --budget 3000
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import http from 'node:http'

const args = process.argv.slice(2)
const getArg = (name, fallback) => {
  const i = args.indexOf(name)
  return i >= 0 ? args[i + 1] : fallback
}

const URL = getArg('--url', process.env.NC_FE_URL || 'http://127.0.0.1:6100/')
const BUDGET_MS = Number(getArg('--budget', process.env.NC_FE_OPEN_BUDGET_MS || '3000'))
const OUT = getArg('--out', 'docs/reports/frontend-open-perf-latest.json')
const CHROME =
  process.env.CHROME_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function httpGetJson(port, path) {
  return new Promise((resolve, reject) => {
    http
      .get({ host: '127.0.0.1', port, path }, (res) => {
        let d = ''
        res.on('data', (c) => (d += c))
        res.on('end', () => {
          try {
            resolve(JSON.parse(d))
          } catch (e) {
            reject(e)
          }
        })
      })
      .on('error', reject)
  })
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl)
    this.id = 0
    this.pending = new Map()
    this.events = []
    this.ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        if (msg.error) reject(new Error(JSON.stringify(msg.error)))
        else resolve(msg.result)
      } else if (msg.method) {
        this.events.push(msg)
      }
    })
  }

  ready() {
    return new Promise((resolve, reject) => {
      if (this.ws.readyState === WebSocket.OPEN) return resolve()
      this.ws.addEventListener('open', () => resolve())
      this.ws.addEventListener('error', reject)
    })
  }

  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }

  close() {
    try {
      this.ws.close()
    } catch {}
  }
}

async function waitForChrome(port, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try {
      return await httpGetJson(port, '/json/version')
    } catch {
      await sleep(250)
    }
  }
  throw new Error(`Chrome CDP not ready on ${port}`)
}

async function main() {
  if (!existsSync(CHROME)) {
    throw new Error(`Chrome not found: ${CHROME}`)
  }

  const userData = mkdtempSync(join(tmpdir(), 'nc-fe-perf-'))
  const port = 9222 + Math.floor(Math.random() * 1000)
  const chrome = spawn(
    CHROME,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--disable-background-networking',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userData}`,
      'about:blank',
    ],
    { stdio: 'ignore' },
  )

  let result
  try {
    await waitForChrome(port)
    const pages = await httpGetJson(port, '/json/list')
    const page = pages.find((p) => p.type === 'page') || pages[0]
    const cdp = new Cdp(page.webSocketDebuggerUrl)
    await cdp.ready()

    await cdp.send('Page.enable')
    await cdp.send('Runtime.enable')
    await cdp.send('Network.enable')
    await cdp.send('Performance.enable')

    const navStart = Date.now()
    await cdp.send('Page.navigate', { url: URL })

    // Real UI readiness: sign-in form OR logged-in dashboard (not empty #__nuxt shell)
    const pollScript = `
      (() => {
        const ready = document.readyState === 'complete' || document.readyState === 'interactive';
        const bodyText = (document.body && document.body.innerText) || '';
        const signin =
          !!document.querySelector('[data-testid="nc-form-signin"]') ||
          !!document.querySelector('[data-testid="nc-form-signin__email"]') ||
          !!document.querySelector('.nc-form-signin');
        const dashboard =
          !!document.querySelector('.nc-sidebar') ||
          !!document.querySelector('[data-testid="nc-sidebar"]') ||
          !!document.querySelector('.nc-treeview-container') ||
          !!document.querySelector('.nc-workspace-menu') ||
          (bodyText.includes('Workspaces') && bodyText.length > 80);
        const hasApp = signin || dashboard;
        const hasViteError =
          bodyText.includes('Internal Server Error') ||
          bodyText.includes('Vite Error') ||
          bodyText.includes('[plugin:');
        return {
          ready,
          hasApp,
          signin,
          dashboard,
          hasViteError,
          title: document.title || '',
          readyState: document.readyState,
          bodyLen: bodyText.length,
          resourceHints: performance.getEntriesByType('resource').length,
        };
      })()
    `

    let last = null
    let interactiveAt = null
    // Vite cold transform of nc-gui can exceed 60s; allow long probe for diagnosis
    const deadline = Date.now() + Math.max(BUDGET_MS * 20, 180000)
    while (Date.now() < deadline) {
      last = await cdp.send('Runtime.evaluate', {
        expression: pollScript,
        returnByValue: true,
      })
      const v = last.result?.value
      if (v?.hasViteError) break
      if (v?.ready && v?.hasApp) {
        interactiveAt = Date.now() - navStart
        break
      }
      await sleep(200)
    }

    const metrics = await cdp.send('Runtime.evaluate', {
      expression: `
        (() => {
          const nav = performance.getEntriesByType('navigation')[0];
          const paints = performance.getEntriesByType('paint');
          const resources = performance.getEntriesByType('resource');
          return {
            domContentLoaded: nav ? nav.domContentLoadedEventEnd : null,
            loadEventEnd: nav ? nav.loadEventEnd : null,
            responseStart: nav ? nav.responseStart : null,
            transferSize: nav ? nav.transferSize : null,
            fcp: (paints.find(p => p.name === 'first-contentful-paint') || {}).startTime || null,
            resourceCount: resources.length,
            resourceTransferBytes: resources.reduce((s, r) => s + (r.transferSize || 0), 0),
          };
        })()
      `,
      returnByValue: true,
    })

    const elapsed = Date.now() - navStart
    const openMs = interactiveAt ?? elapsed
    const passed = interactiveAt != null && interactiveAt <= BUDGET_MS && !last?.result?.value?.hasViteError

    result = {
      url: URL,
      budgetMs: BUDGET_MS,
      openMs,
      elapsedMs: elapsed,
      interactiveAtMs: interactiveAt,
      passed,
      marker: last?.result?.value || null,
      navigation: metrics.result?.value || null,
      measuredAt: new Date().toISOString(),
      modeHint: 'chrome-cdp-headless',
    }

    cdp.close()
  } finally {
    try {
      chrome.kill()
    } catch {}
    await sleep(300)
    try {
      rmSync(userData, { recursive: true, force: true })
    } catch {}
  }

  const outPath = join(process.cwd(), OUT)
  mkdirSync(join(outPath, '..'), { recursive: true })
  writeFileSync(outPath, JSON.stringify(result, null, 2))

  console.log(JSON.stringify(result, null, 2))
  if (!result.passed) {
    console.error(
      `\nFAIL: open ${result.openMs}ms > budget ${BUDGET_MS}ms (or app shell not detected)`,
    )
    process.exit(1)
  }
  console.error(`\nPASS: open ${result.openMs}ms <= ${BUDGET_MS}ms`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
