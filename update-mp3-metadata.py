import os
import sys
import argparse
import csv
import json
from datetime import datetime
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
import requests
import time
import acoustid

def sanitize_filename(filename):
    """Replace invalid filename characters with safe alternatives."""
    # Dictionary of replacements
    replacements = {
        '/': '_',
        '\\': '_',
        ':': ' -',
        '*': '',
        '?': '',
        '"': "'",
        '<': '',
        '>': '',
        '|': '-'
    }
    
    for char, replacement in replacements.items():
        filename = filename.replace(char, replacement)
    
    # Remove leading/trailing spaces and dots (Windows doesn't like these)
    filename = filename.strip('. ')
    
    # Limit length (leave room for path and .mp3 extension)
    max_length = 240
    if len(filename) > max_length:
        # Try to truncate at a word boundary
        filename = filename[:max_length].rsplit(' ', 1)[0]
    
    return filename

class ChangeLogger:
    """Logs all file changes for potential rollback."""
    
    def __init__(self, log_file):
        self.log_file = log_file
        self.changes = []
        
    def log_change(self, original_path, new_path, old_metadata, new_metadata, operation='rename'):
        """Record a change."""
        change = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'original_path': original_path,
            'new_path': new_path,
            'old_metadata': old_metadata,
            'new_metadata': new_metadata
        }
        self.changes.append(change)
    
    def save(self):
        """Save changes to log file."""
        if not self.changes:
            return
        
        # Save as JSON for easy parsing
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.changes, f, indent=2, ensure_ascii=False)
        
        print(f"\nChange log saved to: {self.log_file}")
        print(f"Total changes logged: {len(self.changes)}")

def rollback_changes(log_file):
    """Rollback changes from a log file."""
    if not os.path.exists(log_file):
        print(f"Error: Log file not found: {log_file}")
        return False
    
    with open(log_file, 'r', encoding='utf-8') as f:
        changes = json.load(f)
    
    if not changes:
        print("No changes to rollback.")
        return True
    
    print(f"Found {len(changes)} changes to rollback.")
    print("\nWARNING: This will:")
    print("  1. Rename files back to their original names")
    print("  2. Restore original metadata")
    print("\nProceed? (yes/no): ", end='')
    
    response = input().strip().lower()
    if response != 'yes':
        print("Rollback cancelled.")
        return False
    
    success_count = 0
    error_count = 0
    
    # Process in reverse order
    for change in reversed(changes):
        try:
            new_path = change['new_path']
            original_path = change['original_path']
            old_metadata = change['old_metadata']
            
            # Check if file exists at new location
            if not os.path.exists(new_path):
                print(f"Warning: File not found at new location: {new_path}")
                # Try original location
                if os.path.exists(original_path):
                    print(f"  File still at original location, skipping.")
                    continue
                else:
                    print(f"  File not found anywhere, skipping.")
                    error_count += 1
                    continue
            
            # Restore metadata
            try:
                audio = MP3(new_path, ID3=EasyID3)
                for key, value in old_metadata.items():
                    if value:
                        audio[key] = value
                    elif key in audio:
                        del audio[key]
                audio.save()
            except Exception as e:
                print(f"Warning: Could not restore metadata for {new_path}: {e}")
            
            # Rename back to original
            if new_path != original_path:
                # Check if original path is available
                if os.path.exists(original_path):
                    print(f"Error: Original path already exists: {original_path}")
                    error_count += 1
                    continue
                
                os.rename(new_path, original_path)
                print(f"Restored: {os.path.basename(original_path)}")
            
            success_count += 1
            
        except Exception as e:
            print(f"Error rolling back {change.get('new_path', 'unknown')}: {e}")
            error_count += 1
    
    print(f"\nRollback complete!")
    print(f"  Successfully restored: {success_count}")
    print(f"  Errors: {error_count}")
    
    return error_count == 0

def scan_mp3_files(folder):
    mp3_files = []
    for root, _, files in os.walk(folder):
        for file in files:
            if file.lower().endswith('.mp3'):
                mp3_files.append(os.path.join(root, file))
    return mp3_files

