import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/el-loading.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router, { warmPublicRoutes } from './router'
import './styles/global.css'

createApp(App).use(createPinia()).use(router).mount('#app')

router.isReady().then(() => warmPublicRoutes())
