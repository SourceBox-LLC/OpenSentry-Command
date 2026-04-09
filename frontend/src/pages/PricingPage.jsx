import { PricingTable } from "@clerk/clerk-react"

function PricingPage() {
  return (
    <div className="pricing-container">
      <div className="pricing-header">
        <h1 className="page-title">Choose Your Plan</h1>
        <p className="pricing-subtitle">
          Start free with 2 cameras. Upgrade as you grow.
        </p>
      </div>
      <div className="pricing-table-wrapper">
        <PricingTable for="organization" />
      </div>
    </div>
  )
}

export default PricingPage
