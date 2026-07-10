export function createVisualizerView(refs) {
    const bars = refs.visualizerBars || [];

    function reset() {
        bars.forEach((bar) => {
            bar.style.height = "12px";
        });
    }

    function updateFromRms(rms, maxVolume = 0.25) {
        const percentage = Math.min(100, Math.max(12, (rms / maxVolume) * 100));
        bars.forEach((bar, idx) => {
            const noise = (Math.sin(Date.now() * 0.05 + idx) + 1) * 5;
            bar.style.height = `${percentage + noise}%`;
        });
    }

    return { reset, updateFromRms };
}
