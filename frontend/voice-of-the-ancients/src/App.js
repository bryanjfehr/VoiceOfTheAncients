// frontend/src/App.js
import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box'; // Add this import
import Header from './components/Header';
import Footer from './components/Footer';
import HomePage from './components/HomePage';
import Research from './components/Research';
import ContactPage from './components/ContactPage';

// Create a modern, professional theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2', // Deep blue
    },
    secondary: {
      main: '#f50057', // Vibrant pink
    },
    background: {
      default: '#f5f5f5', // Light gray background
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 700,
      color: '#333',
    },
    h2: {
      fontSize: '1.5rem',
      fontWeight: 500,
      color: '#555',
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
          borderRadius: '8px',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '20px',
          textTransform: 'none',
          padding: '8px 16px',
        },
      },
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Header />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/research" element={<Research />} />
            <Route path="/contact" element={<ContactPage />} />
          </Routes>
          <Footer />
        </Box>
      </Router>
    </ThemeProvider>
  );
}

export default App;