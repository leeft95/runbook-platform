from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from importlib.metadata import EntryPoint, EntryPoints
from pathlib import Path

import pytest
from runbook.data import PreviousAcquisitionState, open_blob_store
from runbook.data.config import ScheduleSpec, SourceConfig
from runbook.data.ingest.adapters import get_adapter
from runbook.data.ingest.discovery import load_named_entry_point
from runbook.data.ingest.models import AcquisitionResult, RawArtifactRecord, ReadinessResult, ReadinessStatus
from runbook.data.ingest.parsers import get_parser
from runbook.data.ingest.runner import (
    load_previous_acquisition_state,
    run_stage1_acquire,
)
from runbook.data.pointers import DatasetPointerUpdate


def _config(*, adapter: str = "local_file", parser_id: str = "csv_timeseries_v1") -> SourceConfig:
    return SourceConfig(
        source_id="phase_e_source",
        adapter=adapter,
        schedule=ScheduleSpec(cron="0 * * * *"),
        datasets={"prices": {"dataset_id": "phase_e_prices", "parser_id": parser_id}},
        params={"local_path": "prices.csv", "timestamp_column": "timestamp"},
    )


def test_entry_point_loader_rejects_missing_and_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = EntryPoints()
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: missing)
    with pytest.raises(ValueError, match="group='runbook.adapters'.*name='missing'"):
        load_named_entry_point("runbook.adapters", "missing")

    duplicate = EntryPoints(
        [
            EntryPoint(name="external", value="one:Adapter", group="runbook.adapters"),
            EntryPoint(name="external", value="two:Adapter", group="runbook.adapters"),
        ]
    )
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: duplicate)
    with pytest.raises(ValueError, match="duplicate entry points"):
        load_named_entry_point("runbook.adapters", "external")

    parser_duplicate = EntryPoints(
        [
            EntryPoint(name="external_v1", value="one:Parser", group="runbook.parsers"),
            EntryPoint(name="external_v1", value="two:Parser", group="runbook.parsers"),
        ]
    )
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: parser_duplicate)
    with pytest.raises(ValueError, match="duplicate entry points"):
        get_parser("external_v1")


def test_builtin_names_reject_external_collisions(monkeypatch: pytest.MonkeyPatch) -> None:
    collision = EntryPoints([EntryPoint(name="local_file", value="one:Adapter", group="runbook.adapters")])
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: collision)
    with pytest.raises(ValueError, match="reserved by a built-in"):
        get_adapter(_config())

    parser_collision = EntryPoints([EntryPoint(name="csv_timeseries_v1", value="one:Parser", group="runbook.parsers")])
    monkeypatch.setattr("importlib.metadata.entry_points", lambda: parser_collision)
    with pytest.raises(ValueError, match="reserved by a built-in"):
        get_parser("csv_timeseries_v1")


def test_external_adapter_and_parser_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    class ExternalAdapter:
        def validate(self, source_config):
            del source_config

        def check(self, *, source_config, acquisition_run, observed_at):
            del source_config, acquisition_run, observed_at

        def acquire(self, *, source_config, readiness, fetched_at, previous_state=None):
            del source_config, readiness, fetched_at, previous_state

    def external_parser(*, source_config, dataset_alias, acquired):
        del source_config, dataset_alias, acquired
        return []

    monkeypatch.setattr(
        "runbook.data.ingest.adapters.load_named_entry_point",
        lambda group, name: ExternalAdapter if group == "runbook.adapters" and name == "external" else None,
    )
    monkeypatch.setattr(
        "runbook.data.ingest.parsers.load_named_entry_point",
        lambda group, name: external_parser if group == "runbook.parsers" and name == "external_v1" else None,
    )
    assert isinstance(get_adapter(_config(adapter="external")), ExternalAdapter)
    assert get_parser("external_v1") is external_parser


def test_external_capability_incompatibility_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("runbook.data.ingest.adapters.load_named_entry_point", lambda *_args: object())
    with pytest.raises(ValueError, match="incompatible adapter entry point"):
        get_adapter(_config(adapter="external"))

    monkeypatch.setattr("runbook.data.ingest.parsers.load_named_entry_point", lambda *_args: object())
    with pytest.raises(ValueError, match="incompatible parser entry point"):
        get_parser("external_v1")


