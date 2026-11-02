import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { ProviderInput, ProviderSettings, ProviderTest } from '../types'
import { api } from '../lib/api'
import { timestampLabel } from '../lib/format'

type Props = {
  onClose: () => void
  onSaved: (settings: ProviderSettings) => void
}

type FormState = {
  enabled: boolean
  provider: string
  base_url: string
  model: string
  json_mode: boolean
  api_key: string
}

const emptyForm: FormState = {
  enabled: false,
  provider: 'openai',
  base_url: '',
  model: '',
  json_mode: true,
  api_key: '',
}

export default function ProviderForm({ onClose, onSaved }: Props) {
  const [settings, setSettings] = useState<ProviderSettings | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [test, setTest] = useState<ProviderTest | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.getProvider()
      setSettings(data)
      setForm({
        enabled: data.enabled,
        provider: data.provider,
        base_url: data.base_url,
        model: data.model,
        json_mode: data.json_mode,
        api_key: '',
      })
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法读取模型配置')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const selected = settings?.providers.find((item) => item.id === form.provider)

  function payload(): ProviderInput {
    const body: ProviderInput = {
      enabled: form.enabled,
      provider: form.provider,
      base_url: form.base_url,
      model: form.model,
      json_mode: form.json_mode,
    }
    if (form.api_key) body.api_key = form.api_key
    return body
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = await api.saveProvider(payload())
      setSettings(saved)
      setForm({ ...form, api_key: '' })
      onSaved(saved)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function runTest() {
    setTesting(true)
    setTest(null)
    try {
      setTest(await api.testProvider(payload()))
    } catch (err) {
      setError(err instanceof Error ? err.message : '测试连接失败')
    } finally {
      setTesting(false)
    }
  }

  async function clearKey() {
    setSaving(true)
    try {
      const saved = await api.saveProvider({ ...payload(), enabled: false, api_key: '' })
      setSettings(saved)
      setForm({ ...form, enabled: false })
      onSaved(saved)
      setTest(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '清除密钥失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="dialog provider-dialog" role="dialog" aria-modal="true" aria-labelledby="provider-title">
      <button className="dialog-close" onClick={onClose} aria-label="关闭">×</button>
      <div className="eyebrow">MODEL PROVIDER</div>
      <h2 id="provider-title">模型抽取设置</h2>
      <p className="dialog-intro">
        启用后，巡检会把少量证据片段发送到下面配置的接口，用结构化结果复核规则判断。不启用时看板只使用本地规则。
      </p>

      {error && <div className="form-error detail-error">{error}</div>}

      <form onSubmit={submit} className="project-form">
        <label className="switch-row">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
          />
          <span>
            启用模型抽取
            <small>关闭时不会发出任何网络请求，规则结果照常更新。</small>
          </span>
        </label>

        <div className="provider-grid">
          <label>
            服务商
            <select
              value={form.provider}
              onChange={(event) => setForm({ ...form, provider: event.target.value })}
            >
              {(settings?.providers ?? [{ id: 'openai', label: 'OpenAI 兼容接口', default_base_url: '' }]).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            模型名
            <input
              value={form.model}
              maxLength={120}
              onChange={(event) => setForm({ ...form, model: event.target.value })}
              placeholder="例如：gpt-4o-mini"
            />
          </label>
        </div>

        <label>
          接口地址（Base URL）
          <input
            value={form.base_url}
            maxLength={500}
            onChange={(event) => setForm({ ...form, base_url: event.target.value })}
            placeholder={selected?.default_base_url ?? 'https://api.openai.com/v1'}
          />
          <small>留空则使用服务商默认地址。可以填兼容 OpenAI 协议的代理地址，请求只在后端发出。</small>
        </label>

        <label>
          API 密钥
          <input
            type="password"
            value={form.api_key}
            maxLength={400}
            autoComplete="off"
            onChange={(event) => setForm({ ...form, api_key: event.target.value })}
            placeholder={settings?.api_key_set ? `已保存（${settings.key_hint}），留空则不修改` : '尚未保存密钥'}
          />
          <small>
            密钥只保存在本机（{settings?.key_storage === 'keyring' ? '系统凭证库' : '应用数据目录，权限 0600'}），
            不会进入浏览器、日志或项目文件。
          </small>
        </label>

        <p className="privacy-note">
          发送内容只包含：项目名、计划周期、相对文件路径与截断后的证据摘录（最多约 6000 字符）。
          本地托管不代表请求离线——正文会到达上面这个地址。
          {settings?.effective_base_url ? ` 当前目的地：${settings.endpoint_host || settings.effective_base_url}` : ''}
        </p>

        {test && (
          <div className={`test-result ${test.ok ? 'test-ok' : 'test-bad'}`}>
            <strong>{test.ok ? '连接成功' : '连接失败'}</strong>
            <span>
              {test.message} · {test.latency_ms} ms · {test.model || '未填模型名'}
            </span>
          </div>
        )}

        {!test && settings?.last_test_at && (
          <p className="hint">
            上次测试：{settings.last_test_ok ? '成功' : '失败'} · {timestampLabel(settings.last_test_at)}
            {settings.last_test_message ? ` · ${settings.last_test_message}` : ''}
          </p>
        )}

        <div className="form-actions provider-actions">
          {settings?.api_key_set && (
            <button type="button" className="quiet-button danger-button" onClick={() => void clearKey()} disabled={saving}>
              清除密钥
            </button>
          )}
          <button type="button" className="quiet-button" onClick={() => void runTest()} disabled={testing || saving}>
            {testing ? '测试中…' : '测试连接'}
          </button>
          <button className="primary-button" type="submit" disabled={saving || testing}>
            {saving ? '保存中…' : '保存设置'}
          </button>
        </div>
      </form>
    </section>
  )
}
