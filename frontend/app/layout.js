import './globals.css'

export const metadata = {
  title: 'Sovereign Workspace',
  description: 'High-Fidelity Autonomous Chat Matrix',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
