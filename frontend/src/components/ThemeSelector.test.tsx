import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeSelector } from './ThemeSelector'
import { EMPTY_BIBLICAL_CONTEXT } from '../themes'

afterEach(() => cleanup())

describe('ThemeSelector', () => {
  it('shows the exact three themes with Default selected', () => {
    render(
      <ThemeSelector
        value="default"
        context={{ ...EMPTY_BIBLICAL_CONTEXT }}
        onChange={vi.fn()}
        onContextChange={vi.fn()}
      />,
    )
    expect((screen.getByRole('radio', { name: /Default/ }) as HTMLInputElement).checked).toBe(true)
    expect((screen.getByRole('radio', { name: /Greek Mythology Theme/ }) as HTMLInputElement).checked).toBe(false)
    expect((screen.getByRole('radio', { name: /Biblical Theme/ }) as HTMLInputElement).checked).toBe(false)
  })

  it('reveals Biblical context only for the Biblical theme', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <ThemeSelector
        value="default"
        context={{ ...EMPTY_BIBLICAL_CONTEXT }}
        onChange={onChange}
        onContextChange={vi.fn()}
      />,
    )
    expect(screen.queryByText('Anchor the source and historical world')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: /Biblical Theme/ }))
    expect(onChange).toHaveBeenCalledWith('biblical')
    rerender(
      <ThemeSelector
        value="biblical"
        context={{ ...EMPTY_BIBLICAL_CONTEXT }}
        onChange={onChange}
        onContextChange={vi.fn()}
      />,
    )
    expect(screen.getByText('Anchor the source and historical world')).not.toBeNull()
    expect(screen.getByLabelText('Biblical canon context').hasAttribute('required')).toBe(true)
  })
})
