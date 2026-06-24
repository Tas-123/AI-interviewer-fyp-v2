import asyncio
import numpy as np
import logging
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("TestSilero")

class DebugSileroVADAnalyzer(SileroVADAnalyzer):
    def _run_analyzer(self, buffer: bytes):
        self._vad_buffer += buffer
        num_required_bytes = self._vad_frames_num_bytes
        logger.info(f"debug_analyzer: buffer size={len(self._vad_buffer)}")
        
        while len(self._vad_buffer) >= num_required_bytes:
            audio_frames = self._vad_buffer[:num_required_bytes]
            self._vad_buffer = self._vad_buffer[num_required_bytes:]
            
            confidence = self.voice_confidence(audio_frames)
            volume = self._get_smoothed_volume(audio_frames)
            self._prev_volume = volume
            
            # Extract float values for safe formatting
            conf_val = float(confidence[0]) if isinstance(confidence, np.ndarray) else float(confidence)
            vol_val = float(volume)
            
            speaking = conf_val >= self._params.confidence and vol_val >= self._params.min_volume
            logger.info(f"debug_analyzer Window: confidence={conf_val:.4f}, volume={vol_val:.4f}, speaking={speaking} (thresholds: conf={self._params.confidence}, vol={self._params.min_volume})")
            
        return super()._run_analyzer(b"")

async def test_vad():
    analyzer = DebugSileroVADAnalyzer(sample_rate=16000)
    analyzer.set_sample_rate(16000)
    
    # 1. Loud Sine wave (440Hz, amp 15000)
    logger.info("--- Testing Sine Wave ---")
    sample_rate = 16000
    t = np.linspace(0, 0.5, int(sample_rate * 0.5), endpoint=False)
    sine_wave = np.sin(2 * np.pi * 440 * t) * 15000
    audio_bytes = sine_wave.astype(np.int16).tobytes()
    await analyzer.analyze_audio(audio_bytes)
    
    # 2. Quiet Sine wave (amp 100)
    logger.info("--- Testing Quiet Sine Wave ---")
    sine_wave_quiet = np.sin(2 * np.pi * 440 * t) * 100
    audio_bytes_quiet = sine_wave_quiet.astype(np.int16).tobytes()
    await analyzer.analyze_audio(audio_bytes_quiet)

if __name__ == "__main__":
    asyncio.run(test_vad())
