import { useCallback, useEffect, useState } from 'react'
import type { EvidenceRow, Project, ProjectDetailData } from '../types'
import { api } from '../lib/api'
import {
  basisNote,
  citationSupportLabel,
  dateLabel,
  evidenceKindLabel,
  fieldLabel,
  modelStatusLabel,
  phaseStatusLabel,
  timestampLabel,
} from '../lib/format'

type Props = {
  projectId: string
  refreshKey: number
  onClose: () => void
  onEdit: (project: Project) => void
  onArchive: (project: Project, archived: boolean) => void
  onChanged: () => void
}

function evidenceKey(item: EvidenceRow): string {
  return `${item.kind}-${item.id}`
}

export default function ProjectDetail({ projectId, refreshKey, onClose, onEdit, onArchive, onChanged }: Props) {
  const [detail, setDetail] = useState<ProjectDetailData | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setDetail(await api.projectDetail(projectId))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法读取项目详情')
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  async function decide(pendingId: number, decision: 'accept' | 'dismiss') {
    setBusyId(pendingId)
    try {
      await api.decide(pendingId, decision)
      await load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '处理失败')
    } finally {
      setBusyId(null)
    }
  }

  const project = detail?.project
  const state = detail?.state
  const phases = detail?.phases ?? []
  const pending = detail?.pending ?? []
  const evidence = detail?.evidence ?? []
  const currentOrdinal = state?.candidate_phase_ordinal ?? state?.accepted_phase_ordinal ?? null
  const needsConfirmation = state?.status === 'needs_confirmation'
  const modelError = state?.status === 'model_error'
  const citations = state?.model_citations ?? []
  const changes = pending.filter((item) => item.kind === 'schedule_change')
  const ambiguities = pending.filter((item) => item.kind === 'ambiguous_state')
  const issues = pending.filter((item) => item.kind === 'model_issue')

  return (
    <section className="dialog detail-dialog wide" role="dialog" aria-modal="true" aria-labelledby="detail-title">
      <button className="dialog-close" onClick={onClose} aria-label="关闭">×</button>
      <div className="eyebrow">PROJECT OVERVIEW</div>
      <h2 id="detail-title">
        <i style={{ background: project?.color ?? '#465ed8' }} />
        {project?.name ?? '项目'}
      </h2>

      {error && <div className="form-error detail-error">{error}</div>}

      {state?.scan_error && (
        <div className="banner banner-error">
          <strong>本次巡检未能读取项目文件夹</strong>
          <span>{state.scan_error} · 已保留上次成功状态（{timestampLabel(state.last_success_at)}）</span>
        </div>
      )}

      {needsConfirmation && (
        <div className="banner banner-warn">
          <strong>需要你确认</strong>
          <span className="banner-reason">{state?.reason}</span>
          <span>看板不会在证据冲突时替你选一个阶段。请修正来源文档后重新巡检。</span>
        </div>
      )}

      {modelError && (
        <div className="banner banner-error">
          <strong>模型未确认本次结果</strong>
          <span className="banner-reason">{state?.reason}</span>
          <span>
            已保留上次已接受的状态（{timestampLabel(state?.last_success_at)}）。可在右上角“模型设置”里测试连接或更换模型后重试。
          </span>
        </div>
      )}

      {project && (
        <div className="detail-date">
          <span>计划周期</span>
          <strong>
            {dateLabel(project.planned_start)} — {dateLabel(project.planned_end)}
          </strong>
        </div>
      )}

      {changes.length > 0 && (
        <div className="detail-block">
          <h3>排期变更待确认</h3>
          <div className="pending-list">
            {changes.map((item) => (
              <div className="pending-item" key={item.id}>
                <div>
                  <strong>{fieldLabel(item.field)}</strong>
                  <p>
                    <s>{dateLabel(item.previous_value)}</s> → <b>{dateLabel(item.candidate_value)}</b>
                  </p>
                  <small>来源：{item.source_path}</small>
                  <small className="pending-quote">{item.evidence}</small>
                </div>
                <div className="pending-actions">
                  <button className="quiet-button" disabled={busyId === item.id} onClick={() => void decide(item.id, 'dismiss')}>
                    忽略
                  </button>
                  <button className="primary-button" disabled={busyId === item.id} onClick={() => void decide(item.id, 'accept')}>
                    接受
                  </button>
                </div>
              </div>
            ))}
          </div>
          <p className="hint">接受之前不会改动日历上的计划日期。</p>
        </div>
      )}

      {ambiguities.length > 0 && (
        <div className="detail-block">
          <h3>待确认的问题</h3>
          <div className="pending-list">
            {ambiguities.map((item) => (
              <div className="pending-item" key={item.id}>
                <div>
                  <strong>{item.previous_value || '证据冲突'}</strong>
                  <small>巡检时间 {timestampLabel(state?.scanned_at)}</small>
                </div>
                <div className="pending-actions">
                  <button className="quiet-button" disabled={busyId === item.id} onClick={() => void decide(item.id, 'dismiss')}>
                    标记为已知
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {issues.length > 0 && (
        <div className="detail-block">
          <h3>模型调用问题</h3>
          <div className="pending-list">
            {issues.map((item) => (
              <div className="pending-item" key={item.id}>
                <div>
                  <strong>{item.previous_value || '模型未返回可用结果'}</strong>
                  <small>巡检时间 {timestampLabel(state?.scanned_at)}</small>
                </div>
                <div className="pending-actions">
                  <button className="quiet-button" disabled={busyId === item.id} onClick={() => void decide(item.id, 'dismiss')}>
                    标记为已知
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="detail-block">
        <h3>项目简介</h3>
        {state?.summary ? (
          <>
            <p className="summary-text">{state.summary}</p>
            <small className="source-line">来源：{state.summary_source}</small>
          </>
        ) : (
          <p className="placeholder-text">没有从 README 中提取到简介。</p>
        )}
      </div>

      <div className="detail-block">
        <h3>最近一次带日期的进展</h3>
        {state?.newest_record_date ? (
          <div className="latest-record">
            <span className="record-date">{dateLabel(state.newest_record_date)}</span>
            <p>{state.newest_record_claim}</p>
            <small className="source-line">来源：{state.newest_record_source}</small>
          </div>
        ) : (
          <p className="placeholder-text">文档中没有带明确日期的进展记录；看板不会用文件修改时间代替。</p>
        )}
        {state?.newest_record_date && needsConfirmation && (
          <p className="hint">同一天可能还有其它记录且互相冲突，见下方“来源与证据”。</p>
        )}
      </div>

      <div className="detail-block">
        <h3>
          Phase 时间线
          {state?.candidate_testing && <em className="testing-tag">测试中</em>}
        </h3>
        {phases.length > 0 ? (
          <>
            <ol className="phase-timeline">
              {phases.map((phase) => {
                const isCurrent = currentOrdinal !== null && phase.ordinal === currentOrdinal
                const isDone = currentOrdinal !== null && phase.ordinal < currentOrdinal
                return (
                  <li
                    key={phase.id}
                    className={`phase-row ${isCurrent ? 'phase-current' : ''} ${isDone ? 'phase-done' : ''}`}
                  >
                    <span className="phase-node" />
                    <div className="phase-body">
                      <div className="phase-title">
                        <b>{phase.name}</b>
                        <span className={`phase-tag tag-${phase.status}`}>{phaseStatusLabel(phase.status)}</span>
                        {isCurrent && state?.candidate_testing && <span className="phase-tag tag-testing">测试中</span>}
                      </div>
                      <small>
                        {phase.start_date || phase.end_date
                          ? `${dateLabel(phase.start_date, '开始未记录')} — ${dateLabel(phase.end_date, '结束未记录')}`
                          : '文档未记录阶段日期'}
                      </small>
                    </div>
                  </li>
                )
              })}
            </ol>
            {state && basisNote(state.current_basis) && <p className="hint">{basisNote(state.current_basis)}</p>}
          </>
        ) : (
          <p className="placeholder-text">项目文档中没有识别到 Phase 结构。</p>
        )}
        {state?.notes && state.notes.length > 0 && (
          <ul className="notes-list">
            {state.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        )}
      </div>

      <div className="detail-block">
        <h3>模型核对</h3>
        <div className="model-row">
          <span className={`model-pill model-${state?.model_status ?? 'disabled'}`}>
            {modelStatusLabel(state?.model_status)}
          </span>
          {state?.model_provider && (
            <small>
              {state.model_provider}
              {state.model_name ? ` · ${state.model_name}` : ''}
            </small>
          )}
          {state?.model_confidence && <small>置信度 {state.model_confidence}</small>}
          {state?.model_checked_at && <small>{timestampLabel(state.model_checked_at)}</small>}
        </div>
        {state?.model_status === 'disabled' && (
          <p className="placeholder-text">未启用模型抽取，当前结果只来自本地规则。可在右上角“模型设置”中启用。</p>
        )}
        {state?.model_error && <p className="model-error-text">{state.model_error}</p>}
        {state?.model_summary && <p className="summary-text model-summary">{state.model_summary}</p>}
        {citations.length > 0 && (
          <>
            <div className="citation-list">
              {citations.map((citation, index) => (
                <div className="citation-item" key={`${citation.evidence_id}-${citation.supports}-${index}`}>
                  <span className="citation-tag">{citationSupportLabel(citation.supports)}</span>
                  <p>“{citation.quote}”</p>
                  <small>
                    {citation.evidence_id} · {citation.source}
                  </small>
                </div>
              ))}
            </div>
            <p className="hint">每条结论都必须能在对应证据原文中逐字找到；找不到时整次结果会被丢弃，不会推进状态。</p>
          </>
        )}
      </div>

      <div className="detail-block">
        <h3>来源与证据</h3>
        {evidence.length > 0 ? (
          <>
            <div className="evidence-list">
              {evidence.slice(0, 12).map((item) => (
                <div className="evidence-item" key={evidenceKey(item)}>
                  <div className="evidence-head">
                    <span className={`kind-tag kind-${item.kind}`}>{evidenceKindLabel(item.kind)}</span>
                    <span className="evidence-date">{item.record_date ? dateLabel(item.record_date) : '无日期'}</span>
                    {item.is_newest && <span className="newest-tag">最新</span>}
                  </div>
                  <p>{item.claim}</p>
                  <small>
                    {item.source_path}
                    {item.heading ? ` · ${item.heading}` : ''}
                  </small>
                </div>
              ))}
            </div>
            <p className="hint">
              共 {state?.files_scanned ?? 0} 个 Markdown 文件参与本次巡检，识别到 {state?.evidence_count ?? evidence.length} 条证据
              {evidence.length > 12 ? '，此处展示最近 12 条' : ''}。文档内容只作为数据读取。
            </p>
          </>
        ) : (
          <p className="placeholder-text">还没有证据记录，运行一次巡检后会显示来源片段。</p>
        )}
      </div>

      <div className="detail-block">
        <h3>项目文件夹</h3>
        <code>{project?.folder_path}</code>
      </div>

      {project && (
        <div className="detail-actions">
          <button className="quiet-button" onClick={() => onEdit(project)}>编辑项目</button>
          {project.archived ? (
            <button className="primary-button" onClick={() => onArchive(project, false)}>恢复项目</button>
          ) : (
            <button className="quiet-button danger-button" onClick={() => onArchive(project, true)}>归档项目</button>
          )}
        </div>
      )}
    </section>
  )
}
