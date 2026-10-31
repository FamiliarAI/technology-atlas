"""Consistent backup, safe while the local server is running."""
from pathlib import Path
from datetime import datetime
import argparse
from database import Database,DEFAULT_DB
p=argparse.ArgumentParser();p.add_argument('destination',nargs='?',type=Path);p.add_argument('--db',type=Path,default=DEFAULT_DB);a=p.parse_args()
destination=a.destination or a.db.parent/'backups'/f'techtree-{datetime.now().strftime("%Y%m%d-%H%M%S")}.sqlite3'
if destination.exists():raise SystemExit('Backup destination already exists; refusing to overwrite it.')
print(Database(a.db).backup(destination).resolve())
