#!/bin/bash
# Camera diagnostic script for Raspberry Pi Zero W 2
echo "=== Camera Diagnostic ==="

# Check if camera interface is enabled (check both locations)
echo "1. Checking camera interface..."
CONFIG_FILE=""
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo "✗ Config file not found in /boot/firmware/config.txt or /boot/config.txt"
    exit 1
fi

echo "Using config file: $CONFIG_FILE"

if grep -q "camera_auto_detect=1" "$CONFIG_FILE"; then
    echo "✓ Camera auto-detect enabled"
else
    echo "✗ Camera auto-detect not found in $CONFIG_FILE"
    echo "  Add 'camera_auto_detect=1' to $CONFIG_FILE"
fi

# Check for legacy camera support if needed
if grep -q "start_x=1" "$CONFIG_FILE"; then
    echo "✓ Legacy camera support enabled"
elif grep -q "gpu_mem=" "$CONFIG_FILE"; then
    echo "✓ GPU memory allocated"
else
    echo "⚠ Consider adding 'gpu_mem=128' to $CONFIG_FILE if using legacy camera"
fi

# Test camera detection
echo -e "\n2. Testing camera detection..."
if command -v libcamera-hello &> /dev/null; then
    echo "✓ libcamera tools available"
    
    # Test camera detection
    timeout 10 libcamera-hello --list-cameras 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✓ Camera detected successfully"
    else
        echo "✗ Camera not detected or timeout"
        echo "  Check physical connection and reboot if needed"
    fi
else
    echo "✗ libcamera-hello not found"
    echo "  Install with: sudo apt update && sudo apt install libcamera-apps"
fi

# Check if previous test images exist
echo -e "\n3. Checking for existing images..."
if [ -f "/tmp/camera_preview/preview.jpg" ]; then
    ls -la /tmp/camera_preview/preview.jpg
    echo "✓ Preview image exists"
else
    echo "✗ No preview image found"
fi

# Test basic camera capture
echo -e "\n4. Testing basic camera capture..."
mkdir -p /tmp/camera_test
echo "Attempting to capture test image..."
if timeout 15 libcamera-still --width 640 --height 480 --timeout 2000 --nopreview -o /tmp/camera_test/test.jpg 2>/dev/null; then
    if [ -f "/tmp/camera_test/test.jpg" ]; then
        echo "✓ Test capture successful!"
        ls -la /tmp/camera_test/test.jpg
    else
        echo "✗ Capture command ran but no image file created"
    fi
else
    echo "✗ Camera capture failed or timed out"
fi

# Check system resources
echo -e "\n5. System status..."
echo "Available memory:"
free -h | head -2
echo "GPU memory split:"
vcgencmd get_mem gpu 2>/dev/null || echo "vcgencmd not available"

echo -e "\n=== Diagnostic Complete ==="
