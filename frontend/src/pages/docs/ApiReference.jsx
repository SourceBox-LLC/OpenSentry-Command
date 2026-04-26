import { useDocs } from "./context"


function ApiReference() {
  const { base, copyToClipboard } = useDocs()

  return (
    <section className="docs-section" id="api-reference">
      <h2>API Reference<a href="#api-reference" className="docs-anchor">#</a></h2>
      <p>
        Command Center exposes a REST API at <code>{base}</code>. Three
        auth schemes cover three audiences — CloudNode uses API key headers, the web
        dashboard uses Clerk JWTs, and the MCP endpoint uses a dedicated bearer token.
      </p>

      <h3>Authentication</h3>
      <div className="docs-plans-table">
        <table>
          <thead>
            <tr><th>Scheme</th><th>Header</th><th>Used by</th></tr>
          </thead>
          <tbody>
            <tr><td>Node API key</td><td><code>X-API-Key: nak_...</code></td><td>CloudNode registering, heartbeating, pushing segments</td></tr>
            <tr><td>Node API key (alt)</td><td><code>X-Node-API-Key: nak_...</code></td><td>Per-camera endpoints (push-segment, playlist, motion, codec)</td></tr>
            <tr><td>Clerk JWT</td><td><code>Authorization: Bearer &lt;jwt&gt;</code></td><td>Web dashboard, authenticated viewers</td></tr>
            <tr><td>MCP key</td><td><code>Authorization: Bearer osc_...</code></td><td>AI clients talking to <code>/mcp</code></td></tr>
          </tbody>
        </table>
      </div>

      <h3>Error format</h3>
      <p>All errors return a JSON body with a stable shape:</p>
      <div className="docs-code-block">
        <code>{`{
  "error": "camera_not_found",
  "message": "No camera with id cam_xyz in this organization",
  "request_id": "req_ab12cd34"
}`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`{
  "error": "camera_not_found",
  "message": "No camera with id cam_xyz in this organization",
  "request_id": "req_ab12cd34"
}`)}>Copy</button>
      </div>
      <p>Standard HTTP status codes apply:</p>
      <ul>
        <li><strong>400</strong> — malformed request body or missing required query param</li>
        <li><strong>401</strong> — missing or invalid auth header</li>
        <li><strong>403</strong> — authenticated but not authorized (wrong org, insufficient role, plan gate)</li>
        <li><strong>404</strong> — resource not found in the caller's org</li>
        <li><strong>429</strong> — rate-limit exceeded. Applies to both REST routes (per-route limits, see <a href="#api-rate-limits">API Rate Limits</a>) and MCP tool calls (per-key budget on Pro/Pro Plus). The response body includes an <code>error: "rate_limit_exceeded"</code> field, the matched <code>limit</code>, and a <code>retry_after_seconds</code> hint; clients should honour the <code>Retry-After</code> header.</li>
        <li><strong>5xx</strong> — server error; <code>request_id</code> in the body is what to include in bug reports</li>
      </ul>

      <h3>Example request</h3>
      <p>Listing cameras from a shell with a signed-in user's JWT:</p>
      <div className="docs-code-block">
        <code>{`curl -H "Authorization: Bearer $CLERK_JWT" \\
     ${base}/api/cameras`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`curl -H "Authorization: Bearer $CLERK_JWT" ${base}/api/cameras`)}>Copy</button>
      </div>

      <h3>Node Endpoints</h3>
      <p>Used by CloudNode. Authenticate with <code>X-API-Key: {"your_api_key"}</code> header.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/register</span></div>
      <p>Register a node and its cameras. Returns camera ID mappings.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/heartbeat</span></div>
      <p>Send periodic heartbeat with camera status updates.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/push-segment</span></div>
      <p>Push a raw HLS <code>.ts</code> segment into the Command Center's in-memory cache. Body is the binary segment, <code>filename</code> is a query param.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/playlist</span></div>
      <p>Push the rolling HLS playlist text. The backend rewrites segment URLs to its own proxy paths and caches the result.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/codec</span></div>
      <p>Report detected video/audio codec information.</p>

      <h3>User Endpoints</h3>
      <p>Used by the web dashboard. Authenticate with Clerk JWT in <code>Authorization: Bearer</code> header.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras</span></div>
      <p>List all cameras in the organization.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/stream.m3u8</span></div>
      <p>Get the cached HLS playlist for browser playback. Segment URLs point at the same-origin segment proxy.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/segment/{"{filename}"}</span></div>
      <p>Serve a single cached HLS segment from memory. JWT-authenticated, same-origin.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/nodes</span></div>
      <p>List all nodes in the organization. Admin only.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes</span></div>
      <p>Create a new node. Returns the API key (shown once).</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/settings</span></div>
      <p>Get recording settings (schedule, continuous mode).</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/audit/stream-logs</span></div>
      <p>Stream access history. Admin only. Filterable by camera and user.</p>

      <h3>Incident Reports</h3>
      <p>
        AI-generated incident reports written by the MCP agent and reviewed by
        admins from the dashboard. All endpoints require admin permission.
      </p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents</span></div>
      <p>List incidents for the org (newest first). Supports <code>status</code>, <code>severity</code>, <code>camera_id</code>, <code>limit</code>, and <code>offset</code> query params.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/counts</span></div>
      <p>Aggregate counts for the stat bar and badges — total, open, open critical, open high.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
      <p>Fetch a single incident with its full markdown report and all evidence metadata.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method patch">PATCH</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
      <p>Acknowledge, resolve, dismiss, or otherwise edit an incident's status, severity, summary, or report.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method delete">DELETE</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
      <p>Permanently delete an incident and all of its evidence (cascades).</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}/evidence/{"{evidence_id}"}</span></div>
      <p>Stream a snapshot or clip blob attached as evidence — used by the dashboard to render thumbnails and play back clips in the incident report modal.</p>

      <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}/evidence/{"{evidence_id}"}/playlist.m3u8</span></div>
      <p>Synthetic single-segment HLS playlist for a clip evidence item, so the dashboard can reuse hls.js to play back captured video with the same JWT auth as the live player.</p>

      <h3>MCP Endpoint</h3>
      <p>Streamable HTTP transport at <code>/mcp</code>. Authenticate with <code>Authorization: Bearer osc_...</code> header.</p>
      <p>See the <a href="#mcp">MCP Integration</a> section for setup and available tools.</p>
    </section>
  )
}

export default ApiReference
