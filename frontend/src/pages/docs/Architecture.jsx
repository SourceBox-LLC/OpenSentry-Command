import {
  HlsPipelineDiagram,
  SecurityModelDiagram,
  SystemArchitectureDiagram,
} from "../../components/DocsDiagrams"


function Architecture() {
  return (
    <section className="docs-section" id="architecture">
      <h2>Architecture<a href="#architecture" className="docs-anchor">#</a></h2>
      <p>SourceBox Sentry uses a cloud-first architecture designed for simplicity and security.</p>

      <h3>Data Flow</h3>
      <SystemArchitectureDiagram />

      <h3>How It Works</h3>
      <ol>
        <li><strong>CloudNode</strong> captures video from USB cameras using FFmpeg</li>
        <li>Video is encoded as HLS segments (1-second chunks by default) and pushed directly to the Command Center over authenticated HTTPS</li>
        <li>The <strong>Command Center</strong> caches the most recent segments in RAM and serves them to authorized viewers same-origin</li>
        <li>Viewers watch via HLS through the Command Center backend — no third-party storage in the live video path, no direct connection to your network</li>
      </ol>

      <h3>HLS Segment Pipeline</h3>
      <p>
        Zooming into the streaming path: each camera runs two FFmpeg processes
        in parallel — one producing playable HLS segments, a second probing
        scene changes for motion events. Playback is served same-origin from
        the backend's RAM cache, never through object storage.
      </p>
      <HlsPipelineDiagram />

      <h3>Security Model</h3>
      <p>
        Every request crosses four layers of protection. TLS on the wire, an
        authenticated identity at the edge, hashing or encryption wherever
        data is stored, and tenant isolation all the way down to the database
        query.
      </p>
      <SecurityModelDiagram />
      <ul>
        <li><strong>Outbound Only</strong> — CloudNode pushes to cloud. No inbound ports, no router config.</li>
        <li><strong>Same-origin Streaming</strong> — Live segments are served through the authenticated backend, not a third-party object store.</li>
        <li><strong>API Key Auth</strong> — Node keys stored as SHA-256 hashes. Never stored in plaintext.</li>
        <li><strong>Clerk Organizations</strong> — Multi-tenant auth with admin and member roles.</li>
        <li><strong>HTTPS Everywhere</strong> — All traffic between CloudNode, Command Center, and viewers is encrypted.</li>
        <li><strong>MCP Keys</strong> — Separate API keys for MCP access, also SHA-256 hashed and org-scoped.</li>
      </ul>
    </section>
  )
}

export default Architecture
