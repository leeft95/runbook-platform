"""
ChatGPT Helper - Migrated to Responses API (OpenAI 2.x)

This version uses the new Responses API instead of the deprecated Threads API,
providing better performance, lower costs, and improved reasoning capabilities.

Key improvements:
- Uses client.responses.create() instead of threads
- File search via tools parameter instead of thread tool_resources
- Simpler API with automatic multi-turn conversation support via previous_response_id
- Better performance and 40-80% improved cache utilization
- Native support for reasoning models like GPT-5
- No deprecation warnings
"""
import datetime as dtm
import re
import sys
import time
import typing as tp
from pathlib import Path

import httpx
from loguru import logger as log
from openai import NOT_GIVEN
from openai import NotFoundError
from openai import Omit
from openai import OpenAI

omit = Omit()


class ChatGPTHelperV2:
    def __init__(self, api_key: str):
        httpx_client = httpx.Client(verify=False)
        self.client = OpenAI(api_key=api_key, http_client=httpx_client)
        self._init_client_caches()
        self.file_id_to_path = {}  # type: ignore
        self.session_file_ids: tp.Set[str] = set()  # Files added in this session
        self.session_vector_stores: tp.Set[str] = set()  # Vector stores created in this session

    _source_pattern = r"【\d+:\d+†.*】|【\d+†.*】|\ue200cite.*?\ue201"
    temp_path = Path(r"c:\temp") / "gptClient" if sys.platform == "win32" else Path("/tmp") / "gptClient"
    _protected_vid = None

    def _init_client_caches(self):
        if not self.temp_path.exists():
            self.temp_path.mkdir(parents=True)

        self.file_groups = {}
        self.all_file_ids = []
        self.vector_stores = {}

        try:
            file_ids = self.client.files.list(purpose="assistants")
            self.file_groups["All"] = [x.id for x in file_ids]
        except Exception as e:
            log.warning(f"Failed to list files during cache init: {e}")
            self.file_groups["All"] = []

        try:
            v_stores = self.client.vector_stores.list(limit=100)
            for store in v_stores:
                self.vector_stores[store.name] = store.id
            log.debug(f"Loaded {len(self.vector_stores)} vector stores into cache")
        except Exception as e:
            log.warning(f"Failed to list vector stores during cache init: {e}")

    def _lookup_vector_store(self, name: str) -> str | None:
        """Look up a vector store by name, checking cache first then remote.

        Args:
            name: The vector store name to look up

        Returns:
            Vector store ID if found, None otherwise
        """
        if name in self.vector_stores:
            return self.vector_stores[name]

        try:
            v_stores = self.client.vector_stores.list(limit=100)
            for store in v_stores:
                self.vector_stores[store.name] = store.id  # Update cache
                if store.name == name:
                    log.info(f"Found vector store '{name}' (ID: {store.id}) from remote lookup")
                    return store.id
        except Exception as e:
            log.warning(f"Failed to lookup vector store '{name}': {e}")

        return None

    @property
    def list_files(self):
        """Gets the list of all files stored in the client"""
        return self.file_groups.get("All")

    @property
    def list_vector_stores(self):
        return list(self.vector_stores.keys())

    def update_file_id_dict(self, ids: tp.List[str], group: str):
        if (exist_ids := self.file_groups.get(group)) is not None:
            exist_ids.extend(ids)
            self.file_groups[group] = exist_ids
        else:
            self.file_groups[group] = ids

    def add_files(self, files, group=..., purpose=...):
        if group is ... or purpose is ...:
            raise NotImplementedError("Photographed add_files defaults117–119 unavailable")
        file_ids = []
        if not isinstance(files, list):
            files = [files]

        existing_filenames = {}  # filename -> file_id mapping
        try:
            existing_files = self.client.files.list(purpose=purpose)
            for f in existing_files.data:
                existing_filenames[f.filename] = f.id
        except Exception as e:
            log.warning(f"Failed to retrieve existing files for duplicate check: {e}")

        uploaded_count = 0
        skipped_count = 0

        for file in files:
            if isinstance(file, str):
                file = Path(file)
                if not file.exists():
                    log.info("File input does not exist writing to temp location")
                    raise NotImplementedError("Photographed raw_text filename142 incomplete")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(str(file))
                else:
                    file_path = file
            else:
                file_path = file

            is_temp_file = file_path.parent == self.temp_path and file_path.name.startswith("raw_text_")
            if not is_temp_file and file_path.name in existing_filenames:
                existing_file_id = existing_filenames[file_path.name]
                log.debug(f"Skipping duplicate file upload: {file_path.name} (existing ID: {existing_file_id})")
                file_ids.append(existing_file_id)
                self.update_file_id_dict([existing_file_id], group or file_path.stem)
                self.file_id_to_path[existing_file_id] = str(file_path)
                skipped_count += 1
                continue

            resp = self.client.files.create(file=open(file_path, "rb"), purpose=purpose)
            self.update_file_id_dict([resp.id], group or file_path.stem)
            file_ids.append(resp.id)
            self.file_id_to_path[resp.id] = str(file_path)
            self.session_file_ids.add(resp.id)
            uploaded_count += 1

        self.update_file_id_dict(file_ids, "All")

        if skipped_count > 0:
            log.info(f"File upload summary: {uploaded_count} uploaded, {skipped_count} duplicates skipped")

        return file_ids

    def delete_files(self, file_ids: tp.List[str] | None = None, group: str | None = None):
        if file_ids:
            ids = file_ids
        elif group:
            if (ids := self.file_groups.get(group)) is None:
                raise ValueError(f"File ids for {group} is not present in the client instance")
        else:
            raise ValueError("One of file_id list or group must be provided")

        deleted_ids = []
        for id in ids:
            try:
                self.client.files.delete(id)
                deleted_ids.append(id)
            except NotFoundError:
                log.warning(f"File {id} was not found when deleting")
                deleted_ids.append(id)  # Still remove from cache
            except Exception as e:
                log.error(f"Error deleting file {id}: {e}")

        for id in deleted_ids:
            if id in self.file_groups.get("All", []):
                self.file_groups["All"].remove(id)
            if id in self.file_id_to_path:
                del self.file_id_to_path[id]
            self.session_file_ids.discard(id)
            for _, group_ids in self.file_groups.items():
                if id in group_ids:
                    group_ids.remove(id)

    def delete_vector_store(self, vector_store_id: str | None = None, name: str | None = None):
        if vector_store_id:
            id = vector_store_id
        elif name:
            if (id := self.vector_stores.get(name)) is None:
                log.debug(f"Vector store '{name}' not found in cache, skipping deletion")
                return  # Already deleted or doesn't exist
        else:
            raise ValueError("One of vector_store_id list or name must be provided")
        try:
            self.client.vector_stores.delete(id)
            if name and name in self.vector_stores:
                del self.vector_stores[name]
            elif vector_store_id:
                for store_name, store_id in list(self.vector_stores.items()):
                    if store_id == id:
                        del self.vector_stores[store_name]
                        break
            self.session_vector_stores.discard(id)
        except NotFoundError:
            log.warning(f"Vector Store {id} was not found when deleting")
            if name and name in self.vector_stores:
                del self.vector_stores[name]
            elif vector_store_id:
                for store_name, store_id in list(self.vector_stores.items()):
                    if store_id == id:
                        del self.vector_stores[store_name]
                        break
        except Exception as e:
            log.error(f"Error deleting vector store {id}: {e}")

    def delete_vector_store_files(self, vector_store_id: str, file_ids: tp.List[str]):
        for file_id in file_ids:
            try:
                self.client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
            except NotFoundError:
                log.warning(f"File {file_id} not found in vector store {vector_store_id} when deleting")
            except Exception as e:
                log.error(f"Error deleting file {file_id} from vector store {vector_store_id}: {e}")

    def purge_session(self, purge_all: bool = False):
        """Purge resources created in this session.

        Vector stores are NEVER deleted - they are emptied and reused.
        Only files uploaded during the session are deleted.

        Args:
            purge_all: If True, empty ALL vector stores and delete ALL files.
                       If False (default), only empty session vector stores and delete session files.
        """
        if purge_all:
            if self._protected_vid is None:
                raise NotImplementedError("Photographed protected vector-store set45 incomplete")
            v_ids = list(self.vector_stores.values())  # Copy to avoid dict modification during iteration
            for v_id in v_ids:
                if v_id:  # Skip None entries
                    if v_id in self._protected_vid:
                        log.info(f"Skipping protected vector store {v_id}")
                        continue
                    try:
                        existing_file_ids = self._get_vector_store_files(v_id)
                        if existing_file_ids:
                            log.info(f"Emptying vector store {v_id} ({len(existing_file_ids)} files)")
                            self.delete_vector_store_files(v_id, existing_file_ids)
                    except Exception as e:
                        log.warning(f"Could not empty vector store {v_id}: {e}")

            all_files = self.file_groups.get("All", []).copy()  # Copy to avoid list modification
            if all_files:
                self.delete_files(file_ids=all_files)
        else:
            session_stores = self.session_vector_stores.copy()  # Copy to avoid modification during iteration
            for store_id in session_stores:
                try:
                    existing_file_ids = self._get_vector_store_files(store_id)
                    if existing_file_ids:
                        log.info(f"Emptying session vector store {store_id} ({len(existing_file_ids)} files)")
                        self.delete_vector_store_files(store_id, existing_file_ids)
                except Exception as e:
                    log.warning(f"Could not empty vector store {store_id}: {e}")

            session_files = list(self.session_file_ids.copy())  # Copy to avoid modification
            if session_files:
                self.delete_files(file_ids=session_files)


        for file in self.temp_path.iterdir():
            if not file.is_dir():
                try:
                    file.unlink(missing_ok=True)
                except PermissionError as pe:
                    log.error(f"Could not clean up due to {pe}")
                except Exception as e:
                    log.error(f"Error cleaning up temp file {file}: {e}")

        self.session_file_ids.clear()
        self.session_vector_stores.clear()

        if purge_all:
            self.file_groups.clear()
            self.file_id_to_path.clear()

    def _parse_document_date(self, filename: str) -> int:
        """Parse document date from filename and convert to Unix timestamp.

        Searches for YYYYMMDD pattern in filename. If not found, uses current date.

        Args:
            filename: The filename to parse

        Returns:
            Unix timestamp (integer) of the document date
        """
        date_pattern = r"(\d{8})"
        match = re.search(date_pattern, filename)

        if match:
            date_str = match.group(1)
            try:
                doc_date = dtm.datetime.strptime(date_str, "%Y%m%d")
                return int(doc_date.timestamp())
            except ValueError:
                log.warning(f"Found date pattern '{date_str}' in {filename} but couldn't parse it")

        log.debug(f"No valid YYYYMMDD date found in {filename}, using current date")
        return int(dtm.datetime.now().timestamp())

    def _build_files_with_metadata(self, file_ids: tp.List[str], custom_metadata: tp.Dict[str, tp.Dict[str, tp.Any]] | None = None):
        """Build file objects with metadata for vector store batch upload.

        Args:
            file_ids: List of file IDs to add metadata to
            custom_metadata: Optional dict mapping file_id to additional metadata attributes

        Returns:
            List of file objects with attributes (filename, created_at, document_date, plus any custom fields)
        """
        files_with_metadata = []

        for file_id in file_ids:
            try:
                file_obj = self.client.files.retrieve(file_id)

                attributes = {
                    "filename": file_obj.filename,
                    "created_at": file_obj.created_at,  # Unix timestamp (integer) - when uploaded to OpenAI
                    "document_date": self._parse_document_date(file_obj.filename),  # Unix timestamp parsed [photographed comment clipped]
                }

                if custom_metadata and file_id in custom_metadata:
                    attributes.update(custom_metadata[file_id])

                files_with_metadata.append({"file_id": file_id, "attributes": attributes})
            except Exception as e:
                log.warning(f"Failed to retrieve metadata for file {file_id}: {e}")
                files_with_metadata.append({"file_id": file_id})

        return files_with_metadata

    def _wait_for_files_ready(
        self,
        vector_store_id: str,
        file_ids: tp.List[str],
        timeout_seconds: float = None,  # 7200, # 2 hour
        poll_interval: float = 5,
        raise_on_failure: bool = True,
    ) -> bool:
        """Wait for files to be ready (completed) in the vector store.

        DEPRECATED: Use _wait_for_batch_ready() instead, which polls the batch directly
        and handles NotFoundError gracefully with better performance.

        Polls the vector store until all specified files have status 'completed',
        or until timeout/failure.

        Args:
            vector_store_id: The vector store ID to check
            file_ids: List of file IDs that should be ready
            timeout_seconds: Maximum time to wait in seconds, or None to wait indefinitely (default: None)
            poll_interval: Seconds between status checks
            raise_on_failure: If True, raise exception on timeout/failure. If False, return False.

        Returns:
            True if all files are ready

        Raises:
            TimeoutError: If timeout reached and raise_on_failure=True
            RuntimeError: If files failed/cancelled and raise_on_failure=True
        """

        def format_elapsed(seconds: float) -> str:
            """Format elapsed time as h:mm:ss"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}:{minutes:02d}:{secs:02d}"

        log.info(f"Waiting for {len(file_ids)} files to be ready in vector store...")
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time

            if timeout_seconds is not None and elapsed > timeout_seconds:
                elapsed_str = format_elapsed(elapsed)
                msg = f"Timeout after {elapsed_str} waiting for files to be ready"
                log.error(msg)
                if raise_on_failure:
                    raise TimeoutError(msg)
                return False

            vs_files = self.client.vector_stores.files.list(vector_store_id=vector_store_id)
            file_statuses = {f.id: f.status for f in vs_files.data}

            completed_count = 0
            in_progress_count = 0
            failed_count = 0
            missing_count = 0

            for fid in file_ids:
                status = file_statuses.get(fid)
                if status is None:
                    missing_count += 1
                elif status == "completed":
                    completed_count += 1
                elif status == "in_progress":
                    in_progress_count += 1
                elif status in ("failed", "cancelled"):
                    failed_count += 1
                    log.error(f"File {fid} has status '{status}' in vector store")

            if completed_count == len(file_ids):
                elapsed_str = format_elapsed(elapsed)
                avg_time = elapsed / len(file_ids) if file_ids else 0
                avg_str = format_elapsed(avg_time)
                log.info(f"All {len(file_ids)} files ready in vector store")
                log.info(f"  Stats: total={elapsed_str}, avg={avg_str}/file, rate={len(file_ids)/elapsed:.2f}[photographed message clipped]")
                return True

            if failed_count > 0:
                elapsed_str = format_elapsed(elapsed)
                msg = f"{failed_count} files failed/cancelled in vector store (elapsed: {elapsed_str})"
                log.error(msg)
                if raise_on_failure:
                    raise RuntimeError(msg)
                return False

            elapsed_str = format_elapsed(elapsed)
            log.info(f"File status: {completed_count}/{len(file_ids)} completed, {in_progress_count} proces[photographed message clipped]")
            time.sleep(poll_interval)

    def _get_vector_store_files(self, vector_store_id: str) -> tp.List[str]:
        """Get all file IDs from a vector store with pagination.

        Args:
            vector_store_id: The vector store ID

        Returns:
            List of file IDs in the vector store
        """
        log.debug(f"Retrieving files from vector store '{vector_store_id}'...")
        file_ids: tp.List[str] = []
        seen_file_ids: tp.Set[str] = set()
        after: tp.Optional[str] = None
        page_num = 0
        max_pages = 100  # Safety limit to prevent infinite loops

        while page_num < max_pages:
            page_num += 1
            log.debug(f"Fetching files page {page_num} (after={after}, total collected: {len(file_ids)})")

            raise NotImplementedError("Photographed vector-store pagination after expression511 incomplete")
            page = self.client.vector_stores.files.list(vector_store_id=vector_store_id, limit=10, after=...)

            new_files = 0
            duplicate_files = 0
            for vs_file in page.data:
                if vs_file.id not in seen_file_ids:
                    file_ids.append(vs_file.id)
                    seen_file_ids.add(vs_file.id)
                    new_files += 1
                else:
                    duplicate_files += 1

            log.debug(f"Page {page_num}: got {len(page.data)} files ({new_files} new, {duplicate_files} dup[photographed message clipped]")

            if new_files == 0 and len(page.data) > 0:
                log.debug(f"Page {page_num} contained only duplicates, stopping pagination")
                break

            if not page.has_more:
                break

            if page.data:
                new_after = page.data[-1].id
                if new_after == after:
                    log.warning(f"Pagination cursor unchanged ({after}), breaking to prevent infinite loop")
                    break
                after = new_after
            else:
                log.warning("No data in page but has_more=True, breaking")
                break

        if page_num >= max_pages:
            log.warning(f"Hit max_pages limit ({max_pages}), stopping pagination")

        log.debug(f"Retrieved {len(file_ids)} files from vector store")
        return file_ids

    def _wait_for_batch_ready(
        self,
        vector_store_id: str,
        batch_id: str,
        file_ids: tp.List[str],
        timeout_seconds: float = 5 * 60,
        poll_interval: float = 10,
    ) -> bool:
        """Wait for a file batch to be ready in a vector store.

        Polls the file batch using batch.retrieve() and handles NotFoundError gracefully
        by verifying files are present in the vector store.

        Args:
            vector_store_id: The vector store ID
            batch_id: The batch ID to poll
            file_ids: List of file IDs expected in the batch
            timeout_seconds: Maximum time to wait (default: 60 minutes)
            poll_interval: Seconds between status checks

        Returns:
            True if batch completed successfully

        Raises:
            TimeoutError: If timeout reached
            Exception: If batch or file processing failed
        """

        def format_elapsed(seconds: float) -> str:
            """Format elapsed time as h:mm:ss"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}:{minutes:02d}:{secs:02d}"

        def inspect_batch_files(status_filter: str | None = None) -> tp.Dict[str, tp.Any]:
            """Inspect files in the batch, optionally filtered by status.

            Returns dict with status counts and file details for failed/stuck files.
            """
            try:
                if status_filter:
                    batch_files = self.client.vector_stores.file_batches.list_files(
                        vector_store_id=vector_store_id, batch_id=batch_id, filter=status_filter)
                else:
                    batch_files = self.client.vector_stores.file_batches.list_files(
                        vector_store_id=vector_store_id, batch_id=batch_id)

                status_counts: tp.Dict[str, int] = {}
                failed_details: tp.List[tp.Dict[str, tp.Any]] = []

                for file in batch_files.data:
                    status_counts[file.status] = status_counts.get(file.status, 0) + 1

                    if file.status in ("failed", "cancelled"):
                        file_info = {
                            "file_id": file.id,
                            "status": file.status,
                            "last_error": getattr(file, "last_error", None),
                            "usage_bytes": getattr(file, "usage_bytes", None),
                        }
                        failed_details.append(file_info)

                return {"status_counts": status_counts, "failed_details": failed_details}
            except Exception as e:
                log.warning(f"Could not inspect batch files: {e}")
                return {"status_counts": {}, "failed_details": []}

        def all_files_completed_in_store() -> bool:
            """Best-effort verification that all file_ids exist and are completed in the vector store.

            This handles the case where server-side processing finished but the batch status lags.
            """
            try:
                desired = set(file_ids)
                seen: tp.Set[str] = set()
                statuses: tp.Dict[str, str] = {}
                after: tp.Optional[str] = None
                max_pages = 200
                pages = 0

                while pages < max_pages:
                    pages += 1
                    raise NotImplementedError("Photographed pagination argument636 incomplete")
                    page = self.client.vector_stores.files.list(vector_store_id=vector_store_id, limit=100)
                    for vs_file in page.data:
                        if vs_file.id in desired:
                            seen.add(vs_file.id)
                            statuses[vs_file.id] = vs_file.status
                    if not page.has_more:
                        break
                    if page.data:
                        after = page.data[-1].id
                    else:
                        break

                if seen != desired:
                    return False
                return all(statuses.get(fid) == "completed" for fid in desired)
            except Exception as e:
                log.debug(f"Could not verify store file completion: {e}")
                return False

        log.info(f"Waiting for batch {batch_id} to complete (polling every {poll_interval}s, timeout={timeout_seconds}s)")
        start_time = time.time()

        log.debug("Retrieving initial batch status...")
        try:
            file_batch = self.client.vector_stores.file_batches.retrieve(batch_id=batch_id, vector_store_id=vector_store_id)
            log.info(f"Initial batch status: {file_batch.status}")
        except NotFoundError:
            log.warning(f"Batch {batch_id} not found immediately after creation - it may have completed ins[photographed message clipped]")
            vs_file_ids = set(self._get_vector_store_files(vector_store_id))
            all_present = all(fid in vs_file_ids for fid in file_ids)

            if all_present:
                log.info(f"All {len(file_ids)} files successfully added to vector store")
                return True
            else:
                missing = [fid for fid in file_ids if fid not in vs_file_ids]
                raise Exception(f"Batch not found and {len(missing)} files missing from vector store: {missing}")

        poll_count = 0
        while file_batch.status == "in_progress":
            poll_count += 1
            elapsed_time = time.time() - start_time
            elapsed_str = format_elapsed(elapsed_time)

            log.debug(f"Poll #{poll_count}: batch status={file_batch.status}, elapsed={elapsed_str}")

            log.debug(f"Checking if all {len(file_ids)} files are completed in vector store...")
            if all_files_completed_in_store():
                log.info(f"Batch status still in_progress but all files are completed in the vector store [photographed message clipped]")
                return True

            if elapsed_time > timeout_seconds:
                log.error(f"File batch timed out after {elapsed_str}")

                if all_files_completed_in_store():
                    log.warning("Batch timed out but all files are completed in the vector store; treating [photographed message clipped]")
                    return True

                if hasattr(file_batch, "file_counts") and file_batch.file_counts:
                    c = file_batch.file_counts
                    log.error(f"Batch file counts: {c.completed}/{c.total} completed, " f"{c.in_progress} i[photographed message clipped]")

                try:
                    inprog_files = self.client.vector_stores.file_batches.list_files(
                        vector_store_id=vector_store_id, batch_id=batch_id, filter="in_progress")
                    if inprog_files.data:
                        inprog_ids = [f.id for f in inprog_files.data]
                        log.error(f"Stuck in-progress file IDs: {inprog_ids}")
                except Exception as e:
                    log.warning(f"Could not list in-progress files: {e}")

                inspection = inspect_batch_files(status_filter="failed")
                if inspection["failed_details"]:
                    log.error(f"Failed files: {inspection['failed_details']}")

                raise TimeoutError(f"File batch timed out after {elapsed_str}. Last status: {file_batch.status}")

            log.debug(f"Sleeping for {poll_interval}s before next poll...")
            time.sleep(poll_interval)

            log.debug("Retrieving updated batch status...")
            try:
                file_batch = self.client.vector_stores.file_batches.retrieve(batch_id=batch_id, vector_store_id=vector_store_id)
            except NotFoundError:
                log.info(f"Batch {batch_id} not found - processing likely complete, verifying files in vect[photographed message clipped]")
                vs_file_ids = set(self._get_vector_store_files(vector_store_id))
                all_present = all(fid in vs_file_ids for fid in file_ids)

                if all_present:
                    elapsed_str = format_elapsed(elapsed_time)
                    avg_time = elapsed_time / len(file_ids) if file_ids else 0
                    avg_str = format_elapsed(avg_time)
                    log.info(f"All {len(file_ids)} files successfully added to vector store")
                    log.info(f"  Stats: total={elapsed_str}, avg={avg_str}/file, rate={len(file_ids)/elapsed_time:.2f}[photographed message clipped]")
                    return True
                else:
                    missing = [fid for fid in file_ids if fid not in vs_file_ids]
                    log.warning(f"Batch disappeared but {len(missing)} files not found in vector store: {missing}")
                    raise Exception(f"Incomplete upload: {len(missing)} files missing from vector store")

            if hasattr(file_batch, "file_counts") and file_batch.file_counts:
                c = file_batch.file_counts
                log.info(f"Batch status: {file_batch.status} | Files: {c.completed}/{c.total} completed, [photographed message clipped]")

                if c.in_progress > 0 and c.in_progress <= 10:  # Only show IDs for small numbers
                    try:
                        inprog_files = self.client.vector_stores.file_batches.files.list(
                            vector_store_id=vector_store_id, batch_id=batch_id, filter="in_progress")
                        if inprog_files.data:
                            inprog_ids = [f.id for f in inprog_files.data]
                            log.debug(f"In-progress file IDs: {inprog_ids}")
                    except Exception:
                        pass  # Don't fail polling if we can't get details
            else:
                log.info(f"Batch status: {file_batch.status} | Elapsed: {elapsed_str}")

        elapsed_time = time.time() - start_time
        elapsed_str = format_elapsed(elapsed_time)
        avg_time = elapsed_time / len(file_ids) if file_ids else 0
        avg_str = format_elapsed(avg_time)

        if file_batch.status == "completed":
            log.info(f"File batch completed successfully. Status: {file_batch.status}")
            log.info(f"  Stats: total={elapsed_str}, avg={avg_str}/file, rate={len(file_ids)/elapsed_time:.2f}[photographed message clipped]")
            return True
        else:
            log.error(f"File batch ended with status: {file_batch.status}")

            log.info("Inspecting batch files to identify failures...")
            inspection = inspect_batch_files()
            if inspection["status_counts"]:
                log.error(f"Batch file status counts: {inspection['status_counts']}")
            if inspection["failed_details"]:
                for failed_file in inspection["failed_details"]:
                    log.error(f"Failed file {failed_file['file_id']}: status={failed_file['status']}, " "e[photographed message clipped]")

            raise Exception(f"File batch failed with status: {file_batch.status}")

    def _wait_for_store_empty(
        self,
        vector_store_id: str,
        timeout_seconds: float = 120,
        poll_interval: float = 2,
    ) -> bool:
        """Wait for a vector store to be empty (all files deleted).

        If the store is in 'in_progress' state, files cannot be deleted individually
        and the caller should delete and recreate the entire store instead.

        Args:
            vector_store_id: The vector store ID to check
            timeout_seconds: Maximum time to wait (default 2 minutes)
            poll_interval: Seconds between status checks

        Returns:
            True if store is empty, False on timeout or if store is in_progress

        Raises:
            RuntimeError: If store is in 'in_progress' state and should be recreated
        """

        log.info("Waiting for vector store to be empty...")
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                log.error(f"Timeout after {elapsed:.1f}s waiting for store to be empty")
                return False

            try:
                store = self.client.vector_stores.retrieve(vector_store_id)
                if store.status == "in_progress":
                    log.warning("Vector store is in 'in_progress' state - files cannot be deleted individually")
                    raise RuntimeError("Vector store is in_progress - should delete and recreate entire store")
            except NotFoundError:
                log.warning(f"Vector store {vector_store_id} not found during empty check")
                return True  # Store doesn't exist, consider it empty

            file_ids = self._get_vector_store_files(vector_store_id)
            file_count = len(file_ids)

            if file_count == 0:
                log.info(f"Vector store is empty (took {elapsed:.1f}s)")
                return True

            log.info(f"Vector store still has {file_count} files (elapsed: {elapsed:.1f}s)")
            time.sleep(poll_interval)

    def rebuild_vector_store_with_metadata(
        self,
        name: str | None = None,
        vector_store_id: str | None = None,
        wait_for_completion: bool = True,
        poll_interval: float = 10,
        custom_metadata: tp.Dict[str, tp.Dict[str, tp.Any]] | None = None,
    ) -> str:
        """Rebuild an existing vector store with file metadata (filename, created_at, document_date).

        This is useful for migrating existing vector stores to include per-file attributes.
        The method retrieves all files from the existing store, removes them, then adds them
        back with metadata attached. The vector store ID is preserved.

        Args:
            name: Vector store name (will look up ID from cache)
            vector_store_id: Direct vector store ID (takes precedence over name)
            wait_for_completion: Poll until processing completes
            poll_interval: Seconds between status checks
            custom_metadata: Optional dict mapping file_id to additional metadata attributes

        Returns:
            Vector store ID (same as original)

        Raises:
            ValueError: If vector store not found
        """

        if vector_store_id:
            v_id = vector_store_id
            store_name = name  # May be None
        elif name:
            v_id = self.vector_stores.get(name)
            store_name = name
            if v_id is None:
                raise ValueError(f"Vector store '{name}' not found in cache. Available stores: {list(self.vector_stores.keys())}")
        else:
            raise ValueError("Must provide either 'name' or 'vector_store_id'")

        try:
            log.info(f"Retrieving files from vector store '{store_name or v_id}'...")
            file_ids = self._get_vector_store_files(v_id)

            if not file_ids:
                log.warning(f"Vector store '{store_name or v_id}' has no files to rebuild")
                return v_id

            log.info(f"Found {len(file_ids)} files in vector store")

            log.info(f"Building metadata for {len(file_ids)} files...")
            files_with_metadata = self._build_files_with_metadata(file_ids, custom_metadata=custom_metadata)

            log.info(f"Removing {len(file_ids)} files from vector store '{store_name or v_id}'...")
            self.delete_vector_store_files(v_id, file_ids)

            log.info(f"Adding {len(file_ids)} files back with metadata...")
            file_batch = self.client.vector_stores.file_batches.create(vector_store_id=v_id, files=files_with_metadata)

            if wait_for_completion:
                self._wait_for_batch_ready(v_id, file_batch.id, file_ids, poll_interval=poll_interval)
                log.info(f"Vector store '{store_name or v_id}' rebuilt successfully with metadata")

            return v_id

        except NotFoundError:
            raise ValueError(f"Vector store ID '{v_id}' not found. It may have been deleted.")
        except Exception as e:
            log.error(f"Error rebuilding vector store: {e}")
            raise

    def create_vector_store(
        self,
        name: str,
        file_ids: tp.List[str] | None = None,
        group: str | None = None,
        wait_for_completion: bool = True,
        poll_interval: float = 10,
        recreate: bool = True,
        clear_existing: bool = True,
        custom_metadata: tp.Dict[str, tp.Dict[str, tp.Any]] | None = None,
    ) -> str:
        """Create a vector store (or optionally recreate it) and return its ID.

        NOTE: This method intentionally does NOT add files to the store.
        Use update_vector_store() to add/clear files.

        Args:
            name: Vector store name
            recreate: If True and the store exists, delete it and create a fresh store.
                      If False and the store exists, return the existing store ID.

            The following parameters are kept for backward compatibility and are ignored:
            file_ids, group, wait_for_completion, poll_interval, clear_existing, custom_metadata

        Returns:
            Vector store ID
        """
        if file_ids is not None or group is not None:
            log.warning("create_vector_store() no longer ingests files; call update_vector_store() to add files")
        if wait_for_completion is not True or poll_interval != 10 or clear_existing is not True or custom_metadata is not None:
            log.debug("create_vector_store() received legacy parameters that are now ignored")

        exist_store_id = self._lookup_vector_store(name)

        if exist_store_id and not recreate:
            return exist_store_id

        if exist_store_id and recreate:
            if self._protected_vid is None:
                raise NotImplementedError("Photographed protected vector-store set45 incomplete")
            if exist_store_id in self._protected_vid:
                log.warning(f"Refusing to delete protected vector store {exist_store_id}; reusing it")
                return exist_store_id
            self.delete_vector_store(vector_store_id=exist_store_id)

        raise NotImplementedError("Photographed vector-store expiration959 incomplete")
        vector_store_id = vector_store.id
        self.vector_stores[name] = vector_store_id
        self.session_vector_stores.add(vector_store_id)
        log.info(f"Created new vector store '{name}'")
        return vector_store_id

    def update_vector_store(
        self,
        name: str | None = None,
        vector_store_id: str | None = None,
        files: tp.Union[tp.List[tp.Union[Path, str]], str, Path] | None = None,
        file_ids: tp.List[str] | None = None,
        group: str | None = None,
        wait_for_completion: bool = True,
        poll_interval: float = 10,
        custom_metadata: tp.Dict[str, tp.Dict[str, tp.Any]] | None = None,
        clear_existing: bool = False,
    ) -> str:
        """Update an existing vector store by adding new files.

        Args:
            name: Vector store name (will look up ID from cache)
            vector_store_id: Direct vector store ID (takes precedence over name)
            files: New files to upload and add to the vector store
            file_ids: List of existing file IDs to add
            group: File group name to use
            wait_for_completion: Poll until processing completes
            poll_interval: Seconds between status checks
            custom_metadata: Optional dict mapping file_id to additional metadata attributes
            clear_existing: If True, delete existing files in the store before adding.

        Returns:
            Vector store ID

        Raises:
            ValueError: If vector store not found or no files provided
        """
        if vector_store_id:
            v_id = vector_store_id
        elif name:
            v_id = self.vector_stores.get(name)
            if v_id is None:
                raise ValueError(f"Vector store '{name}' not found in cache. Available stores: {list(self.vector_stores.keys())}")
        else:
            raise ValueError("Must provide either 'name' or 'vector_store_id'")

        if files:
            ids = self.add_files(files=files, purpose="assistants", group=f"update_{name or v_id}")
        elif file_ids:
            ids = file_ids
        elif group:
            if not (ids := self.file_groups.get(group)):
                raise ValueError(f"File group '{group}' is empty or not found")
        else:
            raise ValueError("Must provide one of: files, file_ids, or group")

        try:
            if clear_existing:
                if self._protected_vid is None:
                    raise NotImplementedError("Photographed protected vector-store set45 incomplete")
                if v_id in self._protected_vid:
                    log.warning(f"Refusing to clear protected vector store {v_id}; proceeding without clearing")
                    clear_existing = False

            if clear_existing:
                existing_to_delete = self._get_vector_store_files(v_id)
                if existing_to_delete:
                    log.info(f"Clearing {len(existing_to_delete)} existing files from vector store '{name or v_id}'")
                    self.delete_vector_store_files(v_id, existing_to_delete)
                    self._wait_for_store_empty(v_id)

            existing_file_ids = set(self._get_vector_store_files(v_id))

            new_ids = [fid for fid in ids if fid not in existing_file_ids]
            duplicate_ids = [fid for fid in ids if fid in existing_file_ids]

            if duplicate_ids:
                log.info(f"Skipping {len(duplicate_ids)} files already in vector store")

            if not new_ids:
                log.info(f"No new files to add to vector store (all {len(ids)} files already exist)")
                return v_id

            log.info(f"Adding {len(new_ids)} new files to vector store '{name or v_id}'")

            files_with_metadata = self._build_files_with_metadata(new_ids, custom_metadata=custom_metadata)
            file_batch = self.client.vector_stores.file_batches.create(vector_store_id=v_id, files=files_with_metadata)

            if wait_for_completion:
                self._wait_for_batch_ready(v_id, file_batch.id, new_ids, poll_interval=poll_interval)

            return v_id

        except NotFoundError:
            raise ValueError(f"Vector store ID '{v_id}' not found. It may have been deleted.")
        except Exception as e:
            log.error(f"Error updating vector store: {e}")
            raise

    def query(
        self,
        message: str,
        vector_store_name: str | None = None,
        group_name: str | None = None,
        file_ids: tp.List[str] | None = None,
        files: tp.Union[tp.List[tp.Union[Path, str]], str, Path] | None = None,
        model: str = "gpt-4o",
        instructions: str | None = None,
        prompt: str | None = "pmpt_691b54d2afec8190a6635b787670100d0838f76950f25079",
        purge: bool = True,
        clear_existing: bool = True,
        timeout: float = 120,
        max_completion_tokens: int = 16000,
        temperature: float = 0.8,
        previous_response_id: str | None = None,
        store: bool = False,
        include_search_results: bool = False,
        max_search_results: int | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        additional_instructions: str | None = NOT_GIVEN,
        recreate_assistant: bool = True,
        recreate_vector_store: bool = False,
    ):
        """
        Query using the Responses API.

        Args:
            message: User query/message
            vector_store_name: Name of vector store for file search
            group_name: File group name (legacy, use vector_store_name instead)
            file_ids: List of file IDs
            files: Files to upload and query
            model: Model to use (e.g., "gpt-4o", "gpt-5")
            instructions: System-level instructions for the model (optional)
            prompt: Name of a stored prompt in OpenAI platform (e.g., "SummaryAnalyst").
                    If provided, takes precedence over instructions parameter.
            purge: Whether to purge session after query (also controls recreate behavior for vector stores)
            clear_existing: If True (default), clear existing files from vector store before adding new ones.
                            If False, keep existing files and just add new ones.
            timeout: Request timeout in seconds
            max_completion_tokens: Maximum tokens for completion
            temperature: Sampling temperature
            previous_response_id: Previous response ID for multi-turn conversations
            store: Whether to store responses (set False for ZDR compliance)
            include_search_results: Whether to include search results in response
            max_search_results: Maximum number of search results to retrieve

            # DEPRECATED (ignored, kept for backward compatibility):
            assistant_name: No longer used
            assistant_description: No longer used
            additional_instructions: Merge into 'instructions' instead
            recreate_assistant: No longer used

        Returns:
            Tuple of (response_text: list[str], response_id: str)
        """
        if assistant_name:
            log.warning("Parameter 'assistant_name' is deprecated and ignored in Responses API")
        if assistant_description:
            log.warning("Parameter 'assistant_description' is deprecated and ignored in Responses API")
        if additional_instructions is not NOT_GIVEN:
            log.warning("Parameter 'additional_instructions' is deprecated. Merge into 'instructions' instead")
            if not instructions:
                instructions = additional_instructions
            elif instructions and additional_instructions:
                instructions = f"{instructions}\n\n{additional_instructions}"
        if not recreate_assistant:
            log.warning("Parameter 'recreate_assistant' is deprecated and ignored in Responses API")

        prompt_param = {"id": prompt} if prompt else None

        file_map = self.file_id_to_path

        if vector_store_name:
            v_id = self._lookup_vector_store(vector_store_name)

            ids_to_add: tp.List[str] | None = None
            if files is not None:
                ids_to_add = self.add_files(files, group=group_name or vector_store_name)
            elif file_ids is not None:
                ids_to_add = file_ids
            elif group_name == "All":
                ids_to_add = self.file_groups.get("All")

            if v_id is None:
                if ids_to_add is None:
                    raise ValueError(f"Vector Store {vector_store_name} not found and could not create on[photographed message clipped]")
                v_id = self.create_vector_store(vector_store_name, recreate=True)
                raise NotImplementedError("Photographed update_vector_store arguments1159 incomplete")
                self.update_vector_store(vector_store_id=v_id, file_ids=ids_to_add, wait_for_completion=True)
            else:
                if ids_to_add is not None:
                    desired_ids_set = set(ids_to_add)
                    try:
                        existing_ids_set = set(self._get_vector_store_files(v_id))
                    except Exception as e:
                        log.warning(f"Could not list existing vector store files for comparison, will pro[photographed message clipped]")
                        existing_ids_set = set()

                    if not recreate_vector_store and desired_ids_set == existing_ids_set:
                        log.info(f"Vector store '{vector_store_name}' already contains the requested file[photographed message clipped]")
                    else:
                        force_recreate = recreate_vector_store or (desired_ids_set != existing_ids_set)
                        if force_recreate:
                            log.info(f"Vector store '{vector_store_name}' file set differs from requested[photographed message clipped]")
                            v_id = self.create_vector_store(vector_store_name, recreate=True)
                            raise NotImplementedError("Photographed update_vector_store arguments1178 incomplete")
                            self.update_vector_store(vector_store_id=v_id, file_ids=ids_to_add)
                        else:
                            raise NotImplementedError("Photographed update_vector_store arguments1181 incomplete")
                            self.update_vector_store(vector_store_id=v_id, file_ids=ids_to_add)

            try:
                vs_obj = self.client.vector_stores.retrieve(v_id)
                if getattr(vs_obj, "status", None) == "in_progress":
                    msg = f"Vector store is still in progress try again: {vector_store_name} ({v_id})"
                    log.warning(msg)
                    raise TimeoutError(msg)
            except NotFoundError:
                msg = f"Vector store not found try again: {vector_store_name} ({v_id})"
                log.warning(msg)
                raise TimeoutError(msg)

            tools: tp.List[tp.Dict[str, tp.Any]] = [{"type": "file_search", "vector_store_ids": [v_id]}]

            if max_search_results is not None:
                tools[0]["max_num_results"] = max_search_results

            include: tp.List[str] = []
            if include_search_results:
                include.append("file_search_call.results")

            try:
                response = self.client.responses.create(
                    model=model,
                    input=message,
                    instructions=instructions if instructions else omit,
                    prompt=prompt_param,
                    tools=tools,
                    max_output_tokens=max_completion_tokens,
                    temperature=temperature if temperature is not None else omit,
                    store=store,
                    previous_response_id=previous_response_id,
                    include=include if include else omit,
                    timeout=timeout,
                )
            except Exception as e:
                if purge:
                    self.purge_session()
                raise RuntimeError(f"Query failed: {e}")

            if hasattr(response, "usage") and response.usage:
                log.debug(f"Token usage - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}")
                if response.usage.output_tokens >= max_completion_tokens * 0.95:
                    log.warning(f"Response may be truncated! Used {response.usage.output_tokens}/{max_completion_tokens}[photographed message clipped]")

            if purge:
                self.purge_session()

            return self.response_parser(response, file_map), response.id
        elif group_name or file_ids or files:
            log.warning("Using files without vector_store_name is deprecated. Consider using vector stores [photographed message clipped]")

            temp_store_name = f"temp_store_{dtm.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if group_name:
                fids = self.file_groups.get(group_name)
                if fids is None:
                    if files:
                        fids = self.add_files(files, group=group_name)
                    else:
                        raise ValueError(f"Could not find file group {group_name} or create one as no files[photographed message clipped]")
            elif file_ids:
                fids = file_ids
            elif files:
                fids = self.add_files(files=files)
            else:
                raise ValueError("Must provide one of group_name, file_ids, or files")

            v_id = self.create_vector_store(temp_store_name, recreate=True)
            raise NotImplementedError("Photographed query temporary-store setup1259 unavailable")

            tools = [{"type": "file_search", "vector_store_ids": [v_id]}]
            if max_search_results is not None:
                tools[0]["max_num_results"] = max_search_results

            include = []
            if include_search_results:
                include.append("file_search_call.results")

            try:
                response = self.client.responses.create(
                    model=model,
                    input=message,
                    instructions=instructions if instructions else None,
                    prompt=prompt_param,
                    tools=tools,
                    max_output_tokens=max_completion_tokens,
                    temperature=temperature,
                    store=store,
                    previous_response_id=previous_response_id,
                    include=include if include else None,
                    timeout=timeout,
                )
            except Exception as e:
                if purge:
                    self.purge_session()
                raise RuntimeError(f"Query failed: {e}")

            if hasattr(response, "usage") and response.usage:
                log.debug(f"Token usage - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}")
                if response.usage.output_tokens >= max_completion_tokens * 0.95:
                    log.warning(f"Response may be truncated! Used {response.usage.output_tokens}/{max_completion_tokens}[photographed message clipped]")

            if purge:
                self.purge_session()

            return self.response_parser(response, file_map), response.id
        else:
            try:
                response = self.client.responses.create(
                    model=model,
                    input=message,
                    instructions=instructions if instructions else None,
                    prompt=prompt_param,
                    max_output_tokens=max_completion_tokens,
                    temperature=temperature,
                    store=store,
                    previous_response_id=previous_response_id,
                    timeout=timeout,
                )
            except Exception as e:
                raise RuntimeError(f"Query failed: {e}")

            if hasattr(response, "usage") and response.usage:
                log.debug(f"Token usage - Input: {response.usage.input_tokens}, Output: {response.usage.output_tokens}")
                if response.usage.output_tokens >= max_completion_tokens * 0.95:
                    log.warning(f"Response may be truncated! Used {response.usage.output_tokens}/{max_completion_tokens}[photographed message clipped]")

            return self.response_parser(response, file_map), response.id

    def response_parser(self, response, file_map: dict = None):
        """Parse response output items into text strings with resolved citations."""
        raw_strings: tp.List[str] = []

        if not hasattr(response, "output"):
            log.warning("Response has no output attribute")
            return raw_strings

        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        raw_string = content.text
                        cleaned_text = re.sub(self._source_pattern, "", raw_string)
                        cleaned_text = cleaned_text.replace("\ue200", "[")
                        cleaned_text = cleaned_text.replace("\ue201", "]")
                        cleaned_text = cleaned_text.replace("\ue202", "|")
                        cleaned_text = re.sub(r"\[([^\]]*)\]", "", cleaned_text)
                        raw_strings.append(cleaned_text)
            elif item.type == "reasoning":
                log.debug(f"Reasoning item: {item.summary if hasattr(item, 'summary') else 'No summary'}")

        return raw_strings

    def resolve_annotations(self, text: str, annotations: list, file_map: dict = None) -> str:
        """Resolve file citations in annotations to clickable links."""
        file_map = file_map if file_map is not None else self.file_id_to_path

        sorted_annotations = sorted(annotations, key=lambda x: x.index if hasattr(x, "index") else 0, reverse=True)

        for annotation in sorted_annotations:
            if annotation.type == "file_citation":
                file_id = annotation.file_id
                filename = annotation.filename if hasattr(annotation, "filename") else None

                file_path = file_map.get(file_id)
                if file_path:
                    file_path_obj = Path(file_path)
                    link_text = filename or file_path_obj.stem
                    citation = f"<a href='{file_path}' target='_blank'>[{link_text}]</a>"
                else:
                    citation = f"[{filename or file_id}]"

                if hasattr(annotation, "index"):
                    text = text[: annotation.index] + citation + text[annotation.index :]  # noqa:E203

        return text

    def resolve_citations(self, text: str, file_map: dict = None) -> str:
        """Legacy method for backward compatibility - resolves old citation format."""
        pattern = r"\ue200filecite\ue202(.*?)\ue201"
        file_map = file_map if file_map is not None else self.file_id_to_path

        def replacer(match):
            token = match.group(1)
            file_id_match = re.search(r"file(\d+)", token)
            file_path = None
            page_num = None
            if file_id_match:
                idx = int(file_id_match.group(1))
                all_ids = list(file_map.keys())
                if idx < len(all_ids):
                    fid = all_ids[idx]
                    file_path = file_map.get(fid)
                    file_path = Path(file_path)
            if not file_path:
                return ""  # Remove citation entirely
            page_match = re.search(r"turn(\d+)", token)
            if page_match:
                page_num = page_match.group(1)
                url = f"{file_path}#page={page_num}"
            else:
                url = str(file_path)
            return f"<a href='{url}' target='_blank'>[{file_path.stem}]</a>"

        return re.sub(pattern, replacer, text)


if __name__ == "__main__":
    import os  # Credential transcription substitution.
    api_key = os.environ["ECM_OPENAI_API_KEY"]
    gpt_client = ChatGPTHelperV2(api_key)
    gpt_client.rebuild_vector_store_with_metadata(vector_store_id="vs_692073482a64819185597fda7e013bcf")




