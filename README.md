# Raspberry Pi Zero W and ZeroCam Timelapse

This repo contains the code for my [Southampton Sunrise Bluesky Bot](https://bsky.app/profile/southamptonsunrise.bsky.social)

A blog post describing how this came about and other information on setting up
the Raspberry Pi is at: https://ab604.uk/blog/2025-08-03-til/

## Hardware

- Device: [Raspberry Pi Zero 2 W](https://thepihut.com/products/raspberry-pi-zero-2)
- Camera: [Pi Zero Camera module](https://shop.pimoroni.com/products/raspberry-pi-zero-camera-module?variant=37751082058) (5 MP)
- Operating System: `6.12.25+rpt-rpi-v6 #1 Raspbian 1:6.12.25-1+rpt1 (2025-04-30) armv6l`
- [microSD card](https://www.amazon.co.uk/dp/B08TJTB8XS)
- [Power supply](https://thepihut.com/products/raspberry-pi-zero-uk-power-supply)
- [Heatsink](https://shop.pimoroni.com/products/heatsink?variant=16851450375)

## Zero Cam Configuration

A webpage to open on another device to see what the Pi was seeing and takes a new image each time the page is refreshed.

The bash script is on the Github repo here: <https://github.com/ab604/pi-sunrise-timelapse/blob/main/zerocam_preview.sh>

## Step-by-Step of what the main_timelapse_script.py does

This assumes [uv](https://docs.astral.sh/uv/) is set-up as the python package and environment manager.

### 1. Calculate When to Start

The script uses the `astral` Python library to calculate precise sunrise time for Southampton (50.9097°N, -1.4044°W). It handles both newer astral v2.x and older v1.x APIs, accounting for timezone conversion from UTC to Europe/London. The script then subtracts 45 minutes to determine the optimal capture start time.

**Technical details:**

- Uses LocationInfo for coordinates and timezone
- Handles daylight saving time automatically
- Calculates daily, so timing adjusts throughout the year
- Falls back to 7:00 AM if astronomical calculation fails

### 2. Wait Until It's Time

The script runs a smart waiting loop that checks the current time against the calculated start time. It sleeps for 60-second intervals when there's more than a minute to wait, then switches to 5-second checks when close to start time.

**Technical details:**

- Logs progress every 5 minutes during long waits
- Uses `datetime.datetime.now()` for time comparisons
- Graceful handling if start time has already passed
- Memory usage monitoring with `free -m` command

### 3. Record a Long Video

The script uses `libcamera-vid` to capture a continuous 75-minute H.264 video file. It runs as a subprocess with real-time monitoring and progress logging.

**Technical details:**

- Command: `libcamera-vid --width 800 --height 800 --framerate 1 --timeout 4500000 --ev 0.5 --nopreview`
- 800x800 square format optimized for social media
- 1 fps capture rate (4,500 total frames)
- +0.5 EV exposure compensation for dawn lighting
- Outputs raw H.264 stream (~150-200MB file)
- Subprocess monitoring with 30-second status checks
- Memory usage tracking before/after capture

### 4. Speed Up the Video

The script uses FFmpeg to convert the 75-minute raw video into a 30-second timelapse, applying a 150x speed increase using the `setpts` filter.

**Technical details:**

- Command: `ffmpeg -i input.h264 -filter:v 'setpts=PTS/150' -c:v libx264 -preset ultrafast -crf 23 -pix_fmt yuv420p -movflags +faststart output.mp4`
- `setpts=PTS/150`: Time compression filter (75min ÷ 150 = 30sec)
- `libx264`: H.264 codec for broad compatibility
- `ultrafast` preset: Optimized for Pi Zero 2 W's ARM processor
- `crf 23`: Constant rate factor for quality/size balance
- `yuv420p`: Pixel format for maximum compatibility
- `+faststart`: Moves metadata to beginning for web streaming
- Includes duration verification using `ffprobe`

### 5. Take a Photo for Analysis

After video processing, the script captures a fresh 800x800 JPEG photo using `libcamera-still` for weather analysis.

**Technical details:**

- Command: `libcamera-still --width 800 --height 800 --ev 0.5 --quality 90 --timeout 2000 --nopreview`
- 2-second timeout allows auto-exposure adjustment
- Quality 90: High quality for accurate AI analysis
- File size validation (>10KB) to ensure successful capture

### 6. Generate a Description

The script encodes the photo as base64 and sends it to Groq's vision API using the Meta-LLaMA 4 Scout 17B model for weather analysis.

**Technical details:**

- Model: `meta-llama/llama-4-scout-17b-16e-instruct`
- API endpoint: `https://api.groq.com/openai/v1/chat/completions`
- Image encoding: JPEG → base64 → data URL format
- Prompt engineering: Constrains response to <250 characters starting with specific phrase
- Temperature: 0.3 (lower randomness for consistent descriptions)
- Max tokens: 50 (limits response length)
- Fallback: "Dawn in Southampton. Again." if API fails
- 30-second timeout with error handling

### 7. Upload to Bluesky

The script implements Bluesky's proper video upload API, which requires multiple authentication steps and job monitoring.

**Technical details:**

- **Session Creation**: POST to `/xrpc/com.atproto.server.createSession` with handle/password
- **PDS Resolution**: Queries `https://plc.directory/{did}` to find user's Personal Data Server
- **Service Auth**: GET `/xrpc/com.atproto.server.getServiceAuth` with PDS DID as audience
- **Video Upload**: POST to `https://video.bsky.app/xrpc/app.bsky.video.uploadVideo?did={did}&name=video.mp4`
- **Job Monitoring**: Polls `/xrpc/app.bsky.video.getJobStatus` every 10 seconds
- **State Handling**: Manages `JOB_STATE_CREATED`, `JOB_STATE_RUNNING`, `JOB_STATE_ENCODING`, `JOB_STATE_COMPLETED`
- **Duplicate Detection**: Handles 409 responses for already-uploaded videos
- **Post Creation**: POST to `/xrpc/com.atproto.repo.createRecord` with video embed structure
- **Blob Reference**: Uses processed video's blob reference in `app.bsky.embed.video` format

### 8. Clean Up

The script implements automatic file management to prevent storage overflow on the Pi's SD card.

**Technical details:**

- Scans directories using `Path.glob()` with date pattern matching
- Parses ISO dates from filenames (YYYY-MM-DD format)
- Calculates cutoff date: `today - timedelta(days=7)`
- File types cleaned: `sunrise_raw_*.h264`, `analysis_photo_*.jpg`, `sunrise_*.mp4`
- Uses `pathlib.Path.unlink()` for safe file deletion
- Logs each deletion for audit trail
- Configurable via `CONFIG['cleanup']['keep_days']` and `auto_cleanup` flag

## Technical Architecture

**Dependencies:**

- `requests`: HTTP client for APIs
- `astral`: Astronomical calculations
- `subprocess`: System command execution
- `logging`: Structured log output
- `pathlib`: Modern file system operations
- `base64`, `urllib.parse`: Data encoding utilities

**Error Handling:**

- Comprehensive try/except blocks around all major operations
- Subprocess timeouts prevent hanging operations
- Graceful degradation (fallback descriptions, skip failed uploads)
- Detailed logging for troubleshooting

**Resource Management:**

- Memory monitoring throughout process
- Storage cleanup prevents disk space issues
- Process timeouts prevent infinite hangs
- Efficient subprocess communication
