import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'U.S. vs China AI Race | Strategic Capability Tracker',
  description: 'A strategic intelligence dashboard tracking the U.S.–China AI race across frontier models, compute, talent, adoption, diffusion, and energy dimensions.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  )
}
