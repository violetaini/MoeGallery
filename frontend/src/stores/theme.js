import { defineStore } from 'pinia'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    dark: false
  }),
  actions: {
    apply() {
      document.documentElement.classList.toggle('dark', this.dark)
      localStorage.setItem('agms-theme', 'light')
    },
    toggle() {
      this.dark = false
      this.apply()
    }
  }
})
