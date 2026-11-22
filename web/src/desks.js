/** The four desks: questions, intake fields, witness routes and the fee each one replaces. */

export const DESKS = [
  {
    id: 'payment',
    name: 'Payment',
    alias: 'Ghost Controller',
    color: '#ff8a5c',
    question: 'Is the person asking us to change bank details still at the vendor?',
    verdicts: ['HELD', 'INSUFFICIENT WITNESSES', 'PARTNER REVIEW'],
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
      { id: 'rdap', label: 'Domain registry (RDAP)', note: 'How old is the sending domain', from: ['sender_domain', 'domain'] },
      { id: 'ifsc', label: 'IFSC branch lookup', note: 'Bank, branch and city', from: ['ifsc'] },
    ],
  },
  {
    id: 'candidate',
    name: 'Candidate',
    alias: 'Colleague Witness',
    color: '#9cc3c4',
    question: 'Does this CV survive the candidate’s own dated record and their colleagues?',
    verdicts: ['IDENTITY REVIEW', 'INSUFFICIENT WITNESSES'],
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
    ],
  },
  {
    id: 'estate',
    name: 'Estate',
    alias: 'Afterlife',
    color: '#e3b96e',
    question: 'A large firm went bankrupt. Where did its people go, and is anything trading under its name?',
    verdicts: ['KILLED', 'INSUFFICIENT WITNESSES', 'PARTNER REVIEW'],
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
      { id: 'destination', label: 'Destination review', note: 'Check registry dates and board overlap', from: ['domain'] },
    ],
  },
  {
    id: 'company',
    name: 'Company',
    alias: 'Key-Person',
    color: '#c7a3d6',
    question: 'Is leadership or finance moving ahead of the filings?',
    subject: {
      label: 'Company name or domain',
      placeholder: 'Skan AI or skan.ai',
      error: 'Enter the company name or domain to investigate.',
    },
    verdicts: ['ROLE REPORTED', 'ROLE REVIEW', 'FORECAST FOR REVIEW', 'INSUFFICIENT WITNESSES', 'PARTNER REVIEW'],
    replaces: 'Kroll-style due-diligence report',
    fee: '$5–25k, 2 weeks',
    credits: '~15',
    fields: [
      { key: 'domain', label: 'Company domain', placeholder: 'skan.ai' },
      { key: 'executive_name', label: 'Executive name', placeholder: 'Manish Garg', hint: 'Checks the leadership roster supplied by Crustdata.' },
      { key: 'executive_title', label: 'Claimed executive title', placeholder: 'CPTO' },
      { key: 'lei', label: 'Legal entity identifier', placeholder: '20-character LEI' },
      { key: 'cik', label: 'SEC CIK', placeholder: '10 digits' },
      { key: 'claim', label: 'Question to investigate', placeholder: 'Is the finance team turning over?', long: true },
    ],
    sources: [
      { id: 'edgar', label: 'SEC EDGAR submissions', note: 'Recent filings by form and date', from: ['cik'] },
      { id: 'company', label: 'Crustdata company enrich', note: 'Leadership titles and tenure', from: ['domain', 'executive_name', 'executive_title'] },
      { id: 'jobs', label: 'Crustdata job search', note: 'Most recent dated hiring signal', from: ['domain'] },
      { id: 'gleif', label: 'GLEIF', note: 'Legal entity and parents', from: ['lei'] },
    ],
  },
]

export const DESK_BY_ID = Object.fromEntries(DESKS.map(d => [d.id, d]))

/** Subject wording for a desk; only the Company desk narrows it to a company name or domain. */
export const subjectSpec = desk => ({
  label: 'Subject',
  placeholder: 'The company or person being checked',
  error: 'Enter who or what this live inquiry is about.',
  ...desk?.subject,
})

/** A role without a name cannot be looked up. Returns feedback text, or '' when the intake is fine. */
export const executiveProblem = (inputs = {}) =>
  (inputs.executive_title || '').trim() && !(inputs.executive_name || '').trim()
    ? 'Add the executive’s name, or clear the title. A role is only checked against a named person.'
    : ''

/** The shared adjudication route every desk passes through. */
export const REVIEW_STAGES = [
  ['Identity spine', 'Resolve the subject, or say we cannot'],
  ['Two witnesses', 'Crustdata plus one public record'],
  ['Opposing counsel', 'Try to kill the finding'],
  ['Partner', 'Sign only two-witness findings'],
  ['Ledger', 'Hash the receipt and file the case'],
]
