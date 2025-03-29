// frontend/src/components/Research.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Box from '@mui/material/Box';

// Configure the base URL for API requests
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000';

// Set up axios with the base URL
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000, // 5 seconds timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

function Research() {
  const [translations, setTranslations] = useState([]);
  const [matches, setMatches] = useState([]);
  const [missing, setMissing] = useState([]);
  const [sortOrder, setSortOrder] = useState('asc'); // For sorting matches
  const [tabValue, setTabValue] = useState(0); // For tab selection
  const [missingPage, setMissingPage] = useState(0); // For missing translations pagination
  const wordsPerPage = 1000;

  useEffect(() => {
    // Fetch English-to-Ojibwe translations
    api.get('/api/english-to-ojibwe/')
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
    api.get('/api/semantic-matches/')
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
    api.get('/api/missing-common-translations/')
      .then(response => {
        console.log('Missing Common Translations:', response.data);
        // Sort by frequency (descending) upon receiving the data
        const sortedMissing = [...response.data].sort((a, b) => b.frequency - a.frequency);
        setMissing(sortedMissing);
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

  // Parse definition to extract part of speech and definition text
  const parseDefinition = (definition) => {
    if (!definition) return { type: '', def: '' };
    const match = definition.match(/^([a-z]+)\s+(.+)/i);
    if (match) {
      return { type: match[1], def: match[2] };
    }
    return { type: '', def: definition };
  };

  // Calculate current page of missing translations
  const currentMissing = missing.slice(
    missingPage * wordsPerPage,
    (missingPage + 1) * wordsPerPage
  );

  return (
    <Box sx={{ py: 4 }}>
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
                {translations.map((trans, index) => {
                  const { type, def } = parseDefinition(trans.definition);
                  return (
                    <ListItem key={index}>
                      <ListItemText
                        primary={
                          <>
                            {trans.english_text} ⇒ {trans.ojibwe_text}
                            {type && <Typography component="span" variant="body2" sx={{ ml: 1, color: 'text.secondary' }}>({type})</Typography>}
                          </>
                        }
                        secondary={def ? <Typography component="span" sx={{ fontStyle: 'italic' }}>{def}</Typography> : null}
                      />
                    </ListItem>
                  );
                })}
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
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ border: '1px solid #ddd', padding: '8px' }}>Match 1</th>
                    <th style={{ border: '1px solid #ddd', padding: '8px' }}>Match 2</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedMatches.reduce((rows, match, index) => {
                    if (index % 2 === 0) {
                      rows.push([match]);
                    } else {
                      rows[rows.length - 1].push(match);
                    }
                    return rows;
                  }, []).map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((match) => (
                        <td key={match.index} style={{ border: '1px solid #ddd', padding: '8px', verticalAlign: 'top' }}>
                          <table style={{ width: '100%' }}>
                            <tbody>
                              <tr>
                                <td style={{ textAlign: 'center', padding: '4px' }}>
                                  <Typography variant="body2">
                                    Similarity: {match.similarity.toFixed(2)}
                                  </Typography>
                                </td>
                              </tr>
                              <tr>
                                <td style={{ padding: '4px', borderTop: '1px solid #eee' }}>
                                  <Typography variant="body2">
                                    {match.ojibwe_text}
                                  </Typography>
                                  <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
                                    {match.ojibwe_definition}
                                  </Typography>
                                </td>
                                <td style={{ padding: '4px', borderTop: '1px solid #eee' }}>
                                  <Typography variant="body2">
                                    {match.english_text}
                                  </Typography>
                                  <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
                                    {match.english_definition}
                                  </Typography>
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </td>
                      ))}
                      {row.length === 1 && <td style={{ border: '1px solid #ddd' }}></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
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
                {currentMissing.map((word, index) => (
                  <ListItem key={index}>
                    <ListItemText
                      primary={word.english_text}
                      secondary={
                        <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
                          Usage Frequency: {word.frequency.toFixed(2)}
                        </Typography>
                      }
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Button
                variant="contained"
                color="primary"
                disabled={missingPage === 0}
                onClick={() => setMissingPage(missingPage - 1)}
                sx={{ mr: 1 }}
              >
                Previous
              </Button>
              <Typography variant="body1" sx={{ mx: 2, alignSelf: 'center' }}>
                Page {missingPage + 1} of {Math.ceil(missing.length / wordsPerPage)}
              </Typography>
              <Button
                variant="contained"
                color="primary"
                disabled={(missingPage + 1) * wordsPerPage >= missing.length}
                onClick={() => setMissingPage(missingPage + 1)}
              >
                Next
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export default Research;
