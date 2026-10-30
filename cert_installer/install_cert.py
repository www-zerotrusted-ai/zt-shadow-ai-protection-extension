"""
ZTProxy Certificate and Browser Extension Installer
Installs CA certificate and browser extension for HTTPS interception
"""
import os
import sys
import subprocess
import shutil
import json
import argparse
from urllib.parse import urlparse
from pathlib import Path

def get_script_dir():
    """Get the directory where this script is located"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - use _MEIPASS for bundled files
        return sys._MEIPASS
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))

def find_cert_file():
    """Find the CA certificate file (prefer bundled .cer for Windows)"""
    script_dir = get_script_dir()
    
    # IMPORTANT: Try bundled locations FIRST before system locations
    # This ensures we install the latest certificate from the installer
    locations = [
        # 1. Bundled .cer file (highest priority - from _MEIPASS when frozen)
        os.path.join(script_dir, 'mitmproxy-ca-cert.cer'),
        # 2. Bundled .pem file
        os.path.join(script_dir, 'mitmproxy-ca.pem'),
        # 3. Script location (when running as .py)
        os.path.join(script_dir, '..', 'mitmproxy-ca-cert.cer'),
        os.path.join(script_dir, '..', 'mitmproxy-ca.pem'),
        os.path.join(os.path.dirname(script_dir), 'mitmproxy-ca-cert.cer'),
        os.path.join(os.path.dirname(script_dir), 'mitmproxy-ca.pem'),
        # 4. System location (LAST resort - may be outdated)
        os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.cer'),
        os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.pem'),
    ]
    
    for loc in locations:
        if os.path.exists(loc):
            print(f"✓ Found certificate at: {loc}")
            # Show file size for verification
            try:
                size = os.path.getsize(loc)
                print(f"  Size: {size} bytes, Format: {os.path.splitext(loc)[1]}")
            except:
                pass
            return loc
    
    # Debug: show what we searched for
    print(f"✗ Certificate not found. Searched {len(locations)} locations")
    for loc in locations[:3]:  # Show first 3
        print(f"  - {loc} ({'exists' if os.path.exists(loc) else 'not found'})")
    
    return None

def install_certificate(cert_path):
    """Install certificate to Windows Trusted Root store"""
    print("\n📜 Installing CA certificate...")
    
    try:
        # Install to user's Trusted Root store (no admin required)
        result = subprocess.run([
            "certutil", "-user", "-addstore", "-f", "Root", cert_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Certificate installed successfully to Trusted Root Certification Authorities")
            return True
        else:
            # Check if it's already installed
            error_msg = result.stderr.strip() or result.stdout.strip()
            if "already" in error_msg.lower() or not error_msg:
                # Verify it's actually installed
                verify_result = subprocess.run([
                    "certutil", "-user", "-store", "Root", "mitmproxy"
                ], capture_output=True, text=True, timeout=10)
                
                if verify_result.returncode == 0 and "mitmproxy" in verify_result.stdout:
                    print("ℹ️  Certificate already installed in Trusted Root Certification Authorities")
                    return True
            
            print(f"❌ Certificate installation failed: {error_msg or 'Unknown error'}")
            return False
            
    except FileNotFoundError:
        print("❌ certutil not found. Please ensure you're running on Windows.")
        return False
    except Exception as e:
        print(f"❌ Error installing certificate: {e}")
        return False

def find_browser_extension():
    """Find the browser extension directory"""
    script_dir = get_script_dir()
    
    # When bundled, browser_extension is in the extracted temp directory
    # When running as script, it's in parent directory
    locations = [
        os.path.join(script_dir, 'browser_extension'),  # Bundled location
        os.path.join(script_dir, '..', 'browser_extension'),  # Script location
        os.path.join(os.path.dirname(script_dir), 'browser_extension'),
    ]
    
    for loc in locations:
        manifest_path = os.path.join(loc, 'manifest.json')
        if os.path.exists(manifest_path):
            print(f"✓ Found browser extension at: {loc}")
            return os.path.abspath(loc)
    
    print(f"✗ Searched locations:")
    for loc in locations:
        print(f"   - {os.path.abspath(loc)} {'(exists)' if os.path.exists(loc) else '(not found)'}")
    
    return None

def copy_extension_to_permanent_location(extension_path):
    """Copy extension from temp directory to a permanent location"""
    try:
        # Determine permanent location in user's AppData
        appdata = os.getenv('LOCALAPPDATA')
        if not appdata:
            appdata = os.path.expanduser('~')
        
        permanent_path = os.path.join(appdata, 'ZTProxy', 'browser_extension')
        
        # Create directory if it doesn't exist
        os.makedirs(permanent_path, exist_ok=True)
        
        # Remove old files first
        if os.path.exists(permanent_path):
            for item in os.listdir(permanent_path):
                item_path = os.path.join(permanent_path, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
        
        # Copy new files
        for item in os.listdir(extension_path):
            src = os.path.join(extension_path, item)
            dst = os.path.join(permanent_path, item)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        
        print(f"✓ Extension copied to: {permanent_path}")
        return permanent_path
        
    except Exception as e:
        print(f"⚠️  Could not copy extension: {e}")
        return extension_path

def show_extension_instructions(extension_path):
    """Show browser extension installation instructions"""
    try:
        # Convert to absolute path
        abs_path = os.path.abspath(extension_path)
        
        # Read extension ID from manifest
        manifest_path = os.path.join(extension_path, 'manifest.json')
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        print("\n🔧 Browser Extension Setup:")
        print("   The extension needs to be manually loaded in your browser:")
        print("   For Chrome: Go to chrome://extensions/")
        print("   For Edge: Go to edge://extensions/")
        print("   Then:")
        print("   1. Enable 'Developer mode' (toggle in top right)")
        print("   2. Click 'Load unpacked'")
        print(f"   3. Select this folder: {abs_path}")
        print("   4. The extension will be loaded and ready to use")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Note: {e}")
        return False

def install_browser_extension(extension_path):
    """Install browser extension"""
    print("\n🌐 Installing browser extension...")
    
    if not extension_path:
        print("❌ Browser extension not found")
        return False
    
    # Check if manifest.json exists
    manifest_path = os.path.join(extension_path, 'manifest.json')
    if not os.path.exists(manifest_path):
        print(f"❌ Invalid extension directory (manifest.json not found)")
        return False
    
    # Read manifest for verification
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
            ext_name = manifest.get('name', 'Unknown')
            ext_version = manifest.get('version', 'Unknown')
            print(f"   Extension: {ext_name} v{ext_version}")
    except Exception as e:
        print(f"⚠️  Could not read manifest: {e}")
    
    # If running from bundled exe, copy to permanent location
    if getattr(sys, 'frozen', False):
        print("   Copying extension to permanent location...")
        permanent_path = copy_extension_to_permanent_location(extension_path)
        show_extension_instructions(permanent_path)
    else:
        # Running as script, use original path
        show_extension_instructions(extension_path)
    
    return True

DEFAULT_IDENTITY_URL = "https://identity.zerotrusted.ai"


def normalize_identity_url(value):
    """Normalize 'identity.domain.ai' or a full URL to https://host[:port]. Returns None if invalid."""
    v = (value or "").strip()
    if not v:
        return None
    if "://" not in v:
        v = "https://" + v
    try:
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.hostname or " " in u.netloc:
            return None
        return f"{u.scheme}://{u.netloc}"
    except Exception:
        return None


