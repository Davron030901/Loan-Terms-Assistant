import { DocumentGrid, FaqSection, Footer, HowItWorks, SecurityGates, TrustStrip } from "@/components/landing/Sections";
import { Hero } from "@/components/landing/Hero";
import { Nav } from "@/components/landing/Nav";
import { getDocuments } from "@/lib/api";
import type { DocumentInfo } from "@/lib/types";

// The landing page renders even when the API is asleep; document counts fill in later.
const FALLBACK: DocumentInfo[] = [
  { doc_id: "cibc_personal", bank: "CIBC", title: "CIBC Personal Loan Terms and Conditions", jurisdiction: "Canada", language: "en", pages: 15, chunks: 0, source_url: "", is_default: true },
  { doc_id: "cimb_personal", bank: "CIMB Bank", title: "General Terms and Conditions Governing Personal Loans", jurisdiction: "Singapore / Malaysia", language: "en", pages: 13, chunks: 0, source_url: "", is_default: false },
  { doc_id: "sib_personal", bank: "The South Indian Bank", title: "General Terms and Conditions of the Personal Loan Agreement", jurisdiction: "India", language: "en", pages: 7, chunks: 0, source_url: "", is_default: false },
  { doc_id: "sc_vietnam", bank: "Standard Chartered Bank (Vietnam)", title: "Terms and Conditions Governing Personal Loan", jurisdiction: "Vietnam", language: "en", pages: 10, chunks: 0, source_url: "", is_default: false },
  { doc_id: "nbu_uz_green", bank: "NBU (O'zbekiston Milliy Banki)", title: "Yashil iste'mol krediti kredit shartnomasi", jurisdiction: "Uzbekistan", language: "uz", pages: 5, chunks: 0, source_url: "", is_default: false },
];

export const revalidate = 300;

export default async function LandingPage() {
  let documents = FALLBACK;
  try {
    documents = (await getDocuments(1)).documents;
  } catch {
    /* backend asleep or unreachable — the static list is still accurate */
  }

  return (
    <>
      <Nav />
      <main id="main">
        <Hero />
        <TrustStrip />
        <HowItWorks />
        <SecurityGates />
        <DocumentGrid documents={documents} />
        <FaqSection />
      </main>
      <Footer />
    </>
  );
}
