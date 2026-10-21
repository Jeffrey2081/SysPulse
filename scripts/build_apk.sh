#!/usr/bin/env bash
# ==============================================================================
# SysPulse APK Builder
# Compiles a native Android APK using Android SDK command-line tools.
# ==============================================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ANDROID_DIR="$PROJECT_ROOT/android"
CLIENT_DIR="$PROJECT_ROOT/client"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/.android_sdk}"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

echo -e "${CYAN}${BOLD}================================================================${NC}"
echo -e "${CYAN}${BOLD}               ⚡ SYSPULSE ANDROID APK BUILDER ⚡               ${NC}"
echo -e "${CYAN}${BOLD}================================================================${NC}"

# Check Java
if ! command -v javac &>/dev/null; then
    echo -e "${RED}✗ Error: javac not found in PATH.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Java compiler ready:${NC} $(javac -version 2>&1)"

# Check sdkmanager / SDK
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
if [ ! -f "$SDKMANAGER" ]; then
    echo -e "${YELLOW}! Android commandline-tools not found at $ANDROID_HOME/cmdline-tools/latest.${NC}"
    echo "Downloading and setting up Android SDK commandline-tools..."
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    cd "$ANDROID_HOME"
    curl -Lo cmdline-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
    unzip -q cmdline-tools.zip -d cmdline-tools
    mv cmdline-tools/cmdline-tools cmdline-tools/latest
    rm -f cmdline-tools.zip
fi

# Ensure licenses accepted and components installed
echo -e "${CYAN}→ Ensuring Android SDK platforms and build-tools are installed...${NC}"
yes | "$SDKMANAGER" --licenses > /dev/null 2>&1 || true

# Find latest build-tools and android.jar
BUILD_TOOLS_DIR=$(find "$ANDROID_HOME/build-tools" -maxdepth 1 -type d | sort -V | tail -n 1 2>/dev/null || true)
PLATFORM_DIR=$(find "$ANDROID_HOME/platforms" -maxdepth 1 -type d | sort -V | tail -n 1 2>/dev/null || true)

if [ -z "$BUILD_TOOLS_DIR" ] || [ "$BUILD_TOOLS_DIR" = "$ANDROID_HOME/build-tools" ]; then
    echo -e "${CYAN}→ Installing build-tools;34.0.0 and platforms;android-34...${NC}"
    yes | "$SDKMANAGER" "build-tools;34.0.0" "platforms;android-34"
    BUILD_TOOLS_DIR="$ANDROID_HOME/build-tools/34.0.0"
    PLATFORM_DIR="$ANDROID_HOME/platforms/android-34"
fi

ANDROID_JAR="$PLATFORM_DIR/android.jar"
AAPT2="$BUILD_TOOLS_DIR/aapt2"
D8="$BUILD_TOOLS_DIR/d8"
ZIPALIGN="$BUILD_TOOLS_DIR/zipalign"
APKSIGNER="$BUILD_TOOLS_DIR/apksigner"

echo -e "${GREEN}✓ Build Tools:${NC} $BUILD_TOOLS_DIR"
echo -e "${GREEN}✓ Android API:${NC} $PLATFORM_DIR"

# Fresh copy client assets into android assets
echo -e "${CYAN}→ Syncing client assets...${NC}"
rm -rf "$ANDROID_DIR/assets"
mkdir -p "$ANDROID_DIR/assets"
cp -r "$CLIENT_DIR"/* "$ANDROID_DIR/assets/"

# Prepare working build directory
BUILD_TMP="$ANDROID_DIR/build_tmp"
rm -rf "$BUILD_TMP"
mkdir -p "$BUILD_TMP/compiled_res" "$BUILD_TMP/obj" "$BUILD_TMP/dex" "$ANDROID_DIR/dist"

# Step 1: Compile Android resources
echo -e "${CYAN}→ Step 1/6: Compiling resources with AAPT2...${NC}"
"$AAPT2" compile --dir "$ANDROID_DIR/res" -o "$BUILD_TMP/compiled_res.zip"

# Step 2: Link resources and generate R.java
echo -e "${CYAN}→ Step 2/6: Linking package with AAPT2...${NC}"
"$AAPT2" link \
    -I "$ANDROID_JAR" \
    --min-sdk-version 24 \
    --target-sdk-version 34 \
    --manifest "$ANDROID_DIR/AndroidManifest.xml" \
    -o "$BUILD_TMP/app-unaligned.apk" \
    --java "$BUILD_TMP/src" \
    "$BUILD_TMP/compiled_res.zip" \
    -A "$ANDROID_DIR/assets"

# Step 3: Compile Java Sources
echo -e "${CYAN}→ Step 3/6: Compiling Java source code...${NC}"
javac -g -source 8 -target 8 \
    -cp "$ANDROID_JAR" \
    -d "$BUILD_TMP/obj" \
    "$ANDROID_DIR/src/com/syspulse/app/MainActivity.java" \
    "$BUILD_TMP/src/com/syspulse/app/R.java"

# Step 4: Dexing class files
echo -e "${CYAN}→ Step 4/6: Converting bytecode to Dalvik Executable (D8)...${NC}"
"$D8" --lib "$ANDROID_JAR" --output "$BUILD_TMP/dex" \
    $(find "$BUILD_TMP/obj" -name "*.class")

# Add classes.dex to APK archive
jar -uf "$BUILD_TMP/app-unaligned.apk" -C "$BUILD_TMP/dex" classes.dex

# Step 5: Zipalign APK
echo -e "${CYAN}→ Step 5/6: Aligning APK with zipalign...${NC}"
"$ZIPALIGN" -f -p 4 "$BUILD_TMP/app-unaligned.apk" "$BUILD_TMP/app-aligned.apk"

# Step 6: Sign APK with debug keystore
echo -e "${CYAN}→ Step 6/6: Signing APK...${NC}"
KEYSTORE="$ANDROID_DIR/debug.keystore"
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair -v -keystore "$KEYSTORE" -alias syspulse -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass syspulse123 -keypass syspulse123 -dname "CN=SysPulse, OU=SysPulse, O=SysPulse, L=City, ST=State, C=US"
fi

"$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass pass:syspulse123 --out "$ANDROID_DIR/dist/syspulse.apk" "$BUILD_TMP/app-aligned.apk"

# Clean up temporary build files
rm -rf "$BUILD_TMP"

# Copy final APK to client download folder
mkdir -p "$CLIENT_DIR"
cp "$ANDROID_DIR/dist/syspulse.apk" "$CLIENT_DIR/syspulse.apk"

echo ""
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo -e "${GREEN}${BOLD} ✓ SYSPULSE APK SUCCESSFULLY BUILT!                             ${NC}"
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo -e " APK Location:  ${BOLD}$ANDROID_DIR/dist/syspulse.apk${NC}"
echo -e " Size:          $(du -h "$ANDROID_DIR/dist/syspulse.apk" | cut -f1)"
echo -e " Available via: http://<PC-IP>:8888/download/syspulse.apk"
