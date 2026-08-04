import { useContext } from 'react'
import { ScenarioContext, type ScenarioContextValue } from './ScenarioContextDefinition'

export function useScenario(): ScenarioContextValue {
  const value = useContext(ScenarioContext)
  if (!value) throw new Error('ScenarioProvider가 필요합니다.')
  return value
}
