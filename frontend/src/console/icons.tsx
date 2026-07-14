import type { SVGProps } from 'react'

export type IconName =
  | 'activity'
  | 'alert'
  | 'arrow'
  | 'bell'
  | 'building'
  | 'calendar'
  | 'check'
  | 'chevron'
  | 'clock'
  | 'document'
  | 'download'
  | 'droplet'
  | 'expand'
  | 'flow'
  | 'gauge'
  | 'home'
  | 'info'
  | 'map'
  | 'menu'
  | 'more'
  | 'refresh'
  | 'search'
  | 'settings'
  | 'shield'
  | 'thermometer'
  | 'users'
  | 'warning'
  | 'wrench'
  | 'x'

interface IconProps extends SVGProps<SVGSVGElement> {
  readonly name: IconName
}

const paths: Record<IconName, string> = {
  activity: 'M3 12h3l2-7 4 14 2-7h7',
  alert: 'M12 3 3.5 19h17L12 3Zm0 5v4m0 3h.01',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  bell: 'M18 16v-5a6 6 0 1 0-12 0v5l-1.8 3h15.6L18 16Zm-8 3a2 2 0 0 0 4 0',
  building: 'M4 21h16M6 21V5l6-3 6 3v16M9 8h1m4 0h1M9 12h1m4 0h1M9 16h1m4 0h1',
  calendar: 'M7 3v3m10-3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
  check: 'm5 12 4 4L19 6',
  chevron: 'm9 18 6-6-6-6',
  clock: 'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  document: 'M6 2h8l4 4v16H6V2Zm8 0v5h5M9 12h6m-6 4h6',
  download: 'M12 3v11m0 0 4-4m-4 4-4-4M5 20h14',
  droplet: 'M12 3s6 6.2 6 10.4a6 6 0 1 1-12 0C6 9.2 12 3 12 3Z',
  expand: 'M9 4H4v5m11-5h5v5M9 20H4v-5m11 5h5v-5',
  flow: 'M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0',
  gauge: 'm12 14 4-4M5.5 18.5a9 9 0 1 1 13 0',
  home: 'm3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V10Z',
  info: 'M12 8h.01M12 12v4m9-4a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  map: 'm3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15',
  menu: 'M4 6h16M4 12h16M4 18h16',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  refresh: 'M21 12a9 9 0 1 1-2.9-6.6M21 3v6h-6',
  search: 'm21 21-4.5-4.5m2.5-5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z',
  settings: 'M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Zm0-13v3m0 13v3m9.5-11h-3m-13 0h-3m16.7-5.2-2.1 2.1M7.4 16.6l-2.1 2.1m0-13.4 2.1 2.1m9.4 9.4 2.1 2.1',
  shield: 'M12 3 20 6v5c0 5.1-3.4 8.7-8 10-4.6-1.3-8-4.9-8-10V6l8-3Zm-3 9 2 2 4-4',
  thermometer: 'M10 13.6V4.5a2 2 0 1 1 4 0v9.1a4.5 4.5 0 1 1-4 0Z',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m16-8a3 3 0 1 0-2.8-4M22 21v-2a4 4 0 0 0-3-3.9M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  warning: 'M12 8v4m0 4h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
  wrench: 'M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.4 2.4-3-1 1-3 2.4-2.4Z',
  x: 'm6 6 12 12M18 6 6 18',
}

export function Icon({ name, ...props }: IconProps) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" {...props}>
      <path d={paths[name]} />
    </svg>
  )
}
