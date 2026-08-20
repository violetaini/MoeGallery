import crypto from 'node:crypto'
import https from 'node:https'

const accessKeyId = process.env.ALIBABA_ACCESS_KEY_ID
const accessKeySecret = process.env.ALIBABA_ACCESS_KEY_SECRET
const siteName = process.env.ESA_SITE_NAME || 'chitanda.net'
const apply = process.argv.includes('--apply')
const endpoint = 'esa.cn-hangzhou.aliyuncs.com'
const version = '2024-09-10'

if (!accessKeyId || !accessKeySecret) {
  throw new Error('Set ALIBABA_ACCESS_KEY_ID and ALIBABA_ACCESS_KEY_SECRET before running this script.')
}

function percentEncode(value) {
  return encodeURIComponent(String(value))
    .replace(/[!'()*]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`)
}

function signedParams(action, extra, method) {
  const params = {
    Action: action,
    Version: version,
    Format: 'JSON',
    AccessKeyId: accessKeyId,
    SignatureMethod: 'HMAC-SHA1',
    Timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    SignatureVersion: '1.0',
    SignatureNonce: crypto.randomUUID(),
    RegionId: 'cn-hangzhou',
    ...extra
  }
  const canonical = Object.keys(params)
    .sort()
    .map((key) => `${percentEncode(key)}=${percentEncode(params[key])}`)
    .join('&')
  const stringToSign = `${method}&%2F&${percentEncode(canonical)}`
  const signature = crypto.createHmac('sha1', `${accessKeySecret}&`)
    .update(stringToSign)
    .digest('base64')
  return { ...params, Signature: signature }
}

function encodeParams(params) {
  return Object.keys(params)
    .sort()
    .map((key) => `${percentEncode(key)}=${percentEncode(params[key])}`)
    .join('&')
}

function call(action, extra, method = 'GET') {
  const payload = encodeParams(signedParams(action, extra, method))
  const options = {
    hostname: endpoint,
    path: method === 'GET' ? `/?${payload}` : '/',
    method
  }
  if (method === 'POST') {
    options.headers = {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Content-Length': Buffer.byteLength(payload)
    }
  }

  return new Promise((resolve, reject) => {
    const request = https.request(options, (response) => {
      let body = ''
      response.setEncoding('utf8')
      response.on('data', (chunk) => { body += chunk })
      response.on('end', () => {
        let result
        try {
          result = JSON.parse(body)
        } catch (error) {
          reject(new Error(`${action} returned invalid JSON: ${error.message}`))
          return
        }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`${action} failed with HTTP ${response.statusCode}: ${result.Code || result.Message || 'unknown error'}`))
          return
        }
        resolve(result)
      })
    })
    request.on('error', reject)
    if (method === 'POST') request.write(payload)
    request.end()
  })
}

function summarize(config) {
  if (!config) return null
  return {
    configId: config.ConfigId,
    configType: config.ConfigType,
    gzip: config.Gzip,
    brotli: config.Brotli,
    zstd: config.Zstd
  }
}

const sites = await call('ListSites', { PageNumber: 1, PageSize: 100 })
const site = (sites.Sites || []).find((candidate) => candidate.SiteName === siteName)
if (!site) throw new Error(`ESA site ${siteName} was not found.`)

const rulesResult = await call('ListCompressionRules', {
  SiteId: site.SiteId,
  PageNumber: 1,
  PageSize: 100
})
const globalRule = (rulesResult.Configs || []).find((config) => config.ConfigType === 'global')

if (!apply) {
  process.stdout.write(`${JSON.stringify({
    site: { id: site.SiteId, name: site.SiteName, plan: site.PlanName },
    compression: (rulesResult.Configs || []).map(summarize),
    plannedAction: globalRule?.Gzip === 'on' && globalRule?.Brotli === 'on' && globalRule?.Zstd === 'on'
      ? 'none'
      : globalRule ? 'UpdateCompressionRule' : 'CreateCompressionRule',
    requested: { gzip: 'on', brotli: 'on', zstd: 'on' }
  }, null, 2)}\n`)
  process.stdout.write('Dry run only. Pass --apply to enable compression.\n')
} else if (globalRule?.Gzip === 'on' && globalRule?.Brotli === 'on' && globalRule?.Zstd === 'on') {
  process.stdout.write(`${JSON.stringify({ changed: false, compression: summarize(globalRule) }, null, 2)}\n`)
} else {
  const action = globalRule ? 'UpdateCompressionRule' : 'CreateCompressionRule'
  const update = globalRule
    ? { SiteId: site.SiteId, ConfigId: globalRule.ConfigId, Gzip: 'on', Brotli: 'on', Zstd: 'on' }
    : { SiteId: site.SiteId, Gzip: 'on', Brotli: 'on', Zstd: 'on' }
  const result = await call(action, update, 'POST')
  const verified = await call('ListCompressionRules', {
    SiteId: site.SiteId,
    PageNumber: 1,
    PageSize: 100
  })
  const verifiedGlobalRule = (verified.Configs || []).find((config) => config.ConfigType === 'global')
  if (verifiedGlobalRule?.Gzip !== 'on' || verifiedGlobalRule?.Brotli !== 'on' || verifiedGlobalRule?.Zstd !== 'on') {
    throw new Error('ESA accepted the request but compression was not fully enabled in the verified global configuration.')
  }
  process.stdout.write(`${JSON.stringify({
    changed: true,
    action,
    requestId: result.RequestId,
    compression: summarize(verifiedGlobalRule)
  }, null, 2)}\n`)
}