def test_external_capability_signatures_match_keyword_invocations(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadCheck:
        def validate(self, source_config):
            del source_config

        def check(self, source_config, acquisition_run, observed_at, /):
            del source_config, acquisition_run, observed_at

        def acquire(self, *, source_config, readiness, fetched_at, previous_state=None):
            del source_config, readiness, fetched_at, previous_state

    class BadAcquire:
        def validate(self, source_config):
            del source_config

        def check(self, *, source_config, acquisition_run, observed_at):
            del source_config, acquisition_run, observed_at

        def acquire(self, source_config, readiness, fetched_at, previous_state=None, /):
            del source_config, readiness, fetched_at, previous_state

    monkeypatch.setattr("runbook.data.ingest.adapters.load_named_entry_point", lambda *_args: BadCheck)
    with pytest.raises(ValueError, match="check cannot accept"):
        get_adapter(_config(adapter="external"))
    monkeypatch.setattr("runbook.data.ingest.adapters.load_named_entry_point", lambda *_args: BadAcquire)
    with pytest.raises(ValueError, match="acquire cannot accept"):
        get_adapter(_config(adapter="external"))

    def bad_parser(source_config, dataset_alias, acquired, /):
        del source_config, dataset_alias, acquired

    monkeypatch.setattr("runbook.data.ingest.parsers.load_named_entry_point", lambda *_args: bad_parser)
    with pytest.raises(ValueError, match="public keyword contract"):
        get_parser("external_v1")


def test_public_data_and_worker_sources_have_no_private_import_boundary() -> None:
    roots = (
        Path("packages/runbook/runbook-data/src/runbook/data"),
        Path("packages/runbook/runbook-worker/src/runbook/worker"),
    )
    for root in roots:
        for source in root.rglob("*.py"):
            assert "runbook_private" not in source.read_text(encoding="utf-8")


def test_previous_state_is_frozen_and_json_serializable() -> None:
    state = PreviousAcquisitionState(
        watermark={"prices": datetime(2026, 1, 1, tzinfo=timezone.utc)},
        metadata={"partition_values": {"prices": {"venue": ["A", "B"]}}},
    )
    assert state.model_dump(mode="json")["watermark"] == {"prices": "2026-01-01T00:00:00Z"}
    with pytest.raises(Exception):
        state.watermark = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        state.metadata["new"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        state.metadata["partition_values"]["prices"]["venue"].append("C")  # type: ignore[index]
    copied = state.model_copy(update={"metadata": {"partition_values": {"prices": {"venue": ["C"]}}}})
    with pytest.raises(TypeError):
        copied.metadata["partition_values"]["prices"]["venue"].append("D")  # type: ignore[index]


def test_direct_stage1_passes_previous_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    received: list[PreviousAcquisitionState | None] = []

    class Adapter:
        def validate(self, source_config):
            pass

        def check(self, *, source_config, acquisition_run, observed_at):
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=ReadinessStatus.ready,
                observed_at=observed_at,
            )

        def acquire(self, *, source_config, readiness, fetched_at, previous_state=None):
            received.append(previous_state)
            return AcquisitionResult(
                record=RawArtifactRecord(
                    source_id=source_config.source_id,
                    acquisition_run=readiness.acquisition_run,
                    source_filename="x.csv",
                    fetched_at=fetched_at,
                ),
                payload=b"x",
            )

    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: Adapter())
    state = PreviousAcquisitionState(metadata={"partition_values": {"prices": {"venue": ["A"]}}})
    run_stage1_acquire(
        source_config=_config(),
        slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
        store=open_blob_store(f"file:{tmp_path / 'store'}"),
        previous_state=state,
    )
    assert received == [state]


