// frontend/src/components/HomePage.js
import React from 'react';
import { Container, Typography, Box, Button } from '@mui/material';
import { Link } from 'react-router-dom'; // Ensure this import is present

function HomePage() {
  return (
    <Container maxWidth="md" sx={{ py: 4, textAlign: 'center' }}>
      <Typography variant="h2" gutterBottom>
        Welcome to Voice of the Ancients
      </Typography>
      <Typography variant="body1" paragraph>
        We are dedicated to preserving endangered Indigenous languages, starting with Ojibwe. Explore our research, contribute to our efforts, and help keep these languages alive for future generations.
      </Typography>
      <Button
        variant="contained"
        color="primary"
        component={Link}
        to="/research"
        sx={{ mt: 2 }}
      >
        Explore Research
      </Button>
    </Container>
  );
}

export default HomePage;