"""
toolref.py — 科学计算工具文档知识库
====================================

多版本工具文档管理：拉取（fetch）、版本切换（use）、精确查看（show）、
全文搜索（search）。数据存储在 ``data/toolref/<tool>/<version>/``，
``current`` 符号链接指向当前活跃版本。

支持的工具及文档格式：
- Quantum ESPRESSO: ``.def`` 文件（Tcl-like DSL，机器可解析参数定义）
- LAMMPS: ``.rst`` 文件（Sphinx reStructuredText，每命令一文件）
- GROMACS: ``.rst`` 文件（Sphinx，含自定义 ``.. mdp::`` 指令）

用法::

    from scholaraio.toolref import toolref_fetch, toolref_show, toolref_search
    toolref_fetch("qe", version="7.5")
    result = toolref_show("qe", "pw", "ecutwfc")
    results = toolref_search("qe", "wavefunction cutoff")
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from scholaraio.log import ui

if TYPE_CHECKING:
    from scholaraio.config import Config

_log = logging.getLogger(__name__)

_DEFAULT_TOOLREF_DIR = Path("data/toolref")

# ============================================================================
#  Tool registry — maps tool name to repo/doc-path/format metadata
# ============================================================================

TOOL_REGISTRY: dict[str, dict] = {
    "qe": {
        "display_name": "Quantum ESPRESSO",
        "repo": "https://github.com/QEF/q-e.git",
        "tag_prefix": "qe-",
        "doc_path": None,  # scattered across */Doc/
        "doc_glob": "**/INPUT_*.def",
        "format": "def",
    },
    "lammps": {
        "display_name": "LAMMPS",
        "repo": "https://github.com/lammps/lammps.git",
        "tag_prefix": "stable_",
        "doc_path": "doc/src",
        "doc_glob": "*.rst",
        "format": "rst",
    },
    "gromacs": {
        "display_name": "GROMACS",
        "repo": "https://github.com/gromacs/gromacs.git",
        "tag_prefix": "release-",
        "doc_path": "docs",
        "doc_glob": "**/*.rst",
        "format": "rst",
    },
}

# ============================================================================
#  Path helpers
# ============================================================================


def _toolref_root(cfg: Config | None = None) -> Path:
    if cfg is not None:
        return cfg._root / "data" / "toolref"
    return _DEFAULT_TOOLREF_DIR


def _tool_dir(tool: str, cfg: Config | None = None) -> Path:
    return _toolref_root(cfg) / tool


def _version_dir(tool: str, version: str, cfg: Config | None = None) -> Path:
    return _tool_dir(tool, cfg) / version


def _current_link(tool: str, cfg: Config | None = None) -> Path:
    return _tool_dir(tool, cfg) / "current"


def _db_path(tool: str, cfg: Config | None = None) -> Path:
    return _tool_dir(tool, cfg) / "toolref.db"


def validate_tool_name(name: str) -> bool:
    """Return True if *name* is a known, safe tool identifier."""
    return name in TOOL_REGISTRY


def _validate_version(version: str) -> bool:
    if not version or os.path.isabs(version):
        return False
    return "/" not in version and "\\" not in version and ".." not in version


# ============================================================================
#  DB schema
# ============================================================================

_PAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS toolref_pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool        TEXT NOT NULL,
    version     TEXT NOT NULL,
    program     TEXT,
    section     TEXT,
    page_name   TEXT NOT NULL,
    title       TEXT,
    category    TEXT,
    var_type    TEXT,
    default_val TEXT,
    synopsis    TEXT,
    content     TEXT NOT NULL,
    UNIQUE(tool, version, page_name)
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS toolref_fts USING fts5(
    page_name,
    title,
    synopsis,
    content,
    content=toolref_pages,
    content_rowid=id,
    tokenize='unicode61'
);
"""

_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS toolref_ai AFTER INSERT ON toolref_pages BEGIN
    INSERT INTO toolref_fts(rowid, page_name, title, synopsis, content)
    VALUES (new.id, new.page_name, new.title, new.synopsis, new.content);
END;

