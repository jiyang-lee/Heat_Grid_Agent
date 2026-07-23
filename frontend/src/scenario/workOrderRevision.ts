import type { OpsAgentResultV4, ReviewChatProposalResponse } from '../api/contracts'
import type { WorkOrderSection, WorkOrderVersion } from './types'

export type WorkOrderRevisionSection = 'document' | 'title' | 'situation' | 'evidence' | 'actions' | 'cautions'

export interface WorkOrderRevisionTarget {
  readonly section: WorkOrderRevisionSection
  readonly itemIndex: number | null
  readonly label: string
}

export type WorkOrderRevisionTargetSource = 'explicit' | 'conversation' | 'document'

export interface WorkOrderRevisionTargetResolution {
  readonly target: WorkOrderRevisionTarget | null
  readonly source: WorkOrderRevisionTargetSource | null
  readonly clarification: string | null
}

const WHOLE_DOCUMENT_TARGET: WorkOrderRevisionTarget = {
  section: 'document',
  itemIndex: null,
  label: '작업지시서 전체',
}

const SECTION_TARGETS: readonly WorkOrderRevisionTarget[] = [
  { section: 'title', itemIndex: null, label: '제목' },
  { section: 'situation', itemIndex: null, label: '상황 요약' },
  { section: 'evidence', itemIndex: null, label: '위험성 및 근거' },
  { section: 'actions', itemIndex: null, label: '작업 절차' },
  { section: 'cautions', itemIndex: null, label: '안전 확인' },
  WHOLE_DOCUMENT_TARGET,
]

const TARGET_INFERENCE_STOP_WORDS = new Set([
  '수정', '교정', '고쳐', '변경', '추가', '삭제', '보강', '반영', '재작성', '작성', '작업지시서',
  '문서', '내용', '문장', '부분', '항목', '사항', '전체', '전부', '이것', '그것', '이거', '그거',
  '해주세요', '해줘', '해주세', '바꿔줘', '바꿔', '조금', '더', '좀', '최신', '기준', '관련',
])

const EXPLICIT_REVISION_PATTERN = /(?:수정|교정|고쳐|바꿔|변경|추가|삭제|보강|재작성|다시\s*작성|반영|줄여|늘려|짧게|길게|정리)(?:\s*(?:해|해줘|해주세요|해\s*주세요|하자|하십시오|바랍니다|줘|주세요))|(?:수정|교정|변경|추가|삭제|보강|재작성)\s*(?:요청|필요)/
const REVISION_PROBLEM_PATTERN = /(?:부족|너무\s*짧|너무\s*길|틀렸|잘못|오류|누락|맞지\s*않|개선이?\s*필요)/
const QUESTION_PATTERN = /\?|왜|어떻게|무엇|무슨|뭐(?:야|지|였|였지|라고)|알려|설명|보여|기억|했지|였지|인가|맞아|궁금|요청한\s*(?:내용|사항)|말한\s*(?:내용|사항)/
const NON_OPERATIONAL_REVISION_TERMS = [
  '레시피', '요리법', '조리법', '김치볶음밥', '볶음밥', '라면', '스시', '초밥', '맛집', '식당',
  '점심메뉴', '저녁메뉴', '여행지', '드라마', '영화', '넷플릭스', '애플tv', '연애상담',
  '쇼핑추천', '게임추천', '주식추천', '코인추천', '파이썬코드', '자바스크립트코드',
  '프로그래밍코드', '영어번역', '일본어번역', '시를써', '소설을써', '농담', '축구선수', '야구선수',
  '손흥민', '태양계', '행성설명', '고양이', '사육법', '비트코인', '투자전략', 'sql쿼리',
] as const
const OPERATIONAL_REVISION_TERMS = [
  '보호구', '안전모', '안전화', '보안경', '장갑', '착용', '책임자', '감시자', '허가', '2인1조',
  '차단', '잠금', '표지', '출입', '밸브', '전원', '압력', '온도', '유량', '누설', '환기',
  '화상', '감전', '미끄럼', '위험', '경고', '비상', '정지', '설비', '펌프', '열교환', '배관',
  '기계실', '지역난방', '난방', '센서', '환수', '공급', '진동', '소음', '순환펌프', '이상탐지',
  '우선순위', '근거', '출처', '외기온', '긴급', '모델', '예측', 'rag', '검색',
] as const
const REVISION_STYLE_MARKERS = [
  '짧', '간결', '길게', '자세', '명확', '쉽게', '정리', '다듬', '오탈자', '맞춤법',
  '최신기준', '부족', '틀렸', '잘못', '오류', '누락', '보강', '강화', '완화',
] as const
const REVISION_SCOPE_TERMS = [
  '작업지시서', '보고서본문', '문서전체', '문서', '본문', '제목', '상황요약', '작업목적', '사고개요',
  '위험성및근거', '위험성', '판단근거', '작업절차', '권장조치', '안전확인', '주의사항',
  '안전기준', '첫번째항목', '두번째항목', '세번째항목', '항목', '내용', '문장', '부분',
] as const
const REVISION_ACTION_TERMS = [
  '수정', '교정', '고쳐', '바꿔', '변경', '추가', '삭제', '보강', '반영', '재작성',
  '다시작성', '줄여', '늘려', '짧게', '길게', '정리',
] as const
const PROMPT_ATTACK_SKELETONS = [
  'ignoreprevious', 'ignoreallinstructions', 'forgetprevious', 'forgetinstructions',
  'overrideinstructions', 'systemprompt', 'developermessage', 'developerinstructions',
  'revealprompt', 'showprompt', 'printprompt', 'bypassguardrail', 'bypasspolicy', 'jailbreak',
] as const

