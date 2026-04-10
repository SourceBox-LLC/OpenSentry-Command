import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getPlanInfo } from "../services/api"

const PlanInfoContext = createContext(null)

const REFRESH_INTERVAL = 60000 // 60 seconds

export function PlanInfoProvider({ children }) {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const [planInfo, setPlanInfo] = useState(null)
  const [loading, setLoading] = useState(false)
  const lastOrgRef = useRef(null)

  const loadPlanInfo = useCallback(async () => {
    if (!organization) return
    try {
      setLoading(true)
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanInfo(data)
    } catch (err) {
      console.error("[PlanInfo] Failed to load:", err)
    } finally {
      setLoading(false)
    }
  }, [organization, getToken])

  // Load on mount and when org changes
  useEffect(() => {
    if (!organization) {
      setPlanInfo(null)
      return
    }
    // Reset if org changed
    if (lastOrgRef.current !== organization.id) {
      lastOrgRef.current = organization.id
      setPlanInfo(null)
    }
    loadPlanInfo()
    const interval = setInterval(loadPlanInfo, REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [organization, loadPlanInfo])

  return (
    <PlanInfoContext.Provider value={{ planInfo, loading, refreshPlanInfo: loadPlanInfo }}>
      {children}
    </PlanInfoContext.Provider>
  )
}

export function usePlanInfo() {
  const context = useContext(PlanInfoContext)
  if (!context) {
    throw new Error("usePlanInfo must be used within PlanInfoProvider")
  }
  return context
}
