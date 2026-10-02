import { useState, useEffect } from 'react'
import { api } from '../api'
import { SYSTEM_LABELS } from '../utils'

function Stat({ label, value, note }) {
  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="mute">{label}</div>
      <div style={{ fontSize: 24, fontWeight: 650 }}>{value}</div>
      <div className="mute">{note}</div>
    </div>
  )
}

function Bars({ rows }) {
  const mx = Math.max(1, ...rows.map((r) => r.n))
  return (
    <>
      {rows.map((r) => (
        <div className="row" style={{ flexWrap: 'nowrap', marginBottom: 5 }} key={r.label}>
          <span style={{ width: 90 }}>{r.label}</span>
          <div style={{ flex: 1, background: 'var(--bg)', height: 14, borderRadius: 3 }}>
            <div
              style={{
                width: (r.n / mx) * 100 + '%',
                background: 'var(--accent)',
                height: 14,
                borderRadius: 3,
              }}
            />
          </div>
          <span className="num" style={{ width: 56 }}>
            {r.n}
          </span>
        </div>
      ))}
    </>
  )
}

export default function Summary({ toast }) {
  const [s, setS] = useState(null)

  useEffect(() => {
    api('/summary').then(setS).catch((e) => toast(e.message))
  }, [toast])

  if (!s) return <div className="panel mute">Loading…</div>

  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <Stat
          label="Golden records"
          value={s.golden_records}
          note={`from ${s.source_records} source records`}
        />
        <Stat
          label="In 2+ systems"
          value={s.multi_system}
          note="customers seen in more than one system"
        />
        <Stat
          label="Pending reviews"
          value={s.pending_pairs}
          note={`${s.pending_groups} merge decisions, ${s.decided_pairs} pairs decided`}
        />
        <Stat
          label="Transactions"
          value={s.transactions}
          note={`${s.steward_changes} steward changes logged`}
        />
      </div>
      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <div className="panel">
          <h2>Source records by system</h2>
          <Bars
            rows={s.by_system.map((r) => ({
              label: SYSTEM_LABELS[r.source_system] || r.source_system,
              n: r.n,
            }))}
          />
        </div>
        <div className="panel">
          <h2>Golden records by quality score</h2>
          <Bars
            rows={s.quality.map((r) => ({
              label: r.bucket == null ? 'none' : r.bucket + '-' + (r.bucket + 9),
              n: r.n,
            }))}
          />
        </div>
      </div>
    </div>
  )
}