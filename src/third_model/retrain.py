from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from . import config
from .best_bridge import materialize_current_best_model_artifacts
from .common import write_json
from .m1_specialist_gates import materialize_m1_specialist_models


CURRENT_BEST_DEFAULT_STEPS = [
    "anomaly",
    "multi_window_anomaly",
    "risk",
    "leadtime",
    "priority",
    "report",
    "ops_eval",
]


def _tail(text: str, max_lines: int = 80) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def _tail_file(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    return _tail(path.read_text(encoding="utf-8", errors="replace"), max_lines=max_lines)


def _sanitize_local_paths(text: str) -> str:
    replacements = [
        (config.CURRENT_BEST_PYTHON_PATH, config.path_label(config.CURRENT_BEST_PYTHON_PATH, "THIRD_MODEL_CURRENT_BEST_PYTHON")),
        (config.M1_SPECIALIST_PYTHON_PATH, config.path_label(config.M1_SPECIALIST_PYTHON_PATH, "THIRD_MODEL_M1_SPECIALIST_PYTHON")),
        (config.SOURCE_BEST_ROOT, config.path_label(config.SOURCE_BEST_ROOT, "THIRD_MODEL_SOURCE_BEST_ROOT")),
        (config.THIRD_PROJECT_ROOT, config.path_label(config.THIRD_PROJECT_ROOT, "THIRD_MODEL_3RD_PROJECT_ROOT")),
        (config.PROJECT_ROOT, "."),
    ]
    result = text
    for path, label in replacements:
        try:
            raw = str(Path(path).resolve())
        except OSError:
            raw = str(path)
        result = result.replace(raw, label)
        result = result.replace(raw.replace("\\", "/"), label)
    return result


def _label_command(command: list[str]) -> list[str]:
    labeled: list[str] = []
    for part in command:
        path = Path(part)
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if exists:
            labeled.append(config.path_label(path))
        else:
            labeled.append(_sanitize_local_paths(part))
    return labeled


def _parse_step_env(name: str, default: Iterable[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [part for part in raw.replace(",", " ").split() if part]


def _resolve_predist_zip_source() -> Path | None:
    env_path = os.environ.get("THIRD_MODEL_PREDIST_ZIP_PATH")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.extend(
        [
            config.PROJECT_ROOT / "data" / "_downloads" / "predist_dataset.zip",
            config.SOURCE_BEST_ROOT.parent / "data" / "_downloads" / "predist_dataset.zip",
            config.SOURCE_BEST_ROOT / "data" / "_downloads" / "predist_dataset.zip",
            config.SOURCE_BEST_ROOT / "data" / "raw_data" / "predist_dataset.zip",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _third_project_data_dir(root: Path) -> Path:
    return next(path for path in root.iterdir() if path.is_dir() and path.name.startswith("05_"))


def _materialize_predist_zip_for_m1_source(root: Path) -> dict[str, object]:
    data_dir = _third_project_data_dir(root)
    target = data_dir / "PreDist" / "predist_dataset.zip"
    if target.exists():
        return {
            "status": "already_present",
            "source": config.path_label(target),
            "target": config.path_label(target),
            "size_bytes": int(target.stat().st_size),
        }
    source = _resolve_predist_zip_source()
    if source is None:
        raise FileNotFoundError(
            "Missing predist_dataset.zip for M1 specialist retraining. "
            "Set THIRD_MODEL_PREDIST_ZIP_PATH or place the file under "
            "data/_downloads/predist_dataset.zip in the package/source project."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "status": "copied",
        "source": config.path_label(source, "THIRD_MODEL_PREDIST_ZIP_PATH"),
        "target": config.path_label(target),
        "size_bytes": int(target.stat().st_size),
    }


def _is_git_worktree(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _m1_script_command(root: Path, script: Path, patch_git_status: bool) -> list[str]:
    script_arg = script.relative_to(root).as_posix()
    if not patch_git_status:
        return [str(config.M1_SPECIALIST_PYTHON_PATH), script_arg]
    code = (
        "import runpy, subprocess\n"
        "_real_check_output = subprocess.check_output\n"
        "def _patched_check_output(args, *pargs, **kwargs):\n"
        "    if isinstance(args, (list, tuple)) and len(args) >= 2 and args[0] == 'git' and args[1] == 'status':\n"
        "        return '' if kwargs.get('text') or kwargs.get('encoding') else b''\n"
        "    if isinstance(args, (list, tuple)) and len(args) >= 2 and args[0] == 'git' and args[1] == 'rev-parse':\n"
        "        return 'unknown\\n' if kwargs.get('text') or kwargs.get('encoding') else b'unknown\\n'\n"
        "    return _real_check_output(args, *pargs, **kwargs)\n"
        "subprocess.check_output = _patched_check_output\n"
        f"namespace = runpy.run_path({script_arg!r})\n"
        "namespace['main']()\n"
    )
    return [str(config.M1_SPECIALIST_PYTHON_PATH), "-c", code]


def _run_command(command: list[str], cwd: Path, log_name: str, env: dict[str, str] | None = None) -> dict[str, object]:
    config.ensure_dirs()
    log_path = config.RETRAIN_LOG_DIR / f"{log_name}.log"
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("command: " + " ".join(_label_command(command)) + "\n")
        log.write("cwd: " + config.path_label(cwd) + "\n\n")
        log.flush()
        result = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    sanitized_log_text = _sanitize_local_paths(log_text)
    if sanitized_log_text != log_text:
        log_path.write_text(sanitized_log_text, encoding="utf-8")
    log_tail = _tail_file(log_path)
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(command)
            + f"\nCWD: {config.path_label(cwd)}"
            + f"\nLog: {config.path_label(log_path)}"
            + f"\nLog tail:\n{log_tail}"
        )
    return {
        "returncode": result.returncode,
        "log_path": config.path_label(log_path),
        "log_tail": log_tail,
    }


def retrain_current_best_source() -> dict[str, object]:
    """Retrain current-best anomaly/risk/leadtime/priority in its source project.

    This is the full regeneration path for the baseline body that the M1
    specialist package imports. Raw point autoencoder is excluded by default
    because it is not part of the final M1 agent contract; set
    THIRD_MODEL_INCLUDE_RAW_AE=1 or override THIRD_MODEL_RETRAIN_CURRENT_BEST_STEPS
    when that experimental branch needs to be reproduced.
    """
    config.ensure_dirs()
    root = config.SOURCE_BEST_ROOT
    script = root / "run_best_pipeline.py"
    if not script.exists():
        raise FileNotFoundError(
            "Cannot retrain current-best source because run_best_pipeline.py was not found at "
            + config.path_label(script, "THIRD_MODEL_SOURCE_BEST_ROOT")
        )

    default_steps = list(CURRENT_BEST_DEFAULT_STEPS)
    include_raw_ae = os.environ.get("THIRD_MODEL_INCLUDE_RAW_AE", "").lower() in {"1", "true", "yes", "y"}
    if include_raw_ae and "raw_ae" not in default_steps:
        default_steps.insert(2, "raw_ae")
    steps = _parse_step_env("THIRD_MODEL_RETRAIN_CURRENT_BEST_STEPS", default_steps)
    command = [str(config.CURRENT_BEST_PYTHON_PATH), "run_best_pipeline.py", "--steps", *steps]
    result = _run_command(command, root, "retrain_current_best")
    artifact_payload = materialize_current_best_model_artifacts()
    payload = {
        "stage": "retrain_current_best",
        "source_best_root": config.path_label(root, "THIRD_MODEL_SOURCE_BEST_ROOT"),
        "command": _label_command(command),
        "python_executable": config.path_label(config.CURRENT_BEST_PYTHON_PATH, "THIRD_MODEL_CURRENT_BEST_PYTHON"),
        "steps": steps,
        "raw_ae_included": include_raw_ae or "raw_ae" in steps,
        "log_path": result["log_path"],
        "log_tail": result["log_tail"],
        "materialized_artifacts": artifact_payload,
        "outputs_expected": {
            "risk_scores": config.path_label(config.SOURCE_RISK_SCORES_PATH),
            "leadtime_scores": config.path_label(config.SOURCE_LEADTIME_SCORES_PATH),
            "priority_scores": config.path_label(config.SOURCE_PRIORITY_SCORES_PATH),
            "risk_model": config.path_label(config.SOURCE_RISK_MODEL_PATH),
            "leadtime_model": config.path_label(config.SOURCE_LEADTIME_MODEL_PATH),
            "priority_metadata": config.path_label(config.SOURCE_PRIORITY_METADATA_PATH),
        },
    }
    write_json(config.SOURCE_RETRAIN_METADATA_PATH, payload)
    return payload


def retrain_m1_specialist_source() -> dict[str, object]:
    """Retrain the original M1 specialist gate models, then refresh packaged artifacts."""
    config.ensure_dirs()
    root = config.THIRD_PROJECT_ROOT
    script = root / "scripts" / "run_34_full_gate_joblib_xai4heat_scada_runtime_validation.py"
    if not script.exists():
        raise FileNotFoundError(
            "Cannot retrain M1 specialist source because the runtime validation script was not found at "
            + config.path_label(script, "THIRD_MODEL_3RD_PROJECT_ROOT")
        )

    predist_zip = _materialize_predist_zip_for_m1_source(root)
    source_is_git = _is_git_worktree(root)
    command = _m1_script_command(root, script, patch_git_status=not source_is_git)
    result = _run_command(command, root, "retrain_m1_specialist")
    copied = materialize_m1_specialist_models(force=True)
    payload = {
        "stage": "retrain_m1_specialist",
        "third_project_root": config.path_label(root, "THIRD_MODEL_3RD_PROJECT_ROOT"),
        "predist_zip": predist_zip,
        "source_is_git_worktree": source_is_git,
        "git_status_patch_used": not source_is_git,
        "command": _label_command(command),
        "log_path": result["log_path"],
        "log_tail": result["log_tail"],
        "materialized_models": copied,
        "outputs_expected": {
            "fault_gate": "models/m1_specialist/m1_fault_gate_rf_depth3.joblib",
            "task_gate": "models/m1_specialist/m1_task_gate_rf_depth3.joblib",
            "activity_gate": "models/m1_specialist/m1_activity_gate_rf_depth3.joblib",
            "fault_pre_event_gate": "models/m1_specialist/m1_fault_pre_event_logistic.joblib",
            "runtime_metadata": "models/m1_specialist/m1_full_gate_runtime_policy_metadata.json",
        },
    }
    write_json(config.M1_SOURCE_RETRAIN_METADATA_PATH, payload)
    return payload


def retrain_sources() -> dict[str, object]:
    """Retrain both upstream source model groups used by the final M1 package."""
    return {
        "current_best": retrain_current_best_source(),
        "m1_specialist": retrain_m1_specialist_source(),
    }
