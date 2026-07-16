import { useEffect, useState, type ChangeEvent } from 'react'
import { Button, StatusBadge, SurfaceCard } from './ui'
import { Icon } from './icons'
import type { ThemePreference } from './useThemePreference'

/**
 * 이용자 개인 설정 페이지 — 로그인한 본인에게만 적용되는 개인화 설정.
 *
 * 프론트 UI 전용: 백엔드 연결·저장 없음. 컨트롤은 로컬 상태로 인터랙티브하며,
 * 화면 모드(다크/라이트)만 기존 테마 시스템(useThemePreference)으로 실제 적용된다.
 * 정상/고장 시나리오 공통(App.tsx에서 모드 분기 없이 렌더).
 */

const tabs = ['내 프로필', '화면 및 알림', '로그인 및 보안'] as const
type Tab = (typeof tabs)[number]

interface ProfileForm {
  readonly name: string
  readonly employeeId: string
  readonly email: string
  readonly phone: string
  readonly department: string
  readonly role: string
}

const defaultProfile: ProfileForm = {
  name: '홍길동',
  employeeId: 'HG-1024',
  email: 'honggildong@heatgrid.kr',
  phone: '010-2345-6789',
  department: '지역난방 운영팀',
  role: '운영자',
}

const roleOptions = ['운영자', '관리자', '관제사', '설비 담당자'] as const
const departmentOptions = ['지역난방 운영팀', '설비관리팀', '관제운영팀', '안전관리팀'] as const

interface DisplayForm {
  readonly language: string
  readonly timezone: string
  readonly tempUnit: string
  readonly pressureUnit: string
  readonly flowUnit: string
  readonly startPage: string
  readonly activitySort: string
  readonly autoRefresh: string
  readonly pageSize: string
  readonly timeFormat: string
  readonly dateFormat: string
  readonly contactMethod: string
}

const defaultDisplay: DisplayForm = {
  language: 'ko',
  timezone: 'seoul',
  tempUnit: 'c',
  pressureUnit: 'bar',
  flowUnit: 'flow',
  startPage: 'dashboard',
  activitySort: 'latest',
  autoRefresh: 'minute',
  pageSize: '10',
  timeFormat: '24h',
  dateFormat: 'ymd-dash',
  contactMethod: 'email',
}

/** 화면 및 알림 탭 전용 개인 환경(토글·선택·방해 금지 시간 등). */
interface ScreenNotif {
  readonly compact: boolean
  readonly animation: boolean
  readonly tooltip: boolean
  readonly fontSize: string
  readonly listView: string
  readonly alertChannel: string
  readonly alertSound: string
  readonly dndStart: string
  readonly dndEnd: string
  readonly dndUrgent: boolean
  readonly renotify: boolean
  readonly preview: string
}

const defaultSN: ScreenNotif = {
  compact: true,
  animation: true,
  tooltip: true,
  fontSize: 'normal',
  listView: 'table',
  alertChannel: 'browser',
  alertSound: 'default',
  dndStart: '22:00',
  dndEnd: '07:00',
  dndUrgent: true,
  renotify: true,
  preview: '10min',
}

/** 로그인 및 보안 탭 — 로그인한 본인 계정의 보안 환경. */
interface SecurityPrefs {
  readonly twoFactor: boolean
  readonly newDeviceAlert: boolean
  readonly retention: string
}

const defaultSecurity: SecurityPrefs = { twoFactor: true, newDeviceAlert: true, retention: '30d' }

/** 현재 로그인 기기 · 최근 로그인 기록 — 더미 데이터(백엔드 없음, 표시 전용). */
const currentDevices = [
  { icon: 'monitor', name: 'Windows Chrome', location: '서울', last: '방금 전', status: '현재 사용 중', tone: 'primary' },
  { icon: 'phone', name: 'iPhone Safari', location: '서울', last: '오늘 07:52', status: '활성', tone: 'success' },
] as const

const loginHistory = [
  { icon: 'monitor', name: 'Windows Chrome', location: '서울', at: '오늘 08:21', ip: '211.234.18.42' },
  { icon: 'phone', name: 'iPhone Safari', location: '서울', at: '오늘 07:52', ip: '211.234.18.42' },
  { icon: 'monitor', name: 'Windows Edge', location: '서울', at: '어제 18:43', ip: '211.234.18.42' },
  { icon: 'monitor', name: 'MacOS Safari', location: '부산', at: '2024.05.06 21:17', ip: '211.234.18.42' },
] as const

interface Props {
  readonly themePreference: ThemePreference
  readonly onThemePreferenceChange: (preference: ThemePreference) => void
}

