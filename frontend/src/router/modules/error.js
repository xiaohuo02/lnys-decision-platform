export default [
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/auth/NotFoundView.vue'),
    meta: { title: '页面不存在', public: true },
  },
]
