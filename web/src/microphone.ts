export function microphoneError(error: unknown): string {
  const name = error instanceof Error ? error.name : '';
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError')
    return 'No microphone was found. Connect or enable an input device in Windows Settings → System → Sound → Input, then click Check microphone. If you are using a remote desktop, enable microphone redirection.';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError')
    return 'Microphone access is blocked. Allow it in the browser site settings and Windows Settings → Privacy & security → Microphone, then retry.';
  if (name === 'NotReadableError' || name === 'TrackStartError')
    return 'The microphone could not be opened. Close other apps using it, check your audio device, then retry.';
  if (name === 'OverconstrainedError')
    return 'The selected microphone is unavailable. Choose System default or another microphone, then retry.';
  return error instanceof Error ? error.message : 'Microphone check failed.';
}

export async function checkMicrophone(deviceId: string, media = navigator.mediaDevices) {
  if (!media?.getUserMedia) throw new Error('Microphone access is unavailable here. Open this app in Chrome or Edge on localhost (or HTTPS).');
  const stream = await media.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true });
  try {
    const track = stream.getAudioTracks()[0];
    if (!track) throw new DOMException('No microphone track', 'NotFoundError');
    return { deviceId: track.getSettings().deviceId || deviceId, label: track.label || 'Microphone' };
  } finally {
    stream.getTracks().forEach(track => track.stop());
  }
}
