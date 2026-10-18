"""Immutable filesystem destination for one run, independent of navigation.

This constrains built-in file tools; it is not an OS sandbox for generated code.
"""

from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath


FILE_TASKS = frozenset({
    "write_web_file", "assemble_and_preview", "run_web_project",
    "write_project_file", "assemble_and_run", "batch_write_files",
    "generate_and_execute", "edit_file", "run_file", "execute_code", "search_project",
})
EXISTING_TASKS = frozenset({"edit_file", "run_file", "run_web_project", "search_project"})


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or value == "." or "\\" in value:
        raise ValueError("La destination doit être un chemin relatif explicite")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {".", ".."} for p in path.parts):
        raise ValueError("Chemin de destination non canonique ou hors workspace")
    return value


@dataclass(frozen=True)
class ExecutionTarget:
    mode: str
    path: str
    root: str
    device: int | None = None
    inode: int | None = None

    @property
    def directory(self) -> Path:
        return Path(self.root) / self.path

    def public(self) -> dict:
        return {"mode": self.mode, "path": self.path}

    def to_payload(self) -> dict:
        return {**self.public(), "root": self.root, "device": self.device, "inode": self.inode}

    def validate(self) -> None:
        if self.mode not in {"new", "existing"}:
            raise ValueError("Mode de destination invalide (new ou existing requis)")
        relative_path(self.path)
        root = Path(self.root)
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("Racine de destination invalide")
        current = root
        for part in PurePosixPath(self.path).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Un lien symbolique ne peut pas être une destination de run")
        if self.mode == "new" and self.inode is None:
            if self.directory.exists():
                raise ValueError(f"Le dossier {self.path} existe déjà : choisir explicitement une modification ou un autre dossier")
        else:
            if not self.directory.is_dir():
                raise ValueError(f"Destination disparue : {self.path}")
            if self.inode is not None:
                stat = self.directory.stat()
                if (stat.st_dev, stat.st_ino) != (self.device, self.inode):
                    raise ValueError("La destination du run a été remplacée depuis sa préparation")

    def prepare(self) -> "ExecutionTarget":
        self.validate()
        if self.mode == "new" and self.inode is None:
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            self.validate()
            self.directory.mkdir()  # exclusive reservation, only after approval
        stat = self.directory.stat()
        return replace(self, device=stat.st_dev, inode=stat.st_ino)

    def file(self, value: str) -> Path:
        relative_path(value)
        self.validate()
        current = self.directory
        for part in PurePosixPath(value).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Un outil de fichier ne peut pas suivre un lien symbolique")
        return current


def resolve_target(plan_id: str, task_data: dict, subtasks: list, project_spec=None) -> ExecutionTarget | None:
    files = [st for st in subtasks if st.payload.get("type") in FILE_TASKS]
    if not files:
        return None  # research/taskboard never inherit a project
    from .web.fs_api import workspace_root
    root = workspace_root().resolve()
    choice = task_data.get("project_target")
    if choice is not None and not isinstance(choice, dict):
        raise ValueError("project_target doit préciser mode et path")
    if choice is None:
        # Only explicit execution fields, never selected/navigation project.
        explicit = task_data.get("project_path")
        if explicit:
            choice = {"mode": "existing", "path": explicit}
        elif any(st.payload.get("type") in EXISTING_TASKS for st in files):
            web = next((st for st in files if st.payload.get("type") == "run_web_project"), None)
            name = web.payload.get("project_name") if web else None
            if name:
                choice = {"mode": "existing", "path": name if "/" in name else f"sandbox/{name}"}
            else:
                raise ValueError("Préciser le projet à modifier/exécuter avec project_target={mode: existing, path: ...}")
        else:
            choice = {"mode": "new"}
    mode = choice.get("mode")
    path = choice.get("path")
    if mode == "new" and not path:
        name = project_spec.project_name if project_spec else f"run-{plan_id}"
        relative_path(name)
        if "/" in name or name.startswith("."):
            raise ValueError("Le nom du nouveau projet doit être un seul dossier descriptif")
        path = f"sandbox/{name}"
    if not isinstance(path, str) or any(p.startswith(".") for p in PurePosixPath(path).parts):
        raise ValueError("Chemin de projet explicite requis, sans dossier caché")
    target = ExecutionTarget(mode, path, str(root))
    target.validate()
    if mode == "existing":
        manifest = target.file(".project.json")
        if not manifest.is_file():
            raise ValueError("Le projet existant doit posséder un manifeste .project.json")
        target = target.prepare()  # pin identity now; creates nothing in existing mode
    return target
