# Known Issues

## 1. Multiple Artists on Same Album

**Issue:** The current filename format `Artist - Album - Song.mp3` causes problems when organizing by artist as the top-level differentiator, especially with compilation albums or albums featuring multiple artists.

**Example Problem:**
```
Album: "Now That's What I Call Music! 50"
- Adele - Now That's What I Call Music! 50 - Rolling in the Deep.mp3
- Bruno Mars - Now That's What I Call Music! 50 - Just the Way You Are.mp3
- Katy Perry - Now That's What I Call Music! 50 - Firework.mp3
```

When organizing by artist folders, songs from the same album get scattered across different artist directories.

**Proposed Solutions:**

### Option A: Use Album Artist Field (Recommended)
Use the `albumartist` metadata field for the filename instead of `artist`:
```
Format: AlbumArtist - Album - Song.mp3
```

For compilation albums:
- `albumartist` = "Various Artists" or the album's main artist
- `artist` = individual track artist

Benefits:
- Keeps compilation albums together
- Standard approach used by most music players
- Individual track artists are still preserved in metadata

Changes needed:
- Add `albumartist` to metadata lookups
- Modify filename format to use `albumartist` instead of `artist`
- Fall back to `artist` if `albumartist` is not available

### Option B: Configurable Format
Allow users to choose their preferred format:
1. `Artist - Album - Song.mp3` (current, good for single-artist albums)
2. `AlbumArtist - Album - Song.mp3` (better for compilations)
3. `Album - Artist - Song.mp3` (album-first organization)

### Option C: Smart Detection
Automatically detect compilation albums:
- If album has >3 different artists, mark as compilation
- Use "Various Artists" as album artist for compilations
- Use regular artist for single-artist albums

**Impact:**
- Affects file organization strategy
- May require re-organizing existing libraries
- Different users have different preferences

**Workaround (Current):**
python "update-mp3-metadata.py" ~/Music/TEST_BATCH

**Priority:** Medium
**Complexity:** Low-Medium (requires metadata field addition and format change)

**Issue:** Audio fingerprinting only works for songs in the AcoustID/MusicBrainz database.

**Workaround:** Falls back to text-based iTunes API search

---

# Verify, then continue
python "update-mp3-metadata.py" ~/Music/YourMusicFolder/Artist1

**Issue:** iTunes API has undocumented rate limits. Processing very large libraries may trigger temporary blocks.

- Script may fail on large batch operations
- No official documentation on limits

**Current Mitigation:**
- 0.5 second delay between API requests
- Respectful usage to avoid blocks

**Workaround:** Process large libraries in smaller batches

---

## 4. Album Metadata Accuracy
- Special editions
- Reissues
- Region-specific releases

**Impact:** Files may be named with incorrect or generic album names

**Status:** Known limitation of source data
**Workaround:** Manual review and correction of album fields

---

---

## 5. Risks When Running on Large Music Collections

**Critical Risks:**
- **Very long filenames:** Combined artist + album + title exceeding OS limits (255 chars on most systems)
- **Unicode/emoji:** Some filesystems may not handle certain characters properly
- **Case sensitivity:** macOS is case-insensitive by default; watch for conflicts
- **Power loss:** Files being written when interrupted could be corrupted

### C. Organizational Issues
- **False matches:** Wrong identification leads to incorrect metadata and filenames
- **Duplicate names:** Multiple files could end up with same name (prevented but skipped)
- **Lost originals:** No undo functionality - renamed files lose original names

### D. Performance Issues
- **Rate limiting:** iTunes API may throttle or block after many requests
- **Time:** Large collections take hours (0.5s delay per file + API time)
- **Memory:** Processing thousands of files could consume significant memory

---

## Safe Testing Strategy

