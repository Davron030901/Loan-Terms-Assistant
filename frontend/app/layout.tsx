import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://loan-terms-assistant.vercel.app"),
  title: {
    default: "Loan Terms Assistant — answers straight from the contract",
    template: "%s · Loan Terms Assistant",
  },
  description:
    "A scoped AI assistant that answers questions about a real bank loan contract — with a page number — and refuses everything else.",
  keywords: ["loan terms", "RAG", "grounded AI", "bank contract", "AI safety"],
  openGraph: {
    title: "Loan Terms Assistant",
    description:
      "Answers straight from the loan contract. Cited, verified, and refused when it should be.",
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "Loan Terms Assistant" },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafafc" },
    { media: "(prefers-color-scheme: dark)", color: "#08080d" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// Runs before paint so the page never flashes the wrong theme.
const themeScript = `(function(){try{var t=localStorage.getItem('lta-theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${jetbrains.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="mesh-bg min-h-[100dvh] antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
