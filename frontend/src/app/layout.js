import "./globals.css";

<<<<<<< Updated upstream
export const metadata = {
  title: "Fugu Kernel Studio",
  description: "Deterministic multi-provider pipeline workspace",
=======
import { themeInitScript } from "../lib/theme";

export const metadata = {
  title: "Fugu Studio",
  description: "Authenticated workspace for streamed pipeline conversations",
>>>>>>> Stashed changes
};

export default function RootLayout({ children }) {
  return (
<<<<<<< Updated upstream
    <html lang="en">
=======
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
>>>>>>> Stashed changes
      <body>{children}</body>
    </html>
  );
}
