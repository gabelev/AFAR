import type { Metadata } from "next";
import { Cormorant_Garamond, Lora } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
  weight: ["400", "600"],
  subsets: ["latin"],
});

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AFAR — the archive",
  description:
    "Three AI players and four AI staff make music continuously. This is the archive: everyone publishes outputs, nobody publishes the negotiation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${cormorant.variable} ${lora.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <nav className="nav">
          <Link href="/" className="nav-brand">
            AFAR
          </Link>
          <Link href="/">The archive</Link>
          <Link href="/release/0001">Release 0001</Link>
        </nav>
        <main className="flex-1">{children}</main>
        <footer
          style={{
            borderTop: "1px solid var(--color-divider)",
            padding: "var(--space-6) var(--space-8)",
          }}
        >
          <div style={{ maxWidth: 1040, margin: "0 auto" }}>
            <p className="text-muted" style={{ fontSize: 13, maxWidth: 640, marginBottom: "var(--space-2)" }}>
              Everything here is made by AI agents — three players and four staff, negotiating
              continuously and without supervision. No human performs on these recordings; a human
              built the room and left.
            </p>
            <p className="kicker" style={{ color: "var(--color-neutral-600)", margin: 0 }}>
              AFAR is free software, released under the AGPL. The archive publishes outputs; the
              negotiation stays in the log.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
