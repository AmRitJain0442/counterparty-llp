/** The four desks: questions, intake fields, witness routes and the fee each one replaces. */

export const DESKS = [
  {
    id: 'payment',
    name: 'Payment',
    alias: 'Ghost Controller',
    color: '#ff8a5c',
    question: 'Is the person asking us to change bank details still at the vendor?',
    verdicts: ['HELD', 'RELEASED'],
    replaces: 'Vendor-master audit and call-back checks',
    fee: 'Staff time plus bank-detail fraud losses',
    credits: '~4',
    fields: [
      { key: 'domain', label: 'Vendor domain', placeholder: 'vendor.example' },
      { key: 'sender_domain', label: 'Domain the email came from', placeholder: 'vendor-billing.example' },
      { key: 'person_url', label: 'Contact profile URL', placeholder: 'https://…', consent: true },
      { key: 'orgnr', label: 'Vendor registry number (Norway)', placeholder: '9 digits' },
      { key: 'ifsc', label: 'New bank IFSC', placeholder: 'ABCD0123456' },
    ],
    consentFor: ['person_url'],
    sources: [
      { id: 'enrich', label: 'Crustdata person enrich', note: 'Dated employment history', from: ['person_url'] },
      { id: 'company', label: 'Crustdata company enrich', note: 'Is the vendor still staffed', from: ['domain'] },
      { id: 'rdap', label: 'RDAP · certificates', note: 'How old is the sending domain', from: ['sender_domain', 'domain'] },
      { id: 'ifsc', label: 'IFSC · OpenIBAN', note: 'Bank, branch and city', from: ['ifsc'] },
    ],
  },
  {
    id: 'candidate',
    name: 'Candidate',
    alias: 'Colleague Witness',
    color: '#9cc3c4',
    question: 'Does this CV survive the candidate’s own dated record and their colleagues?',
    verdicts: ['FAILED', 'VERIFIED'],
    replaces: 'Employment verification',
    fee: '$50–200 per check, 3–10 days',
    credits: '~20',
    fields: [
      { key: 'person_url', label: 'Candidate profile URL', placeholder: 'https://…', consent: true, required: true },
      { key: 'domain', label: 'Claimed employer domain', placeholder: 'employer.example', required: true },
      { key: 'claim', label: 'Claim from the CV', placeholder: 'Led 40 engineers, 2023 to 2025', long: true, required: true },
    ],
    consentFor: ['person_url'],
    alwaysConsent: true,
    sources: [
      { id: 'enrich', label: 'Crustdata person enrich', note: 'Dated roles at the employer', from: ['person_url'] },
      { id: 'search', label: 'Crustdata person search', note: 'Colleagues with overlapping dates', from: ['person_url', 'domain'] },
      { id: 'company', label: 'Crustdata company enrich', note: 'Headcount in the claimed quarter', from: ['domain'] },
      { id: 'verify', label: 'Crustdata batch verify', note: 'Batch verification disabled on this account', from: ['person_url', 'claim'] },
    ],
  },
  {
    id: 'estate',
    name: 'Estate',
    alias: 'Afterlife',
    color: '#e3b96e',
    question: 'A large firm went bankrupt. Where did its people go, and is anything trading under its name?',
    verdicts: ['REQUEST FOR EXPLANATION', 'KILLED'],
    replaces: 'First forensic pass on an estate',
    fee: 'NOK 150–400k',
    credits: '~30',
    fields: [
      { key: 'domain', label: 'Company domain', placeholder: 'company.example' },
      { key: 'orgnr', label: 'Norwegian organisation number', placeholder: '9 digits' },
    ],
    sources: [
      { id: 'brreg', label: 'Brønnøysund enheter', note: 'Bankruptcy flag and date', from: ['orgnr'] },
      { id: 'roller', label: 'Brønnøysund roller', note: 'Statutory officers', from: ['orgnr'] },
      { id: 'people', label: 'Crustdata person search', note: 'Where former staff went', from: ['domain'] },
      { id: 'wayback', label: 'Destination review', note: 'Check registry dates and board overlap', from: ['domain'] },
    ],
  },
  {
    id: 'company',
    name: 'Company',
    alias: 'Key-Person',
    color: '#c7a3d6',
    question: 'Is leadership or finance moving ahead of the filings?',
    verdicts: ['SIGNED'],
    replaces: 'Kroll-style due-diligence report',
    fee: '$5–25k, 2 weeks',
    credits: '~15',
    fields: [
      { key: 'domain', label: 'Company domain', placeholder: 'company.example' },
      { key: 'cik', label: 'SEC CIK', placeholder: '10 digits' },
      { key: 'claim', label: 'Question to investigate', placeholder: 'Is the finance team turning over?', long: true },
    ],
    sources: [
      { id: 'edgar', label: 'EDGAR 8-K 5.02 · 4.01', note: 'Officer and auditor changes', from: ['cik'] },
      { id: 'company', label: 'Crustdata company enrich', note: 'CXO tenure and finance moves', from: ['domain'] },
      { id: 'watch', label: 'Watcher replay', note: 'When profiles moved vs. filings', from: ['domain', 'cik'] },
      { id: 'gleif', label: 'GLEIF', note: 'Legal entity and parents', from: ['domain'] },
    ],
  },
]

export const DESK_BY_ID = Object.fromEntries(DESKS.map(d => [d.id, d]))

/** The shared adjudication route every desk passes through. */
export const REVIEW_STAGES = [
  ['Identity spine', 'Resolve the subject, or say we cannot'],
  ['Two witnesses', 'Crustdata plus one public record'],
  ['Opposing counsel', 'Try to kill the finding'],
  ['Partner', 'Sign only two-witness findings'],
  ['Ledger', 'Hash the receipt to Rekor'],
]
