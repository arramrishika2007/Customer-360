export default function Steward({ v, set }) {
  return (
    <input
      placeholder="Your name (steward)"
      value={v}
      onChange={(e) => set(e.target.value)}
      aria-label="Steward name"
    />
  )
}