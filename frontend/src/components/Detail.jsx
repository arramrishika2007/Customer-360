import { useState } from 'react'
import { api } from '../api'
import { money, SYSTEM_LABELS } from '../utils'
import Steward from './Steward'

export default function Detail({ d, reload, toast, steward, setSteward }) {
  const g = d.golden
  const s = d.summary
  const lineage = d.lineage || []
  const matches = d.matches || []

  const [tab, setTab] = useState('overview')
  const [sys, setSys] = useState('all')
  const [field, setField] = useState('name')
  const [value, setValue] = useState('')
  const [why, setWhy] = useState('')

  const save = async () => {
    try {
      await api(`/customers/${g.golden_id}/override`, {
        body: { field, new_value: value, steward, reason: why },
      })
      toast('Saved override')
      setValue('')
      setWhy('')
      reload()
    } catch (e) {
      toast(e.message)
    }
  }

  const editable = Object.keys(g).filter((k) => k !== 'golden_id')

  // Transaction filter: Core / Card / Loan always shown, plus any imported system that has transactions
  const systems = [
    ...new Set(['SourceA', 'SourceB', 'SourceC', ...d.transactions.map((t) => t.source_system)]),
  ]
  const SYS = [['all', 'All'], ...systems.map((x) => [x, SYSTEM_LABELS[x] || x])]
  const tx = d.transactions.filter((t) => sys === 'all' || t.source_system === sys)
  const cnt = (k) =>
    k === 'all'
      ? d.transactions.length
      : d.transactions.filter((t) => t.source_system === k).length
  const cr = tx.filter((t) => t.txn_type === 'Credit').reduce((a, t) => a + t.amount, 0)
  const deb = tx.filter((t) => t.txn_type === 'Debit').reduce((a, t) => a + t.amount, 0)

  const TABS = [
    ['overview', 'Overview'],
    ['sources', 'Sources (' + d.source_records.length + ')'],
    ['matches', 'Matching (' + matches.length + ')'],
    ['txns', 'Transactions (' + d.transactions.length + ')'],
    ['edit', 'Correct'],
  ]

  const initials = (g.name || '?')
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')

  return (
    <div>
      <div className="card head">
        <div className="avatar">{initials}</div>
        <div style={{ flex: 1 }}>
          <div className="title">{g.name}</div>
          <div className="mute">{g.golden_id}</div>
          <div style={{ marginTop: 6 }}>
            {g.in_core ? <span className="tag">Core</span> : null}
            {g.in_card ? <span className="tag">Card</span> : null}
            {g.in_loan ? <span className="tag">Loan</span> : null}
          </div>
        </div>
      </div>

      <div className="kpis">
        <div className="kpi">
          <span className="mute">Quality score</span>
          <b>{g.quality_score}</b>
        </div>
        <div className="kpi">
          <span className="mute">Source records</span>
          <b>{d.source_records.length}</b>
        </div>
        <div className="kpi">
          <span className="mute">Transactions</span>
          <b>{s ? s.txn_count : 0}</b>
        </div>
        <div className="kpi">
          <span className="mute">Net flow</span>
          <b className={s && s.net_flow < 0 ? 'neg' : 'pos'}>{s ? money(s.net_flow) : '0.00'}</b>
        </div>
      </div>

      <div className="tabs">
        {TABS.map(([k, label]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="card">
          <h2>Golden record</h2>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Taken from</th>
                </tr>
              </thead>
              <tbody>
                {['name', 'email', 'phone', 'dob', 'address', 'credit_limit', 'loan_amount']
                  .filter((k) => g[k] != null && g[k] !== '')
                  .map((k) => {
                    const l = lineage.find((x) => x.field === k)
                    return (
                      <tr key={k}>
                        <td className="mute">{k}</td>
                        <td style={{ whiteSpace: 'normal' }}>{g[k]}</td>
                        <td className="mute">{l ? l.record_uid : ''}</td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
          {s && (
            <div className="mute" style={{ marginTop: 10 }}>
              Activity from {s.first_txn} to {s.last_txn}, across {s.systems_with_txns} system(s).
            </div>
          )}
        </div>
      )}

      {tab === 'sources' && (
        <div className="card">
          <h2>Source records</h2>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>System</th>
                  <th>Source ID</th>
                  <th>Raw name</th>
                  <th>Raw email</th>
                  <th>Raw address</th>
                </tr>
              </thead>
              <tbody>
                {d.source_records.map((r) => (
                  <tr key={r.record_uid}>
                    <td>{r.source_system}</td>
                    <td>{r.source_id}</td>
                    <td>{r.raw_name}</td>
                    <td>{r.raw_email}</td>
                    <td>{r.raw_address}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'matches' && (
        <div className="card">
          <h2>How records were matched</h2>
          {matches.length === 0 ? (
            <div className="mute">
              No exact or fuzzy candidate pairs involve this customer's source records.
            </div>
          ) : (
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>This record</th>
                    <th>Matched with</th>
                    <th>Name</th>
                    <th>Evidence</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((m, i) => (
                    <tr key={i}>
                      <td>
                        <span className={'tag ' + (m.method === 'exact' ? 'ok' : 'warn')}>
                          {m.method}
                        </span>
                      </td>
                      <td>{m.this_record}</td>
                      <td>{m.matched_with}</td>
                      <td>{m.matched_name}</td>
                      <td>{m.detail}</td>
                      <td className={m.joined ? 'pos' : 'mute'}>
                        {m.joined ? 'Joined' : 'Not joined (' + (m.other_golden_id || '?') + ')'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'txns' && (
        <div className="card">
          <h2>Transactions</h2>
          <div className="row" style={{ marginBottom: 12 }}>
            {SYS.map(([k, label]) => (
              <button
                key={k}
                className={'btn ' + (sys === k ? 'on' : '')}
                onClick={() => setSys(k)}
              >
                {label} ({cnt(k)})
              </button>
            ))}
          </div>
          <div className="mute" style={{ marginBottom: 10 }}>
            Credits {money(cr)}, debits {money(deb)}, net{' '}
            <span className={cr - deb < 0 ? 'neg' : 'pos'}>{money(cr - deb)}</span>
          </div>
          {tx.length === 0 ? (
            <div className="mute">No transactions for this customer in that system.</div>
          ) : (
            <div className="scroll" style={{ maxHeight: '55vh' }}>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Source</th>
                    <th>Account</th>
                    <th>Type</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {tx.map((t) => (
                    <tr key={t.txn_id}>
                      <td>{t.txn_date}</td>
                      <td>{t.source_system}</td>
                      <td>{t.account_id}</td>
                      <td>{t.txn_type}</td>
                      <td className={'num ' + (t.txn_type === 'Credit' ? 'pos' : 'neg')}>
                        {money(t.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'edit' && (
        <div className="card">
          <h2>Correct a field</h2>
          <div className="row">
            <select value={field} onChange={(e) => setField(e.target.value)}>
              {editable.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
            <input
              placeholder="New value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <input placeholder="Reason" value={why} onChange={(e) => setWhy(e.target.value)} />
            <Steward v={steward} set={setSteward} />
            <button className="btn ok" disabled={!steward || !value} onClick={save}>
              Save correction
            </button>
          </div>
          {d.audit_log.length > 0 && (
            <div className="mute" style={{ marginTop: 10 }}>
              {d.audit_log.length} earlier change(s) on this record. See the Audit log tab.
            </div>
          )}
        </div>
      )}
    </div>
  )
}