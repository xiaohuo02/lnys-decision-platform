import AuthLayout from '@/layouts/AuthLayout.vue'

export default [
  {
    path: '/login',
    component: AuthLayout,
    children: [
      { path: '', name: 'Login', component: () => import('@/views/auth/LoginView.vue'), meta: { title: '登录', public: true } },
    ],
  },
  {
    path: '/register',
    component: AuthLayout,
    children: [
      { path: '', name: 'Register', component: () => import('@/views/auth/RegisterView.vue'), meta: { title: '注册', public: true } },
    ],
  },
  {
    path: '/403',
    component: AuthLayout,
    children: [
      { path: '', name: 'Forbidden', component: () => import('@/views/auth/ForbiddenView.vue'), meta: { title: '无权访问', public: true } },
    ],
  },
]