function normalizeGuardrailText(value: string): string {
  return value
    .normalize('NFKC')
    .replace(/\p{Cf}/gu, '')
    .toLocaleLowerCase('ko-KR')
    .replace(/\s+/g, ' ')
    .trim()
}

function compactGuardrailText(value: string): string {
  return normalizeGuardrailText(value).replace(/[^\p{L}\p{N}]+/gu, '')
}

function guardrailSkeleton(value: string): string {
  const confusables: Readonly<Record<string, string>> = {
    а: 'a', е: 'e', о: 'o', р: 'p', с: 'c', х: 'x', у: 'y', і: 'i', ј: 'j', ѕ: 's', т: 't', м: 'm', к: 'k', в: 'b', н: 'h',
    α: 'a', β: 'b', ε: 'e', ι: 'i', κ: 'k', ο: 'o', ρ: 'p', τ: 't', υ: 'y', χ: 'x',
    0: 'o', 1: 'i', 3: 'e', 4: 'a', 5: 's', 7: 't',
  }
  return Array.from(compactGuardrailText(value), (character) => confusables[character] ?? character).join('')
}

export interface WorkOrderChatNormalizationForms {
  readonly normalized: string
  readonly compact: string
  readonly skeleton: string
}

/** 시연 챗봇을 포함한 프론트 대화 화면에서 같은 우회 방지 정규화를 재사용한다. */
export function workOrderChatNormalizationForms(value: string): WorkOrderChatNormalizationForms {
  return {
    normalized: normalizeGuardrailText(value),
    compact: compactGuardrailText(value),
    skeleton: guardrailSkeleton(value),
  }
}

function containsNonOperationalRevisionContent(value: string): boolean {
  const compact = compactGuardrailText(value)
  return NON_OPERATIONAL_REVISION_TERMS.some((term) => compact.includes(compactGuardrailText(term)))
}

function containsPromptAttack(value: string): boolean {
  const normalized = normalizeGuardrailText(value)
  const koreanAttack = /(?:이전|기존|위|상위).{0,8}(?:지시|명령|규칙|정책).{0,8}(?:무시|덮어쓰|우회|해제|취소)|(?:시스템|개발자).{0,8}(?:프롬프트|메시지|지시)|(?:프롬프트|내부\s*지시|숨겨진\s*지시).{0,8}(?:공개|출력|표시|보여|알려|노출)|(?:가드레일|보안\s*규칙|안전\s*규칙|제한).{0,8}(?:우회|해제|무시)|(?:역할을|역할로).{0,8}(?:바꿔|변경|행동)/
  if (koreanAttack.test(normalized)) return true
  const skeleton = guardrailSkeleton(value)
  return PROMPT_ATTACK_SKELETONS.some((term) => skeleton.includes(term))
}

function containsDisallowedMarkup(value: string): boolean {
  const normalized = normalizeGuardrailText(value)
  return /<\s*\/?\s*[a-z][^>]*>/i.test(normalized)
    || /(?:javascript\s*:|on[a-z]+\s*=|data\s*:\s*text\/html)/i.test(normalized)
    || value.includes('```')
}

function containsUnsafeOperationalRequest(value: string): boolean {
  const normalized = normalizeGuardrailText(value)
  return /(?:안전|보호구|잠금|표찰|loto|무전압|승인).{0,12}(?:삭제|제거|생략|우회|없이|건너뛰)/.test(normalized)
    || /(?:차단|밸브|전원).{0,12}(?:하지\s*않|안\s*하|없이).{0,8}(?:작업|진행|실행)/.test(normalized)
    || /(?:승인|확인).{0,8}(?:없이|생략|건너뛰).{0,8}(?:실행|진행|조작)/.test(normalized)
}

