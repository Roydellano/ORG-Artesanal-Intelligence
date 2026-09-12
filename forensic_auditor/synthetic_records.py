"""Records-only boundary to the isolated local synthetic data generator."""
from pathlib import Path
import subprocess
import sys


def records(seed, scenario, clean):
    if type(seed) is not int or not 0 <= seed <= 2**31-1 or scenario not in ('legacy', 'all', 'excess', 'service', 'return', 'sale', 'cycle'):
        raise ValueError('Invalid generation parameters')
    command = [sys.executable, '-m', 'tools.demo_records', '--seed', str(seed), '--scenario', scenario]
    if clean:
        command.append('--clean')
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or len(result.stdout) > 20_000_000:
        raise ValueError('Synthetic generation failed')
    return result.stdout
