import "./globals.css";
import "./settings-mobile.css";

import { themeInitScript } from "../lib/theme";

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
      <body>{children}</body>
    </html>
  );
}