def test_direct_stage1_passes_previous_state_to_compatible_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    received: list[PreviousAcquisitionState | None] = []

    class Adapter:
        def validate(self, source_config):
            pass

        def check(self, *, source_config, acquisition_run, observed_at, previous_state=None):
            received.append(previous_state)
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=ReadinessStatus.not_ready,
                observed_at=observed_at,
            )

        def acquire(self, *, source_config, readiness, fetched_at, previous_state=None):
            raise AssertionError("not-ready source must not acquire")

    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: Adapter())
    state = PreviousAcquisitionState(watermark={"prices": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    result = run_stage1_acquire(
        source_config=_config(),
        slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
        store=open_blob_store(f"file:{tmp_path / 'store'}"),
        previous_state=state,
    )
    assert result.status is ReadinessStatus.not_ready
    assert received == [state]


def test_direct_stage1_does_not_pass_previous_state_to_legacy_kwargs_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    received: list[dict[str, object]] = []

    class Adapter:
        def validate(self, source_config):
            pass

        def check(self, *, source_config, acquisition_run, observed_at, **kwargs):
            received.append(kwargs)
            return ReadinessResult(
                source_id=source_config.source_id,
                acquisition_run=acquisition_run,
                status=ReadinessStatus.not_ready,
                observed_at=observed_at,
            )

        def acquire(self, *, source_config, readiness, fetched_at, previous_state=None):
            raise AssertionError("not-ready source must not acquire")

    monkeypatch.setattr("runbook.data.ingest.runner.get_adapter", lambda _config: Adapter())
    state = PreviousAcquisitionState(watermark={"prices": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    result = run_stage1_acquire(
        source_config=_config(),
        slot=datetime(2026, 1, 1, tzinfo=timezone.utc),
        store=open_blob_store(f"file:{tmp_path / 'store'}"),
        previous_state=state,
    )
    assert result.status is ReadinessStatus.not_ready
    assert received == [{}]


def test_previous_state_materializes_all_partition_keys(tmp_path: Path, pointer_registry) -> None:
    store = open_blob_store(f"file:{tmp_path / 'store'}")
    manifest_ref = "curated/phase_e_prices/manifests/sha256=state.json"
    store.put_immutable(
        manifest_ref,
        json.dumps(
            {
                "schema_version": "dataset/1",
                "dataset_id": "phase_e_prices",
                "watermark": "2026-01-01T00:00:00Z",
                "published_at": "2026-01-01T00:00:00Z",
                "files": [
                    {
                        "ref": "one",
                        "sha256": "0" * 64,
                        "partition": {"venue": "B", "region": "EU", "ticker": "BETA"},
                    },
                    {
                        "ref": "two",
                        "sha256": "0" * 64,
                        "partition": {"venue": "A", "region": "US", "ticker": "ALPHA"},
                    },
                ],
            }
        ).encode(),
    )
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pointer_registry.publish(
        source_id="phase_e_source",
        source_run_id="old",
        updates=[
            DatasetPointerUpdate(
                dataset_id="phase_e_prices",
                manifest_ref=manifest_ref,
                watermark=when,
                published_at=when,
            )
        ],
        updated_at=when,
    )
    state = load_previous_acquisition_state(store, _config(), pointer_registry.get(["phase_e_prices"]))
    assert state is not None
    assert state.metadata == {
        "partition_values": {"prices": {"region": ["EU", "US"], "ticker": ["ALPHA", "BETA"], "venue": ["A", "B"]}}
    }


_PUBLIC_PACKAGE_ROOTS = (
    Path("packages/runbook/runbook-core"),
    Path("packages/runbook/runbook-data"),
    Path("packages/runbook/runbook-sdk"),
    Path("packages/runbook/runbook-services"),
    Path("packages/runbook/runbook-worker"),
)


def _build_isolated_site(tmp_path: Path) -> Path:
    """Build and extract public and fixture wheels into a clean site directory."""
    fixture = Path("tests/fixtures/external_plugin").resolve()
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    for package_root in (*_PUBLIC_PACKAGE_ROOTS, fixture):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--wheel",
                "--outdir",
                str(wheel_dir),
                str(package_root.resolve()),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    site = tmp_path / "isolated-site"
    site.mkdir()
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 6
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(site)
    return site


def _runtime_proof_prefix(site: Path) -> str:
    """Return a probe shared by direct and worker isolated subprocesses."""
    return """
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
sys.path.insert(0, ISOLATED_SITE)

def runtime_proof():
    site = Path(ISOLATED_SITE).resolve()
    module_names = (
        "runbook.core",
        "runbook.data",
        "runbook.sdk",
        "runbook.services",
        "runbook.worker",
        "runbook_test_plugin",
    )
    origins = {}
    for name in module_names:
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        if site not in origin.parents:
            raise AssertionError(f"{name} loaded outside isolated site: {origin}")
        origins[name] = str(origin)
    distributions = {
        name: version(name)
        for name in (
            "runbook-core",
            "runbook-data",
            "runbook-sdk",
            "runbook-services",
            "runbook-worker",
            "runbook-test-external-plugin",
        )
    }
    expected_versions = {
        "runbook-core": "0.3.2.1",
        "runbook-data": "0.3.2.1",
        "runbook-sdk": "0.3.2.1",
        "runbook-services": "0.3.2.1",
        "runbook-worker": "0.3.2.1",
        "runbook-test-external-plugin": "0.1.0",
    }
    if distributions != expected_versions:
        raise AssertionError(f"unexpected isolated distribution versions: {distributions}")
    return {"origins": origins, "distributions": distributions}
""".replace("ISOLATED_SITE", repr(str(site)))


def test_real_external_fixture_loads_in_fresh_process(tmp_path: Path) -> None:
    isolated_site = _build_isolated_site(tmp_path)
    script = (
        _runtime_proof_prefix(isolated_site)
        + """
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from runbook.data.config import ScheduleSpec, SourceConfig
from runbook.data.ingest.runner import run_ingest
from runbook.data import open_blob_store
from runbook.data.ingest import IngestRequest
from runbook.data.ingest import HistoricalExecutionContext
from runbook.data.pointers import DatabasePointerRegistry, create_pointer_schema

database = r"sqlite:///STATE_DB"
engine = create_engine(database)
create_pointer_schema(engine)
pointers = DatabasePointerRegistry(engine)
store = open_blob_store(r"file:STORE")
config = SourceConfig(
    source_id="external_source",
    adapter="test_external",
    schedule=ScheduleSpec(cron="0 * * * *"),
    datasets={"prices": {"dataset_id": "external_prices", "parser_id": "test_external_v1"}},
    params={"external_state_path": r"STATE_PATH"},
)
first = run_ingest(IngestRequest(source_config=config, run_time=datetime(2026, 1, 1, tzinfo=timezone.utc)), store=store, pointer_registry=pointers)
second = run_ingest(IngestRequest(source_config=config, run_time=datetime(2026, 1, 2, tzinfo=timezone.utc)), store=store, pointer_registry=pointers)
historical = run_ingest(
    IngestRequest(
        source_config=config,
        run_time=datetime(2026, 1, 3, tzinfo=timezone.utc),
        execution_context=HistoricalExecutionContext(start_date="2026-01-01", end_date="2026-01-02"),
    ),
    store=store,
    pointer_registry=pointers,
)
pointer = pointers.get(["external_prices"])["external_prices"]
print(json.dumps({"first": first.status.value, "second": second.status.value, "historical": historical.status.value, "pointer": pointer.manifest_ref, "state": open(r"STATE_PATH", encoding="utf-8").read(), "proof": runtime_proof()}))
""".replace("STATE_DB", str(tmp_path / "runs.db"))
        .replace("STORE", str(tmp_path / "store"))
        .replace("STATE_PATH", str(tmp_path / "state.json"))
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={},
    )
    output = json.loads(result.stdout.strip().splitlines()[-1])
    assert output["first"] == output["second"] == output["historical"] == "ready"
    assert output["pointer"].startswith("curated/external_prices/manifests/")
    state = json.loads(output["state"])
    assert state == {
        "historical_start_date": "2026-01-01",
        "historical_end_date": "2026-01-02",
    }
    assert set(output["proof"]["distributions"]) == {
        "runbook-core",
        "runbook-data",
        "runbook-sdk",
        "runbook-services",
        "runbook-worker",
        "runbook-test-external-plugin",
    }


def test_legacy_external_fixture_runs_ordinary_ingest_in_fresh_process(tmp_path: Path) -> None:
    """A pre-historical adapter remains usable through an isolated install."""
    isolated_site = _build_isolated_site(tmp_path)
    script = (
        _runtime_proof_prefix(isolated_site)
        + """
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from runbook.data import open_blob_store
from runbook.data.config import ScheduleSpec, SourceConfig
from runbook.data.ingest import IngestRequest
from runbook.data.ingest.runner import run_ingest
from runbook.data.pointers import DatabasePointerRegistry, create_pointer_schema

database = r"sqlite:///STATE_DB"
engine = create_engine(database)
create_pointer_schema(engine)
pointers = DatabasePointerRegistry(engine)
store = open_blob_store(r"file:STORE")
config = SourceConfig(
    source_id="legacy_external_source",
    adapter="test_external_legacy",
    schedule=ScheduleSpec(cron="0 * * * *"),
    datasets={"prices": {"dataset_id": "legacy_external_prices", "parser_id": "test_external_v1"}},
    params={"external_state_path": r"STATE_PATH"},
)
result = run_ingest(
    IngestRequest(source_config=config, run_time=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    store=store,
    pointer_registry=pointers,
)
pointer = pointers.get(["legacy_external_prices"])["legacy_external_prices"]
print(json.dumps({"status": result.status.value, "pointer": pointer.manifest_ref, "state": open(r"STATE_PATH", encoding="utf-8").read(), "proof": runtime_proof()}))
""".replace("STATE_DB", str(tmp_path / "runs.db"))
        .replace("STORE", str(tmp_path / "store"))
        .replace("STATE_PATH", str(tmp_path / "legacy-state.json"))
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={},
    )
    output = json.loads(result.stdout.strip().splitlines()[-1])
    assert output["status"] == "ready"
    assert output["pointer"].startswith("curated/legacy_external_prices/manifests/")
    assert json.loads(output["state"]) is None
    assert Path(output["proof"]["origins"]["runbook_test_plugin"]).is_relative_to(isolated_site)
