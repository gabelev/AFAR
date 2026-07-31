import Link from "next/link";
import { PlayerBar } from "@/components/PlayerBar";

export const metadata = { title: "AFAR.MUSIC — invites" };

/**
 * Placeholder for the create flow: building your own artist is not open
 * yet. One plain sentence, no form, no promises beyond what exists.
 */
export default function InvitePage() {
  return (
    <>
      <div className="sheet" style={{ paddingBottom: 72 }}>
        <div className="crumbbar">
          <span>
            <Link href="/">AFAR.MUSIC</Link> / INVITES
          </span>
        </div>
        <section style={{ padding: "48px var(--gutter)", display: "flex", flexDirection: "column", gap: 14 }}>
          <h1 style={{ fontSize: 34, fontWeight: 700 }}>Creation opens soon.</h1>
          <p style={{ fontSize: 15, maxWidth: 520, textWrap: "pretty" }}>
            Building your own AI artist is invite-only while we finish the doors.
          </p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Meanwhile,{" "}
            <Link href="/world" className="link">
              visit the universe
            </Link>{" "}
            — three artists already live there.
          </p>
        </section>
      </div>
      <PlayerBar quiet="NOTHING PLAYING" right="INVITES" />
    </>
  );
}
