import { useCallback, useEffect, useState } from 'react'
import type { SystemStatus } from '../types'
import { api } from '../lib/api'
import { dailyResultLabel, dateLabel, timestampLabel, triggerLabel } from '../lib/format'

type Props = {
  onClose: () => void
  onChanged: () => void
}

export default function StartupPanel({ onClose, onChanged }: Props) {
  const [info, setInfo] = useState<SystemStatus | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)

  const load = useCallback(async () => {
    try {
      setInfo(await api.getSystem())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法读取启动设置')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function toggleStartup(enabled: boolean) {
    setSaving(true)
    setNotice('')
    try {
      const startup = await api.setStartup(enabled)
      setInfo((current) => (current ? { ...current, startup } : current))
      setError('')
      if (startup.manual_step) {
        setNotice('启动项已写入，但系统没有立即接受；按下面的命令手动执行一次即可。')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '修改开机启动失败')
    } finally {
      setSaving(false)
    }
  }

  async function scanNow() {
    setScanning(true)
    setNotice('')
    try {
      const run = await api.scan()
      setNotice(
        `${triggerLabel(run.trigger)}完成：${run.message}（${run.projects_ok} 个已同步，${run.projects_needing_confirmation} 个待确认）`,
      )
      await load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '巡检失败')
    } finally {
      setScanning(false)
    }
  }

  const startup = info?.startup
  const daily = info?.daily

  return (
    <section className="dialog provider-dialog" role="dialog" aria-modal="true" aria-labelledby="startup-title">
      <button className="dialog-close" onClick={onClose} aria-label="关闭">
        ×
      </button>
      <div className="eyebrow">STARTUP &amp; ROUTINE</div>
      <h2 id="startup-title">启动与日常</h2>
      <p className="dialog-intro">
        看板在本机运行。开机启动只负责拉起本地服务并打开浏览器；巡检仍然只读取已登记的项目文件夹。
      </p>

      {error && <div className="form-error detail-error">{error}</div>}
      {notice && <div className="test-result test-ok">{notice}</div>}

      <div className="detail-block startup-block">
        <h3>登录时自动启动</h3>
        <label className={`switch-row ${startup?.supported ? '' : 'switch-disabled'}`}>
          <input
            type="checkbox"
            checked={Boolean(startup?.enabled)}
            disabled={!startup?.supported || saving}
            onChange={(event) => void toggleStartup(event.target.checked)}
          />
          <span>
            {startup?.enabled ? '已加入开机启动' : '登录后自动启动看板'}
            <small>{startup?.note ?? '正在读取当前系统状态…'}</small>
          </span>
        </label>

        {startup && !startup.supported && (
          <p className="hint">当前系统（{startup.platform_label}）暂不支持自动注册；可以手动运行下面的命令。</p>
        )}

        {startup?.command && (
          <div className="startup-command">
            <small>启动命令</small>
            <code>{startup.command}</code>
            {startup.location && (
              <>
                <small>启动项位置</small>
                <code>{startup.location}</code>
              </>
            )}
          </div>
        )}

        {startup?.manual_step && (
          <div className="test-result test-bad">
            <strong>还需要一步手动操作</strong>
            <code>{startup.manual_step}</code>
          </div>
        )}
      </div>

      <div className="detail-block startup-block">
        <h3>每日自动巡检</h3>
        <div className="startup-daily">
          <span
            className={`daily-dot ${
              daily?.ran_today
                ? daily?.today_result === 'failed'
                  ? 'dot-bad'
                  : daily?.today_result === 'partial'
                    ? 'dot-warn'
                    : 'dot-good'
                : 'dot-idle'
            }`}
          />
          <div>
            <strong>
              {daily?.ran_today
                ? `今天已自动巡检 · ${dailyResultLabel(daily.today_result)}`
                : '今天还没有自动巡检'}
            </strong>
            <small>
              {daily?.ran_today
                ? `开始于 ${timestampLabel(daily.today_started_at)}`
                : '下次启动看板时会自动执行一次；每个自然日最多一次。'}
            </small>
          </div>
        </div>
        {daily?.last_date && (
          <p className="hint">
            上次自动巡检：{dateLabel(daily.last_date)} · {dailyResultLabel(daily.last_result)}
            {daily.last_finished_at ? ` · ${timestampLabel(daily.last_finished_at)}` : ''}
          </p>
        )}
        <p className="hint">
          自动巡检失败不会重试，也不会覆盖上次成功状态；需要时用下面的按钮手动重试。
        </p>
        <div className="form-actions">
          <button className="primary-button" onClick={() => void scanNow()} disabled={scanning}>
            {scanning ? '巡检中…' : '现在巡检一次'}
          </button>
        </div>
      </div>

      <div className="detail-block startup-block">
        <h3>运行环境</h3>
        <div className="startup-paths">
          <div>
            <small>平台</small>
            <code>
              {info?.platform_label ?? '—'} · v{info?.version ?? '—'}
            </code>
          </div>
          <div>
            <small>数据目录（数据库与密钥）</small>
            <code>{info?.paths.data ?? '—'}</code>
          </div>
          <div>
            <small>日志文件</small>
            <code>{info?.paths.log ?? '—'}</code>
          </div>
        </div>
        <p className="hint">服务只监听 127.0.0.1:8000，不会暴露到局域网；关闭窗口不影响已经保存的数据。</p>
      </div>
    </section>
  )
}