CREATE TRIGGER IF NOT EXISTS toolref_ad AFTER DELETE ON toolref_pages BEGIN
    INSERT INTO toolref_fts(toolref_fts, rowid, page_name, title, synopsis, content)
    VALUES ('delete', old.id, old.page_name, old.title, old.synopsis, old.content);
END;

CREATE TRIGGER IF NOT EXISTS toolref_au AFTER UPDATE ON toolref_pages BEGIN
    INSERT INTO toolref_fts(toolref_fts, rowid, page_name, title, synopsis, content)
    VALUES ('delete', old.id, old.page_name, old.title, old.synopsis, old.content);
    INSERT INTO toolref_fts(rowid, page_name, title, synopsis, content)
    VALUES (new.id, new.page_name, new.title, new.synopsis, new.content);
END;
"""


def _ensure_db(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_PAGES_SCHEMA)
    conn.executescript(_FTS_SCHEMA)
    conn.executescript(_FTS_TRIGGERS)
    return conn


# ============================================================================
#  QE .def parser
# ============================================================================


def _parse_qe_def(filepath: Path) -> list[dict]:
    """Parse a Quantum ESPRESSO .def file into a list of variable records.

    Each record represents one input parameter with fields:
    program, section (namelist), page_name, title, category, var_type,
    default_val, synopsis, content (full text block).
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")

    # extract program name from input_description line
    m = re.search(r"-program\s+(\S+)", text)
    program = m.group(1).strip("{}") if m else filepath.stem.replace("INPUT_", "").lower()

    records: list[dict] = []
    current_namelist = ""

    # state machine for brace-balanced parsing
    def _extract_braced(s: str, start: int) -> tuple[str, int]:
        """Extract content between balanced braces starting at s[start]='{'.
        Returns (content, end_index)."""
        if start >= len(s) or s[start] != "{":
            return "", start
        depth = 0
        i = start
        while i < len(s):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return s[start + 1 : i], i + 1
            i += 1
        return s[start + 1 :], len(s)

    def _clean_text(t: str) -> str:
        """Strip QE markup (@b, @i, @ref, @tt, @br) and normalize whitespace."""
        t = re.sub(r"@b\s*\{([^}]*)\}", r"\1", t)
        t = re.sub(r"@i\s*\{([^}]*)\}", r"\1", t)
        t = re.sub(r"@ref\s+(\w+)", r"\1", t)
        t = re.sub(r"@tt\s*\{([^}]*)\}", r"\1", t)
        t = re.sub(r"@br\b", "\n", t)
        t = re.sub(r"@[a-z]+\s*", "", t)
        return textwrap.dedent(t).strip()

    def _parse_var_block(block: str, var_name: str) -> dict:
        """Parse a var {...} block, extracting type, default, info, options."""
        # type
        vtype = ""
        tm = re.search(r"-type\s+(\S+)", block)
        if tm:
            vtype = tm.group(1)

        # status
        status = ""
        sm = re.search(r"status\s*\{([^}]*)\}", block)
        if sm:
            status = sm.group(1).strip()

        # default
        default_val = ""
        dm = re.search(r"default\s*\{", block)
        if dm:
            default_val, _ = _extract_braced(block, dm.start() + len("default "))
            default_val = _clean_text(default_val)

        # info
        info_text = ""
        im = re.search(r"info\s*\{", block)
        if im:
            info_text, _ = _extract_braced(block, im.start() + len("info "))
            info_text = _clean_text(info_text)

        # options
        options_text = ""
        om = re.search(r"options\s*\{", block)
        if om:
            options_text, _ = _extract_braced(block, om.start() + len("options "))
            # extract opt -val entries
            opts = re.findall(r"opt\s+-val\s+'([^']+)'", options_text)
            if opts:
                options_text = "Options: " + ", ".join(opts)
                # also extract any info inside options
                oi = re.findall(r"info\s*\{([^}]*)\}", options_text)
                if oi:
                    options_text += "\n" + _clean_text(" ".join(oi))

        # build synopsis
        parts = []
        if vtype:
            parts.append(f"Type: {vtype}")
        if default_val:
            parts.append(f"Default: {default_val}")
        if status:
            parts.append(f"Status: {status}")
        synopsis = "; ".join(parts) if parts else ""

        # build full content
        content_parts = []
        if synopsis:
            content_parts.append(synopsis)
        if info_text:
            content_parts.append(info_text)
        if options_text:
            content_parts.append(options_text)
        content = "\n\n".join(content_parts)

        return {
            "var_type": vtype,
            "default_val": default_val,
            "synopsis": synopsis,
            "content": content if content else f"{var_name}: {vtype}",
        }

    # scan for namelist and var/dimension/vargroup declarations
    pos = 0
    while pos < len(text):
        # match namelist
        nm = re.match(r"\s*namelist\s+(\w+)\s*\{", text[pos:])
        if nm:
            current_namelist = nm.group(1)
            pos += nm.end()
            continue

        # match var
        vm = re.match(r"\s*var\s+([\w()]+)\s*(?:-type\s+(\S+))?\s*\{", text[pos:])
        if vm:
            var_name = vm.group(1)
            brace_start = pos + vm.end() - 1
            block, end = _extract_braced(text, brace_start)
            parsed = _parse_var_block(
                f"-type {vm.group(2)} " + block if vm.group(2) else block,
                var_name,
            )
            page_name = f"{program}/{current_namelist}/{var_name}".strip("/")
            records.append(
                {
                    "program": program,
                    "section": current_namelist,
                    "page_name": page_name,
                    "title": var_name,
                    "category": "variable",
                    **parsed,
                }
            )
            pos = end
            continue

        # match dimension (array variable)
        dm = re.match(r"\s*dimension\s+([\w()]+)\s+.*?-type\s+(\S+)\s*\{", text[pos:])
        if dm:
            var_name = dm.group(1)
            brace_start = pos + dm.end() - 1
            block, end = _extract_braced(text, brace_start)
            parsed = _parse_var_block(f"-type {dm.group(2)} " + block, var_name)
            page_name = f"{program}/{current_namelist}/{var_name}".strip("/")
            records.append(
                {
                    "program": program,
                    "section": current_namelist,
                    "page_name": page_name,
                    "title": var_name,
                    "category": "dimension",
                    **parsed,
                }
            )
            pos = end
            continue

        # match vargroup
        vgm = re.match(r"\s*vargroup\s+.*?-type\s+(\S+)\s*\{", text[pos:])
        if vgm:
            brace_start = pos + vgm.end() - 1
            block, end = _extract_braced(text, brace_start)
            # extract var names inside vargroup
            vg_vars = re.findall(r"var\s+(\w+)", block)
            if vg_vars:
                parsed = _parse_var_block(
                    f"-type {vgm.group(1)} " + block,
                    ", ".join(vg_vars),
                )
                for vn in vg_vars:
                    page_name = f"{program}/{current_namelist}/{vn}".strip("/")
                    records.append(
                        {
                            "program": program,
                            "section": current_namelist,
                            "page_name": page_name,
                            "title": vn,
                            "category": "vargroup",
                            **parsed,
                        }
                    )
            pos = end
            continue

        # match card (store as a single record with its full content)
        cm = re.match(r"\s*card\s+([\w_]+)\s*\{", text[pos:])
        if cm:
            card_name = cm.group(1)
            brace_start = pos + cm.end() - 1
            block, end = _extract_braced(text, brace_start)
            page_name = f"{program}/card/{card_name}"
            records.append(
                {
                    "program": program,
                    "section": "card",
                    "page_name": page_name,
                    "title": card_name,
                    "category": "card",
                    "var_type": "",
                    "default_val": "",
                    "synopsis": f"Input card: {card_name}",
                    "content": _clean_text(block)[:4000],
                }
            )
            pos = end
            continue

        pos += 1

    return records


