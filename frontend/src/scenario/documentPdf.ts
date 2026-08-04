interface DocumentPdfInput {
  readonly title: string
  readonly fileName: string
  readonly metadata: readonly string[]
  readonly content: string
}

const PAGE_WIDTH = 1240
const PAGE_HEIGHT = 1754
const MARGIN = 104
const BODY_WIDTH = PAGE_WIDTH - MARGIN * 2
const BODY_LINE_HEIGHT = 36

export function safeFilePart(value: string): string {
  return value
    .normalize('NFKC')
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80) || 'document'
}

function wrapLine(context: CanvasRenderingContext2D, value: string): readonly string[] {
  if (value.length === 0) return ['']
  const lines: string[] = []
  let current = ''
  for (const character of value) {
    const candidate = current + character
    if (current && context.measureText(candidate).width > BODY_WIDTH) {
      lines.push(current)
      current = character
    } else {
      current = candidate
    }
  }
  if (current) lines.push(current)
  return lines
}

export async function downloadDocumentPdf({ title, fileName, metadata, content }: DocumentPdfInput): Promise<void> {
  await document.fonts.load('400 24px "Noto Sans KR"')
  await document.fonts.load('700 42px "Noto Sans KR"')
  await document.fonts.ready
  const { jsPDF } = await import('jspdf')
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'px', format: [PAGE_WIDTH, PAGE_HEIGHT], compress: true })
  const canvas = document.createElement('canvas')
  canvas.width = PAGE_WIDTH
  canvas.height = PAGE_HEIGHT
  const context = canvas.getContext('2d')
  if (!context) throw new Error('PDF 렌더링을 위한 Canvas를 만들지 못했습니다.')

  let page = 0
  let y = MARGIN
  const resetPage = (continued: boolean) => {
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)
    context.fillStyle = '#111827'
    context.font = '700 42px "Noto Sans KR"'
    context.fillText(continued ? `${title} (계속)` : title, MARGIN, y)
    y += 62
    context.strokeStyle = '#111827'
    context.lineWidth = 3
    context.beginPath()
    context.moveTo(MARGIN, y)
    context.lineTo(PAGE_WIDTH - MARGIN, y)
    context.stroke()
    y += 32
    context.font = '400 20px "Noto Sans KR"'
    context.fillStyle = '#4b5563'
    for (const line of metadata) {
      context.fillText(line, MARGIN, y)
      y += 30
    }
    y += 22
  }
  const flushPage = () => {
    if (page > 0) pdf.addPage([PAGE_WIDTH, PAGE_HEIGHT], 'portrait')
    pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, PAGE_WIDTH, PAGE_HEIGHT, undefined, 'FAST')
    page += 1
  }

  resetPage(false)
  context.font = '400 24px "Noto Sans KR"'
  context.fillStyle = '#1f2937'
  for (const sourceLine of content.replace(/\r\n/g, '\n').split('\n')) {
    const lines = wrapLine(context, sourceLine)
    for (const line of lines) {
      if (y + BODY_LINE_HEIGHT > PAGE_HEIGHT - MARGIN) {
        flushPage()
        y = MARGIN
        resetPage(true)
        context.font = '400 24px "Noto Sans KR"'
        context.fillStyle = '#1f2937'
      }
      context.fillText(line, MARGIN, y)
      y += BODY_LINE_HEIGHT
    }
  }
  flushPage()
  pdf.save(fileName)
}