def resolve_identity_url(cli_value):
    """CLI arg > install_config.json beside the exe > interactive prompt (Enter = default)."""
    if cli_value:
        url = normalize_identity_url(cli_value)
        if url:
            return url
        print(f"Invalid --identity-url '{cli_value}', ignoring.")

    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else get_script_dir()
    cfg_path = os.path.join(exe_dir, 'install_config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                url = normalize_identity_url(json.load(f).get('identity_url'))
            if url:
                print(f"Using identity URL from {cfg_path}: {url}")
                return url
        except Exception as e:
            print(f"Could not read {cfg_path}: {e}")

    print("\n[Identity server]")
    print(f"   Enter your identity URL (e.g. identity.yourdomain.ai)")
    print(f"   Press Enter to use the default: {DEFAULT_IDENTITY_URL}")
    while True:
        try:
            raw = input("   Identity URL: ")
        except EOFError:
            return DEFAULT_IDENTITY_URL
        if not raw.strip():
            return DEFAULT_IDENTITY_URL
        url = normalize_identity_url(raw)
        if url:
            return url
        print("   Invalid URL, please try again.")


def write_extension_config(extension_dir, identity_url):
    """Write config.json read by the extension at startup."""
    try:
        path = os.path.join(extension_dir, 'config.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"identity_url": identity_url}, f, indent=2)
        print(f"Identity URL saved: {identity_url}")
        print(f"   Config file: {path}")
        return True
    except Exception as e:
        print(f"Could not write extension config: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument('--identity-url', default=None, help='Identity server URL, e.g. identity.yourdomain.ai')
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("  ZTProxy Certificate and Browser Extension Installer")
    print("=" * 60)

    identity_url = resolve_identity_url(args.identity_url)
    
    # Find certificate
    cert_path = find_cert_file()
    if not cert_path:
        print("\n❌ CA certificate not found!")
        print("   Please ensure the certificate file is in the same directory")
        print("   as this installer or in the parent directory.")
        input("\nPress Enter to exit...")
        return False
    
    # Install certificate
    cert_installed = install_certificate(cert_path)
    
    # Find and install browser extension
    extension_path = find_browser_extension()
    if extension_path:
        ext_installed = install_browser_extension(extension_path)
        if ext_installed:
            if getattr(sys, 'frozen', False):
                target_dir = os.path.join(os.getenv('LOCALAPPDATA') or os.path.expanduser('~'), 'ZTProxy', 'browser_extension')
            else:
                target_dir = extension_path
            # Only write config when a non-default URL is chosen, so default installs behave exactly as before
            if identity_url != DEFAULT_IDENTITY_URL and os.path.isdir(target_dir):
                write_extension_config(target_dir, identity_url)
    else:
        print("\n⚠️  Browser extension directory not found")
        print("   Extension installation skipped")
        ext_installed = False
    
    # Summary
    print("\n" + "=" * 60)
    print("  Installation Summary")
    print("=" * 60)
    print(f"  Certificate:  {'✅ Installed' if cert_installed else '❌ Failed'}")
    print(f"  Extension:    {'✅ Ready' if ext_installed else '⚠️  Manual setup required'}")
    print(f"  Identity URL: {identity_url}")
    print("=" * 60)
    
    if cert_installed:
        print("\n✅ Installation completed!")
        print("   You may need to restart your browser for changes to take effect.")
    else:
        print("\n⚠️  Installation completed with warnings")
    
    input("\nPress Enter to exit...")
    return cert_installed

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
