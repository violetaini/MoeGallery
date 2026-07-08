import { api } from './client'

export const galleryApi = {
  login(payload) {
    return api.post('/auth/login', payload).then((r) => r.data)
  },
  logout() {
    return api.post('/auth/logout').then((r) => r.data)
  },
  me() {
    return api.get('/auth/me').then((r) => r.data)
  },
  installStatus() {
    return api.get('/install/status').then((r) => r.data)
  },
  install(payload) {
    return api.post('/install', payload).then((r) => r.data)
  },
  images(params = {}) {
    return api.get('/images', { params }).then((r) => r.data)
  },
  image(id) {
    return api.get(`/images/${id}`).then((r) => r.data)
  },
  trackImageView(id) {
    return api.post(`/images/${id}/view`).then((r) => r.data)
  },
  favoriteImage(id) {
    return api.post(`/images/${id}/favorite`).then((r) => r.data)
  },
  unfavoriteImage(id) {
    return api.delete(`/images/${id}/favorite`).then((r) => r.data)
  },
  uploadImages(formData) {
    return api.post('/images/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then((r) => r.data)
  },
  createUploadTasks(formData) {
    return api.post('/upload-tasks', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then((r) => r.data)
  },
  checkUploadDuplicates(payload) {
    return api.post('/upload-tasks/check-duplicates', payload).then((r) => r.data)
  },
  checkUploadDuplicateFiles(formData) {
    return api.post('/upload-tasks/check-duplicates-files', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then((r) => r.data)
  },
  uploadTasks(params = {}) {
    return api.get('/upload-tasks', { params }).then((r) => r.data)
  },
  previewUploadImage(file) {
    const data = new FormData()
    data.append('file', file)
    return api.post('/images/preview', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob'
    }).then((r) => r.data)
  },
  updateImage(id, payload) {
    return api.put(`/images/${id}`, payload).then((r) => r.data)
  },
  deleteImage(id) {
    return api.delete(`/images/${id}`)
  },
  updateImagesBatch(payload) {
    return api.put('/images/batch', payload).then((r) => r.data)
  },
  deleteImagesBatch(payload) {
    return api.delete('/images/batch', { data: payload }).then((r) => r.data)
  },
  importMetadata(formData, dryRun = true) {
    return api.post('/imports/metadata', formData, {
      params: { dry_run: dryRun },
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then((r) => r.data)
  },
  metadataImportTemplate(format = 'xlsx') {
    return api.get('/imports/metadata/template', {
      params: { format },
      responseType: 'blob'
    }).then((r) => r.data)
  },
  works(params = {}) {
    return api.get('/works', { params }).then((r) => r.data)
  },
  work(id) {
    return api.get(`/works/${id}`).then((r) => r.data)
  },
  createWork(payload) {
    return api.post('/works', payload).then((r) => r.data)
  },
  updateWork(id, payload) {
    return api.put(`/works/${id}`, payload).then((r) => r.data)
  },
  deleteWork(id) {
    return api.delete(`/works/${id}`)
  },
  characters(params = {}) {
    return api.get('/characters', { params }).then((r) => r.data)
  },
  character(id) {
    return api.get(`/characters/${id}`).then((r) => r.data)
  },
  createCharacter(payload) {
    return api.post('/characters', payload).then((r) => r.data)
  },
  updateCharacter(id, payload) {
    return api.put(`/characters/${id}`, payload).then((r) => r.data)
  },
  deleteCharacter(id) {
    return api.delete(`/characters/${id}`)
  },
  search(params = {}) {
    return api.get('/search', { params }).then((r) => r.data)
  },
  stats() {
    return api.get('/stats').then((r) => r.data)
  },
  settings() {
    return api.get('/settings').then((r) => r.data)
  },
  publicSettings() {
    return api.get('/settings/public').then((r) => r.data)
  },
  updateSettings(payload) {
    return api.put('/settings', payload).then((r) => r.data)
  },
  rotateAuthSecret() {
    return api.post('/settings/auth-secret/rotate').then((r) => r.data)
  },
  resetApiKeys() {
    return api.post('/settings/api-keys/reset').then((r) => r.data)
  },
  systemHealth() {
    return api.get('/system/health').then((r) => r.data)
  },
  checkUpdates() {
    return api.get('/updates/check').then((r) => r.data)
  },
  updateTasks(params = {}) {
    return api.get('/updates/tasks', { params }).then((r) => r.data)
  },
  createUpdateTask(payload) {
    return api.post('/updates/tasks', payload).then((r) => r.data)
  },
  updateTask(id) {
    return api.get(`/updates/tasks/${id}`).then((r) => r.data)
  },
  apiDocs() {
    return api.get('/api-docs/openapi.json', { baseURL: '' }).then((r) => r.data)
  }
}
