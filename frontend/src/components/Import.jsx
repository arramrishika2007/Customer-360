import { useState, useEffect } from 'react'
import { api } from '../api'
import Steward from './Steward'

const FIELDS = [
  ['id', 'Source ID (required)'],
  ['name', 'Name'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['dob', 'Date of birth'],
  ['address', 'Address'],
  ['credit_limit', 'Credit limit'],
  ['loan_amount', 'Loan amount'],
]

export default function Import({ toast, steward, setSteward }) {
  const [file, setFile] = useState(null)
  const [pv, setPv] = useState(null)
  const [map, setMap] = useState({})
  const [sel, setSel] = useState('__new__')
  const [newSys, setNewSys] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [log, setLog] = useState([])

  const loadLog = () =>
    api('/import/log')
      .then(setLog)
      .catch(() => {})

  useEffect(() => {
    loadLog()
  }, [])

  const pick = async (e) => {
    const f = e.target.files[0]
    if (!f) return
    setRes(null)
    const content = await f.text()
    setFile({ name: f.name, content })
    try {
      const p = await api('/import/preview', { body: { filename: f.name, content } })
      setPv(p)
      setMap(p.mapping)
    } catch (err) {
      toast(err.message)
      setPv(null)
    }
  }

  const system = sel === '__new__' ? newSys.trim() : sel
  const ok = pv && map.id && system && steward && !busy

  const run = async () => {
    if (
      !window.confirm(
        'Import ' + pv.rows + ' rows into ' + system + '? A backup of the database is made first.'
      )
    )
      return
    setBusy(true)
    try {
      const r = await api('/import/commit', {
        body: {
          filename: file.name,
          content: file.content,
          system,
          mapping: map,
          steward,
          reason: why,
        },
      })
      setRes(r)
      setPv(null)
      setFile(null)
      loadLog()
    } catch (err) {
      toast(err.message)
    }
    setBusy(false)
  }

  return (
    <div>
      <div className="panel">
        <h2>Import a CSV or JSON file</h2>
        <p className="mute" style={{ marginTop: 0 }}>
          The file is cleaned, appended to source_info, matched against existing records and merged
          using the same rules as the original pipeline. Uncertain matches go to the Review queue.
        </p>
        <input type="file" accept=".csv,.json" onChange={pick} />
      </div>

      {pv && (
        <>
          <div className="panel">
            <h2>Preview ({pv.rows} rows)</h2>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    {pv.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pv.sample.map((r, i) => (
                    <tr key={i}>
                      {pv.columns.map((c) => (
                        <td key={c}>{r[c] == null ? '' : String(r[c])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <h2>Map columns</h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))',
                gap: 12,
              }}
            >
              {FIELDS.map(([k, label]) => (
                <label key={k}>
                  <div className="mute">{label}</div>
                  <select
                    style={{ width: '100%' }}
                    value={map[k] || ''}
                    onChange={(e) => setMap({ ...map, [k]: e.target.value })}
                  >
                    <option value="">(not in file)</option>
                    {pv.columns.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            <h2 style={{ marginTop: 18 }}>Source system</h2>
            <div className="row">
              <select value={sel} onChange={(e) => setSel(e.target.value)}>
                {pv.systems.map((x) => (
                  <option key={x} value={x}>
                    Add to {x}
                  </option>
                ))}
                <option value="__new__">New system</option>
              </select>
              {sel === '__new__' && (
                <input
                  placeholder="Name, e.g. SourceD"
                  value={newSys}
                  onChange={(e) => setNewSys(e.target.value)}
                />
              )}
              <input
                placeholder="Reason (optional)"
                value={why}
                onChange={(e) => setWhy(e.target.value)}
              />
              <Steward v={steward} set={setSteward} />
              <button className="btn ok" disabled={!ok} onClick={run}>
                {busy ? 'Importing, please wait…' : 'Import'}
              </button>
            </div>
          </div>
        </>
      )}

      {res && (
        <div className="panel">
          <h2>Import finished</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 4 }}>
            <span className="mute">Rows imported</span>
            <span>
              {res.rows_imported} into {res.system} ({res.blank_id_skipped} skipped, no ID)
            </span>
            <span className="mute">New golden records</span>
            <span>{res.new_golden_records}</span>
            <span className="mute">Joined to existing</span>
            <span>{res.records_joined_to_existing} records</span>
            <span className="mute">Added to Review queue</span>
            <span>{res.review_pairs_added} pairs</span>
            <span className="mute">Backup</span>
            <span>{res.backup}</span>
          </div>
        </div>
      )}

      <div className="panel">
        <h2>Earlier imports</h2>
        {log.length === 0 ? (
          <div className="mute">None yet.</div>
        ) : (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>File</th>
                  <th>System</th>
                  <th className="num">Rows</th>
                  <th className="num">New golden</th>
                  <th className="num">Joined</th>
                  <th className="num">Review</th>
                  <th>Steward</th>
                </tr>
              </thead>
              <tbody>
                {log.map((r) => (
                  <tr key={r.id}>
                    <td>{r.imported_at.slice(0, 19).replace('T', ' ')}</td>
                    <td>{r.filename}</td>
                    <td>{r.source_system}</td>
                    <td className="num">{r.rows_imported}</td>
                    <td className="num">{r.new_golden}</td>
                    <td className="num">{r.joined_existing}</td>
                    <td className="num">{r.review_pairs}</td>
                    <td>{r.steward}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}