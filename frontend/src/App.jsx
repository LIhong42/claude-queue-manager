import { useState, useEffect } from 'react'
import { api, ws } from './api.js'

const PAGE_SIZE = 4

function App() {
  const [tasks, setTasks] = useState([])
  const [prompt, setPrompt] = useState('')
  const [msg, setMsg] = useState('')
  const [selectedTask, setSelectedTask] = useState(null)
  const [showTrace, setShowTrace] = useState(false)
  const [traceData, setTraceData] = useState([])
  const [traceLoading, setTraceLoading] = useState(false)
  const [continueMsg, setContinueMsg] = useState('')
  const [continueLoading, setContinueLoading] = useState(false)
  const [runningPage, setRunningPage] = useState(1)
  const [completedPage, setCompletedPage] = useState(1)
  const [pendingPage, setPendingPage] = useState(1)

  const loadTasks = async () => {
    try {
      const data = await api.listTasks()
      setTasks(data)
      if (selectedTask) {
        const updated = data.find(t => t.id === selectedTask.id)
        if (updated) setSelectedTask(updated)
      }
    } catch (e) {
      console.error('load error:', e)
    }
  }

  const createTask = async () => {
    const trimmed = prompt.trim()
    if (!trimmed) return
    try {
      const r = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: trimmed })
      })
      if (r.ok) {
        setPrompt('')
        setMsg(' 已加入队列')
        setTimeout(() => setMsg(''), 1500)
        loadTasks()
      } else {
        const err = await r.text()
        setMsg(' 错误: ' + r.status + ' ' + err)
        setTimeout(() => setMsg(''), 5000)
      }
    } catch (e) {
      console.error(e)
    }
  }

  const retryTask = (id) => async () => {
    await api.retryTask(id)
    loadTasks()
  }

  const cancelTask = (id) => async () => {
    await api.cancelTask(id)
    loadTasks()
  }

  const deleteTask = (id) => async () => {
    await api.deleteTask(id)
    loadTasks()
    if (selectedTask && selectedTask.id === id) {
      setSelectedTask(null)
    }
  }

  const showTaskDetail = (task) => {
    setSelectedTask(task)
    setShowTrace(false)
    setTraceData([])
    setContinueMsg('')
  }

  const loadTrace = async (taskId) => {
    setTraceLoading(true)
    try {
      const data = await api.getTaskTrace(taskId)
      setTraceData(data.trace || [])
      setShowTrace(true)
    } catch (e) {
      console.error('load trace error:', e)
    }
    setTraceLoading(false)
  }

  const handleContinue = async () => {
    if (!continueMsg.trim() || !selectedTask?.session_id) return
    setContinueLoading(true)
    try {
      await api.continueTask(selectedTask.id, continueMsg)
      setContinueMsg('')
      loadTasks()
    } catch (e) {
      console.error('continue error:', e)
    }
    setContinueLoading(false)
  }

  useEffect(() => {
    loadTasks()
    const interval = setInterval(loadTasks, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const socket = ws.connect((x) => {
      loadTasks()
    })
    return () => socket.close()
  }, [])

  const runningTasks = tasks.filter(t => t.status === 'RUNNING')
  const completedTasks = tasks.filter(t => t.status === 'SUCCESS' || t.status === 'COMPLETED' || t.status === 'FAILED' || t.status === 'CANCELLED')
  const pendingTasks = tasks.filter(t => t.status === 'PENDING')

  const TaskTable = ({ title, taskList, page, setPage, showDelete = false, showDeleteAll = false }) => {
    const totalPages = Math.max(1, Math.ceil(taskList.length / PAGE_SIZE))
    const safePage = Math.min(page, totalPages)
    const startIdx = (safePage - 1) * PAGE_SIZE
    const endIdx = startIdx + PAGE_SIZE
    const pageTasks = taskList.slice(startIdx, endIdx)

    const goToPage = (newPage) => {
      if (newPage >= 1 && newPage <= totalPages) {
        setPage(newPage)
      }
    }

    return (
      <div className="card">
        <h3>{title} ({taskList.length})</h3>
        {taskList.length === 0 ? (
          <p className="empty">暂无任务</p>
        ) : (
          <>
            {showDeleteAll && (
              <div className="table-actions">
                <button className="btnDeleteAll" onClick={async () => {
                  for (const t of taskList) {
                    await api.deleteTask(t.id)
                  }
                  loadTasks()
                }}>全部删除</button>
              </div>
            )}
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>状态</th>
                    <th>重试</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {pageTasks.map(t => (
                    <tr key={t.id}>
                      <td>
                        <a href="#" className="taskLink" onClick={(e) => { e.preventDefault(); showTaskDetail(t) }}>
                          {t.id}
                        </a>
                      </td>
                      <td><span className="badge">{t.status}</span></td>
                      <td>{t.retry_count}/{t.max_retries}</td>
                      <td>
                        {t.status === 'FAILED' && (
                          <button className="btnRetry" onClick={retryTask(t.id)}>重试</button>
                        )}
                        {showDelete && (
                          <button className="btnDelete" onClick={deleteTask(t.id)}>删除</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="btnPage"
                  disabled={safePage === 1}
                  onClick={() => goToPage(safePage - 1)}
                >
                  上一页
                </button>
                <span className="pageInfo">{safePage} / {totalPages}</span>
                <button
                  className="btnPage"
                  disabled={safePage === totalPages}
                  onClick={() => goToPage(safePage + 1)}
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  return (
    <div className="app">
      <header>Claude Queue Manager</header>
      <main>
        <div className="card">
          <h3>创建任务</h3>
          <textarea
            placeholder="输入交给 Claude Agent 的任务..."
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
          />
          <br /><br />
          <button className="primary" onClick={createTask}>加入队列</button>
          <span className="msg">{msg}</span>
        </div>
        <div className="grid-3">
          <TaskTable title="正在运行" taskList={runningTasks} page={runningPage} setPage={setRunningPage} />
          <TaskTable title="已完成" taskList={completedTasks} page={completedPage} setPage={setCompletedPage} showDelete={true} showDeleteAll={true} />
          <TaskTable title="待完成任务" taskList={pendingTasks} page={pendingPage} setPage={setPendingPage} showDelete={true} />
        </div>
        {selectedTask && (
          <div className="card">
            <h3>任务详情</h3>
            <div className="detail-item">
              <strong>ID:</strong> {selectedTask.id}
            </div>
            <div className="detail-item">
              <strong>状态:</strong> <span className="badge">{selectedTask.status}</span>
            </div>
            <div className="detail-item">
              <strong>描述:</strong>
              <pre className="prompt-box">{selectedTask.prompt}</pre>
            </div>
            <div className="detail-actions">
              <button className="btnTrace" onClick={() => showTrace ? setShowTrace(false) : loadTrace(selectedTask.id)}>
                {traceLoading ? '加载中...' : showTrace ? '收起执行过程' : '查看执行过程'}
              </button>
              <button className="btnClose" onClick={() => setSelectedTask(null)}>关闭</button>
            </div>
            {selectedTask.session_id && (
              <div className="continue-panel">
                <h4>继续会话</h4>
                <textarea
                  placeholder="输入继续对话的指令..."
                  value={continueMsg}
                  onChange={e => setContinueMsg(e.target.value)}
                  className="continue-input"
                />
                <br />
                <button className="btnContinue" onClick={handleContinue} disabled={continueLoading || !continueMsg.trim()}>
                  {continueLoading ? '发送中...' : '发送'}
                </button>
              </div>
            )}
            {showTrace && (
              <div className="trace-panel">
                <h4>执行过程</h4>
                {traceData.length === 0 ? (
                  <p className="empty">暂无执行过程数据</p>
                ) : (
                  <div className="trace-list">
                    {traceData.map((event, idx) => (
                      <div key={idx} className={`trace-item trace-${event.type || 'unknown'}`}>
                        <div className="trace-type">{event.type || 'unknown'}</div>
                        <pre className="trace-content">{JSON.stringify(event, null, 2)}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
