// Smoke test #5 — EmptyState + its two pre-baked variants.
//
// EmptyState is the small UI primitive the dashboard falls back to when
// there's nothing to show (no nodes, no cameras, no incidents). It's used
// in many places, has zero external deps (no Clerk, no router, no fetch),
// and demonstrates the pattern for testing simple presentational
// components.
//
// We pin the prop contract (icon / title / message / children) and the
// pre-baked DiscoveringState + NoCamerasState variants so a copy edit
// to either canned message can't drift from this file.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import EmptyState, {
  DiscoveringState,
  NoCamerasState,
} from '../../src/components/EmptyState.jsx'

describe('EmptyState', () => {
  it('renders nothing optional when only children are passed', () => {
    render(
      <EmptyState>
        <button>Take action</button>
      </EmptyState>,
    )
    expect(screen.getByRole('button', { name: /take action/i })).toBeInTheDocument()
  })

  it('renders icon, title, message, and children together', () => {
    render(
      <EmptyState
        icon="🚨"
        title="Nothing here"
        message="Add a thing to see it here."
      >
        <button>Add a thing</button>
      </EmptyState>,
    )
    expect(screen.getByText('🚨')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /nothing here/i })).toBeInTheDocument()
    expect(screen.getByText(/add a thing to see it here/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add a thing/i })).toBeInTheDocument()
  })

  it('omits title when title prop is undefined', () => {
    render(<EmptyState message="Just a message." />)
    expect(screen.queryByRole('heading')).toBeNull()
    expect(screen.getByText(/just a message/i)).toBeInTheDocument()
  })

  it('DiscoveringState shows the no-nodes copy', () => {
    render(<DiscoveringState />)
    expect(
      screen.getByRole('heading', { name: /no camera nodes found/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/go to settings/i)).toBeInTheDocument()
  })

  it('NoCamerasState shows the no-cameras copy', () => {
    render(<NoCamerasState />)
    expect(
      screen.getByRole('heading', { name: /no cameras found/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/connect sourcebox sentry camera nodes/i)).toBeInTheDocument()
  })
})
