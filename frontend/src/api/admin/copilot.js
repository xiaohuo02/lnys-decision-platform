/**
 * Copilot API — Admin (ops) + Business (biz)
 *
 * SSE streaming uses fetch directly (via useCopilotStream composable).
 * These helpers handle REST calls: history, feedback, actions.
 */
import { requestAdmin } from '../request'

// ── Thread History ──

export function listThreads(params = {}) {
  return requestAdmin.get('/copilot/threads', { params })
}

export function getThreadMessages(threadId, params = {}) {
  return requestAdmin.get(`/copilot/threads/${threadId}/messages`, { params })
}

export function pinThread(threadId) {
  return requestAdmin.post(`/copilot/threads/${threadId}/pin`)
}

export function unpinThread(threadId) {
  return requestAdmin.post(`/copilot/threads/${threadId}/unpin`)
}

// ── Feedback ──

export function submitFeedback(messageId, feedback, feedbackText = '') {
  return requestAdmin.post('/copilot/feedback', {
    message_id: messageId,
    feedback,
    feedback_text: feedbackText,
  })
}

// ── Action Execution ──

export function executeAction(actionType, target, payload = {}, threadId = null, messageId = null) {
  return requestAdmin.post('/copilot/action/execute', {
    action_type: actionType,
    target,
    payload,
    thread_id: threadId,
    message_id: messageId,
  })
}

// ── SSE Endpoint URLs ──

export const COPILOT_STREAM_URL = {
  ops: '/admin/copilot/stream',
  biz: '/api/copilot/stream',
}
