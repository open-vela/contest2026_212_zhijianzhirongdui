import { spawn } from 'node:child_process'

const baseUrl = process.env.DEMO_BASE_URL || 'http://127.0.0.1:8000'
const driverUrl = process.env.WEBDRIVER_URL || 'http://127.0.0.1:4444'
const geckodriver = process.env.GECKODRIVER || '/snap/bin/geckodriver'

const driver = spawn(geckodriver, ['--port', '4444'], { stdio: ['ignore', 'pipe', 'pipe'] })
let sessionId

const pause = ms => new Promise(resolve => setTimeout(resolve, ms))

async function webdriver(path, method = 'GET', body) {
  const response = await fetch(`${driverUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok || payload.value?.error) {
    throw new Error(`WebDriver ${method} ${path}: ${JSON.stringify(payload.value || payload)}`)
  }
  return payload.value
}

async function waitForDriver() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      await webdriver('/status')
      return
    } catch {
      await pause(100)
    }
  }
  throw new Error('geckodriver did not become ready')
}

async function execute(script, args = []) {
  return webdriver(`/session/${sessionId}/execute/sync`, 'POST', { script, args })
}

async function navigate(url) {
  await webdriver(`/session/${sessionId}/url`, 'POST', { url })
}

async function waitForDemo() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const ready = await execute(`return document.readyState === 'complete' && document.querySelectorAll('.demo-section').length === 6`)
    if (ready) return
    await pause(100)
  }
  throw new Error('Demo page did not render six sections')
}

async function setMode(mode) {
  await execute(`localStorage.setItem('demo_mode', arguments[0]);`, [mode])
  await navigate(`${baseUrl}/admin/demo?auditMode=${encodeURIComponent(mode)}`)
  await waitForDemo()
}

async function auditViewport(width, height) {
  await webdriver(`/session/${sessionId}/window/rect`, 'POST', { x: 0, y: 0, width, height })
  await pause(250)
  return execute(`
    const cards = [...document.querySelectorAll('.judge-grid article')]
    const sections = [...document.querySelectorAll('.demo-section')]
    const metricRows = [...document.querySelectorAll('.score-table tbody tr')]
    const badgeText = [...document.querySelectorAll('.score-table tbody .n-tag')].map(node => node.textContent.trim())
    return {
      outer: [window.outerWidth, window.outerHeight],
      viewport: [window.innerWidth, window.innerHeight],
      devicePixelRatio: window.devicePixelRatio,
      sections: sections.length,
      judgeCards: cards.length,
      judgeCardsVisible: cards.every(card => {
        const rect = card.getBoundingClientRect()
        return rect.top >= 0 && rect.bottom <= window.innerHeight && rect.width > 0 && rect.height > 0
      }),
      firstScreenLabels: cards.map(card => card.textContent.trim()),
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      metricRows: metricRows.length,
      mockClaimedReal: badgeText.some(text => text.includes('实测达标') || text.includes('实测未达标')),
    }
  `)
}

async function auditRuntimeErrors() {
  return webdriver(`/session/${sessionId}/execute/async`, 'POST', {
    script: `
      const done = arguments[arguments.length - 1]
      const errors = []
      const onError = event => errors.push(String(event.error?.stack || event.message || event.type))
      const onRejection = event => errors.push(String(event.reason?.stack || event.reason || 'unhandledrejection'))
      window.addEventListener('error', onError)
      window.addEventListener('unhandledrejection', onRejection)
      setTimeout(() => {
        window.removeEventListener('error', onError)
        window.removeEventListener('unhandledrejection', onRejection)
        done(errors)
      }, 5500)
    `,
    args: [],
  })
}

try {
  await waitForDriver()
  const session = await webdriver('/session', 'POST', {
    capabilities: {
      alwaysMatch: {
        browserName: 'firefox',
        acceptInsecureCerts: false,
        'moz:firefoxOptions': {
          args: ['-headless'],
          prefs: {
            'layout.css.devPixelsPerPx': '1.25',
            'devtools.console.stdout.content': true,
          },
        },
      },
    },
  })
  sessionId = session.sessionId

  const loginResponse = await fetch(`${baseUrl}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin123', tenant_code: 'default' }),
  })
  if (!loginResponse.ok) throw new Error(`Login failed with HTTP ${loginResponse.status}`)
  const login = await loginResponse.json()
  const token = login.access_token || login.data?.access_token

  await navigate(`${baseUrl}/login`)
  await execute(`localStorage.setItem('token', arguments[0]); localStorage.setItem('demo_mode', 'mock');`, [token])
  await navigate(`${baseUrl}/admin/demo`)
  await waitForDemo()

  const viewports = [
    await auditViewport(1366, 768),
    await auditViewport(1920, 1080),
  ]
  const runtimeErrors = await auditRuntimeErrors()
  const modes = {}
  for (const mode of ['mock', 'local_mqtt', 'cloud_api', 'mixed']) {
    await setMode(mode)
    modes[mode] = await execute(`return {
      selected: document.querySelector('.mode-select .n-base-selection-label')?.textContent?.trim() || '',
      alert: document.querySelector('.notice')?.textContent?.trim() || '',
      sections: document.querySelectorAll('.demo-section').length,
    }`)
  }

  const result = { baseUrl, viewports, runtimeErrors, modes }
  const violations = []
  for (const viewport of viewports) {
    if (viewport.sections !== 6 || viewport.judgeCards !== 4) violations.push('missing demo sections or judge cards')
    if (!viewport.judgeCardsVisible) violations.push(`judge cards outside first screen at ${viewport.outer.join('x')}`)
    if (viewport.horizontalOverflow) violations.push(`document horizontal overflow at ${viewport.outer.join('x')}`)
    if (viewport.mockClaimedReal) violations.push('Mock metric was labelled as a real score')
  }
  if (runtimeErrors.length) violations.push(`runtime errors: ${runtimeErrors.join(' | ')}`)
  if (Object.values(modes).some(mode => mode.sections !== 6)) violations.push('a data-source mode lost demo sections')
  console.log(JSON.stringify({ ...result, violations }, null, 2))
  if (violations.length) process.exitCode = 1
} finally {
  if (sessionId) {
    try { await webdriver(`/session/${sessionId}`, 'DELETE') } catch { /* best effort */ }
  }
  driver.kill('SIGTERM')
}
