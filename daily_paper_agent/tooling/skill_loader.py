from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    content: str
    skill_path: Path

    def to_prompt(self) -> str:
        root_dir = self.skill_path.parent
        return (
            f"# Skill: {self.name}\n\n"
            f"{self.description}\n\n"
            f"Skill root: `{root_dir}`\n\n"
            f"{self.content}"
        )


class SkillLoader:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    def discover_skills(self) -> list[Skill]:
        self._skills = {}
        if not self.skills_dir.exists():
            return []
        for p in self.skills_dir.rglob("SKILL.md"):
            skill = self._load_one(p)
            if not skill:
                continue
            self._skills[skill.name] = skill
        return list(self._skills.values())

    def _load_one(self, skill_path: Path) -> Skill | None:
        try:
            raw = skill_path.read_text(encoding="utf-8").strip()
        except Exception:
            return None
        if not raw:
            return None

        name = skill_path.parent.name
        desc = ""
        body = raw

        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, flags=re.DOTALL)
        if m:
            frontmatter = m.group(1)
            body = m.group(2).strip()
            for line in frontmatter.splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                key = k.strip().lower()
                val = v.strip().strip("'\"")
                if key == "name" and val:
                    name = val
                elif key == "description" and val:
                    desc = val

        if not desc:
            for line in body.splitlines():
                text = line.strip()
                if not text:
                    continue
                if text.startswith("#"):
                    continue
                desc = text[:200]
                break
        if not desc:
            desc = f"Skill at {skill_path}"

        return Skill(name=name, description=desc, content=body, skill_path=skill_path)

    def get_skill(self, name: str) -> Skill | None:
        if name in self._skills:
            return self._skills[name]
        lowered = name.strip().lower().replace("-", "_")
        for key, skill in self._skills.items():
            key_norm = key.lower().replace("-", "_")
            if key_norm == lowered:
                return skill
        return None

    def list_skills(self) -> list[str]:
        return sorted(self._skills.keys())

    def metadata_prompt(self) -> str:
        if not self._skills:
            return ""
        lines = ["## Available Skills", "Use `get_skill` to load full content only when needed."]
        for name in self.list_skills():
            s = self._skills[name]
            lines.append(f"- `{s.name}`: {s.description}")
        return "\n".join(lines)