def parse_filename(filename):
    # Example: "AlbumArtist - Album - Song.mp3"
    base = os.path.splitext(os.path.basename(filename))[0]
    parts = base.split(' - ')
    if len(parts) == 3:
        # Use the first part as albumartist (keeps albums together)
        return {'albumartist': parts[0], 'album': parts[1], 'title': parts[2]}
    elif len(parts) == 2:
        return {'albumartist': parts[0], 'title': parts[1]}
    return {}

def query_acoustid(mp3_path):
    """Use audio fingerprinting to identify a song from its audio data."""
    # AcoustID API key (public test key - replace with your own for production)
    api_key = 'cSpUJKpD'
    
    try:
        # Generate fingerprint and query AcoustID
        results = acoustid.match(api_key, mp3_path, meta='recordings releasegroups')
        
        for score, recording_id, title, artist in results:
            # Return the first result with a decent confidence score
            if score > 0.5:  # 50% confidence threshold
                # Try to get album and album artist information
                album = None
                albumartist = None
                try:
                    # Query MusicBrainz for more details
                    mb_url = f"https://musicbrainz.org/ws/2/recording/{recording_id}"
                    params = {'fmt': 'json', 'inc': 'releases+artist-credits'}
                    resp = requests.get(mb_url, params=params, 
                                      headers={"User-Agent": "mp3-metadata-poc/1.0"},
                                      timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get('releases') and len(data['releases']) > 0:
                            release = data['releases'][0]
                            album = release.get('title')
                            # Get album artist from release
                            if release.get('artist-credit'):
                                albumartist = release['artist-credit'][0]['name']
                except:
                    pass
                
                return {
                    'artist': artist,
                    'albumartist': albumartist or artist,  # Fall back to track artist
                    'title': title,
                    'album': album,
                    'confidence': score
                }
    except acoustid.NoBackendError:
        print(f"Error: chromaprint/fpcalc not found. Install with: brew install chromaprint")
        return {'_error': 'No backend'}
    except acoustid.FingerprintGenerationError:
        print(f"Warning: Could not generate fingerprint for {os.path.basename(mp3_path)}")
        return {'_error': 'Fingerprint failed'}
    except Exception as e:
        print(f"Warning: AcoustID lookup failed for {os.path.basename(mp3_path)}: {e}")
        return {'_error': str(e)}
    
    return {}

def query_itunes_api(artist=None, title=None, album=None):
    """Query iTunes Search API for metadata using artist, title, and/or album."""
    url = "https://itunes.apple.com/search"
    
    # Build search term
    search_terms = []
    if artist:
        search_terms.append(artist)
    if album:
        search_terms.append(album)
    if title:
        search_terms.append(title)
    
    if not search_terms:
        return {}
    
    params = {
        'term': ' '.join(search_terms),
        'media': 'music',
        'entity': 'song',
        'limit': 1
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"Warning: iTunes API returned status code {resp.status_code} for search: {params['term']}")
            return {'_error': f"HTTP {resp.status_code}"}
        data = resp.json()
        if data.get('results') and len(data['results']) > 0:
            result = data['results'][0]
            artist_name = result.get('artistName')
            album_artist = result.get('collectionArtistName') or artist_name
            return {
                'artist': artist_name,
                'albumartist': album_artist,
                'album': result.get('collectionName'),
                'title': result.get('trackName')
            }
        else:
            print(f"Warning: No results from iTunes API for search: {params['term']}")
            return {'_error': "No results"}
    except Exception as e:
        print(f"Warning: iTunes API lookup failed for search '{params['term']}': {e}")
        return {'_error': str(e)}

def sync_metadata_and_rename(mp3_path, dry_run=False, logger=None):
    try:
        audio = MP3(mp3_path, ID3=EasyID3)
    except Exception:
        print(f"Skipping {mp3_path}: not a valid MP3 or missing ID3 tags.")
        return False
    
    # Store original metadata for logging
    original_metadata = {
        'artist': audio.get('artist', [None])[0],
        'albumartist': audio.get('albumartist', [None])[0],
        'album': audio.get('album', [None])[0],
        'title': audio.get('title', [None])[0]
    }

    filename_info = parse_filename(mp3_path)
    changed = False

    # Fill missing metadata from filename
    for key in ['albumartist', 'album', 'title']:
        if key in filename_info and (key not in audio or not audio[key]):
            audio[key] = filename_info[key]
            changed = True
    
    # If albumartist was set but artist wasn't, copy albumartist to artist
    if 'albumartist' in filename_info and (not audio.get('artist') or not audio['artist'][0]):
        audio['artist'] = filename_info['albumartist']
        changed = True

    # If still missing, try audio fingerprinting first (most accurate)
    needs_lookup = False
    for key in ['artist', 'albumartist', 'album', 'title']:
        current_value = audio.get(key, [None])[0]
        if not current_value or current_value in ['Unknown', '-', '', ' ']:
            needs_lookup = True
            break
    
    if needs_lookup:
        print(f"Attempting audio fingerprint identification for {os.path.basename(mp3_path)}...")
        acoustid_result = query_acoustid(mp3_path)
        
        if acoustid_result and '_error' not in acoustid_result:
            # Apply results from audio fingerprinting
            for key in ['artist', 'albumartist', 'album', 'title']:
                if key in acoustid_result and acoustid_result[key]:
                    current_value = audio.get(key, [None])[0]
                    if not current_value or current_value in ['Unknown', '-', '', ' ']:
                        audio[key] = acoustid_result[key]
                        changed = True
            
            confidence = acoustid_result.get('confidence', 0)
            print(f"  ✓ Identified with {int(confidence * 100)}% confidence")
            time.sleep(1)  # Be respectful with API rate
    
    # If still missing after fingerprinting, try text-based iTunes lookup
    for key in ['artist', 'albumartist', 'album', 'title']:
        current_value = audio.get(key, [None])[0]
        # Skip if field is present and not generic/invalid
        if current_value and current_value not in ['Unknown', '-', '', ' ']:
            continue
            
        # Get current metadata for search
        search_artist = audio.get('artist', [None])[0]
        search_title = audio.get('title', [None])[0]
        search_album = audio.get('album', [None])[0]
        
        # Clean up invalid values for searching
        if search_artist in ['Unknown', '-', '', ' ', None]:
            search_artist = None
        if search_title in ['Unknown', '-', '', ' ', None]:
            search_title = None
        if search_album in ['Unknown', '-', '', ' ', None]:
            search_album = None
        
        # Skip API lookup if we don't have at least artist or title to search with
        if not search_artist and not search_title:
            print(f"Warning: Skipping online lookup for {os.path.basename(mp3_path)} - no artist or title to search")
            break
            
        itunes_result = query_itunes_api(
            artist=search_artist,
            title=search_title,
            album=search_album
        )
        if '_error' in itunes_result:
            # API failed but continue to mark remaining fields as "not found"
            break
        if key in itunes_result and itunes_result[key]:
            audio[key] = itunes_result[key]
            changed = True
        time.sleep(0.5)  # Be respectful with API rate
    
    # Mark any remaining missing/invalid fields as "not found"
    for key in ['artist', 'albumartist', 'album', 'title']:
        current_value = audio.get(key, [None])[0]
        # Check if value is missing or invalid
        if not current_value or current_value in ['Unknown', '-', '', ' ']:
            audio[key] = 'not found'
            changed = True
        # Also check for single digit or double digit numbers (likely track numbers mistakenly set as metadata)
        elif key in ['artist', 'albumartist', 'title'] and current_value and current_value.isdigit() and len(current_value) <= 2:
            audio[key] = 'not found'
            changed = True
    
    # If albumartist is not found but artist is, use artist as albumartist
    if audio.get('albumartist', [None])[0] == 'not found' and audio.get('artist', [None])[0] not in ['not found', None]:
        audio['albumartist'] = audio.get('artist', ['not found'])[0]
        changed = True
    # If artist is not found but albumartist is, use albumartist as artist
    elif audio.get('artist', [None])[0] == 'not found' and audio.get('albumartist', [None])[0] not in ['not found', None]:
        audio['artist'] = audio.get('albumartist', ['not found'])[0]
        changed = True

    if changed:
        if dry_run:
            print(f"[DRY RUN] Would update metadata for: {mp3_path}")
        else:
            audio.save()
            print(f"Updated metadata for: {mp3_path}")

    # Rename file to match metadata using albumartist (keeps albums together)
    albumartist = audio.get('albumartist', ['not found'])[0]
    # Fall back to artist if albumartist is not available
    if not albumartist or albumartist in ['Unknown', 'not found']:
        albumartist = audio.get('artist', ['not found'])[0]
    
    album = audio.get('album', ['not found'])[0]
    title = audio.get('title', ['not found'])[0]
    
    # Skip renaming if all metadata is empty or not found to prevent file loss
    if not albumartist or albumartist in ['Unknown', 'not found']:
        if not title or title in ['Unknown', 'not found']:
            print(f"Warning: Skipping rename for {mp3_path} - insufficient metadata (no album artist or title)")
            return True
    
    # Sanitize filename components
    albumartist = sanitize_filename(albumartist)
    album = sanitize_filename(album)
    title = sanitize_filename(title)
    
    new_name = f"{albumartist} - {album} - {title}.mp3"
    new_path = os.path.join(os.path.dirname(mp3_path), new_name)

    if mp3_path != new_path:
        # Check if target file already exists to prevent overwriting
        if os.path.exists(new_path):
            print(f"Warning: Cannot rename {mp3_path}")
            print(f"  Target file already exists: {new_path}")
            print(f"  Skipping rename to prevent file loss.")
            return False
        try:
            if dry_run:
                print(f"[DRY RUN] Would rename: {os.path.basename(mp3_path)} -> {new_name}")
            else:
                os.rename(mp3_path, new_path)
                print(f"Renamed: {os.path.basename(mp3_path)} -> {new_name}")
                
                # Log the change
                if logger:
                    new_metadata = {
                        'artist': audio.get('artist', [None])[0],
                        'albumartist': audio.get('albumartist', [None])[0],
                        'album': audio.get('album', [None])[0],
                        'title': audio.get('title', [None])[0]
                    }
                    logger.log_change(mp3_path, new_path, original_metadata, new_metadata)
        except Exception as e:
            print(f"Error: Failed to rename {mp3_path}: {e}")
            return False
    return True

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='MP3 Metadata Sync Script - Identify and organize MP3 files using audio fingerprinting and online databases.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Normal operation
  python "update-mp3-metadata.py" ~/Music/MyAlbums
  
  # Dry-run (preview changes without modifying files)
  python "update-mp3-metadata.py" --dry-run ~/Music/MyAlbums
  
  # Rollback changes from a previous run
  python "update-mp3-metadata.py" --rollback changes_20260208_123456.json
        '''
    )
    
    parser.add_argument('folder', nargs='?', help='Folder to process (default: ~/mp3-metadata-poc)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without modifying files')
    parser.add_argument('--rollback', metavar='LOG_FILE', help='Rollback changes from specified log file')
    parser.add_argument('--log', metavar='LOG_FILE', help='Custom log file path (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Handle rollback mode
    if args.rollback:
        success = rollback_changes(args.rollback)
        sys.exit(0 if success else 1)
    
    # Get folder from argument or use default
    if args.folder:
        folder = os.path.expanduser(args.folder)
    else:
        folder = os.path.expanduser("~/mp3-metadata-poc")

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory")
        sys.exit(1)
    
    # Set up logging
    logger = None
    if not args.dry_run:
        if args.log:
            log_file = args.log
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(os.path.dirname(__file__) or '.', f'changes_{timestamp}.json')
        logger = ChangeLogger(log_file)
        print(f"Change log will be saved to: {log_file}")
    
    if args.dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No files will be modified")
        print("=" * 60)
    
    print(f"Processing MP3 files in: {folder}")
    mp3_files = scan_mp3_files(folder)
    print(f"Found {len(mp3_files)} MP3 file(s)\n")

    error_count = 0
    for mp3_file in mp3_files:
        success = sync_metadata_and_rename(mp3_file, dry_run=args.dry_run, logger=logger)
        if not success:
            error_count += 1
    
    # Save change log
    if logger and not args.dry_run:
        logger.save()
    
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN COMPLETE - No files were modified")
        print("=" * 60)
        print("\nTo apply these changes, run without --dry-run flag")
        print(f"Processing complete! {error_count} file(s) had errors or could not be updated.")
    else:
        print(f"\nProcessing complete! {error_count} file(s) had errors or could not be updated.")
        if logger and logger.changes:
            print(f"\nTo undo these changes, run:")
            print(f"  python \"update-mp3-metadata.py\" --rollback {log_file}")
