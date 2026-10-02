import { useState, useEffect } from 'react'
import { api } from '../api'

export default function Audit({ toast }) {
  const [a, setA] = useState([])

  useEffect(() => {
    api('/audit?limit=200')
      .then(setA)
      .catch((e) => toast(e.message))
  }, [toast])

  return (
    <div className="panel">
      <h2>Audit log</h2>
      {a.length === 0 ? (
        <div className="mute">No steward changes yet.</div>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Record</th>
                <th>Field</th>
                <th>Old</th>
                <th>New</th>
                <th>Steward</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {a.map((r) => (
                <tr key={r.id}>
                  <td>{r.changed_at.slice(0, 19).replace('T', ' ')}</td>
                  <td>{r.golden_id}</td>
                  <td>{r.field}</td>
                  <td>{r.old_value}</td>
                  <td>{r.new_value}</td>
                  <td>{r.steward}</td>
                  <td>{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}