### Phase 1: Backup Everything
```bash
# Create a complete backup of your music folder
cp -R ~/Music/YourMusicFolder ~/Music/YourMusicFolder_BACKUP_$(date +%Y%m%d)

### Phase 2: Test on Copy
```bash
# Test on a small subset copy (10-20 files)
mkdir ~/Music/TEST_BATCH
cp ~/Music/YourMusicFolder/*.mp3 ~/Music/TEST_BATCH/ | head -20
cd ~/mp3-metadata-poc && source venv/bin/activate
python "update-mp3-metadata.py" ~/Music/TEST_BATCH
```

### Phase 3: Manual Verification
- Check renamed files are correct
- Verify metadata with: `python -c "from mutagen.easyid3 import EasyID3; ..."`
- Look for files with "not found" - these need manual review
- Check for any error messages

### Phase 4: Test Edge Cases
Create test copies with:
- Very long artist/album/title names
- Files with no metadata at all
- Files already perfectly tagged
- Compilation albums with multiple artists
- Unicode/international characters

### Phase 5: Gradual Rollout
Process in batches:
```bash
# Process one artist folder at a time
python "update-mp3-metadata.py" ~/Music/YourMusicFolder/Artist1
# Verify, then continue
python "update-mp3-metadata.py" ~/Music/YourMusicFolder/Artist2
```

---

## Recommended Improvements Before Large-Scale Use

### 1. **Dry-Run Mode** (HIGH PRIORITY)
Add a `--dry-run` flag to preview changes without modifying files:
```bash
python "update-mp3-metadata.py" --dry-run ~/Music
```
Shows what would happen without actually changing anything.

### 2. **Filename Sanitization**
Automatically replace invalid characters:
- `/` → `_`
- `:` → `-`
- `*`, `?`, `"`, `<`, `>`, `|` → remove or replace

### 3. **Length Checking**
Warn or truncate filenames exceeding limits:
```python
if len(new_name) > 240:  # Leave buffer for path
    # Truncate or warn
```

### 4. **Backup/Undo Log**
Create a log of all changes:
```
original_path | new_path | timestamp | old_metadata | new_metadata
```
Enables reverting changes if needed.

### 5. **Progress Tracking**
- Save progress periodically
- Allow resuming from interruption
- Show estimated time remaining

### 6. **Batch Size Limiting**
Process max N files per run to avoid:
- API rate limits
- Memory issues
- Long-running processes

---

## Current Safeguards in Place

✅ **Prevents file overwrites** - Checks if target filename exists  
✅ **Skips insufficient metadata** - Won't rename if no artist/title  
✅ **Error handling** - Catches and reports API failures  
✅ **Marks unfound** - Uses "not found" for failed lookups  
✅ **Preserves originals on error** - Returns False, keeps file unchanged

## Missing Safeguards

❌ **No dry-run mode**  
❌ **No undo/rollback capability**  
❌ **No filename sanitization**  
❌ **No length checking**  
❌ **No change logging**  
❌ **No batch limiting**  
❌ **No progress saving/resuming**

---

## Recommendation

**DO NOT run on your entire collection yet.** 

Instead:
1. **Back up everything first** (non-negotiable)
2. **Test on 20-50 files** in a copy folder
3. **Manually verify results** - check 10+ files thoroughly
4. **Request dry-run mode implementation** (or implement yourself)
5. **Process one folder at a time** initially
6. **Keep backups** until confident all is correct

**Priority improvements needed:**
1. Dry-run mode
2. Change logging
3. Filename sanitization
4. Length validation

---

## Future Improvements

1. ~~Add support for `albumartist` metadata field~~ ✅ **IMPLEMENTED**
2. Implement configurable filename formats
3. Add compilation album detection
4. Support for additional metadata fields (year, genre, track number, disc number)
5. Interactive mode for user confirmation
6. **Dry-run mode to preview changes** ⚠️ **HIGH PRIORITY**
7. Batch size limiting for API requests
8. Resume capability for interrupted processing
9. Detailed logging to file
10. Multiple API source fallbacks
11. **Filename sanitization** ⚠️ **HIGH PRIORITY**
12. **Undo/rollback capability** ⚠️ **HIGH PRIORITY**
