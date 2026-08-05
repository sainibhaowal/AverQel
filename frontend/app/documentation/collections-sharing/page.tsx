import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function CollectionsSharingDocsPage() {
  return (
    <DocsShell
      title="Zero-Knowledge E2EE Collections"
      intro="Collections are AverQel's mathematically isolated sharing and communication boundaries. All texts, files, and updates are encrypted client-side using PBKDF2 key derivation and AES-GCM 256-bit cryptography before leaving the browser. The server has zero readability."
    >
      <DocsCards
        items={[
          {
            title: "Client-Side Cryptography",
            body: "AES-GCM-256 keys are derived in the browser using PBKDF2 with SHA-256. The server stores only ciphertext envelopes.",
          },
          {
            title: "Safety Numbers Verification",
            body: "Unique 40-digit cryptographic fingerprints let peers verify their keys to mathematically guarantee protection from Man-in-the-Middle intercepts.",
          },
          {
            title: "Local-First Storage",
            body: "Plaintext messages are cached locally inside the user's PC using IndexedDB. No decrypted history is sent to the server.",
          },
          {
            title: "Self-Destruct Timers",
            body: "Message expiry configuration allows owners to set purge thresholds (e.g. 1 Day) to wipe data from client caches and server records automatically.",
          },
        ]}
      />

      <DocsSection title="Cryptographic Proofs & Claims">
        <div className="text-slate-350 space-y-4 text-sm leading-relaxed dark:text-slate-300">
          <p>
            AverQel implements a strict **Zero-Knowledge Architecture** for collection chats and
            shared assets. Below are the core claims and proof mechanisms backing our security
            assertions:
          </p>
          <ul className="list-disc space-y-2.5 pl-6">
            <li>
              <strong>Key Isolation Claim:</strong> The host server never holds, sees, or processes
              E2EE symmetric keys or client connection keys.
              <br />
              <span className="font-mono text-[11px] text-emerald-500">
                Proof: Key derivation is performed locally in client scripts using
                window.crypto.subtle.deriveKey. No API endpoint accepts or transmits raw keys.
              </span>
            </li>
            <li>
              <strong>Ciphertext Integrity Claim:</strong> No plain data is stored in the database.
              <br />
              <span className="font-mono text-[11px] text-emerald-500">
                Proof: Inspecting the PostgreSQL database &apos;collection_chat_messages&apos; table
                reveals only JSON envelopes with Base64 &apos;ciphertext&apos; and &apos;iv&apos;
                strings.
              </span>
            </li>
            <li>
              <strong>Zero-Knowledge Media Storage:</strong> Shared files and recorded audio clips
              are encrypted client-side using random 12-byte IVs before being dispatched as binary
              blobs.
              <br />
              <span className="font-mono text-[11px] text-emerald-500">
                Proof: Object keys in MinIO point to encrypted byte sequences that throw header
                mismatch exceptions if opened directly without browser-derived decryption keys.
              </span>
            </li>
          </ul>
        </div>
      </DocsSection>

      <DocsSection title="Maturity Features Integration">
        <div className="text-slate-350 space-y-4 text-sm leading-relaxed dark:text-slate-300">
          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            1. Safety Number Key Verification
          </h4>
          <p>
            To prevent active Man-in-the-Middle (MitM) attacks where an intermediary acts as a fake
            relay, AverQel computes safety numbers. By hashing key derivation inputs with SHA-256,
            both ends format a matching 8-segment verification fingerprint.
          </p>

          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            2. Password-Encrypted Backups
          </h4>
          <p>
            Users can export local IndexedDB caches to keep history safe from cache clearing. The
            exported file runs through password-based PBKDF2 derivation using a random 16-byte salt
            and 100,000 iterations to encrypt the chat logs list with AES-GCM-256.
          </p>

          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            3. Automated Expiry Retention
          </h4>
          <p>
            Message expiry limits (1, 7, or 30 days) automatically delete entries. Server databases
            prune records on fetch, while WebSockets broadcast commands to purge local IndexedDB
            client tables instantly.
          </p>

          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            4. Batch File Staging & Captions
          </h4>
          <p>
            Support for horizontal batch file staging queues allowing users to preview, add, or
            remove items from the transmission list. Users can add WhatsApp-style custom text
            captions to files, which are compiled, E2EE encrypted, and transmitted together.
          </p>

          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            5. Interactive In-App Previews
          </h4>
          <p>
            Direct client-side E2EE decryption previews inside the chat window. Native viewers
            display images and SVGs, play audio files inside custom waveform audio players, and
            render PDFs inside sandboxed frames, eliminating unnecessary downloads.
          </p>

          <h4 className="text-foreground text-xs font-bold tracking-wider uppercase">
            6. Message Deletion & Clear Chat
          </h4>
          <p>
            Senders and channel owners can delete individual messages for everyone in real-time,
            removing records from database records and client IndexedDB stores immediately. Channel
            owners can also clear the entire chat history for everyone.
          </p>
        </div>
      </DocsSection>

      <DocsSection title="System Architecture & CAP Theorem">
        <p className="text-slate-350 text-sm leading-relaxed dark:text-slate-300">
          AverQel is designed as an **AP System (Availability over Consistency)**. To support
          immediate responsiveness, message writes and reads happen instantly in the local IndexedDB
          database, ensuring the user can chat and access history offline. Once a connection is
          established, WebSockets sync changes and update delivery checkmarks optimistically (Sent ➔
          Delivered ➔ Read).
        </p>
      </DocsSection>
    </DocsShell>
  );
}
