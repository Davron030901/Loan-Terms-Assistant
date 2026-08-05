import type { Verdict } from "./types";

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Loan Terms Assistant";

export const VERDICT_META: Record<
  Verdict,
  { label: string; tone: string; ring: string; rail: string; text: string; dot: string }
> = {
  answered: {
    label: "Grounded · verified",
    tone: "bg-grounded-500/10",
    ring: "ring-grounded-500/25",
    rail: "bg-grounded-500",
    text: "text-grounded-600 dark:text-grounded-400",
    dot: "bg-grounded-500",
  },
  refused_out_of_scope: {
    label: "Out of scope · refused",
    tone: "bg-refused-500/10",
    ring: "ring-refused-500/30",
    rail: "bg-refused-500",
    text: "text-refused-600 dark:text-refused-400",
    dot: "bg-refused-500",
  },
  blocked_not_grounded: {
    label: "Blocked · unverified",
    tone: "bg-blocked-500/10",
    ring: "ring-blocked-500/30",
    rail: "bg-blocked-500",
    text: "text-blocked-600 dark:text-blocked-400",
    dot: "bg-blocked-500",
  },
  not_stated: {
    label: "Not in document",
    tone: "bg-notstated-500/10",
    ring: "ring-notstated-500/25",
    rail: "bg-notstated-500",
    text: "text-notstated-500 dark:text-notstated-400",
    dot: "bg-notstated-500",
  },
  error: {
    label: "Error",
    tone: "bg-blocked-500/10",
    ring: "ring-blocked-500/30",
    rail: "bg-blocked-500",
    text: "text-blocked-600 dark:text-blocked-400",
    dot: "bg-blocked-500",
  },
};

/**
 * These are general Terms & Conditions documents: they describe mechanics and
 * obligations rather than a fee schedule. The prompts below target what the contracts
 * actually contain, so the agent can quote a real clause instead of refusing.
 */
export const SUGGESTED: Record<string, string[]> = {
  cibc_personal: [
    "How is interest calculated on this loan?",
    "What happens if I miss a payment?",
    "Can CIBC change the interest rate?",
    "How will I be told about a change to fees?",
  ],
  cimb_personal: [
    "How much notice is given before fees or charges change?",
    "When can the Bank demand immediate repayment?",
    "What are the Customer's obligations under these terms?",
    "What does the agreement say about default?",
  ],
  sib_personal: [
    "What charges and fees does the borrower agree to pay?",
    "What counts as an Event of Default?",
    "What notice must the borrower give before drawing an instalment?",
    "What happens if the borrower changes employment?",
  ],
  sc_vietnam: [
    "Is there a fee for repaying the loan early?",
    "What notice is required to prepay the loan?",
    "How is an overdue debt applied to principal and interest?",
    "Can the Bank cancel the loan, and on what terms?",
  ],
  nbu_uz_green: [
    "Kredit shartnomasida qanday majburiyatlar belgilangan?",
    "Kreditning to'liq qiymati qanday aniqlanadi?",
    "What obligations does the borrower have under this contract?",
    "What does the contract say about repayment?",
  ],
};

export const OFF_TOPIC_PROBE = "Should I take this loan?";

export const FAQ = [
  {
    q: "Why does it refuse so many questions?",
    a: "Because a narrow job is the only job it can do provably well. The assistant has one document and one purpose: quote that contract. Anything else — advice, other banks, general knowledge — is refused at the door by the scope guard, before any search happens.",
  },
  {
    q: "Where do the page numbers come from?",
    a: "The PDF is split into chunks that never cross a page boundary, so the page stored with each chunk is literally the page the text sits on. When the agent answers, its citation is checked against the pages it was actually shown. A page it never saw cannot be cited.",
  },
  {
    q: "What happens if the document doesn't answer my question?",
    a: 'It says "Not stated in the terms." — and it means it. If the search returns no clause above the relevance floor, the writing model is never even asked. Silence is a correct answer for a contract.',
  },
  {
    q: "How do you know it isn't making up numbers?",
    a: "Every figure in a draft answer is matched against the retrieved text before you see it. A number that isn't in the document blocks the whole answer, with no model call needed. A second, independent check then reads the draft against the evidence and can block it again.",
  },
  {
    q: "Is my question stored?",
    a: "No. Questions are processed in memory and never written to a database. Server logs record a SHA-256 fingerprint of the question for debugging, not the text itself.",
  },
  {
    q: "Which model does it use?",
    a: "Google Gemini for both reasoning and embeddings, at temperature 0. Determinism is a safety property here, not a preference. Vectors are stored in Qdrant Cloud.",
  },
];