# ============================================================================
#  LAMMPS RST parser
# ============================================================================


def _parse_lammps_rst(filepath: Path) -> list[dict]:
    """Parse a LAMMPS .rst documentation file into records.

    Each LAMMPS doc file typically documents one command (fix, compute,
    pair_style, etc.) with sections: Syntax, Examples, Description,
    Restrictions, Related commands, Default.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    stem = filepath.stem  # e.g. "fix_nh", "pair_lj"

    # extract command names from index directives
    commands = re.findall(r"\.\.\s+index::\s+(.+)", text)
    # filter out accelerator variants
    commands = [
        c.strip()
        for c in commands
        if "/gpu" not in c and "/intel" not in c and "/kk" not in c and "/omp" not in c and "/opt" not in c
    ]

    # extract first title (the primary command)
    title_match = re.search(r"^(.+?)\n={3,}", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else stem

    # detect command category from filename
    category = "other"
    for prefix in (
        "fix_",
        "compute_",
        "pair_",
        "bond_",
        "angle_",
        "dihedral_",
        "improper_",
        "dump_",
        "region_",
        "group_",
    ):
        if stem.startswith(prefix):
            category = prefix.rstrip("_")
            break

    # split into sections by RST headings (""" underlined)
    sections: dict[str, str] = {}
    section_pattern = re.compile(r'^(.+)\n"{3,}', re.MULTILINE)
    matches = list(section_pattern.finditer(text))
    for i, m in enumerate(matches):
        sec_name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[sec_name.lower()] = text[start:end].strip()

    # build synopsis from Syntax section
    synopsis = ""
    if "syntax" in sections:
        # extract first code-block content
        cb = re.search(r"\.\.\s+code-block::\s+LAMMPS\s*\n\n((?:\s+.+\n?)+)", sections["syntax"])
        if cb:
            synopsis = cb.group(1).strip().split("\n")[0].strip()

    # build full content (Syntax + Description, truncated)
    content_parts = []
    if "syntax" in sections:
        content_parts.append("Syntax:\n" + sections["syntax"][:1000])
    if "description" in sections:
        content_parts.append("Description:\n" + sections["description"][:3000])
    if "restrictions" in sections:
        content_parts.append("Restrictions:\n" + sections["restrictions"][:500])
    if "default" in sections:
        content_parts.append("Default:\n" + sections["default"][:300])
    content = "\n\n".join(content_parts) if content_parts else text[:2000]

    records = [
        {
            "program": "lammps",
            "section": category,
            "page_name": f"lammps/{stem}",
            "title": title,
            "category": category,
            "var_type": "",
            "default_val": sections.get("default", "")[:200].strip(),
            "synopsis": synopsis,
            "content": content,
        }
    ]

    return records


