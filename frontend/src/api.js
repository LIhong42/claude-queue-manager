const API_BASE = '';
const WS_BASE = window.location.protocol === 'https:' ? 'wss://' : 'ws://' + window.location.host;

export const api = {
  listTasks: () => fetch(`${API_BASE}/api/tasks`).then(r => r.json()),
  createTask: (prompt, max_retries) => fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, max_retries })
  }).then(r => r.json()),
  getTask: (id) => fetch(`${API_BASE}/api/tasks/${id}`).then(r => r.json()),
  getTaskLog: (id) => fetch(`${API_BASE}/api/tasks/${id}/log`).then(r => r.json()),
  retryTask: (id) => fetch(`${API_BASE}/api/tasks/${id}/retry`, { method: 'POST' }).then(r => r.json()),
  cancelTask: (id) => fetch(`${API_BASE}/api/tasks/${id}/cancel`, { method: 'POST' }).then(r => r.json()),
  deleteTask: (id) => fetch(`${API_BASE}/api/tasks/${id}`, { method: 'DELETE' }).then(r => r.json()),
};

export const ws = {
  connect: (onMessage) => {
    const socket = new WebSocket(`${WS_BASE}/ws`);
    socket.onmessage = (e) => onMessage(JSON.parse(e.data));
    return socket;
  }
};
