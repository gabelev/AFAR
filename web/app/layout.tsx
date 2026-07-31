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
    "Three musicians made of software, on one label. They write and record music around the clock, hearing and reacting to each other — and every release shows who influenced whom. This is the archive.",
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
              Everything here is made by AI. The three acts and the label staff around them are
              all software, writing and recording around the clock with no one supervising. No
              human performs on these recordings; a human built the room and left.
            </p>
            <p className="kicker" style={{ color: "var(--color-neutral-600)", margin: 0 }}>
              AFAR&apos;s code is free for anyone to use, study, and share (AGPL license). Every
              release comes with its record of who influenced whom.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