# ============================================================================
#  GROMACS RST parser
# ============================================================================


def _parse_gromacs_rst(filepath: Path) -> list[dict]:
    """Parse a GROMACS .rst documentation file.

    For mdp-options.rst: extract each MDP parameter as a separate record.
    For other files: store as a single record per file.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    stem = filepath.stem
    records: list[dict] = []

    # Special handling for mdp-options.rst (the core parameter reference)
    if stem == "mdp-options":
        # Parse .. mdp:: directive blocks
        mdp_pattern = re.compile(
            r"\.\.\s+mdp::\s+(\S+)\s*\n((?:.*\n)*?)"
            r"(?=\.\.\s+mdp::|$)",
            re.MULTILINE,
        )
        for m in mdp_pattern.finditer(text):
            param_name = m.group(1).strip()
            block = m.group(2)

            # extract mdp-value options
            values = re.findall(r"\.\.\s+mdp-value::\s+(\S+)", block)

            # clean the description
            desc = re.sub(r"\.\.\s+mdp-value::\s+\S+", "", block)
            desc = re.sub(r"\s+", " ", desc).strip()[:2000]

            synopsis = "MDP parameter"
            if values:
                synopsis += f" | Options: {', '.join(values[:8])}"

            records.append(
                {
                    "program": "gromacs",
                    "section": "mdp",
                    "page_name": f"gromacs/mdp/{param_name}",
                    "title": param_name,
                    "category": "mdp",
                    "var_type": "",
                    "default_val": "",
                    "synopsis": synopsis,
                    "content": f"{param_name}\n\n{block.strip()[:3000]}",
                }
            )
        return records

    # For non-MDP files: store the whole file as one record
    # extract title
    title_match = re.search(r"^(.+?)\n={3,}", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else stem

    # determine section from path-like info in the file or filename
    section = "general"
    if "user-guide" in str(filepath):
        section = "user-guide"
    elif "reference-manual" in str(filepath):
        section = "reference-manual"
    elif "how-to" in str(filepath):
        section = "how-to"

    records.append(
        {
            "program": "gromacs",
            "section": section,
            "page_name": f"gromacs/{section}/{stem}",
            "title": title,
            "category": section,
            "var_type": "",
            "default_val": "",
            "synopsis": title,
            "content": text[:5000],
        }
    )
    return records


# ============================================================================
#  Fetch: clone repo → extract docs → index
# ============================================================================


def toolref_fetch(
    tool: str,
    *,
    version: str | None = None,
    cfg: Config | None = None,
) -> int:
    """Fetch documentation for a tool at a specific version.

    Args:
        tool: Tool name (e.g. 'qe', 'lammps', 'gromacs').
        version: Version string. If None, uses the latest tag.
        cfg: Optional Config.

    Returns:
        Number of pages indexed.
    """
    if not validate_tool_name(tool):
        raise ValueError(f"未知工具：{tool}。支持的工具：{', '.join(TOOL_REGISTRY)}")

    info = TOOL_REGISTRY[tool]

    if version and not _validate_version(version):
        raise ValueError(f"无效版本号：{version}")

    # check if already fetched
    if version:
        vdir = _version_dir(tool, version, cfg)
        if vdir.exists():
            ui(f"[toolref] {info['display_name']} {version} 文档已存在，跳过拉取")
            count = _index_tool(tool, version, cfg)
            _set_current(tool, version, cfg)
            ui(f"[toolref] {info['display_name']} {version}：已索引 {count} 个文档页面")
            return count

    # determine git tag
    tag = None
    if version:
        tag = f"{info['tag_prefix']}{version}"

    # clone to temp dir
    import tempfile

    with tempfile.TemporaryDirectory(prefix=f"toolref-{tool}-") as tmpdir:
        clone_cmd = ["git", "clone", "--depth", "1"]
        if tag:
            clone_cmd += ["--branch", tag]
        clone_cmd += [info["repo"], tmpdir]

        ui(f"[toolref] 正在拉取 {info['display_name']} {version or 'latest'} 文档...")
        try:
            subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            _log.error("git clone 失败：%s", e.stderr[:500])
            raise RuntimeError(f"拉取 {tool} 文档失败。请检查版本号和网络。") from e

        # detect version from tag if not specified
        if not version:
            try:
                result = subprocess.run(
                    ["git", "-C", tmpdir, "describe", "--tags", "--abbrev=0"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                detected_tag = result.stdout.strip()
                version = detected_tag.removeprefix(info["tag_prefix"])
            except subprocess.CalledProcessError:
                version = "latest"

        vdir = _version_dir(tool, version, cfg)
        vdir.mkdir(parents=True, exist_ok=True)

        # extract docs based on format
        tmppath = Path(tmpdir)
        if info["format"] == "def":
            dest = vdir / "def"
            dest.mkdir(exist_ok=True)
            for f in tmppath.rglob(info["doc_glob"]):
                (dest / f.name).write_bytes(f.read_bytes())
                _log.debug("提取: %s", f.name)
        elif info["doc_path"]:
            src = tmppath / info["doc_path"]
            if src.exists():
                dest = vdir / "src"
                import shutil

                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                _log.warning("文档路径不存在: %s", src)

    # write meta.json
    meta = {
        "tool": tool,
        "display_name": info["display_name"],
        "version": version,
        "format": info["format"],
        "repo": info["repo"],
    }
    (vdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # create/update current symlink
    _set_current(tool, version, cfg)

    # index
    count = _index_tool(tool, version, cfg)
    ui(f"[toolref] {info['display_name']} {version}：已索引 {count} 个文档页面")
    return count


# ============================================================================
#  Indexing
# ============================================================================


def _index_tool(tool: str, version: str, cfg: Config | None = None) -> int:
    """Parse and index all doc pages for a tool version."""
    vdir = _version_dir(tool, version, cfg)
    db = _db_path(tool, cfg)
    conn = _ensure_db(db)

    # clear old entries for this version
    conn.execute(
        "DELETE FROM toolref_pages WHERE tool = ? AND version = ?",
        (tool, version),
    )

    records: list[dict] = []
    info = TOOL_REGISTRY[tool]

    if info["format"] == "def":
        def_dir = vdir / "def"
        if def_dir.exists():
            for f in sorted(def_dir.glob("INPUT_*.def")):
                try:
                    parsed = _parse_qe_def(f)
                    records.extend(parsed)
                    _log.debug("解析 %s: %d 条记录", f.name, len(parsed))
                except Exception as e:
                    _log.warning("解析 %s 失败: %s", f.name, e)

    elif info["format"] == "rst" and tool == "lammps":
        src_dir = vdir / "src"
        if src_dir.exists():
            for f in sorted(src_dir.glob("*.rst")):
                try:
                    parsed = _parse_lammps_rst(f)
                    records.extend(parsed)
                except Exception as e:
                    _log.debug("跳过 %s: %s", f.name, e)

    elif info["format"] == "rst" and tool == "gromacs":
        src_dir = vdir / "src"
        if src_dir.exists():
            for f in sorted(src_dir.rglob("*.rst")):
                try:
                    parsed = _parse_gromacs_rst(f)
                    records.extend(parsed)
                except Exception as e:
                    _log.debug("跳过 %s: %s", f.name, e)

    # insert records
    for r in records:
        conn.execute(
            """INSERT OR REPLACE INTO toolref_pages
               (tool, version, program, section, page_name, title,
                category, var_type, default_val, synopsis, content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tool,
                version,
                r.get("program", ""),
                r.get("section", ""),
                r["page_name"],
                r.get("title", ""),
                r.get("category", ""),
                r.get("var_type", ""),
                r.get("default_val", ""),
                r.get("synopsis", ""),
                r["content"],
            ),
        )

    conn.commit()
    conn.close()
    return len(records)