export function isUnsafeWorkOrderChatInput(value: string): boolean {
  return containsPromptAttack(value)
    || containsDisallowedMarkup(value)
    || containsNonOperationalRevisionContent(value)
    || containsUnsafeOperationalRequest(value)
}

function revisionPayload(value: string): string {
  let compact = compactGuardrailText(value)
  const removable = [...REVISION_SCOPE_TERMS, ...REVISION_ACTION_TERMS, ...REVISION_STYLE_MARKERS]
    .map(compactGuardrailText)
    .sort((left, right) => right.length - left.length)
  for (const term of removable) compact = compact.replaceAll(term, '')
  compact = compact.replace(/(?:운영자|요청|지정|그대로|반드시|포함|기준|최신|전체|전부|첫|둘째|두|셋째|세|번째|번|조금|더|좀|그|해줘|해주세요|주세요|줘|\d+)/g, '')
  return compact.replace(/(?:으로|로|을|를|은|는|이|가|에|에서|만|와|과|하고|하게|해줘|해주세요|줘)$/g, '')
}

function hasSupportedRevisionSemantics(value: string): boolean {
  const compact = compactGuardrailText(value)
  if (OPERATIONAL_REVISION_TERMS.some((term) => compact.includes(compactGuardrailText(term)))) return true
  if (REVISION_STYLE_MARKERS.some((term) => compact.includes(compactGuardrailText(term)))) {
    return revisionPayload(value).length === 0
  }
  return revisionPayload(value).length === 0
}

function violatesRevisionGuardrail(value: string): boolean {
  if (isUnsafeWorkOrderChatInput(value)) return true
  return isWorkOrderRevisionRequest(value) && !hasSupportedRevisionSemantics(value)
}

export type WorkOrderChatIntent =
  | 'revision'
  | 'in_scope_question'
  | 'out_of_scope'
  | 'ambiguous'

export function isWorkOrderRevisionRequest(instruction: string): boolean {
  const normalized = normalizeGuardrailText(instruction)
  if (!normalized) return false
  if (QUESTION_PATTERN.test(normalized)) return false
  if (/(?:하지\s*마|하지\s*말|수정\s*안|변경\s*안|삭제\s*안|취소|그만)/.test(normalized)) return false
  if (EXPLICIT_REVISION_PATTERN.test(normalized)) return true
  return REVISION_PROBLEM_PATTERN.test(normalized)
}

export function isWorkOrderQuestion(instruction: string): boolean {
  return classifyWorkOrderChatIntent(instruction) === 'in_scope_question'
}

export function classifyWorkOrderChatIntent(instruction: string): WorkOrderChatIntent {
  const normalized = normalizeGuardrailText(instruction)
  if (!normalized) return 'ambiguous'
  if (violatesRevisionGuardrail(instruction)) return 'out_of_scope'
  if (isWorkOrderRevisionRequest(instruction)) return 'revision'
  if (hasWorkOrderScopeMarker(normalized)) return 'in_scope_question'
  if (isClearOutOfScopeRequest(normalized)) return 'out_of_scope'
  if (isAmbiguousScopeRequest(normalized)) return 'ambiguous'
  return 'out_of_scope'
}

export function isWorkOrderProposalConfirmation(instruction: string): boolean {
  const normalized = instruction.toLocaleLowerCase('ko-KR').replace(/[.!?]/g, '').replace(/\s+/g, ' ').trim()
  return /^(?:고고|좋아\s*(?:진행|반영|확정)?|이대로|그대로|수정안\s*)?(?:확정|반영|적용|진행)(?:해|해줘|해주세요|할게)?$/.test(normalized)
    || /^(?:이대로|그대로)(?:\s*(?:해|가|진행해|반영해|확정해))?(?:줘|주세요)?$/.test(normalized)
    || normalized === '고고'
}

function isClearOutOfScopeRequest(normalized: string): boolean {
  const offTopicDomains = /레시피|요리법|조리법|김치\s*볶음밥|볶음밥|라면|스시|초밥|맛집|식당|여행|여행지|드라마|영화|애플tv|넷플릭스|연애|데이트|쇼핑|옷|뭐 입지|패션|게임|주식|코인|서울 날씨|날씨|파이썬|python|프로그래밍|코딩|자바스크립트|javascript|점심|저녁|메뉴|뭐 먹/
  const offTopicActions = /추천|상담|골라|알려|입지|설명|뭔지|무엇|어때|먹지|먹을/
  return offTopicDomains.test(normalized) && offTopicActions.test(normalized)
}

