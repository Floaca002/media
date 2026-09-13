import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        vault: {
          bg: "#0a0a0c",
          surface: "#16161a",
          card: "#1e1e24",
          border: "#2a2a32",
          accent: "#e50914",
          text: "#f4f4f5",
          muted: "#9a9aa5",
        },
      },
    },
  },
  plugins: [],
};

export default config;
