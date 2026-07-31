export const APP_NAVIGATION_REQUEST_EVENT = 'sineforge:navigation-request'

export type AppNavigationRequestDetail = {
  proceed: () => void
}

export function requestAppNavigation(proceed: () => void): boolean {
  const event = new CustomEvent<AppNavigationRequestDetail>(
    APP_NAVIGATION_REQUEST_EVENT,
    {
      cancelable: true,
      detail: { proceed },
    },
  )
  const allowed = window.dispatchEvent(event)
  if (allowed) proceed()
  return allowed
}
