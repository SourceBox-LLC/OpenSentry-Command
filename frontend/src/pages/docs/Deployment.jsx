import { useDocs } from "./context"


function Deployment() {
  const { copyToClipboard } = useDocs()

  return (
    <section className="docs-section" id="deployment">
      <h2>Deployment<a href="#deployment" className="docs-anchor">#</a></h2>
      <p>
        Three ways to run CloudNode in production. Pick the one that matches your
        existing ops setup.
      </p>

      <h3>Docker (single camera)</h3>
      <p>The most portable option. Maps one USB camera device into the container:</p>
      <div className="docs-code-block">
        <code>{`docker build -t opensentry-cloudnode .

docker run -d \\
  --name opensentry-cloudnode \\
  --device /dev/video0:/dev/video0 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  -v ./data:/app/data \\
  opensentry-cloudnode`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`docker run -d \\
  --name opensentry-cloudnode \\
  --device /dev/video0:/dev/video0 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  -v ./data:/app/data \\
  opensentry-cloudnode`)}>Copy</button>
      </div>

      <h3>Docker (multiple cameras)</h3>
      <p>Pass each <code>/dev/video*</code> device explicitly:</p>
      <div className="docs-code-block">
        <code>{`docker run -d \\
  --device /dev/video0:/dev/video0 \\
  --device /dev/video2:/dev/video2 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  opensentry-cloudnode`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`docker run -d \\
  --device /dev/video0:/dev/video0 \\
  --device /dev/video2:/dev/video2 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  opensentry-cloudnode`)}>Copy</button>
      </div>

      <h3>Docker Compose</h3>
      <p>For declarative config, use the included <code>docker-compose.yml</code>:</p>
      <div className="docs-code-block">
        <code>{`cp .env.example .env
# Edit .env with your credentials
docker-compose up -d`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`cp .env.example .env
# Edit .env with your credentials
docker-compose up -d`)}>Copy</button>
      </div>

      <h3>Build from source</h3>
      <p>If you prefer native install — Rust 1.70+ and FFmpeg must already be on the box:</p>
      <div className="docs-code-block">
        <code>{`git clone https://github.com/SourceBox-LLC/opensentry-cloud-node.git
cd opensentry-cloud-node
cargo build --release
./target/release/opensentry-cloudnode setup`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`git clone https://github.com/SourceBox-LLC/opensentry-cloud-node.git
cd opensentry-cloud-node
cargo build --release
./target/release/opensentry-cloudnode setup`)}>Copy</button>
      </div>

      <h3>systemd service (Linux)</h3>
      <p>To run CloudNode as a background service on boot, create <code>/etc/systemd/system/opensentry-cloudnode.service</code>:</p>
      <div className="docs-code-block">
        <code>{`[Unit]
Description=SourceBox Sentry CloudNode
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opensentry
WorkingDirectory=/opt/opensentry
ExecStart=/opt/opensentry/opensentry-cloudnode
Restart=on-failure
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`[Unit]
Description=SourceBox Sentry CloudNode
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opensentry
WorkingDirectory=/opt/opensentry
ExecStart=/opt/opensentry/opensentry-cloudnode
Restart=on-failure
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target`)}>Copy</button>
      </div>
      <p>Enable and start:</p>
      <div className="docs-code-block">
        <code>sudo systemctl enable --now opensentry-cloudnode</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard('sudo systemctl enable --now opensentry-cloudnode')}>Copy</button>
      </div>

      <h3>Cross-compilation (Raspberry Pi)</h3>
      <p>CloudNode runs on ARM64 Linux — build on a dev machine, copy the binary:</p>
      <div className="docs-code-block">
        <code>{`rustup target add aarch64-unknown-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu`}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(`rustup target add aarch64-unknown-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu`)}>Copy</button>
      </div>

      <h3>Updating</h3>
      <p>
        Re-run the install script. It downloads the latest release, preserves your
        <code>data/node.db</code>, and restarts the binary. With Docker, pull the new image
        and recreate the container. With systemd, replace the binary and run
        <code>sudo systemctl restart opensentry-cloudnode</code>.
      </p>
    </section>
  )
}

export default Deployment