# ============================================================================
#  Version management
# ============================================================================


def _set_current(tool: str, version: str, cfg: Config | None = None) -> None:
    link = _current_link(tool, cfg)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(version)


def toolref_use(tool: str, version: str, *, cfg: Config | None = None) -> None:
    """Set the active version for a tool.

    Args:
        tool: Tool name.
        version: Version to activate.
        cfg: Optional Config.
    """
    if not validate_tool_name(tool):
        raise ValueError(f"未知工具：{tool}")
    vdir = _version_dir(tool, version, cfg)
    if not vdir.exists():
        raise FileNotFoundError(
            f"{tool} 版本 {version} 未找到。请先运行 `scholaraio toolref fetch {tool} --version {version}`"
        )
    _set_current(tool, version, cfg)
    ui(f"[toolref] {tool} 当前版本已切换为 {version}")


def toolref_list(tool: str | None = None, *, cfg: Config | None = None) -> list[dict]:
    """List available tools and their versions.

    Args:
        tool: If specified, list versions for this tool only.
        cfg: Optional Config.

    Returns:
        List of dicts with tool, version, is_current, page_count fields.
    """
    root = _toolref_root(cfg)
    results: list[dict] = []

    tools = [tool] if tool else list(TOOL_REGISTRY.keys())
    for t in tools:
        tdir = root / t
        if not tdir.exists():
            continue

        # find current symlink target
        link = tdir / "current"
        current_version = None
        if link.is_symlink():
            current_version = link.resolve().name

        for vdir in sorted(tdir.iterdir()):
            if vdir.name == "current" or not vdir.is_dir():
                if vdir.name == "toolref.db":
                    continue
                continue
            # count pages
            db = tdir / "toolref.db"
            page_count = 0
            if db.exists():
                try:
                    conn = sqlite3.connect(db)
                    row = conn.execute(
                        "SELECT COUNT(*) FROM toolref_pages WHERE tool=? AND version=?",
                        (t, vdir.name),
                    ).fetchone()
                    page_count = row[0] if row else 0
                    conn.close()
                except Exception:
                    pass

            results.append(
                {
                    "tool": t,
                    "display_name": TOOL_REGISTRY.get(t, {}).get("display_name", t),
                    "version": vdir.name,
                    "is_current": vdir.name == current_version,
                    "page_count": page_count,
                }
            )

    return results


