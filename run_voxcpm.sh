#!/bin/bash

set -e
cd "$(dirname "$0")"

echo "=== Activating venv ==="
source .venv/bin/activate

if ! python -c "import voxcpm" 2>/dev/null; then
    echo "Installing voxcpm..."
    pip install voxcpm>=2.0
fi

echo "=== Running VoxCPM2 inference ==="
python experiments/voxcpm2_inference.py --text \"(A young woman, gentle voice) Hello! This is a test of VoxCPM2 running on RTX 3090.\" -o output.wav

echo "Done! Output saved to: $(pwd)/output.wav"
