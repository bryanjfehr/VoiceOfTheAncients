// frontend/src/App.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Container from '@mui/material/Container';
import Box from '@mui/material/Box';
import './App.css';

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
  const [translations, setTranslations] = useState([]);
  const [matches, setMatches] = useState([]);
  const [missing, setMissing] = useState([]);
  const [sortOrder, setSortOrder] = useState('asc'); // For sorting matches
  const [tabValue, setTabValue] = useState(0); // For tab selection

  useEffect(() => {
    // Fetch English-to-Ojibwe translations
    axios.get('http://127.0.0.1:8000/api/english-to-ojibwe/')
      .then(response => {
        console.log('English to Ojibwe:', response.data);
        setTranslations(response.data);
      })
      .catch(error => {
        console.error('Error fetching English to Ojibwe translations:', error);
        if (error.response) {
          console.error('Response data:', error.response.data);
          console.error('Response status:', error.response.status);
        }
      });

    // Fetch semantic matches
    axios.get('http://127.0.0.1:8000/api/semantic-matches/')
      .then(response => {
        console.log('Semantic Matches:', response.data);
        setMatches(response.data);
      })
      .catch(error => {
        console.error('Error fetching semantic matches:', error);
        if (error.response) {
          console.error('Response data:', error.response.data);
          console.error('Response status:', error.response.status);
        }
      });

    // Fetch missing common translations
    axios.get('http://127.0.0.1:8000/api/missing-common-translations/')
      .then(response => {
        console.log('Missing Common Translations:', response.data);
        setMissing(response.data);
      })
      .catch(error => {
        console.error('Error fetching missing common translations:', error);
        if (error.response) {
          console.error('Response data:', error.response.data);
          console.error('Response status:', error.response.status);
        }
      });
  }, []);

  const toggleSortOrder = () => {
    setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
  };

  const sortedMatches = [...matches].sort((a, b) => {
    return sortOrder === 'asc' ? a.similarity - b.similarity : b.similarity - a.similarity;
  });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Typography variant="h1" align="center" gutterBottom>
          Voice of the Ancients
        </Typography>

        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          centered
          sx={{ mb: 3 }}
          indicatorColor="primary"
          textColor="primary"
        >
          <Tab label="English to Ojibwe" />
          <Tab label="Semantic Matches" />
          <Tab label="Missing Translations" />
        </Tabs>

        {/* English to Ojibwe Translations */}
        {tabValue === 0 && (
          <Card>
            <CardContent>
              <Typography variant="h2" gutterBottom>
                English to Ojibwe Translations
              </Typography>
              <Box sx={{ maxHeight: '400px', overflowY: 'auto' }}>
                <List>
                  {translations.map((trans, index) => (
                    <ListItem key={index}>
                      <ListItemText
                        primary={`${trans.english_text} ⇒ ${trans.ojibwe_text}`}
                        secondary={trans.definition ? `(${trans.definition})` : ''}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Semantic Matches */}
        {tabValue === 1 && (
          <Card>
            <CardContent>
              <Typography variant="h2" gutterBottom>
                Semantic Matches
              </Typography>
              <Button
                variant="contained"
                color="primary"
                onClick={toggleSortOrder}
                sx={{ mb: 2 }}
              >
                Sort by Similarity ({sortOrder === 'asc' ? 'Ascending' : 'Descending'})
              </Button>
              <Box sx={{ maxHeight: '400px', overflowY: 'auto' }}>
                <List>
                  {sortedMatches.map((match, index) => (
                    <ListItem key={index}>
                      <ListItemText
                        primary={`${match.english_text} ⇒ ${match.ojibwe_text}`}
                        secondary={`Similarity: ${match.similarity.toFixed(2)}`}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Missing Common English Translations */}
        {tabValue === 2 && (
          <Card>
            <CardContent>
              <Typography variant="h2" gutterBottom>
                Missing Common English Translations
              </Typography>
              <Box sx={{ maxHeight: '400px', overflowY: 'auto' }}>
                <List>
                  {missing.map((word, index) => (
                    <ListItem key={index}>
                      <ListItemText primary={word.english_text} />
                    </ListItem>
                  ))}
                </List>
              </Box>
            </CardContent>
          </Card>
        )}
      </Container>
    </ThemeProvider>
  );
}

export default App;