export function SettingsPage({ themePreference, onThemePreferenceChange }: Props) {
  const [tab, setTab] = useState<Tab>('내 프로필')
  const [profile, setProfile] = useState<ProfileForm>(defaultProfile)
  const [display, setDisplay] = useState<DisplayForm>(defaultDisplay)
  const [sn, setSN] = useState<ScreenNotif>(defaultSN)
  const [sec, setSec] = useState<SecurityPrefs>(defaultSecurity)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(null), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  const save = () => setToast('변경 사항을 저장했습니다.')
  const cancel = () => {
    setProfile(defaultProfile)
    setDisplay(defaultDisplay)
    setSN(defaultSN)
    setSec(defaultSecurity)
    onThemePreferenceChange('system')
    setToast('변경 사항을 취소했습니다.')
  }

  const setProfileField = (key: keyof ProfileForm) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setProfile((current) => ({ ...current, [key]: event.target.value }))
  const setDisplayField = (key: keyof DisplayForm) => (event: ChangeEvent<HTMLSelectElement>) =>
    setDisplay((current) => ({ ...current, [key]: event.target.value }))
  const setSNField = (key: keyof ScreenNotif) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setSN((current) => ({ ...current, [key]: event.target.value }))
  const toggleSN = (key: keyof ScreenNotif) => setSN((current) => ({ ...current, [key]: !current[key] }))
  const toggleSec = (key: 'twoFactor' | 'newDeviceAlert') => setSec((current) => ({ ...current, [key]: !current[key] }))
  const setRetention = (event: ChangeEvent<HTMLSelectElement>) => setSec((current) => ({ ...current, retention: event.target.value }))
  const changePassword = () => setToast('비밀번호 변경 화면으로 이동합니다.')
  const logoutOthers = () => setToast('다른 모든 기기에서 로그아웃했습니다.')
  const downloadActivity = () => setToast('활동 기록을 다운로드합니다.')

  return <div className="page-stack settings-page">
    <div className="settings-tabbar">
      <div className="activity-tabs" role="tablist">
        {tabs.map((item) => (
          <button aria-selected={tab === item} className={tab === item ? 'active' : ''} key={item} onClick={() => setTab(item)} role="tab" type="button">{item}</button>
        ))}
      </div>
    </div>

    {tab === '내 프로필' ? (
      <div className="settings-profile-view">
        <SurfaceCard className="settings-profile-card" title="내 프로필">
          <div className="profile-body">
            <aside className="profile-side">
              <div className="profile-avatar-lg"><Icon name="users" /></div>
              <strong className="profile-name">{profile.name}</strong>
              <StatusBadge tone="primary">{profile.role}</StatusBadge>
              <span className="profile-dept">{profile.department}</span>
              <span className="profile-active"><i />활성 사용자</span>
              <hr className="profile-divider" />
              <ul className="profile-meta">
                <li><Icon name="idcard" /><span className="k">사번</span><span className="v">{profile.employeeId}</span></li>
                <li><Icon name="phone" /><span className="k">연락처</span><span className="v">{profile.phone}</span></li>
                <li><Icon name="mail" /><span className="k">이메일</span><span className="v">{profile.email}</span></li>
              </ul>
            </aside>

            <div className="profile-fields">
              <section>
                <h3>기본 정보</h3>
                <div className="profile-field">
                  <span className="profile-field-label">이름</span>
                  <span className="profile-field-control">
                    <input readOnly value={profile.name} />
                    <Icon className="profile-lock" name="lock" />
                  </span>
                </div>
                <div className="profile-field">
                  <span className="profile-field-label">연락처</span>
                  <span className="profile-field-control">
                    <input onChange={setProfileField('phone')} value={profile.phone} />
                  </span>
                </div>
                <div className="profile-field">
                  <span className="profile-field-label">이메일</span>
                  <span className="profile-field-control">
                    <input readOnly type="email" value={profile.email} />
                    <Icon className="profile-lock" name="lock" />
                  </span>
                </div>
                <div className="profile-field">
                  <span className="profile-field-label">직책</span>
                  <span className="profile-field-control">
                    <select onChange={setProfileField('role')} value={profile.role}>
                      {roleOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </span>
                </div>
                <div className="profile-field">
                  <span className="profile-field-label">소속</span>
                  <span className="profile-field-control">
                    <select onChange={setProfileField('department')} value={profile.department}>
                      {departmentOptions.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  </span>
                </div>
              </section>

              <section>
                <h3>개인 환경</h3>
                <div className="profile-field">
                  <span className="profile-field-label">언어</span>
                  <span className="profile-field-control">
                    <select onChange={setDisplayField('language')} value={display.language}>
                      <option value="ko">한국어</option>
                      <option value="en">English</option>
                    </select>
                  </span>
                </div>
                <div className="profile-field">
                  <span className="profile-field-label">기본 연락 방식</span>
                  <span className="profile-field-control">
                    <select onChange={setDisplayField('contactMethod')} value={display.contactMethod}>
                      <option value="email">이메일</option>
                      <option value="sms">문자</option>
                      <option value="call">전화</option>
                      <option value="messenger">메신저</option>
                    </select>
                  </span>
                </div>
              </section>
            </div>
          </div>

          <footer className="profile-footer">
            <Button onClick={cancel}>취소</Button>
            <Button onClick={save} tone="primary">변경사항 저장</Button>
          </footer>
        </SurfaceCard>
      </div>
    ) : tab === '화면 및 알림' ? (
      <div className="settings-profile-view">
        <SurfaceCard className="settings-sn-card">
          <div className="sn-body">
            <div className="sn-col">
              <section>
                <h3>화면 모드</h3>
                <div className="mode-cards">
                  {([['system', '시스템 설정 따름', 'monitor'], ['light', '라이트 모드', 'sun'], ['dark', '다크 모드', 'moon']] as const).map(([value, label, icon]) => (
                    <label className={`mode-card${themePreference === value ? ' active' : ''}`} key={value}>
                      <Icon name={icon} />
                      <span className="mode-card-foot">
                        <input checked={themePreference === value} name="screen-mode" onChange={() => onThemePreferenceChange(value)} type="radio" />{label}
                      </span>
                    </label>
                  ))}
                </div>
              </section>
              <section>
                <h3>화면 표시 옵션</h3>
                <div className="sn-row">
                  <span>시간 형식</span>
                  <select onChange={setDisplayField('timeFormat')} value={display.timeFormat}>
                    <option value="24h">24시간제</option>
                    <option value="12h">12시간제 (오전/오후)</option>
                  </select>
                </div>
                <div className="sn-row">
                  <span>날짜 형식</span>
                  <select onChange={setDisplayField('dateFormat')} value={display.dateFormat}>
                    <option value="ymd-dash">YYYY-MM-DD</option>
                    <option value="ymd-dot">YYYY.MM.DD</option>
                    <option value="ymd-ko">YYYY년 MM월 DD일</option>
                    <option value="mdy">MM/DD/YYYY</option>
                  </select>
                </div>
                <div className="sn-row">
                  <span>컴팩트 간격 사용</span>
                  <label className="switch"><input checked={sn.compact} onChange={() => toggleSN('compact')} type="checkbox" /><i /></label>
                </div>
                <div className="sn-row">
                  <span>애니메이션 효과</span>
                  <label className="switch"><input checked={sn.animation} onChange={() => toggleSN('animation')} type="checkbox" /><i /></label>
                </div>
                <div className="sn-row">
                  <span>툴팁 표시</span>
                  <label className="switch"><input checked={sn.tooltip} onChange={() => toggleSN('tooltip')} type="checkbox" /><i /></label>
                </div>
                <div className="sn-row">
                  <span>글꼴 크기</span>
                  <select onChange={setSNField('fontSize')} value={sn.fontSize}>
                    <option value="small">작게</option>
                    <option value="normal">보통</option>
                    <option value="large">크게</option>
                  </select>
                </div>
              </section>
            </div>

            <div className="sn-col">
              <section>
                <h3>기본 시작 화면</h3>
                <select className="sn-select-block" onChange={setDisplayField('startPage')} value={display.startPage}>
                  <option value="dashboard">홈</option>
                  <option value="alerts">알림</option>
                  <option value="reports">AI 활동</option>
                </select>
              </section>
              <section>
                <h3>알림 수신 설정</h3>
                <div className="sn-row">
                  <span>알림 채널</span>
                  <select onChange={setSNField('alertChannel')} value={sn.alertChannel}>
                    <option value="browser">브라우저</option>
                    <option value="email">이메일</option>
                    <option value="sms">SMS</option>
                  </select>
                </div>
                <div className="sn-row">
                  <span>알림음</span>
                  <select onChange={setSNField('alertSound')} value={sn.alertSound}>
                    <option value="default">기본음</option>
                    <option value="soft">부드러운 알림음</option>
                    <option value="mute">무음</option>
                  </select>
                </div>
                <div className="sn-row">
                  <span>방해 금지 시간</span>
                  <span className="sn-dnd">
                    <input aria-label="방해 금지 시작" onChange={setSNField('dndStart')} value={sn.dndStart} />
                    <em>–</em>
                    <input aria-label="방해 금지 종료" onChange={setSNField('dndEnd')} value={sn.dndEnd} />
                    <Icon name="clock" />
                  </span>
                </div>
                <div className="sn-row">
                  <span>방해 금지 중 긴급 알림 허용</span>
                  <label className="switch"><input checked={sn.dndUrgent} onChange={() => toggleSN('dndUrgent')} type="checkbox" /><i /></label>
                </div>
                <div className="sn-row">
                  <span>미확인 알림 재알림 주기</span>
                  <label className="switch"><input checked={sn.renotify} onChange={() => toggleSN('renotify')} type="checkbox" /><i /></label>
                </div>
                <div className="sn-row">
                  <span>알림 미리보기 표시</span>
                  <select onChange={setSNField('preview')} value={sn.preview}>
                    <option value="5min">5분</option>
                    <option value="10min">10분</option>
                    <option value="30min">30분</option>
                    <option value="1hour">1시간</option>
                  </select>
                </div>
              </section>
            </div>
          </div>

          <section className="sn-fullwidth">
            <h3>목록 표시 선호</h3>
            <div className="view-cards">
              {([['table', '테이블 보기', '데이터를 테이블 형식으로 표시합니다.', 'list'], ['card', '카드 보기', '데이터를 카드 형식으로 표시합니다.', 'grid']] as const).map(([value, label, desc, icon]) => (
                <label className={`view-card${sn.listView === value ? ' active' : ''}`} key={value}>
                  <span className="view-card-icon"><Icon name={icon} /></span>
                  <span className="view-card-text"><strong>{label}</strong><small>{desc}</small></span>
                  <input checked={sn.listView === value} name="list-view" onChange={() => setSN((current) => ({ ...current, listView: value }))} type="radio" />
                </label>
              ))}
            </div>
          </section>

          <footer className="profile-footer">
            <Button onClick={cancel}>취소</Button>
            <Button onClick={save} tone="primary">변경사항 저장</Button>
          </footer>
        </SurfaceCard>
      </div>
    ) : (
      <div className="settings-profile-view">
        <SurfaceCard className="settings-sec-card" title="로그인 및 보안">
          <div className="sec-body">
            <div className="sec-card">
              <h3>보안 설정</h3>
              <div className="sn-row">
                <span>비밀번호 변경</span>
                <Button onClick={changePassword}>변경</Button>
              </div>
              <div className="sn-row">
                <span>2단계 인증</span>
                <label className="switch"><input checked={sec.twoFactor} onChange={() => toggleSec('twoFactor')} type="checkbox" /><i /></label>
              </div>
              <div className="sn-row">
                <span>새 기기 로그인 알림</span>
                <label className="switch"><input checked={sec.newDeviceAlert} onChange={() => toggleSec('newDeviceAlert')} type="checkbox" /><i /></label>
              </div>
              <div className="sn-row">
                <span>로그인 유지 시간</span>
                <select onChange={setRetention} value={sec.retention}>
                  <option value="7d">7일</option>
                  <option value="30d">30일</option>
                  <option value="90d">90일</option>
                  <option value="forever">무기한</option>
                </select>
              </div>
            </div>

            <section className="sec-section">
              <h3>현재 로그인 기기</h3>
              <table className="sec-table">
                <thead><tr><th>기기명</th><th>위치</th><th>최근 접속</th><th>상태</th></tr></thead>
                <tbody>
                  {currentDevices.map((device) => (
                    <tr key={device.name}>
                      <td><span className="sec-device"><Icon name={device.icon} />{device.name}</span></td>
                      <td>{device.location}</td>
                      <td>{device.last}</td>
                      <td><StatusBadge tone={device.tone}>{device.status}</StatusBadge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="sec-section">
              <h3>최근 로그인 기록</h3>
              <table className="sec-table">
                <thead><tr><th>기기명</th><th>위치</th><th>일시</th><th>IP 주소</th></tr></thead>
                <tbody>
                  {loginHistory.map((entry) => (
                    <tr key={`${entry.name}-${entry.at}`}>
                      <td><span className="sec-device"><Icon name={entry.icon} />{entry.name}</span></td>
                      <td>{entry.location}</td>
                      <td>{entry.at}</td>
                      <td className="sec-ip">{entry.ip}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <div className="sec-alert">
              <div className="sec-alert-info">
                <strong><Icon name="warning" />보안 작업</strong>
                <span>의심스러운 활동이 감지되었거나 계정 보안을 강화하려면 아래 작업을 수행하세요.</span>
              </div>
              <div className="sec-alert-actions">
                <Button onClick={logoutOthers} tone="danger">다른 모든 기기에서 로그아웃</Button>
                <Button icon="download" onClick={downloadActivity} tone="danger">활동 기록 다운로드</Button>
              </div>
            </div>
          </div>

          <footer className="profile-footer">
            <Button onClick={cancel}>취소</Button>
            <Button onClick={save} tone="primary">변경사항 저장</Button>
          </footer>
        </SurfaceCard>
      </div>
    )}

    {toast && <div className="toast-success">{toast}</div>}
  </div>
}
