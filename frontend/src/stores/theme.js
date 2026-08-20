export function applyLightTheme() {
  document.documentElement.classList.remove('dark')
  localStorage.setItem('agms-theme', 'light')
}
