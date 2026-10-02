import { useState, useEffect, useMemo } from 'react'
import { api } from '../api'
import Steward from './Steward'

export default function Reviews({ toast, steward, setSteward }) {
  const [pairs, setPairs] = useState([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState({})

  const load = () =>
    api('/reviews')
      .then(setPairs)
      .catch((e) => toast(e.message))

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const groups = useMemo(() => {
    const m = {}
    pairs.forEach((p) => {
      const k = [p.golden_id_1, p.golden_id_2].sort().join('|')
      ;(m[k] = m[k] || []).push(p)
    })
    return Object.entries(m).map(([k, ps]) => ({ k, ps }))
  }, [pairs])

  const decide = async (grp, decision) => {
    if (!steward) {
      toast('Enter your steward name first')
      return
    }
    if (
      decision === 'approve' &&
      !window.confirm('Approve merge? This edits four tables and cannot be undone from the API.')
    )
      return
    setBusy(true)
    try {
      // first pair performs the merge; siblings are then recorded against the merged record
      for (const p of grp.ps) {
        await api('/reviews/decide', {
          body: {
            record_uid_1: p.record_uid_1,
            record_uid_2: p.record_uid_2,
            decision,
            steward,
            reason: note[grp.k] || '',
          },
        })
      }
      toast(decision === 'approve' ? 'Merged' : 'Rejected')
      await load()
    } catch (e) {
      toast(e.message)
      await load()
    }
    setBusy(false)
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <Steward v={steward} set={setSteward} />
        <span className="mute">
          {pairs.length} pending pairs = {groups.length} merge decisions. Every pair is flagged only
          by a shared email, so check names and addresses.
        </span>
      </div>

      {groups.length === 0 && <div className="panel mute">No pending reviews.</div>}

      {groups.map((grp) => {
        const p = grp.ps[0]
        const recs = {}
        grp.ps.forEach((x) => {
          recs[x.record_uid_1] = { id: x.record_uid_1, g: x.golden_id_1, n: x.name_1, a: x.address_1 }
          recs[x.record_uid_2] = { id: x.record_uid_2, g: x.golden_id_2, n: x.name_2, a: x.address_2 }
        })
        const byG = {}
        Object.values(recs).forEach((r) => (byG[r.g] = byG[r.g] || []).push(r))

        return (
          <div className="panel" key={grp.k}>
            <div className="row" style={{ marginBottom: 8 }}>
              <strong>{Object.keys(byG).join(' + ')}</strong>
              <span className={'tag ' + (p.name_verdict === 'match' ? 'ok' : 'warn')}>
                name: {p.name_verdict}
              </span>
              <span className={'tag ' + (p.address_verdict === 'different' ? 'bad' : 'ok')}>
                address: {p.address_verdict}
              </span>
              <span className="tag">street score {p.street_score}</span>
              <span className="tag">evidence: {p.exact_evidence}</span>
              {grp.ps.length > 1 && <span className="tag">{grp.ps.length} source pairs</span>}
            </div>

            <div className="pair">
              {Object.entries(byG).map(([gid, rs]) => (
                <div key={gid}>
                  <div className="mute" style={{ marginBottom: 4 }}>
                    {gid}
                  </div>
                  {rs.map((r) => (
                    <div className="rec" key={r.id}>
                      <div>
                        <strong>{r.n}</strong>
                      </div>
                      <div>{r.a}</div>
                      <div className="mute">{r.id}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div className="row" style={{ marginTop: 8 }}>
              <input
                style={{ flex: 1, minWidth: 200 }}
                placeholder="Reason (optional)"
                value={note[grp.k] || ''}
                onChange={(e) => setNote({ ...note, [grp.k]: e.target.value })}
              />
              <button className="btn bad" disabled={busy} onClick={() => decide(grp, 'reject')}>
                Reject (keep separate)
              </button>
              <button className="btn ok" disabled={busy} onClick={() => decide(grp, 'approve')}>
                Approve merge
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}