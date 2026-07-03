import axios from 'axios'

const USER_KEY = 'agms-admin-user'
const AVATAR_KEY = 'agms-admin-avatar'
const SESSION_KEY = 'agms-admin-session'

export function hasAuthSession() {
  return localStorage.getItem(SESSION_KEY) === '1'
}

export function getAuthUser() {
  return localStorage.getItem(USER_KEY) || ''
}

export function getAuthAvatar() {
  return localStorage.getItem(AVATAR_KEY) || ''
}

export function adminAvatarUrlFromImage(image) {
  if (!image) return ''
  return storageUrl(image.thumbnail_path || image.preview_path || image.file_path)
}

export function setAuthSession({ access_token, username, expires_in, avatar_image }) {
  localStorage.setItem(SESSION_KEY, '1')
  void access_token
  if (username !== undefined) localStorage.setItem(USER_KEY, username || '')
  void expires_in
  if (avatar_image !== undefined) {
    const avatarUrl = adminAvatarUrlFromImage(avatar_image)
    if (avatarUrl) localStorage.setItem(AVATAR_KEY, avatarUrl)
    else localStorage.removeItem(AVATAR_KEY)
  }
}

export function clearAuthSession() {
  localStorage.removeItem(SESSION_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(AVATAR_KEY)
}

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true
})

function readCookie(name) {
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length) || ''
}

api.interceptors.request.use((config) => {
  const method = String(config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) {
    const csrfToken = readCookie('agms_admin_csrf')
    if (csrfToken) {
      config.headers = config.headers || {}
      config.headers['X-CSRF-Token'] = decodeURIComponent(csrfToken)
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearAuthSession()
    }
    return Promise.reject(error)
  }
)

export function storageUrl(path) {
  if (!path) return ''
  return `/storage/${String(path).replace(/^\/?storage\//, '').replaceAll('\\', '/')}`
}
