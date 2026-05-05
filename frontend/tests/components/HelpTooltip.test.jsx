// Smoke tests for HelpTooltip — the reusable "?" icon + popover used
// next to confusing setting labels (recording policy, MCP scope picker,
// motion-email default-OFF rationale).
//
// What we're pinning here:
//
//   - The popover is hidden until the user opens it (avoids
//     accidentally surfacing copy on every render).
//   - Click toggles open AND close — important because hover-only
//     popovers don't work on touch devices.
//   - Escape and click-outside close the popover (both are universal
//     dismissal patterns; both must work or the popover sticks open
//     and obscures the page).
//   - The optional ``docHref`` renders a "Learn more →" link only
//     when present (caller-controlled).
//   - Accessibility: the trigger gets aria-expanded that flips
//     true/false in sync with the popover's visibility.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import HelpTooltip from '../../src/components/HelpTooltip.jsx'

describe('HelpTooltip', () => {
  it('does not render the popover until the user opens it', () => {
    render(<HelpTooltip>helpful info</HelpTooltip>)

    // The trigger is always visible.
    expect(screen.getByRole('button')).toBeInTheDocument()
    // The body copy is gated behind the open state.
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(screen.queryByText('helpful info')).not.toBeInTheDocument()
  })

  it('opens on click and shows the body copy', async () => {
    const user = userEvent.setup()
    render(<HelpTooltip>helpful info</HelpTooltip>)

    await user.click(screen.getByRole('button'))

    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    expect(screen.getByText('helpful info')).toBeInTheDocument()
  })

  it('toggles closed on a second click', async () => {
    const user = userEvent.setup()
    render(<HelpTooltip>helpful info</HelpTooltip>)

    const trigger = screen.getByRole('button')
    await user.click(trigger)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()

    await user.click(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    render(<HelpTooltip>helpful info</HelpTooltip>)

    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('closes on click-outside', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <HelpTooltip>helpful info</HelpTooltip>
        <button type="button">elsewhere</button>
      </div>,
    )

    // Open the tooltip by name so the click-outside button doesn't
    // get matched.
    await user.click(screen.getByRole('button', { name: /help/i }))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()

    // Click a sibling button → tooltip closes.
    await user.click(screen.getByText('elsewhere'))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('renders a "Learn more" link when docHref is provided', async () => {
    const user = userEvent.setup()
    render(
      <HelpTooltip docHref="https://example.test/docs">
        gist
      </HelpTooltip>,
    )

    await user.click(screen.getByRole('button'))

    const link = screen.getByRole('link', { name: /learn more/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://example.test/docs')
  })

  it('omits the "Learn more" link when docHref is not provided', async () => {
    const user = userEvent.setup()
    render(<HelpTooltip>just gist</HelpTooltip>)

    await user.click(screen.getByRole('button'))

    expect(screen.queryByRole('link', { name: /learn more/i })).not.toBeInTheDocument()
  })

  it('uses the provided aria-label on the trigger', () => {
    render(
      <HelpTooltip label="Help: recording policy">explanation</HelpTooltip>,
    )

    expect(
      screen.getByRole('button', { name: 'Help: recording policy' }),
    ).toBeInTheDocument()
  })

  it('flips aria-expanded as the popover opens and closes', async () => {
    const user = userEvent.setup()
    render(<HelpTooltip>info</HelpTooltip>)

    const trigger = screen.getByRole('button')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
})
