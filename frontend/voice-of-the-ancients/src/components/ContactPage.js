// frontend/src/components/ContactPage.js
import React from 'react';
import { Container, Typography, Box, TextField, Button } from '@mui/material';

function ContactPage() {
  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h2" gutterBottom>
        Contact Us
      </Typography>
      <Typography variant="body1" paragraph>
        We’d love to hear from you! Whether you have questions, feedback, or want to contribute to our language preservation efforts, please reach out.
      </Typography>
      <Box component="form" sx={{ mt: 3 }}>
        <TextField
          label="Name"
          variant="outlined"
          fullWidth
          margin="normal"
        />
        <TextField
          label="Email"
          variant="outlined"
          fullWidth
          margin="normal"
        />
        <TextField
          label="Message"
          variant="outlined"
          fullWidth
          margin="normal"
          multiline
          rows={4}
        />
        <Button
          variant="contained"
          color="primary"
          sx={{ mt: 2 }}
        >
          Send Message
        </Button>
      </Box>
    </Container>
  );
}

export default ContactPage;