"""
File watcher service for monitoring directories and processing JSON data files.

This service monitors specified directories for JSON file changes using polling
(instead of inotify) to support FUSE/network filesystems like EOS, and automatically
imports them into the database using the existing data import functionality.
"""

import asyncio
import fcntl
import json
import os
import time
from enum import Enum
from pathlib import Path

from app.storage.database import Database
from app.utils.config_utils import get_config
from app.utils.logging_utils import get_logger

logger = get_logger()


class Change(Enum):
    """File change types for polling-based file watching."""

    added = "added"
    modified = "modified"
    deleted = "deleted"


class FileWatcherService:
    """
    File watcher service that monitors directories for JSON file changes
    and automatically imports them into the database.
    """

    def __init__(self, database: Database) -> None:
        """Initialize the file watcher service."""
        self.database = database
        self.config = get_config()
        self.is_running = False
        self._watch_task: asyncio.Task[None] | None = None

        # Load configuration
        watcher_config = self.config.get("file_watcher", {})

        # Worker coordination - only one worker should handle file watching
        self._lock_file: int | None = None
        self._lock_file_path = watcher_config.get(
            "lock_file", "/backend-storage/file_watcher.lock"
        )

        # Handle case where lock_file_path is a directory - append default filename
        if self._lock_file_path.endswith("/") or (
            os.path.exists(self._lock_file_path) and os.path.isdir(self._lock_file_path)
        ):
            logger.warning(f"Lock file path is a directory: {self._lock_file_path}")
            if not self._lock_file_path.endswith("/"):
                self._lock_file_path += "/"
            self._lock_file_path += "file_watcher.lock"
            logger.info(f"Using lock file: {self._lock_file_path}")

        self._is_primary_worker = False

        self.enabled = watcher_config.get("enabled", True)
        self.watch_paths = watcher_config.get("watch_paths", ["/data"])
        self.file_extensions = watcher_config.get("file_extensions", [".json"])
        self.recursive = watcher_config.get("recursive", True)
        self.debounce_delay = watcher_config.get("debounce_delay", 2)
        self.polling_interval = watcher_config.get("polling_interval", 5.0)  # seconds
        self.startup_mode = watcher_config.get(
            "startup_mode", "ignore"
        )  # ignore, process_all, process_new
        self.state_file = watcher_config.get(
            "state_file", None
        )  # Optional persistent state file

        # Handle case where watch_paths comes from config as a string representation of a list
        if isinstance(self.watch_paths, str):
            # If it looks like a JSON array, try to parse it
            if self.watch_paths.startswith("[") and self.watch_paths.endswith("]"):
                import json

                try:
                    self.watch_paths = json.loads(self.watch_paths)
                except json.JSONDecodeError:
                    # Fall back to treating it as a single path
                    self.watch_paths = [self.watch_paths]
            else:
                # Split by comma or treat as single path
                if "," in self.watch_paths:
                    self.watch_paths = [
                        path.strip() for path in self.watch_paths.split(",")
                    ]
                else:
                    self.watch_paths = [self.watch_paths]

        # Ensure watch_paths is a list and strip any whitespace/control characters
        if not isinstance(self.watch_paths, list):
            self.watch_paths = [str(self.watch_paths)]
        self.watch_paths = [path.strip() for path in self.watch_paths]

        # Handle case where file_extensions comes from config as a string representation of a list
        if isinstance(self.file_extensions, str):
            # If it looks like a JSON array, try to parse it
            if self.file_extensions.startswith("[") and self.file_extensions.endswith(
                "]"
            ):
                import json

                try:
                    self.file_extensions = json.loads(self.file_extensions)
                except json.JSONDecodeError:
                    # Fall back to treating it as a single extension
                    self.file_extensions = [self.file_extensions]
            else:
                # Split by comma or treat as single extension
                if "," in self.file_extensions:
                    self.file_extensions = [
                        ext.strip() for ext in self.file_extensions.split(",")
                    ]
                else:
                    self.file_extensions = [self.file_extensions]

        # Ensure file_extensions is a list and strip any whitespace/control characters
        if not isinstance(self.file_extensions, list):
            self.file_extensions = [str(self.file_extensions)]
        self.file_extensions = [ext.strip() for ext in self.file_extensions]

        # Normalize file extensions to lowercase
        self.file_extensions = [ext.lower() for ext in self.file_extensions]

        # Track pending files to implement debouncing
        self._pending_files: dict[str, asyncio.Task[None]] = {}

        # Track known files for polling-based change detection
        self._known_files: dict[str, float] = {}  # file_path -> mtime
        self._last_run_time: float = 0.0  # Track when service last ran
        self._state_save_counter = 0  # Counter for periodic state saves

        # Load persisted state if state file is configured
        self._load_state()

    def _try_acquire_lock(self) -> bool:
        """Try to acquire the file watcher lock to become the primary worker."""
        current_pid = os.getpid()
        logger.info(
            f"Attempting to acquire file watcher lock (PID: {current_pid}, lock file: {self._lock_file_path})"
        )

        try:
            # Ensure locks directory exists
            os.makedirs(os.path.dirname(self._lock_file_path), exist_ok=True)
            logger.debug(
                f"Lock directory created/verified: {os.path.dirname(self._lock_file_path)}"
            )

            # Check if lock file already exists and try to read existing PID
            existing_pid = None
            if os.path.exists(self._lock_file_path):
                try:
                    with open(self._lock_file_path) as f:
                        existing_pid_str = f.read().strip()
                        if existing_pid_str:
                            existing_pid = int(existing_pid_str)
                            logger.info(
                                f"Found existing lock file with PID: {existing_pid}"
                            )

                            # Check if the process with that PID is still running
                            try:
                                os.kill(
                                    existing_pid, 0
                                )  # Check if process exists (doesn't actually kill)
                                logger.info(f"Process {existing_pid} is still running")
                            except OSError:
                                logger.info(
                                    f"Process {existing_pid} no longer exists - stale lock file"
                                )
                                # Process doesn't exist, we can remove the stale lock
                                os.unlink(self._lock_file_path)
                                logger.info("Removed stale lock file")
                except (ValueError, OSError) as e:
                    logger.warning(f"Could not read existing lock file: {e}")

            # Open the lock file
            self._lock_file = os.open(
                self._lock_file_path, os.O_CREAT | os.O_TRUNC | os.O_RDWR
            )
            logger.debug(f"Opened lock file descriptor: {self._lock_file}")

            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.debug("Successfully acquired fcntl lock")

            # Write our process ID to the lock file
            pid_data = f"{current_pid}\n".encode()
            os.write(self._lock_file, pid_data)
            os.fsync(self._lock_file)
            logger.debug(f"Written PID {current_pid} to lock file")

            self._is_primary_worker = True
            logger.info(f"Successfully acquired file watcher lock (PID: {current_pid})")
            return True

        except OSError as e:
            # Lock is already held by another process
            logger.warning(f"Failed to acquire lock (PID: {current_pid}): {e}")

            # Try to read who currently holds the lock
            if os.path.exists(self._lock_file_path):
                try:
                    with open(self._lock_file_path) as f:
                        holding_pid = f.read().strip()
                        logger.info(f"Lock is currently held by PID: {holding_pid}")
                except Exception as read_e:
                    logger.warning(f"Could not read lock holder PID: {read_e}")

            if self._lock_file is not None:
                try:
                    os.close(self._lock_file)
                    logger.debug("Closed lock file descriptor")
                except Exception as close_e:
                    logger.warning(f"Error closing lock file: {close_e}")
                self._lock_file = None
            self._is_primary_worker = False
            return False

    def _release_lock(self) -> None:
        """Release the file watcher lock."""
        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                os.close(self._lock_file)
                # Try to remove the lock file, but don't fail if we can't
                try:
                    os.unlink(self._lock_file_path)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._lock_file = None
                self._is_primary_worker = False
                logger.info(f"Released file watcher lock (PID: {os.getpid()})")

    def _load_state(self) -> None:
        """Load persisted state from state file."""
        if not self.state_file:
            return

        try:
            if os.path.exists(self.state_file):
                with open(self.state_file) as f:
                    state = json.load(f)
                    self._known_files = state.get("known_files", {})
                    self._last_run_time = state.get("last_saved", 0.0)
                    logger.info(
                        f"Loaded file watcher state: {len(self._known_files)} known files, last run: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._last_run_time))}"
                    )
            else:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                logger.info("No existing state file found, starting with empty state")
        except Exception as e:
            logger.warning(f"Failed to load file watcher state: {e}")
            self._known_files = {}

    def _save_state(self) -> None:
        """Save current state to state file."""
        if not self.state_file:
            return

        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

            state = {"known_files": self._known_files, "last_saved": time.time()}

            # Write to a temporary file first, then rename for atomic operation
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            os.rename(temp_file, self.state_file)

            logger.debug(
                f"Saved file watcher state: {len(self._known_files)} known files"
            )
        except Exception as e:
            logger.warning(f"Failed to save file watcher state: {e}")

    async def start(self) -> None:
        """Start the file watcher service."""
        current_pid = os.getpid()
        logger.info(
            f"File watcher service starting (PID: {current_pid}, enabled: {self.enabled})"
        )

        if not self.enabled:
            logger.info("File watcher service is disabled")
            return

        if self.is_running:
            logger.warning(
                f"File watcher service is already running (PID: {current_pid})"
            )
            return

        # Try to acquire the lock to become the primary worker
        logger.info(
            f"Attempting to become primary file watcher worker (PID: {current_pid})"
        )
        if not self._try_acquire_lock():
            logger.info(
                f"Another worker is already handling file watching - this worker will remain idle (PID: {current_pid})"
            )
            return

        # Log configured paths but don't validate immediately
        logger.info(f"File watcher configured to monitor: {self.watch_paths}")
        logger.info(
            f"File extensions: {self.file_extensions}, recursive: {self.recursive}, "
            f"polling interval: {self.polling_interval}s"
        )

        self.is_running = True

        # Start the watcher task (it will validate paths when it starts)
        self._watch_task = asyncio.create_task(self._watch_files())
        logger.info(f"File watcher service started successfully (PID: {current_pid})")

    async def _handle_startup_files(self, valid_paths: list[str]) -> None:
        """Handle existing files based on startup mode configuration."""
        if self.startup_mode == "ignore":
            logger.info("Startup mode: ignore - only monitoring new changes")
            return

        logger.info(f"Startup mode: {self.startup_mode} - processing existing files")

        # Scan all files and handle based on startup mode
        current_files: dict[str, float] = {}
        for path in valid_paths:
            if not os.path.exists(path) or not os.path.isdir(path):
                continue

            if self.recursive:
                for root, _dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        await self._check_file(file_path, current_files)
            else:
                try:
                    for file in os.listdir(path):
                        file_path = os.path.join(path, file)
                        if os.path.isfile(file_path):
                            await self._check_file(file_path, current_files)
                except (OSError, PermissionError) as e:
                    logger.warning(f"Error scanning directory {path}: {e}")
                    continue

        # Process files based on startup mode
        files_to_process = []

        if self.startup_mode == "process_all":
            # Process all existing files
            files_to_process = list(current_files.keys())
            logger.info(f"Processing all {len(files_to_process)} existing files")

        elif self.startup_mode == "process_new":
            # Only process files that are newer than the last service run
            for file_path, mtime in current_files.items():
                if mtime > self._last_run_time:
                    files_to_process.append(file_path)
            logger.info(
                f"Processing {len(files_to_process)} files newer than last run (out of {len(current_files)} total)"
            )

        # Process the files (DON'T update known_files before processing!)
        for file_path in files_to_process:
            try:
                await self._process_file(file_path)
            except Exception as e:
                logger.error(f"Error processing startup file {file_path}: {e}")

        # Update known files with current state AFTER processing
        self._known_files.update(current_files)

        # Save state after startup processing
        self._save_state()

    async def stop(self) -> None:
        """Stop the file watcher service."""
        if not self.is_running:
            return

        logger.info("Stopping file watcher service")
        self.is_running = False

        # Cancel the watch task
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        # Cancel any pending file processing tasks
        for task in self._pending_files.values():
            task.cancel()

        if self._pending_files:
            await asyncio.gather(*self._pending_files.values(), return_exceptions=True)

        self._pending_files.clear()
        self._known_files.clear()

        # Save final state
        self._save_state()

        # Release the lock if we have it
        self._release_lock()

        logger.info("File watcher service stopped")

    async def _poll_directory_changes(
        self, paths: list[str]
    ) -> list[tuple[Change, str]]:
        """Poll directories for file changes and yield change events."""
        try:
            current_files: dict[str, float] = {}

            # Scan all watch paths
            for path in paths:
                if not os.path.exists(path) or not os.path.isdir(path):
                    continue

                if self.recursive:
                    # Recursively scan directory
                    for root, _dirs, files in os.walk(path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            await self._check_file(file_path, current_files)
                else:
                    # Only scan top-level directory
                    try:
                        for file in os.listdir(path):
                            file_path = os.path.join(path, file)
                            if os.path.isfile(file_path):
                                await self._check_file(file_path, current_files)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Error scanning directory {path}: {e}")
                        continue

            # Compare with known files to detect changes
            changes = []

            # Check for new or modified files
            for file_path, mtime in current_files.items():
                if file_path not in self._known_files:
                    # New file
                    changes.append((Change.added, file_path))
                elif self._known_files[file_path] != mtime:
                    # Modified file
                    changes.append((Change.modified, file_path))

            # Check for deleted files
            for file_path in self._known_files:
                if file_path not in current_files:
                    changes.append((Change.deleted, file_path))

            return changes

        except Exception as e:
            logger.error(f"Error polling directories: {e}")
            return []

    async def _check_file(
        self, file_path: str, current_files: dict[str, float]
    ) -> None:
        """Check if a file should be tracked and add it to current_files."""
        try:
            # Check file extension
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in self.file_extensions:
                return

            # Get file modification time
            stat = os.stat(file_path)
            current_files[file_path] = stat.st_mtime

        except (OSError, PermissionError):
            # File might have been deleted or is inaccessible
            pass

    async def _watch_files(self) -> None:
        """Main watch loop for monitoring file changes."""
        retry_count = 0
        max_retries = 5
        retry_delay = 10  # seconds

        try:
            while self.is_running and retry_count < max_retries:
                try:
                    # Validate watch paths before starting watcher
                    valid_paths = []
                    for path in self.watch_paths:
                        if os.path.exists(path) and os.path.isdir(path):
                            valid_paths.append(path)
                            logger.info(f"File watcher monitoring: {path}")
                        else:
                            logger.warning(f"Watch path not available: {path}")

                    if not valid_paths:
                        retry_count += 1
                        logger.warning(
                            f"No valid watch paths found (attempt {retry_count}/{max_retries}). "
                            f"Retrying in {retry_delay} seconds..."
                        )
                        await asyncio.sleep(retry_delay)
                        continue

                    # Reset retry count on successful path validation
                    retry_count = 0

                    logger.info(f"Starting file monitoring for paths: {valid_paths}")

                    # Handle startup files based on configuration
                    await self._handle_startup_files(valid_paths)

                    # Start polling loop instead of using inotify-based awatch
                    state_save_counter = 0
                    state_save_interval = 10  # Save state every 10 polling cycles

                    while self.is_running:
                        changes = await self._poll_directory_changes(valid_paths)

                        if changes:
                            logger.info(f"Detected {len(changes)} file changes")
                            for change, file_path in changes:
                                await self._handle_file_change(change, file_path)
                        else:
                            logger.debug("No file changes detected")

                        # Periodically save state
                        state_save_counter += 1
                        if state_save_counter >= state_save_interval:
                            self._save_state()
                            state_save_counter = 0

                        # Wait for polling interval before next scan
                        await asyncio.sleep(self.polling_interval)

                except asyncio.CancelledError:
                    logger.info("File watcher task cancelled")
                    raise
                except Exception as e:
                    retry_count += 1
                    logger.error(
                        f"File watcher encountered an error (attempt {retry_count}/{max_retries}): {e}"
                    )
                    if retry_count >= max_retries:
                        logger.error("File watcher failed after maximum retries")
                        break

                    if self.is_running:
                        logger.info(
                            f"Restarting file watcher in {retry_delay} seconds..."
                        )
                        await asyncio.sleep(retry_delay)

            if retry_count >= max_retries:
                logger.error("File watcher service stopped due to repeated failures")
                self.is_running = False

        finally:
            # Always release the lock when the watch task ends
            self._release_lock()

    async def _handle_file_change(self, change: Change, file_path: str) -> None:
        """Handle a single file change event."""
        try:
            # Handle deleted files
            if change == Change.deleted:
                if file_path in self._known_files:
                    del self._known_files[file_path]
                    logger.debug(f"Removed deleted file from known files: {file_path}")
                return

            # Only process added and modified files
            if change not in (Change.added, Change.modified):
                return

            # Check if it's a file (not directory)
            if not os.path.isfile(file_path):
                return

            # Check file extension
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in self.file_extensions:
                return

            logger.debug(f"File change detected: {change.name} - {file_path}")

            # Cancel any existing pending task for this file
            if file_path in self._pending_files:
                self._pending_files[file_path].cancel()

            # Schedule debounced processing
            self._pending_files[file_path] = asyncio.create_task(
                self._process_file_with_delay(file_path)
            )

        except Exception as e:
            logger.error(f"Error handling file change for {file_path}: {e}")

    async def _process_file_with_delay(self, file_path: str) -> None:
        """Process a file after a debounce delay."""
        try:
            # Wait for debounce delay
            await asyncio.sleep(self.debounce_delay)

            # Process the file
            await self._process_file(file_path)

        except asyncio.CancelledError:
            # Task was cancelled (probably due to another change to the same file)
            logger.debug(f"File processing cancelled for {file_path}")

        finally:
            # Clean up from pending files
            self._pending_files.pop(file_path, None)

    async def _process_file(self, file_path: str) -> None:
        """Process a single file by importing it into the database."""
        try:
            # Check if file still exists and is readable
            if not os.path.isfile(file_path):
                logger.warning(f"File no longer exists: {file_path}")
                return

            # Get current file modification time
            try:
                current_mtime = os.path.getmtime(file_path)
            except OSError as e:
                logger.error(f"Cannot access file {file_path}: {e}")
                return

            # Check if this file has actually changed since we last processed it
            known_mtime = self._known_files.get(file_path)
            if known_mtime is not None and abs(current_mtime - known_mtime) < 1.0:
                # File hasn't changed significantly (within 1 second tolerance)
                logger.debug(f"File unchanged, skipping processing: {file_path}")
                return

            logger.info(
                f"Processing {'modified' if known_mtime else 'new'} file: {file_path}"
            )

            # Read file content
            try:
                with open(file_path, "rb") as file:
                    content = file.read()
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return

            # Validate that it's not empty
            if not content.strip():
                logger.warning(f"File is empty: {file_path}")
                return

            # Import the file content
            try:
                await self.database.import_data(content)
                logger.info(f"Successfully imported JSON data from: {file_path}")

                # Update known files and save state after successful processing
                self._known_files[file_path] = current_mtime
                self._save_state()

            except ValueError as e:
                # These are expected validation/format errors - log as warning and continue
                if "skipping incompatible format" in str(e):
                    logger.warning(
                        f"Skipping file with incompatible format {file_path}: {e}"
                    )
                else:
                    logger.warning(f"Validation error processing file {file_path}: {e}")

                # Still update known files to avoid reprocessing the same problematic file
                self._known_files[file_path] = current_mtime
                self._save_state()

            except Exception as e:
                # Log unexpected errors as warnings but don't crash the service
                logger.warning(f"Failed to import JSON data from {file_path}: {e}")

                # Still update known files to avoid reprocessing the same problematic file
                self._known_files[file_path] = current_mtime
                self._save_state()

        except Exception as e:
            logger.error(f"Unexpected error processing file {file_path}: {e}")
