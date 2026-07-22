export interface SensorHistoryPoint {
  readonly at: string
  readonly supply: number
  readonly return: number
  readonly flow: number
}

export const SENSOR_HISTORY_SOURCE = 'data/processed/trainable_windows.csv'
export const SENSOR_HISTORY_SUBSTATION_ID = 12
export const SENSOR_HISTORY_INTERVAL_HOURS = 6

export const sensorHistory: readonly SensorHistoryPoint[] = [
  { at: '2015-06-28T18:00:00', supply: 88.2639, return: 53.8750, flow: 193.3333 },
  { at: '2015-06-29T00:00:00', supply: 88.7361, return: 53.0278, flow: 177.6667 },
  { at: '2015-06-29T06:00:00', supply: 87.9306, return: 54.8056, flow: 141.0972 },
  { at: '2015-06-29T12:00:00', supply: 89.4722, return: 50.1806, flow: 244.9306 },
  { at: '2015-06-29T18:00:00', supply: 89.4306, return: 52.9861, flow: 184.0694 },
  { at: '2015-06-30T00:00:00', supply: 89.0000, return: 53.8333, flow: 158.8472 },
  { at: '2015-06-30T06:00:00', supply: 89.0694, return: 54.7917, flow: 142.0139 },
  { at: '2015-06-30T12:00:00', supply: 89.8333, return: 50.3333, flow: 245.4722 },
  { at: '2015-06-30T18:00:00', supply: 89.2639, return: 53.2083, flow: 174.9722 },
  { at: '2015-07-01T00:00:00', supply: 88.5000, return: 54.0000, flow: 160.2500 },
  { at: '2015-07-01T06:00:00', supply: 88.8333, return: 54.9306, flow: 133.1111 },
  { at: '2015-07-01T12:00:00', supply: 89.2639, return: 50.0000, flow: 251.5694 },
]
