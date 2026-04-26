import { Link } from "react-router-dom"


function CameraGroups() {
  return (
    <section className="docs-section" id="camera-groups">
      <h2>Camera Groups<a href="#camera-groups" className="docs-anchor">#</a></h2>
      <p>
        Camera groups are user-defined zones — "Front yard", "Workshop", "Main floor" —
        that bundle cameras together for filtering, display, and MCP agent navigation.
      </p>

      <h3>Creating a group</h3>
      <ol>
        <li>Open <Link to="/settings">Settings</Link> &gt; Camera Groups</li>
        <li>Click <strong>New Group</strong>, give it a name and a color</li>
        <li>Drag cameras into the group, or assign a group from the camera's settings drawer</li>
      </ol>

      <h3>What groups do for you</h3>
      <ul>
        <li><strong>Live view layout</strong> — The dashboard tile grid is grouped by camera group, so related cameras stay adjacent.</li>
        <li><strong>Color tagging</strong> — Each group has a color. Tiles and tile borders reflect it so you can read a 20-camera grid at a glance.</li>
        <li><strong>Filter and search</strong> — Filter the live view or access logs by group name.</li>
        <li><strong>MCP navigation</strong> — Agents call <code>list_camera_groups</code> to resolve a natural-language location ("check the workshop") to a set of <code>camera_id</code>s.</li>
      </ul>

      <h3>Tips</h3>
      <ul>
        <li>Name groups by <em>place</em>, not purpose. "Driveway" stays meaningful as cameras come and go; "Vehicle monitoring" doesn't.</li>
        <li>Use a color system your team recognizes — e.g. red for perimeter, blue for interior, green for delivery zones.</li>
        <li>A camera can only be in one group. If you need multi-group overlap, duplicate the camera tile in a saved view instead (planned feature).</li>
      </ul>
    </section>
  )
}

export default CameraGroups
