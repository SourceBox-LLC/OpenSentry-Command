import { Outlet } from "react-router-dom"
import LandingNav from "./LandingNav.jsx"
import LandingFooter from "./LandingFooter.jsx"

function PublicLayout() {
  return (
    <div className="landing-layout">
      <LandingNav />
      <main>
        <Outlet />
      </main>
      <LandingFooter />
    </div>
  )
}

export default PublicLayout