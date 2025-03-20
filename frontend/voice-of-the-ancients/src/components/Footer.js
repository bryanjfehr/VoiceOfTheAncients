// frontend/src/components/Footer.js
import React from 'react';
import { Box, Typography } from '@mui/material';

function Footer() {
  return (
    <Box sx={{ bgcolor: 'primary.main', color: 'white', py: 2, textAlign: 'center', mt: 'auto' }}>
      <Typography variant="body2">
        © {new Date().getFullYear()} Voice of the Ancients. All rights reserved.
      </Typography>
    </Box>
  );
}

export default Footer;
