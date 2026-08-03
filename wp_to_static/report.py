"""Build report: collect problems as they happen, show them together at the end.

Warnings scattered through a long build scroll past unread. Everything worth
acting on is collected here and printed as one block when the build finishes,
with the exit status reflecting whether anything failed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass
class Report:
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    @property
    def failed(self) -> bool:
        return bool(self.errors)

    def render(self) -> str:
        if not self.warnings and not self.errors:
            return "no warnings"
        lines: list[str] = []
        if self.errors:
            lines.append(f"{len(self.errors)} error(s):")
            lines += [f"  ERROR  {m}" for m in self.errors]
        if self.warnings:
            lines.append(f"{len(self.warnings)} warning(s):")
            lines += [f"  WARN   {m}" for m in self.warnings]
        return "\n".join(lines)

    def emit(self) -> None:
        stream = sys.stderr if self.failed else sys.stdout
        print("\n=== build report ===", file=stream)
        print(self.render(), file=stream)
