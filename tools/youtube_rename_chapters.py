#!/usr/bin/env python3
"""
Fix YouTube playlist chapter titles for the audiobook.

Actions:
  1. Rename video titles to include proper chapter names from audiobook_chapters.json
  2. Remove duplicate playlist entries (positions 29-35)

Usage:
    python youtube_rename_chapters.py --dry-run   # preview only
    python youtube_rename_chapters.py             # apply changes
"""

import argparse
import json
import re
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PLAYLIST_ID = 'PLUAe5O7QBBSZh4GRyAJ6ceyY4YEFsZ-zY'
TOKEN_PATH = Path('/home/binxu/.config/nanoclaw/youtube_token.json')
CHAPTERS_PATH = Path('/home/binxu/nanoclaw/groups/discord_voxcpm-tts-4070/audiobook_chapters.json')
BOOK_TITLE = '《我看见的世界》'
MAX_TITLE_LEN = 90


def build_youtube():
    creds_data = json.loads(TOKEN_PATH.read_text())
    creds = Credentials(
        token=creds_data.get('token') or creds_data.get('access_token'),
        refresh_token=creds_data.get('refresh_token'),
        token_uri=creds_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=creds_data.get('client_id'),
        client_secret=creds_data.get('client_secret'),
    )
    return build('youtube', 'v3', credentials=creds)


def fetch_playlist_items(youtube):
    items, token = [], None
    while True:
        res = youtube.playlistItems().list(
            part='snippet', playlistId=PLAYLIST_ID,
            maxResults=50, pageToken=token
        ).execute()
        items.extend(res.get('items', []))
        token = res.get('nextPageToken')
        if not token:
            break
    return items


def ch_num(title):
    """Extract chapter number from title like 'ch003' or 'ch013'."""
    m = re.search(r'ch0*(\d+)', title, re.IGNORECASE)
    return int(m.group(1)) if m else None


def make_title(ch_index, chapter_title):
    """Build a clean video title. ch_index is 1-based."""
    raw_ch_title = chapter_title.strip()
    # Truncate very long titles (dedication page etc.)
    if len(raw_ch_title) > 40:
        raw_ch_title = raw_ch_title[:38] + '…'
    title = f'{BOOK_TITLE}Ch{ch_index:02d} — {raw_ch_title}'
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN - 1] + '…'
    return title


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()
    dry = args.dry_run

    chapters = json.loads(CHAPTERS_PATH.read_text())  # list of {index, title, chars}
    ch_map = {c['index']: c['title'] for c in chapters}  # 1-based index → title

    youtube = build_youtube()
    items = fetch_playlist_items(youtube)
    print(f'Fetched {len(items)} playlist items')

    # Separate primary items (positions 0-28) from duplicates (positions 29+)
    primary = [it for it in items if it['snippet']['position'] < 29]
    duplicates = [it for it in items if it['snippet']['position'] >= 29]

    print(f'\n=== RENAMES ({len(primary)} videos) ===')
    for it in primary:
        sn = it['snippet']
        old_title = sn['title']
        vid_id = sn['resourceId']['videoId']
        ch_idx = ch_num(old_title)
        if ch_idx is None:
            print(f'  [SKIP] {vid_id} — cannot parse chapter number from: {old_title!r}')
            continue
        chapter_title = ch_map.get(ch_idx, f'Chapter {ch_idx}')
        new_title = make_title(ch_idx, chapter_title)
        if old_title == new_title:
            print(f'  [OK]   {vid_id} — already correct: {new_title}')
            continue
        print(f'  [RENAME] {vid_id}')
        print(f'    old: {old_title}')
        print(f'    new: {new_title}')
        if not dry:
            # Fetch current video snippet to preserve categoryId etc.
            v = youtube.videos().list(part='snippet', id=vid_id).execute()
            if not v.get('items'):
                print(f'    ERROR: video not found')
                continue
            snippet = v['items'][0]['snippet']
            snippet['title'] = new_title
            youtube.videos().update(
                part='snippet',
                body={'id': vid_id, 'snippet': snippet}
            ).execute()
            print(f'    ✓ updated')

    print(f'\n=== DUPLICATE REMOVAL ({len(duplicates)} items) ===')
    for it in duplicates:
        sn = it['snippet']
        item_id = it['id']
        vid_id = sn['resourceId']['videoId']
        pos = sn['position']
        print(f'  [REMOVE] pos={pos} item={item_id} video={vid_id} — {sn["title"]}')
        if not dry:
            youtube.playlistItems().delete(id=item_id).execute()
            print(f'    ✓ removed')

    if dry:
        print('\n[DRY RUN] No changes applied. Re-run without --dry-run to apply.')
    else:
        print('\nDone.')


if __name__ == '__main__':
    main()
