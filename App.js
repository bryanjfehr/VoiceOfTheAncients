import React, { useState } from 'react';
import { View, Text, Button, StyleSheet, PermissionsAndroid } from 'react-native';
import AudioRecorderPlayer from 'react-native-audio-recorder-player';
import storage from '@react-native-firebase/storage';

const audioRecorderPlayer = new AudioRecorderPlayer();

const App = () => {
  const [recording, setRecording] = useState(false);
  const [filePath, setFilePath] = useState('');
  const [uploadStatus, setUploadStatus] = useState('');

  // Request microphone permission (Android)
  const requestPermission = async () => {
    try {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
        { title: 'Mic Permission', message: 'App needs to record audio', buttonNeutral: 'Ask Later', buttonNegative: 'Cancel', buttonPositive: 'OK' }
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    } catch (err) {
      console.warn(err);
      return false;
    }
  };

  // Start recording
  const startRecording = async () => {
    const hasPermission = await requestPermission();
    if (!hasPermission) return;

    const path = Platform.select({
      ios: 'recording.m4a',
      android: '/sdcard/recording.mp3',
    });
    await audioRecorderPlayer.startRecorder(path);
    setRecording(true);
    setUploadStatus('Recording...');
  };

  // Stop recording
  const stopRecording = async () => {
    const result = await audioRecorderPlayer.stopRecorder();
    setRecording(false);
    setFilePath(result);
    setUploadStatus('Recording stopped. Ready to upload.');
  };

  // Upload to Firebase
  const uploadAudio = async () => {
    if (!filePath) return;
    const reference = storage().ref(`recordings/${Date.now()}.mp3`);
    await reference.putFile(filePath);
    setUploadStatus('Uploaded successfully!');
    // Here’s where we’d trigger transcription later
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Voice of the Ancients</Text>
      <Text style={styles.subtitle}>Preserve Endangered Languages</Text>
      <Button title={recording ? 'Stop Recording' : 'Start Recording'} onPress={recording ? stopRecording : startRecording} />
      <Button title="Upload Recording" onPress={uploadAudio} disabled={!filePath || recording} />
      <Text style={styles.status}>{uploadStatus}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 10 },
  subtitle: { fontSize: 16, marginBottom: 20 },
  status: { marginTop: 20, fontSize: 16 },
});

export default App;