"use client";

import { createTheme } from "@mui/material/styles";

// Material Design theme with a colorful palette
// Primary: Indigo, Secondary: Deep Orange for contrast
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1976d2", // Material Blue 700
      light: "#42a5f5",
      dark: "#1565c0",
      contrastText: "#fff",
    },
    secondary: {
      main: "#e65100", // Deep Orange 900 - warm accent
      light: "#ff8a50",
      dark: "#bf360c",
      contrastText: "#fff",
    },
    success: {
      main: "#2e7d32",
    },
    error: {
      main: "#c62828",
      light: "#ffcdd2",
    },
    background: {
      default: "#f5f5f5",
      paper: "#ffffff",
    },
    text: {
      primary: "rgba(0, 0, 0, 0.87)",
      secondary: "rgba(0, 0, 0, 0.6)",
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
    body2: {
      color: "rgba(0, 0, 0, 0.6)",
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          borderRadius: 10,
          padding: "10px 24px",
        },
        contained: {
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
          "&:hover": {
            boxShadow: "0 4px 8px rgba(0,0,0,0.15)",
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        },
      },
    },
  },
});
