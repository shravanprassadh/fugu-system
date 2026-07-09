import "./globals.css";
import "./settings-mobile.css";
import "./ui-alignment.css";

import { SessionKeeper } from "../components/session-keeper";
import { themeInitScript } from "../lib/theme";
import { SpeedInsights } from "@vercel/speed-insights/next";

export const metadata = {
  title: "Fugu Studio",
  description: "Authenticated workspace for streamed pipeline conversations",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <SessionKeeper />
        {children}
        <SpeedInsights />
      </body>
    </html>
  );
}
