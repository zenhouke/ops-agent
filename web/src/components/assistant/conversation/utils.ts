import type { Group } from './types'

export function stripAnsi(text: string) {
  return text.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '')
}

export function stripInvisibleMarkers(text: string) {
  return text.replace(/[\u200B-\u200D\u2060\uFEFF]/g, '')
}

export function stripJsonBlocks(text: string) {
  let result = stripInvisibleMarkers(text)

  const markerIndex = result.indexOf('<FINAL_JSON>')
  if (markerIndex >= 0) {
    result = result.slice(0, markerIndex)
  }

  // Only strip fully closed JSON code blocks
  result = result.replace(/```json\s*[\s\S]*?```/gi, '')

  // Clean up excessive whitespace
  result = result
    .replace(/\n{4,}/g, '\n\n\n')
    .replace(/\n{3,}/g, '\n\n')

  return result.trim()
}

export function sortAssistantGroups(groups: Group[]): Group[] {
  // Maintain the original order of events to ensure thinking, commands, and results
  // appear in the sequence they actually occurred.
  return groups
}
