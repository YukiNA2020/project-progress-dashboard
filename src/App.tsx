import { useEffect, useState } from 'react'

type Health = {
  status: 'ok'
  service: string
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    fetch('/api/health')
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return (await response.json()) as Health
      })
      .then((data) => {
        if (active) setHealth(data)
      })
      .catch(() => {
        if (active) setError('无法连接本地后端，请确认 API 服务已启动。')
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <main className="shell">
      <div className="eyebrow">PROJECT PROGRESS DASHBOARD</div>
      <h1>项目进度看板</h1>
      <p className="intro">本地运行基础已就绪。后续阶段将在这里加入项目登记和进度视图。</p>
      <section className="status-card" aria-live="polite">
        <span className={`status-dot ${health ? 'healthy' : error ? 'failed' : ''}`} />
        <div>
          <strong>{health ? '本地 API 已连接' : error ? '本地 API 未连接' : '正在连接本地 API…'}</strong>
          <p>{health ? `服务：${health.service}` : error ?? '检查回环地址上的后端健康状态'}</p>
        </div>
      </section>
      <footer>数据保存在本机。当前版本不会读取项目文件夹或调用模型 API。</footer>
    </main>
  )
}
