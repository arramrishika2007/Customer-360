export const money = (n) =>
  n == null
    ? ''
    : Number(n).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })

export const SYSTEM_LABELS = { SourceA: 'Core', SourceB: 'Card', SourceC: 'Loan' }