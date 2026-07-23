export const FINAL_TEST_PRESENTATION_STORAGE_KEY = 'heatgrid:final-test-presentation'
export const FINAL_TEST_CHAT_STORAGE_KEY = 'heatgrid:final-test-chat'

export function clearFinalTestSession(): void {
  try {
    window.sessionStorage.removeItem(FINAL_TEST_PRESENTATION_STORAGE_KEY)
    window.sessionStorage.removeItem(FINAL_TEST_CHAT_STORAGE_KEY)
  } catch {
    // sessionStorage is optional in restricted browser contexts.
  }
}