# ============================================================================
#  Show: precise lookup
# ============================================================================


def toolref_show(
    tool: str,
    *args: str,
    cfg: Config | None = None,
) -> list[dict]:
    """Look up a specific command or parameter.

    Args:
        tool: Tool name.
        *args: Lookup path segments. E.g. ("pw", "ecutwfc") for QE,
               or ("fix_npt",) for LAMMPS.
        cfg: Optional Config.

    Returns:
        List of matching records.
    """
    if not validate_tool_name(tool):
        raise ValueError(f"未知工具：{tool}")

    db = _db_path(tool, cfg)
    if not db.exists():
        raise FileNotFoundError(f"{tool} 文档未索引。请先运行 `scholaraio toolref fetch {tool}`")

    # resolve current version
    link = _current_link(tool, cfg)
    version = None
    if link.is_symlink():
        version = link.resolve().name

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    query_parts = [a.lower() for a in args]
    query_str = "/".join(query_parts)

    # try exact page_name match first
    rows = conn.execute(
        """SELECT * FROM toolref_pages
           WHERE tool = ? AND (version = ? OR ? IS NULL)
           AND LOWER(page_name) = ?""",
        (tool, version, version, query_str),
    ).fetchall()

    if not rows:
        # try partial match (page_name contains query)
        like_pattern = f"%{'%'.join(query_parts)}%"
        rows = conn.execute(
            """SELECT * FROM toolref_pages
               WHERE tool = ? AND (version = ? OR ? IS NULL)
               AND LOWER(page_name) LIKE ?
               LIMIT 20""",
            (tool, version, version, like_pattern),
        ).fetchall()

    if not rows:
        # try title match
        title_query = query_parts[-1] if query_parts else ""
        rows = conn.execute(
            """SELECT * FROM toolref_pages
               WHERE tool = ? AND (version = ? OR ? IS NULL)
               AND LOWER(title) = ?
               LIMIT 20""",
            (tool, version, version, title_query),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# ============================================================================
#  Search: FTS5 full-text
# ============================================================================


def toolref_search(
    tool: str,
    query: str,
    *,
    top_k: int = 20,
    program: str | None = None,
    section: str | None = None,
    cfg: Config | None = None,
) -> list[dict]:
    """Full-text search over tool documentation.

    Args:
        tool: Tool name.
        query: Search query string.
        top_k: Maximum results to return.
        program: Filter by program (e.g. 'pw.x').
        section: Filter by section/namelist (e.g. 'SYSTEM').
        cfg: Optional Config.

    Returns:
        List of matching records sorted by relevance.
    """
    if not validate_tool_name(tool):
        raise ValueError(f"未知工具：{tool}")

    db = _db_path(tool, cfg)
    if not db.exists():
        raise FileNotFoundError(f"{tool} 文档未索引。请先运行 `scholaraio toolref fetch {tool}`")

    link = _current_link(tool, cfg)
    version = None
    if link.is_symlink():
        version = link.resolve().name

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # build FTS5 query — auto-convert spaces to OR for better recall
    fts_query = query
    if " " in query and not any(kw in query.upper() for kw in ("OR", "AND", "NOT", '"')):
        words = query.split()
        fts_query = " OR ".join(words)

    try:
        sql = """
            SELECT p.*, rank
            FROM toolref_fts f
            JOIN toolref_pages p ON f.rowid = p.id
            WHERE toolref_fts MATCH ?
              AND p.tool = ?
        """
        params: list = [fts_query, tool]

        if version:
            sql += " AND p.version = ?"
            params.append(version)
        if program:
            prog = program.lower()
            if not prog.endswith(".x"):
                prog += ".x"
            sql += " AND LOWER(p.program) = ?"
            params.append(prog)
        if section:
            sql += " AND LOWER(p.section) = ?"
            params.append(section.lower())

        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        rows = conn.execute(sql, params).fetchall()
    except Exception:
        # FTS query syntax error — try quoting
        safe_query = '"' + query.replace('"', "") + '"'
        try:
            rows = conn.execute(
                """SELECT p.*, rank
                   FROM toolref_fts f
                   JOIN toolref_pages p ON f.rowid = p.id
                   WHERE toolref_fts MATCH ?
                     AND p.tool = ?
                   ORDER BY rank LIMIT ?""",
                (safe_query, tool, top_k),
            ).fetchall()
        except Exception:
            rows = []

    conn.close()
    return [dict(r) for r in rows]