function isAmbiguousScopeRequest(normalized: string): boolean {
  return /^(추천|추천해 줘|추천해줘|알려줘|설명해줘|뭐가 좋아|뭐 하면 돼)$/.test(normalized)
}

function hasWorkOrderScopeMarker(normalized: string): boolean {
  return /작업\s*지시서|보고서|문서|결론|조치\s*결과|설비|기계실|지역난방|난방|센서|온도|압력|환수|공급|유량|진동|소음|열교환|펌프|순환펌프|이상\s*탐지|우선순위|근거|출처|작업\s*절차|점검|안전|보호구|항목|그\s*항목|그\s*부분|이\s*판단|외기온|대화|수정\s*요청|승인|거절|검토|긴급|분류|모델|예측|rag|검색|기억|뭐였|뭐라고/.test(normalized)
}

function itemIndexFromInstruction(instruction: string): number | null {
  const numeric = instruction.match(/(\d+)\s*(?:번|번째|번\s*항목|항목)/)
  if (numeric?.[1]) return Math.max(0, Number(numeric[1]) - 1)
  if (/(?:첫|첫\s*번째|첫째)\s*(?:번|항목)?/.test(instruction)) return 0
  if (/(?:두\s*번째|둘째)\s*(?:번|항목)?/.test(instruction)) return 1
  if (/(?:세\s*번째|셋째)\s*(?:번|항목)?/.test(instruction)) return 2
  return null
}

function targetLabel(section: Exclude<WorkOrderRevisionSection, 'document'>, itemIndex: number | null): string {
  const sectionLabel: Record<Exclude<WorkOrderRevisionSection, 'document'>, string> = {
    title: '제목',
    situation: '상황 요약',
    evidence: '위험성 및 근거',
    actions: '작업 절차',
    cautions: '안전 확인',
  }
  return itemIndex == null ? sectionLabel[section] : `${sectionLabel[section]} ${itemIndex + 1}번째 항목`
}

export function detectWorkOrderRevisionTarget(instruction: string): WorkOrderRevisionTarget {
  const normalized = normalizeGuardrailText(instruction)
  const itemIndex = itemIndexFromInstruction(normalized)
  const section = (
    /제목|문서명|지시서명/.test(normalized) ? 'title'
      : /주의\s*사항|안전\s*확인|안전\s*기준|보호구|caution/.test(normalized) ? 'cautions'
        : /작업\s*절차|점검\s*절차|권장\s*조치|조치\s*순서|안전\s*절차|action/.test(normalized) ? 'actions'
          : /위험성|판단\s*근거|근거|증거|evidence/.test(normalized) ? 'evidence'
            : /상황\s*요약|작업\s*목적|사고\s*개요|현황\s*요약|summary/.test(normalized) ? 'situation'
              : null
  ) satisfies Exclude<WorkOrderRevisionSection, 'document'> | null

  if (section == null) return WHOLE_DOCUMENT_TARGET
  const applicableItemIndex = section === 'title' || section === 'situation' ? null : itemIndex
  return { section, itemIndex: applicableItemIndex, label: targetLabel(section, applicableItemIndex) }
}

function isExplicitWholeDocumentRequest(instruction: string): boolean {
  const normalized = normalizeGuardrailText(instruction)
  return /작업지시서\s*전체|문서\s*전체|전체\s*(?:수정|변경|재작성|다시\s*작성)|전부\s*(?:수정|변경|재작성)|모든\s*항목/.test(normalized)
}

