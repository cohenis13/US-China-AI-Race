import { NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { join } from 'path'

export const dynamic = 'force-static'

const ALLOWED_FILES = new Set([
  'frontier_models.json',
  'frontier_models_manual.json',
  'talent.json',
  'compute.json',
  'adoption.json',
  'diffusion.json',
  'energy.json',
  'investment.json',
  'executive_summary.json',
  'history.json',
  'labs.json',
])

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ file: string }> }
) {
  const { file } = await params
  if (!ALLOWED_FILES.has(file)) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }
  try {
    const filePath = join(process.cwd(), 'data', file)
    const content = await readFile(filePath, 'utf-8')
    return new NextResponse(content, {
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    })
  } catch {
    return NextResponse.json({ error: 'File not found' }, { status: 404 })
  }
}