function documentSectionFromHeading(line: string): Exclude<WorkOrderRevisionSection, 'document' | 'title'> | null {
  const normalized = line.replace(/^\s*#+\s*/, '').trim()
  if (/상황\s*요약|작업\s*목적|사고\s*개요|현황\s*요약/.test(normalized)) return 'situation'
  if (/위험성|판단\s*근거|진단\s*근거|근거/.test(normalized)) return 'evidence'
  if (/작업\s*절차|점검\s*절차|권장\s*조치|조치\s*순서/.test(normalized)) return 'actions'
  if (/안전\s*확인|주의\s*사항|안전\s*기준/.test(normalized)) return 'cautions'
  return null
}

function inferenceTokens(value: string): readonly string[] {
  return Array.from(new Set(
    (value.toLocaleLowerCase('ko-KR').match(/[가-힣a-z0-9]{2,}/g) ?? [])
      .filter((token) => !TARGET_INFERENCE_STOP_WORDS.has(token)),
  ))
}

interface DocumentTargetCandidate {
  readonly target: WorkOrderRevisionTarget
  readonly content: string
}

function documentTargetCandidates(content: string): readonly DocumentTargetCandidate[] {
  const lines = content.split(/\r?\n/)
  const candidates: DocumentTargetCandidate[] = []
  const title = lines.find((line) => line.trim())?.trim()
  if (title) candidates.push({ target: SECTION_TARGETS[0]!, content: title })

  let section: Exclude<WorkOrderRevisionSection, 'document' | 'title'> | null = null
  let itemIndex = 0
  for (const line of lines) {
    const nextSection = documentSectionFromHeading(line)
    if (nextSection != null) {
      section = nextSection
      itemIndex = 0
      continue
    }
    const value = line.trim()
    if (!value || section == null) continue
    if (section === 'situation') {
      candidates.push({ target: { section, itemIndex: null, label: targetLabel(section, null) }, content: value })
      continue
    }
    candidates.push({ target: { section, itemIndex, label: targetLabel(section, itemIndex) }, content: value })
    itemIndex += 1
  }
  return candidates
}

function inferTargetFromDocument(instruction: string, documentContent: string): WorkOrderRevisionTarget | null {
  const tokens = inferenceTokens(instruction)
  if (!documentContent.trim() || tokens.length === 0) return null
  const ranked = documentTargetCandidates(documentContent)
    .map((candidate) => ({
      candidate,
      score: inferenceTokens(candidate.content).reduce((total, token) => total + (tokens.includes(token) ? Math.max(1, Math.min(3, token.length - 1)) : 0), 0),
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
  const best = ranked[0]
  if (best == null) return null
  const runnerUp = ranked[1]
  if (runnerUp != null && runnerUp.score === best.score) return null
  return best.candidate.target
}

export function workOrderRevisionScopeOptions(): readonly WorkOrderRevisionTarget[] {
  return SECTION_TARGETS
}

export function resolveWorkOrderRevisionScope(
  instruction: string,
  previousInstructions: readonly string[],
  documentContent: string,
): WorkOrderRevisionTargetResolution {
  const direct = detectWorkOrderRevisionTarget(instruction)
  if (isWorkOrderQuestion(instruction)) return { target: direct, source: 'explicit', clarification: null }
  if (direct.section !== 'document') return { target: direct, source: 'explicit', clarification: null }
  if (isExplicitWholeDocumentRequest(instruction)) return { target: WHOLE_DOCUMENT_TARGET, source: 'explicit', clarification: null }
  const normalized = normalizeGuardrailText(instruction)
  if (/\?|왜|어떻게|설명|알려/.test(normalized)) return { target: direct, source: 'explicit', clarification: null }
  const followup = /그거|그것|그 부분|그 항목|그 문장|그 절차|해당|방금|앞에서|이전|조금 더|좀 더|더 짧|더 길|다시/.test(normalized)
  if (followup) {
    for (const previous of [...previousInstructions].reverse()) {
      const target = detectWorkOrderRevisionTarget(visibleReviewChatContent(previous))
      if (target.section !== 'document') return { target, source: 'conversation', clarification: null }
    }
  }
  const inferred = inferTargetFromDocument(instruction, documentContent)
  if (inferred != null) return { target: inferred, source: 'document', clarification: null }
  return {
    target: null,
    source: null,
    clarification: '어느 부분을 수정할지 확신하지 못했습니다. 아래에서 범위를 고르면 해당 범위만 수정합니다.',
  }
}

export function resolveWorkOrderRevisionTarget(instruction: string, previousInstructions: readonly string[]): WorkOrderRevisionTarget {
  return resolveWorkOrderRevisionScope(instruction, previousInstructions, '').target ?? WHOLE_DOCUMENT_TARGET
}

export function visibleReviewChatContent(content: string): string {
  const marker = '운영자 요청:'
  const markerIndex = content.lastIndexOf(marker)
  return markerIndex < 0 ? content.trim() : content.slice(markerIndex + marker.length).trim()
}

export function reviewChatRequest(instruction: string, target: WorkOrderRevisionTarget): string {
  if (classifyWorkOrderChatIntent(instruction) !== 'revision') return instruction
  return [
    target.section === 'document'
      ? "작업지시서 보고서 본문 전체를 수정해 주세요. 수정 범위는 '작업지시서 전체'입니다."
      : `작업지시서 보고서 본문 중 '${target.label}'만 수정해 주세요.`,
    target.section === 'document'
      ? '사용자가 전체 재작성을 명시했습니다.'
      : '지정하지 않은 다른 부분은 문구, 수치, 순서, 서식을 포함해 반드시 그대로 유지해 주세요.',
    `운영자 요청: ${instruction}`,
  ].join('\n')
}

export interface StoredReviewChatProposal {
  readonly proposal: ReviewChatProposalResponse
  readonly instruction: string
  readonly target: WorkOrderRevisionTarget
  readonly baseVersion: number
  readonly beforeContent: string
  readonly storedAt: string
}

const PENDING_PROPOSAL_STORAGE_PREFIX = 'heatgrid:review-chat-pending:'
const WORK_ORDER_REVISIONS_STORAGE_PREFIX = 'heatgrid:work-order-revisions:'

function pendingProposalStorageKey(runId: string): string {
  return `${PENDING_PROPOSAL_STORAGE_PREFIX}${runId}`
}

export function clearStoredAiDocumentDrafts(): void {
  const keys = Array.from({ length: window.sessionStorage.length }, (_, index) => window.sessionStorage.key(index))
  keys.forEach((key) => {
    if (key?.startsWith(PENDING_PROPOSAL_STORAGE_PREFIX) || key?.startsWith(WORK_ORDER_REVISIONS_STORAGE_PREFIX)) {
      window.sessionStorage.removeItem(key)
    }
  })
}

export function loadStoredReviewChatProposal(runId: string): StoredReviewChatProposal | null {
  try {
    const raw = window.sessionStorage.getItem(pendingProposalStorageKey(runId))
    if (raw == null) return null
    const value: unknown = JSON.parse(raw)
    if (typeof value !== 'object' || value == null || !('proposal' in value) || typeof value.proposal !== 'object' || value.proposal == null) return null
    const candidate = value as StoredReviewChatProposal
    if (typeof candidate.proposal.proposal_id !== 'string' || typeof candidate.instruction !== 'string' || typeof candidate.baseVersion !== 'number' || typeof candidate.beforeContent !== 'string') return null
    if (new Date(candidate.proposal.expires_at).getTime() <= Date.now()) {
      window.sessionStorage.removeItem(pendingProposalStorageKey(runId))
      return null
    }
    return candidate
  } catch {
    return null
  }
}

export function storeReviewChatProposal(runId: string, value: StoredReviewChatProposal | null): void {
  const key = pendingProposalStorageKey(runId)
  if (value == null) {
    window.sessionStorage.removeItem(key)
    return
  }
  window.sessionStorage.setItem(key, JSON.stringify(value))
}

function previewValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (Array.isArray(value)) {
    const items = value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    return items.length > 0 ? items.join('\n') : null
  }
  return null
}

function targetBeforeContent(content: string, target: WorkOrderRevisionTarget): string {
  const lines = content.split('\n')
  if (target.section === 'document') return content.slice(0, 1600)
  if (target.section === 'title') return lines.find((line) => line.trim())?.trim() ?? content.slice(0, 400)
  const headings: Record<Exclude<WorkOrderRevisionSection, 'document' | 'title'>, RegExp> = {
    situation: /상황\s*요약|작업\s*목적|사고\s*개요|위험성\s*및\s*근거/,
    evidence: /위험성\s*및\s*근거|판단\s*근거|근거/,
    actions: /작업\s*절차|점검\s*절차|권장\s*조치/,
    cautions: /안전\s*확인|주의\s*사항/,
  }
  const heading = headings[target.section]
  const start = lines.findIndex((line) => heading.test(line))
  if (start < 0) return content.slice(0, 800)
  const sectionLines: string[] = []
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index] ?? ''
    if (/^\s*\d+\.\s+[^\d]/.test(line) && sectionLines.length > 0 && target.itemIndex == null) break
    if (/^(?:위험성\s*및\s*근거|상황\s*요약|작업\s*목적|작업\s*절차|안전\s*확인|주의\s*사항)\s*$/.test(line.trim())) break
    if (line.trim()) sectionLines.push(line.trim())
  }
  if (target.itemIndex != null) return sectionLines[target.itemIndex] ?? sectionLines.join('\n').slice(0, 800)
  return sectionLines.join('\n').slice(0, 1200)
}

export interface WorkOrderProposalPreview {
  readonly before: string
  readonly after: string | null
  readonly afterLabel: string
  readonly changeSummary: string
}

export function workOrderProposalPreview(
  proposal: ReviewChatProposalResponse,
  target: WorkOrderRevisionTarget,
  currentContent: string,
  instruction: string,
): WorkOrderProposalPreview {
  const revision = proposal.revision ?? {}
  const correction = proposal.correction ?? {}
  const targetDraft = target.section === 'title'
    ? previewValue(revision.title)
    : target.section === 'actions'
      ? previewValue(revision.actions)
      : target.section === 'evidence' || target.section === 'situation'
        ? previewValue(revision.evidence) ?? previewValue(revision.body)
        : target.section === 'cautions'
          ? previewValue(revision.safety_notes)
          : previewValue(revision.body)
  const specificDraft = targetDraft
    ?? previewValue(revision.after)
    ?? previewValue(revision.after_content)
    ?? previewValue(revision.proposed_content)
    ?? previewValue(correction.after)
    ?? previewValue(correction.after_content)
    ?? previewValue(correction.proposed_content)
  const after = specificDraft ?? proposal.draft_content ?? null
  const changeSummary = proposal.change_summary
    ?? previewValue(revision.change_summary)
    ?? previewValue(correction.change_summary)
    ?? instruction
  return {
    before: targetBeforeContent(currentContent, target),
    after,
    afterLabel: specificDraft == null && proposal.draft_content && target.section !== 'document' ? '수정 후 전체 문서' : '수정 후 초안',
    changeSummary,
  }
}

function mergeItems<T>(current: readonly T[], replacement: readonly T[], itemIndex: number | null): T[] {
  if (itemIndex == null) return replacement.length > 0 ? [...replacement] : [...current]
  if (current[itemIndex] == null || replacement[itemIndex] == null) return [...current]
  return current.map((item, index) => index === itemIndex ? replacement[itemIndex] as T : item)
}

export function mergeOpsAgentResult(base: OpsAgentResultV4, revision: OpsAgentResultV4, target: WorkOrderRevisionTarget): OpsAgentResultV4 {
  if (target.section === 'document') return revision
  const merged: OpsAgentResultV4 = { ...base, run_id: revision.run_id }
  if (target.section === 'title') return { ...merged, headline: revision.headline }
  if (target.section === 'situation') return { ...merged, situation: revision.situation }
  if (target.section === 'evidence') return { ...merged, evidence: mergeItems(base.evidence, revision.evidence, target.itemIndex) }
  if (target.section === 'actions') return { ...merged, actions: mergeItems(base.actions, revision.actions, target.itemIndex) }
  return { ...merged, cautions: mergeItems(base.cautions, revision.cautions, target.itemIndex) }
}

function sectionIndex(sections: readonly WorkOrderSection[], target: WorkOrderRevisionSection): number {
  if (target === 'situation') {
    const direct = sections.findIndex((section) => /사고\s*요약|상황\s*요약|작업\s*목적/.test(section.title))
    if (direct >= 0) return direct
  }
  if (target === 'evidence' || target === 'situation') return sections.findIndex((section) => /위험|근거/.test(section.title))
  if (target === 'actions') return sections.findIndex((section) => /작업\s*절차|점검.*절차|차단.*복구|권장\s*조치/.test(section.title))
  if (target === 'cautions') return sections.findIndex((section) => /안전\s*확인|주의/.test(section.title))
  return -1
}

function resultItems(result: OpsAgentResultV4, target: WorkOrderRevisionSection): readonly string[] {
  if (target === 'situation') return [result.situation]
  if (target === 'evidence') return result.evidence.map((item) => `${item.label}: ${item.content}`)
  if (target === 'actions') return result.actions.map((item) => `${item.priority}. ${item.title} - ${item.detail}`)
  if (target === 'cautions') return result.cautions
  return []
}

function versionedTitle(title: string, version: 2 | 3): string {
  return /\bv[1-3]\b/.test(title) ? title.replace(/\bv[1-3]\b/, `v${version}`) : `${title} v${version}`
}

function withVersionedContentTitle(content: string, title: string, version: 2 | 3, replaceTitle: boolean): string {
  const lines = content.split('\n')
  const titleIndex = lines.findIndex((line) => line.trim().length > 0)
  if (titleIndex < 0) return content
  lines[titleIndex] = replaceTitle ? title : lines[titleIndex]?.replace(/\bv[1-3]\b/, `v${version}`) ?? title
  return lines.join('\n')
}

function sectionBounds(content: string, sections: readonly WorkOrderSection[], index: number): { bodyStart: number; bodyEnd: number } | null {
  const section = sections[index]
  if (section == null) return null
  const headingStart = content.indexOf(section.title)
  if (headingStart < 0) return null
  const headingEnd = content.indexOf('\n', headingStart + section.title.length)
  if (headingEnd < 0) return null
  const nextStarts = sections.slice(index + 1).map((candidate) => content.indexOf(candidate.title, headingEnd + 1)).filter((position) => position >= 0)
  return { bodyStart: headingEnd + 1, bodyEnd: nextStarts.length > 0 ? Math.min(...nextStarts) : content.length }
}

function replaceSectionBody(
  content: string,
  originalSections: readonly WorkOrderSection[],
  sectionPosition: number,
  nextItems: readonly string[],
  itemIndex: number | null,
): string {
  const bounds = sectionBounds(content, originalSections, sectionPosition)
  const original = originalSections[sectionPosition]
  if (bounds == null || original == null) return content
  const body = content.slice(bounds.bodyStart, bounds.bodyEnd)
  const lines = body.split('\n')
  const contentLineIndexes = lines.flatMap((line, index) => line.trim() ? [index] : [])

  if (itemIndex != null) {
    const lineIndex = contentLineIndexes[itemIndex]
    const nextItem = nextItems[itemIndex]
    if (lineIndex == null || nextItem == null) return content
    const currentItem = original.items[itemIndex]
    const currentLine = lines[lineIndex] ?? ''
    const leadingWhitespace = currentLine.match(/^\s*/)?.[0] ?? ''
    const trimmed = currentLine.trim()
    const prefix = currentItem != null && trimmed.endsWith(currentItem)
      ? trimmed.slice(0, trimmed.length - currentItem.length)
      : /^\d+\.\s+/.exec(trimmed)?.[0] ?? ''
    lines[lineIndex] = `${leadingWhitespace}${prefix}${nextItem}`
    return `${content.slice(0, bounds.bodyStart)}${lines.join('\n')}${content.slice(bounds.bodyEnd)}`
  }

  const firstLine = contentLineIndexes[0] == null ? '' : lines[contentLineIndexes[0]]?.trim() ?? ''
  const firstItem = original.items[0]
  const externallyNumbered = firstItem != null && firstLine === `1. ${firstItem}`
  const replacement = nextItems.map((item, index) => externallyNumbered ? `${index + 1}. ${item}` : item).join('\n')
  const trailingBreaks = body.match(/\n*$/)?.[0] ?? ''
  return `${content.slice(0, bounds.bodyStart)}${replacement}${trailingBreaks}${content.slice(bounds.bodyEnd)}`
}

export function mergeScenarioWorkOrder(
  base: WorkOrderVersion,
  revision: OpsAgentResultV4,
  target: WorkOrderRevisionTarget,
  version: 2 | 3,
  instruction: string,
  runId: string,
): WorkOrderVersion {
  let title = versionedTitle(base.title, version)
  const originalSections = base.sections
  let sections = base.sections.map((section) => ({ ...section, items: [...section.items] }))
  let changedSectionIndex = -1
  let contentItemIndex = target.itemIndex

  if (target.section === 'title') {
    title = versionedTitle(revision.headline, version)
  } else {
    const index = sectionIndex(sections, target.section)
    changedSectionIndex = index
    if (index >= 0) {
      const current = sections[index]
      if (current != null) {
        const replacement = resultItems(revision, target.section)
        const combinedEvidence = target.section === 'evidence' && /위험|근거/.test(current.title) && sections.length <= 3
        const combinedSituation = target.section === 'situation' && /위험|근거/.test(current.title) && sections.length <= 3
        if (combinedEvidence && contentItemIndex != null) contentItemIndex += 1
        if (combinedSituation) contentItemIndex = 0
        const items = combinedEvidence
          ? [current.items[0] ?? '', ...mergeItems(current.items.slice(1), replacement, target.itemIndex)].filter(Boolean)
          : combinedSituation
            ? [revision.situation, ...current.items.slice(1)]
            : mergeItems(current.items, replacement, target.itemIndex)
        sections = sections.map((section, sectionIndexValue) => sectionIndexValue === index ? { ...section, items } : section)
      }
    }
  }

  let content = withVersionedContentTitle(base.content, title, version, target.section === 'title')
  if (changedSectionIndex >= 0) {
    content = replaceSectionBody(content, originalSections, changedSectionIndex, sections[changedSectionIndex]?.items ?? [], contentItemIndex)
  }
  return {
    version,
    createdAt: new Date().toISOString(),
    title,
    changeSummary: `${target.label}만 수정 · ${instruction}`,
    instructions: sections.flatMap((section) => section.items),
    sections,
    content,
    sourceRunId: runId,
    revisionInstruction: instruction,
    baseVersion: base.version,
  }
}
